#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# server.py  —  Local web server for the LinkedIn Outreach dashboard
#
# Start:  python server.py
# Open:   http://localhost:5555
#
# Provides a web API so the dashboard can trigger commands without Terminal.
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import sys
import threading
import time
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from config import STATE_FILE_PATH
from ai_proxy import call_ai as _proxy_ai, search_web as _proxy_search
from wizard_linkedin import start_login_flow, get_login_status, copy_wizard_profile_to_client

PORT = 5555
LOG_FILE = "outreach_log.txt"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_FILE = os.path.join(BASE_DIR, ".stop_signal")
SCHEDULER_FIRED_FILE = os.path.join(BASE_DIR, ".scheduler_fired.json")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.py")
ENV_FILE    = os.path.join(BASE_DIR, ".env")
ENV_EXAMPLE = os.path.join(BASE_DIR, ".env.example")
KB_FILE    = os.path.join(BASE_DIR, "knowledge_base.json")
SWIPE_FILE = os.path.join(BASE_DIR, "swipe_file.json")
QUEUE_FILE = os.path.join(BASE_DIR, "post_queue.json")

# In-memory conversation history for the AI assistant chat
_chat_history: list = []

# Track running tasks
_current_task = None
_task_lock = threading.Lock()
_task_log = []  # recent log lines for the UI


class _LogCapture(logging.Handler):
    """Capture log lines for the dashboard."""
    def emit(self, record):
        line = self.format(record)
        _task_log.append({"ts": datetime.now().isoformat(), "msg": line})
        # Keep only last 200 lines
        if len(_task_log) > 200:
            _task_log.pop(0)


# Set up log capture (in-memory for dashboard Activity Log)
_capture = _LogCapture()
_capture.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Also write to the outreach log file so disk logs are always kept
_file_handler = logging.FileHandler(os.path.join(BASE_DIR, LOG_FILE))
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(_capture)
root_logger.addHandler(_file_handler)


def _classify_error(exc: Exception):
    """
    Translate a raw exception into a UI-friendly (code, message, action) tuple.
    code   — short machine-readable identifier (used by the dashboard to decide
             which modal/banner to show, e.g. 'session_expired', 'no_api_key').
    message — human-readable sentence shown in the error banner.
    action — one of: 'reconnect' | 'open_settings' | 'retry' | 'wait' | None.
    """
    err_name = type(exc).__name__
    msg      = str(exc) or err_name

    if err_name == "StopSignal":
        return ("stopped", "Task stopped by user.", None)

    if err_name == "MissingAPIKey":
        return (
            "no_api_key",
            "Claude API key is missing. Open Settings → Account and paste your key.",
            "open_settings",
        )

    if "AuthenticationError" in err_name:
        return (
            "bad_api_key",
            "Claude rejected the API key. Paste a fresh key in Settings → Account.",
            "open_settings",
        )

    if "RateLimitError" in err_name:
        return (
            "rate_limited",
            "Claude rate limit hit. Wait a few minutes, or lower your daily caps.",
            "wait",
        )

    if "APIConnectionError" in err_name:
        return (
            "network",
            "Could not reach Claude. Check your internet connection and retry.",
            "retry",
        )

    # LinkedIn session problems (raised as RuntimeError from linkedin_client)
    low = msg.lower()
    if (
        "session expired" in low
        or "err_too_many_redirects" in low
        or "redirected to: https://www.linkedin.com/login" in low
        or "authwall" in low
    ):
        return (
            "session_expired",
            "Your LinkedIn session expired. Click Reconnect to log in again.",
            "reconnect",
        )

    if "captcha" in low or "unusual activity" in low or "linkedin_paused" in low:
        return (
            "linkedin_paused",
            "LinkedIn showed a security challenge. Automation is paused for 24 hours. "
            "Open LinkedIn manually, resolve it, then click Resume.",
            "reconnect",
        )

    if "brave" in low and ("401" in msg or "403" in msg or "unauthorized" in low):
        return (
            "bad_brave_key",
            "Brave Search rejected the API key. Paste a fresh key in Settings → Account.",
            "open_settings",
        )

    return ("error", "Something went wrong. Click Retry or try again in a few minutes. If it keeps happening, reach out to support@influentia.io.", "retry")


def _run_command(cmd_name: str, extra_args: list = None, limit: int = None):
    """Run a main.py command in a background thread."""
    global _current_task
    with _task_lock:
        if _current_task and _current_task.get("running"):
            return False, "A task is already running"
        _current_task = {
            "name":    cmd_name,
            "running": True,
            "started": datetime.now().isoformat(),
            "error":   None,
            "error_code": None,
            "error_action": None,
        }

    # Clear any previous stop signal
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    def _worker():
        global _current_task
        original_argv = sys.argv[:]
        worker_error = None
        worker_error_code = None
        worker_error_action = None
        worker_stopped = False
        try:
            sys.argv = ["main.py", cmd_name]
            if extra_args:
                sys.argv += extra_args
            if limit:
                sys.argv += ["--limit", str(limit)]

            import importlib
            # Reload all local modules so code changes take effect without restarting server
            for _mod_name in ['config', 'leads_loader', 'state_manager', 'linkedin_client',
                               'comment', 'analytics', 'main']:
                if _mod_name in sys.modules:
                    try:
                        importlib.reload(sys.modules[_mod_name])
                    except Exception:
                        pass
            import main as main_module

            if cmd_name in main_module.COMMANDS:
                main_module.COMMANDS[cmd_name]()
        except Exception as e:
            code, message, action = _classify_error(e)
            worker_error_code   = code
            worker_error        = message
            worker_error_action = action
            if code == "stopped":
                worker_stopped = True
                logging.info(message)
            else:
                logging.error(message)
                # Include traceback in the log file only — not in the dashboard feed
                import traceback
                logging.debug(traceback.format_exc())
        finally:
            sys.argv = original_argv
            # Clean up stop file
            if os.path.exists(STOP_FILE):
                try:
                    os.remove(STOP_FILE)
                except OSError:
                    pass
            with _task_lock:
                if _current_task:
                    _current_task["running"]  = False
                    _current_task["finished"] = datetime.now().isoformat()
                    if worker_stopped:
                        _current_task["stopped"] = True
                    if worker_error:
                        _current_task["error"]        = worker_error
                        _current_task["error_code"]   = worker_error_code
                        _current_task["error_action"] = worker_error_action

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True, f"Started '{cmd_name}'"


def _stop_task():
    """Signal the current task to stop by creating the stop file."""
    global _current_task
    # Create the stop signal file — linkedin_client.py checks for this
    with open(STOP_FILE, "w") as f:
        f.write("stop")
    with _task_lock:
        if _current_task:
            _current_task["running"] = False
            _current_task["finished"] = datetime.now().isoformat()
            _current_task["stopped"] = True
    logging.info("Stop requested — task will halt after current action.")
    return True


# ── LinkedIn pause state ──────────────────────────────────────────────────────
# Written by linkedin_client.py when it detects a CAPTCHA / security challenge.
# Dashboard reads this to decide whether to show the "paused" banner.
PAUSE_FILE    = os.path.join(BASE_DIR, ".linkedin_paused.json")
ONBOARD_FILE  = os.path.join(BASE_DIR, ".onboarding.json")
FEEDBACK_DIR  = os.path.join(BASE_DIR, "feedback")


def _linkedin_pause_state():
    """
    Returns {'paused': bool, 'until': iso_str|None, 'reason': str|None}.
    An expired pause is auto-cleared.
    """
    if not os.path.exists(PAUSE_FILE):
        return {"paused": False, "until": None, "reason": None}
    try:
        with open(PAUSE_FILE) as f:
            data = json.load(f)
        until = data.get("until")
        if until:
            try:
                if datetime.fromisoformat(until) <= datetime.now():
                    # Pause has expired — auto-clear
                    os.remove(PAUSE_FILE)
                    return {"paused": False, "until": None, "reason": None}
            except Exception:
                pass
        return {
            "paused":  True,
            "until":   until,
            "reason":  data.get("reason", "LinkedIn security challenge detected."),
        }
    except Exception:
        return {"paused": False, "until": None, "reason": None}


def _clear_linkedin_pause():
    if os.path.exists(PAUSE_FILE):
        try:
            os.remove(PAUSE_FILE)
        except OSError:
            pass


def _set_manual_pause():
    """Write a manual (no-expiry) pause so customers can stop outreach from the dashboard."""
    with open(PAUSE_FILE, "w") as f:
        json.dump({
            "until":  None,
            "reason": "Outreach manually paused.",
            "manual": True,
            "paused_at": datetime.now().isoformat(),
        }, f)


def _is_manual_pause() -> bool:
    state = _linkedin_pause_state()
    return state.get("paused") and state.get("manual", False)


# ── License / billing ─────────────────────────────────────────────────────────
# Influentia uses a hosted license backend (Cloudflare Worker + D1 + Stripe).
# The local app stores a cached copy of the license state in .license.json and
# revalidates with the worker every 12h. If the license is missing, expired, or
# the trial has run out, /api/run/* endpoints are blocked with HTTP 402.
LICENSE_FILE        = os.path.join(BASE_DIR, ".license.json")
LICENSE_WORKER_URL  = os.environ.get(
    "LICENSE_WORKER_URL",
    "https://outreach-pilot-api-production.plain-king-ead0.workers.dev",
).rstrip("/")
LICENSE_CACHE_TTL_S = 12 * 60 * 60  # 12 hours
UPGRADE_URL_BASE    = "https://influentia.io/account"


# ── Daily usage tracking (scan cap per user) ─────────────────────────
DAILY_SCAN_CAP = 50

def _today():
    from datetime import date
    return date.today().isoformat()

def _load_usage():
    """Return today's scan count, reset if new day."""
    lic = _load_license() or {}
    scan_date = lic.get("scan_date", "")
    scan_count = lic.get("daily_scan_count", 0)
    # Reset counter when date changes (UTC-based)
    if scan_date != _today():
        scan_count = 0
        scan_date = _today()
        lic["scan_date"] = scan_date
        lic["daily_scan_count"] = 0
        _save_license(lic)
    return scan_count

def _increment_scan():
    """Increment today's scan count and return new total."""
    lic = _load_license() or {}
    count = lic.get("daily_scan_count", 0) + 1
    lic["daily_scan_count"] = count
    lic["scan_date"] = _today()
    _save_license(lic)
    return count


def _load_license():
    """Return the cached license dict, or None if no license is stored yet."""
    if not os.path.exists(LICENSE_FILE):
        return None
    try:
        with open(LICENSE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _save_license(data):
    try:
        with open(LICENSE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.warning("Could not save license file: %s", e)


def _check_license_with_worker(key):
    """
    Hit the hosted Worker's /api/license/validate endpoint.
    Returns the parsed worker response dict on success, or None on network
    failure (caller should fall back to cache).
    """
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            f"{LICENSE_WORKER_URL}/api/license/validate",
            data=json.dumps({"key": key}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 4xx from worker — treat as authoritative (e.g. license revoked)
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"valid": False, "reason": "worker_error"}
    except Exception as e:
        logging.info("License worker unreachable (%s) — using cached state", e)
        return None


def _license_state():
    """
    Return a normalized view of the license for the dashboard:
      {
        has_license: bool,
        key_masked:  str | None,      # e.g. "••••-••••-••••-XXXX"
        email:       str | None,
        tier:        'trial'|'active'|'expired'|'cancelled'|None,
        trial_ends_at: int | None,    # unix seconds
        days_remaining: int | None,   # trial days left, or None
        subscription_status: str | None,
        allow_runs:  bool,            # whether /api/run/* should be allowed
        upgrade_url: str,
      }
    Revalidates with the worker if the cached copy is stale.
    """
    lic = _load_license() or {}
    key = lic.get("key")
    if not key:
        return {
            "has_license": False,
            "key_masked": None,
            "email": None,
            "tier": None,
            "trial_ends_at": None,
            "days_remaining": None,
            "subscription_status": None,
            "allow_runs": False,
            "upgrade_url": UPGRADE_URL_BASE,
        }

    # Refresh from worker if stale
    last_checked = lic.get("last_checked_at", 0)
    if (time.time() - last_checked) > LICENSE_CACHE_TTL_S:
        fresh = _check_license_with_worker(key)
        if fresh and fresh.get("valid"):
            lic.update({
                "email": fresh.get("email", lic.get("email")),
                "tier":  fresh.get("tier", lic.get("tier")),
                "trial_ends_at": fresh.get("trial_ends_at", lic.get("trial_ends_at")),
                "current_period_end": fresh.get("current_period_end", lic.get("current_period_end")),
                "subscription_status": fresh.get("subscription_status", lic.get("subscription_status")),
                "last_checked_at": int(time.time()),
            })
            _save_license(lic)
        elif fresh and not fresh.get("valid"):
            # Worker says this key is unknown or revoked.
            lic["tier"] = "revoked"
            lic["last_checked_at"] = int(time.time())
            _save_license(lic)

    tier    = lic.get("tier") or "unknown"
    sub_st  = lic.get("subscription_status")
    trial_end = lic.get("trial_ends_at")
    now_s   = int(time.time())
    days_rem = None
    if tier == "trial" and trial_end:
        # Use ceiling so "23h 55m left" reads as "1 day left" not "0 days left"
        # — matches the worker's Math.ceil rounding.
        secs_left = int(trial_end) - now_s
        days_rem  = max(0, -(-secs_left // 86400)) if secs_left > 0 else 0
        if int(trial_end) <= now_s:
            tier = "expired"

    allow_runs = tier in ("trial", "active") and sub_st not in ("canceled", "past_due", "incomplete_expired", "unpaid")

    # Mask key: keep last 4 chars
    masked = None
    if key:
        last4 = key.replace("-", "")[-4:]
        masked = f"••••-••••-••••-{last4}"

    return {
        "has_license": True,
        "key_masked": masked,
        "email": lic.get("email"),
        "tier": tier,
        "trial_ends_at": trial_end,
        "days_remaining": days_rem,
        "subscription_status": sub_st,
        "allow_runs": allow_runs,
        "upgrade_url": f"{UPGRADE_URL_BASE}?license={key}",
    }


def _reddit_verify_credentials(username: str, password: str) -> tuple:
    """
    Returns (verified: bool, message: str).
    message is ALWAYS non-empty — callers should display it directly.

    Two-level check:
      1. Always: confirm the username exists on Reddit (public API).
      2. If REDDIT_CLIENT_ID + CLIENT_SECRET are also set: try an OAuth token
         exchange to confirm the password is correct too.
    """
    import urllib.request, urllib.parse, urllib.error, base64, json as _json

    _UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # Step 1 — does this username exist?
    try:
        req = urllib.request.Request(
            f"https://www.reddit.com/user/{urllib.parse.quote(username)}/about.json",
            headers={"User-Agent": _UA},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())
        if data.get("error") == 404 or not data.get("data"):
            return False, f"u/{username} doesn't exist on Reddit — double-check the username."
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"u/{username} doesn't exist on Reddit — double-check the username."
        if e.code == 429:
            return False, "Reddit is rate-limiting right now. Wait 60 seconds and try again."
        return False, f"Reddit returned HTTP {e.code}. Check your internet connection and try again."
    except Exception as e:
        return False, f"Couldn't reach Reddit ({type(e).__name__}). Check your internet connection."

    # Step 2 — if OAuth keys are present, test the password too
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    if client_id and client_secret and password:
        try:
            creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            post_data = urllib.parse.urlencode({
                "grant_type": "password",
                "username":   username,
                "password":   password,
                "scope":      "submit read",
            }).encode()
            req = urllib.request.Request(
                "https://www.reddit.com/api/v1/access_token",
                data=post_data,
                headers={
                    "Authorization":  f"Basic {creds}",
                    "User-Agent":     _UA,
                    "Content-Type":   "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                result = _json.loads(r.read())
            err = result.get("error", "")
            if err == "invalid_grant":
                return False, "Wrong password — Reddit rejected it. Re-enter your credentials."
            if err:
                return False, f"Reddit rejected the login ({err}). Check your credentials."
            return True, f"Connected as u/{username} — full OAuth verified."
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Wrong Client ID or Secret. Check your Reddit app settings."
            body = e.read().decode(errors="replace")[:120]
            return False, f"Reddit auth failed (HTTP {e.code}): {body}"
        except Exception as e:
            return False, f"Could not verify password ({type(e).__name__}). Try again."

    # Username confirmed but no client_id/secret to test the password
    return True, (
        f"u/{username} found on Reddit. "
        "Password will be verified on first post — a browser window opens briefly."
    )


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the dashboard + handle API requests."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoints
        if path == "/api/daily-report":
            try:
                from collections import Counter
                from state_manager import load_state
                state = load_state()
                leads = state.get("leads", {})
                if isinstance(leads, dict):
                    leads_list = list(leads.values())
                else:
                    leads_list = leads
                counts = Counter(l.get("status") for l in leads_list if isinstance(l, dict))
                today = datetime.now().strftime("%Y-%m-%d")

                # Parse today's numbers from the persisted daily_summary.log
                summary_file = os.path.join(BASE_DIR, "daily_summary.log")
                def parse_summary_number(label, content):
                    import re
                    m = re.search(rf"{re.escape(label)}\s+(\d+)", content)
                    return int(m.group(1)) if m else 0

                today_data = {
                    "connections_sent": 0, "messages_sent": 0,
                    "replies_sent": 0, "followups_sent": 0,
                    "leads_found": 0, "withdrawn": 0,
                    "comments_queued": 0, "comments_posted": 0,
                }
                last_run = None
                ran_today = False

                if os.path.exists(summary_file):
                    with open(summary_file) as f:
                        content = f.read()
                    # Find the last block for today
                    import re
                    blocks = re.split(r"═{10,}", content)
                    for block in reversed(blocks):
                        if today in block and "TODAY'S ACTIVITY" in block:
                            ran_today = True
                            today_data["connections_sent"] = parse_summary_number("Connection requests:", block)
                            today_data["messages_sent"]    = parse_summary_number("Messages sent:", block)
                            today_data["replies_sent"]     = parse_summary_number("Replies sent:", block)
                            today_data["leads_found"]      = parse_summary_number("New leads found:", block)
                            today_data["withdrawn"]        = parse_summary_number("Old requests withdrawn:", block)
                            today_data["comments_queued"]  = parse_summary_number("Comments queued:", block)
                            m = re.search(r"Run at:\s+(\S+ \S+)", block)
                            if m:
                                last_run = m.group(1)
                            break

                # Also check in-memory log for anything since last restart
                def count_in_log(phrase):
                    return sum(1 for e in _task_log if phrase in e.get("msg", "").lower())
                if not ran_today:
                    today_data["connections_sent"] = count_in_log("connection request sent")
                    today_data["messages_sent"]    = count_in_log("message sent")
                    today_data["replies_sent"]     = count_in_log("reply sent") + count_in_log("auto-reply")
                    today_data["leads_found"]      = count_in_log("new lead") + count_in_log("lead found")
                    today_data["withdrawn"]        = count_in_log("withdrew") + count_in_log("withdrawn")
                    today_data["comments_queued"]  = count_in_log("queued")
                    if _task_log:
                        last_run = _task_log[-1]["ts"]

                report = {
                    "date": today,
                    "ran_today": ran_today,
                    "pipeline": dict(counts),
                    "total_leads": len(leads_list),
                    "today": today_data,
                    "last_run": last_run,
                }
                self._json_response({"ok": True, "report": report})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/state":
            from state_manager import load_state
            from config import MAX_MESSAGES_PER_DAY
            from datetime import datetime as _dt
            qs = parse_qs(parsed.query)
            campaign_filter = qs.get("campaign", [None])[0]
            state = load_state()
            # Count outreach messages sent today — same rules as _count_messages_sent_today
            # in main.py: exclude "reply" and "manual", count legacy (no tag) conservatively.
            _today = _dt.utcnow().date().isoformat()
            _sent_today = sum(
                1 for lead in state["leads"].values()
                for msg in lead.get("messages", [])
                if msg.get("role") == "ai"
                and (msg.get("ts") or "")[:10] == _today
                and msg.get("msg_type", "") not in ("reply", "manual")
            )
            pending_replies = [r for r in state.get("pending_replies", []) if r.get("status") == "pending"]
            auto_reply_enabled = state.get("settings", {}).get("auto_reply_enabled", False)
            if campaign_filter and campaign_filter != "all":
                filtered = {k: v for k, v in state["leads"].items()
                            if v.get("campaign_id") == campaign_filter}
                out = dict(state)
                out["leads"] = filtered
                out["messages_sent_today"] = _sent_today
                out["max_messages_per_day"] = MAX_MESSAGES_PER_DAY
                out["pending_replies"] = pending_replies
                out["auto_reply_enabled"] = auto_reply_enabled
                self._json_response(out)
            else:
                out = dict(state)
                out["messages_sent_today"] = _sent_today
                out["max_messages_per_day"] = MAX_MESSAGES_PER_DAY
                out["pending_replies"] = pending_replies
                out["auto_reply_enabled"] = auto_reply_enabled
                self._json_response(out)
            return

        if path == "/api/campaigns":
            from state_manager import load_state
            state = load_state()
            camps = list(state.get("campaigns", {}).values())
            # Add lead count per campaign
            for c in camps:
                c["lead_count"] = sum(
                    1 for l in state["leads"].values()
                    if l.get("campaign_id") == c["id"]
                )
            self._json_response({"campaigns": camps})
            return

        if path == "/api/comments":
            from state_manager import load_state, mark_comment, save_state, purge_stale_pending_comments
            state = load_state()

            # Auto-skip stale comments where the post text failed to load
            _USELESS = [
                "we cannot provide a description",
                "sign in to view",
                "join linkedin",
                "log in or sign up",
            ]
            for c in list(state.get("pending_comments", [])):
                if c.get("status") == "pending":
                    pt = (c.get("post_text") or "").lower()
                    if any(u in pt for u in _USELESS):
                        mark_comment(state, c["id"], "skipped")

            pending  = [c for c in state.get("pending_comments", []) if c.get("status") == "pending"]
            approved = [c for c in state.get("pending_comments", []) if c.get("status") == "approved"]
            posted   = state.get("posted_comments", [])[-20:]  # last 20
            self._json_response({"pending": pending + approved, "posted": posted})
            return

        if path == "/api/status":
            # Per-command soft timeouts (in seconds) — tuned for real runs.
            # These are generous because Playwright + LinkedIn delays are slow.
            _CMD_TIMEOUTS = {
                "find_leads":   900,   # 15 min — searches + profile scrapes
                "scan_posts":   900,   # 15 min — Brave + LinkedIn post scan
                "connect":      1200,  # 20 min — up to 15 connection requests @ 90s
                "check":        600,   # 10 min
                "sync_connections": 600,
                "send":         1200,  # 20 min — 20 messages @ 90s
                "reply":        600,
                "followup":     600,
                "post_comments": 900,
                "withdraw":     600,
                "scan":         600,
                "add":          180,   # 3 min
            }
            with _task_lock:
                task = dict(_current_task) if _current_task else None
                # Auto-fail stuck tasks based on per-command timeout
                if task and task.get("running"):
                    started = task.get("started", "")
                    if started:
                        try:
                            age = (datetime.now() - datetime.fromisoformat(started)).total_seconds()
                            limit = _CMD_TIMEOUTS.get(task.get("name"), 900)
                            if age > limit:
                                _current_task["running"]      = False
                                _current_task["finished"]     = datetime.now().isoformat()
                                _current_task["timed_out"]    = True
                                _current_task["error"]        = (
                                    f"'{task.get('name')}' timed out after {int(age)//60} minutes. "
                                    "This usually means LinkedIn got slow, your network hiccupped, "
                                    "or a page load hung. Click Retry or check the activity log."
                                )
                                _current_task["error_code"]   = "timeout"
                                _current_task["error_action"] = "retry"
                                task = dict(_current_task)
                                logging.warning(f"Auto-failed stuck task '{task.get('name')}' after {age:.0f}s")
                        except Exception:
                            pass
            # Include LinkedIn pause state so dashboard can surface it even when no task is running
            pause_info = _linkedin_pause_state()
            self._json_response({"task": task, "linkedin": pause_info})
            return

        if path == "/api/logs":
            qs = parse_qs(parsed.query)
            since = int(qs.get("since", [0])[0])
            logs = _task_log[since:]
            self._json_response({"logs": logs, "total": len(_task_log)})
            return

        if path == "/api/stop":
            ok = _stop_task()
            self._json_response({"ok": ok, "message": "Stop signal sent"})
            return

        if path == "/api/pause":
            try:
                _set_manual_pause()
                self._json_response({"ok": True, "paused": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/resume":
            try:
                _clear_linkedin_pause()
                self._json_response({"ok": True, "paused": False})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path.startswith("/api/run/"):
            # Pause gate: respect manual pause (all except reply) and security pause (all).
            pause = _linkedin_pause_state()
            if pause.get("paused"):
                cmd_peek = path.split("/api/run/")[1].split("?")[0]
                is_manual = pause.get("manual", False)
                # Manual pause: still allow reply so active conversations get answered.
                # Security pause: block everything including reply.
                if not (is_manual and cmd_peek == "reply"):
                    msg = ("Outreach is manually paused. Resume from the dashboard to continue."
                           if is_manual else
                           f"LinkedIn automation is paused. {pause.get('reason', '')}")
                    self._json_response({
                        "ok": False,
                        "error": msg,
                        "error_code": "paused",
                    }, 409)
                    return

            # License gate: block action commands when trial/subscription isn't live.
            lic = _license_state()
            if not lic["allow_runs"]:
                if not lic["has_license"]:
                    self._json_response({
                        "ok": False,
                        "error": "No license found. Enter your license key to start.",
                        "error_code": "license_required",
                        "error_action": "enter_license",
                        "upgrade_url": lic["upgrade_url"],
                    }, 402)
                elif lic["tier"] == "expired":
                    self._json_response({
                        "ok": False,
                        "error": "Your free trial has ended. Upgrade to keep sending.",
                        "error_code": "trial_expired",
                        "error_action": "upgrade",
                        "upgrade_url": lic["upgrade_url"],
                    }, 402)
                elif lic["tier"] == "cancelled" or lic["subscription_status"] == "canceled":
                    self._json_response({
                        "ok": False,
                        "error": "Your subscription has been cancelled.",
                        "error_code": "subscription_cancelled",
                        "error_action": "upgrade",
                        "upgrade_url": lic["upgrade_url"],
                    }, 402)
                else:
                    self._json_response({
                        "ok": False,
                        "error": "License is inactive. Re-activate or upgrade to continue.",
                        "error_code": "license_inactive",
                        "error_action": "upgrade",
                        "upgrade_url": lic["upgrade_url"],
                    }, 402)
                return
            cmd = path.split("/api/run/")[1]
            qs = parse_qs(parsed.query)
            limit = int(qs["limit"][0]) if "limit" in qs else None
            valid = {"scan", "connect", "check", "sync_connections", "send", "reply",
                     "followup", "preview", "status", "scan_posts", "post_comments",
                     "withdraw", "find_leads"}
            if cmd not in valid:
                self._json_response({"ok": False, "error": f"Unknown command: {cmd}"}, 400)
                return

            # Daily scan cap: limit scans per user to prevent abuse/credit drain
            if cmd in ("scan", "scan_posts", "find_leads"):
                current = _load_usage()
                if current >= DAILY_SCAN_CAP:
                    self._json_response({
                        "ok": False,
                        "error": f"Daily scan cap reached ({DAILY_SCAN_CAP}/day). Resets at midnight.",
                        "error_code": "daily_limit_reached",
                    }, 429)
                    return
                _increment_scan()
            # Pass keywords to scan_posts so the user's input is actually used
            extra_args = []
            if cmd == "scan_posts":
                kw = qs.get("keywords", [None])[0]
                if kw:
                    extra_args = ["--keywords", kw]
            ok, msg = _run_command(cmd, extra_args=extra_args or None, limit=limit)
            self._json_response({"ok": ok, "message": msg})
            return

        if path == "/api/add":
            qs = parse_qs(parsed.query)
            url = qs.get("url", [None])[0]
            if not url or "linkedin.com/in/" not in url:
                self._json_response({"ok": False, "error": "Invalid LinkedIn URL"}, 400)
                return
            ok, msg = _run_command("add", extra_args=[url])
            self._json_response({"ok": ok, "message": msg})
            return

        # Prompts API — read prompt files and offering
        if path == "/api/prompts":
            prompts = {}
            for fname in ["first_message.txt", "context.txt", "follow_up.txt",
                          "comment_style.txt", "dm_tone.txt"]:
                fpath = os.path.join(PROMPTS_DIR, fname)
                try:
                    with open(fpath, "r") as f:
                        prompts[fname] = f.read()
                except Exception:
                    prompts[fname] = ""
            # Also read offering from config
            offering = self._read_offering()
            self._json_response({"prompts": prompts, "offering": offering})
            return

        if path == "/api/config":
            self._json_response(self._read_config_vars())
            return

        if path == "/api/config/validate":
            # Lightweight check: is every must-have credential present and sane?
            try:
                import importlib, config as _cfg
                importlib.reload(_cfg)
                problems = _cfg.validate_config(strict=False)
                needs_onboarding = any(
                    p.startswith(("YOUR_NAME", "YOUR_COMPANY"))
                    for p in problems
                )
                self._json_response({
                    "ok": True,
                    "problems": problems,
                    "valid": not problems,
                    "needs_onboarding": needs_onboarding,
                })
            except Exception as e:
                self._json_response({
                    "ok": False, "error": str(e),
                    "problems": [f"Could not load config: {e}"],
                    "valid": False, "needs_onboarding": True,
                })
            return

        if path == "/api/icp":
            try:
                icp_file = os.path.join(BASE_DIR, "icp_settings.json")
                if os.path.exists(icp_file):
                    data = json.load(open(icp_file))
                    # Migrate old single-profile format to new multi-profile format
                    if "profiles" not in data and ("job_titles" in data or "industries" in data):
                        data = {"profiles": [{
                            "id": "default",
                            "name": "My ICP",
                            "job_titles": data.get("job_titles", []),
                            "industries": data.get("industries", []),
                            "locations":  data.get("locations", []),
                            "keywords":   data.get("keywords", []),
                            "last_used_at": None,
                            "leads_found":  0,
                        }]}
                        json.dump(data, open(icp_file, "w"), indent=2)
                    self._json_response({"ok": True, "profiles": data.get("profiles", [])})
                else:
                    self._json_response({"ok": True, "profiles": []})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # ── Video outreach settings ────────────────────────────────────────────
        if path == "/api/video-settings":
            try:
                vf = os.path.join(BASE_DIR, "video_settings.json")
                data = json.load(open(vf)) if os.path.exists(vf) else {}
                self._json_response({"ok": True, **data})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/last-search":
            try:
                from state_manager import load_state
                cache_file = os.path.join(BASE_DIR, ".last_search.json")
                if not os.path.exists(cache_file):
                    self._json_response({"ok": False, "error": "No previous search found"})
                    return
                with open(cache_file) as f:
                    cache = json.load(f)
                # Re-mark already_tracked in case leads were added since cache was written
                state = load_state()
                for lead in cache.get("leads", []):
                    lead["already_tracked"] = lead["linkedin_url"] in state["leads"]
                self._json_response({"ok": True, **cache})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/setup-status":
            # Returns a checklist of first-time setup steps with done/not-done status.
            try:
                from linkedin_client import PROFILE_DIR
                steps = []

                # Step 0: API keys + identity set in .env
                try:
                    import importlib, config as _cfg
                    importlib.reload(_cfg)
                    creds_problems = _cfg.validate_config(strict=False)
                    creds_ok = not creds_problems
                except Exception:
                    creds_ok = False
                    creds_problems = ["Could not load config — check .env file."]
                steps.append({
                    "id":    "credentials",
                    "label": "Set up your profile",
                    "detail": "Go to Settings → Identity & Outreach. Enter your name, company, goal, and Calendly booking link. This is what the AI uses to personalise every message.",
                    "done":  creds_ok,
                    "problems": creds_problems,
                })

                # Step 1: LinkedIn session
                session_file = os.path.join(PROFILE_DIR, "state.json")
                steps.append({
                    "id":    "session",
                    "label": "Connect your LinkedIn account",
                    "detail": "Run the server, then click Connect in the dashboard. A browser opens — log in once and the session is saved forever.",
                    "done":  os.path.exists(session_file),
                })

                # Step 2: ICP profiles configured
                icp_file = os.path.join(BASE_DIR, "icp_settings.json")
                icp_ok = False
                if os.path.exists(icp_file):
                    try:
                        icp_data = json.load(open(icp_file))
                        icp_ok = bool(icp_data.get("profiles"))
                    except Exception:
                        pass
                steps.append({
                    "id":    "icp",
                    "label": "Set up your ICP profiles",
                    "detail": "Your ideal client profiles are pre-configured (consultants, recruiters, agency owners). You can refine them in Settings → Find Leads.",
                    "done":  icp_ok,
                })

                # Step 3: Knowledge base filled in
                kb_ok = False
                if os.path.exists(KB_FILE):
                    try:
                        kb = json.load(open(KB_FILE))
                        kb_ok = bool(kb.get("origin_story") and kb.get("brand_voice_notes"))
                    except Exception:
                        pass
                steps.append({
                    "id":    "knowledge_base",
                    "label": "Fill in your Knowledge Base",
                    "detail": "Go to Settings → Knowledge Base. Your story, process and voice notes are used to personalise every message and comment.",
                    "done":  kb_ok,
                })

                # Step 4: Posts published (at least 2 posts live — check post history in state)
                from state_manager import load_state
                state = load_state()
                posts_published = len(state.get("post_history", [])) >= 2
                # Also count queue items marked as posted
                queue = {}
                if os.path.exists(QUEUE_FILE):
                    try:
                        queue = json.load(open(QUEUE_FILE))
                    except Exception:
                        pass
                posted_count = sum(1 for week in queue.values() if isinstance(week, list)
                                   for p in week if p.get("posted"))
                steps.append({
                    "id":    "posts",
                    "label": "Publish at least 2 posts to LinkedIn",
                    "detail": "Go to My Posts tab → Generate this week's posts → copy each one and paste it into LinkedIn. Buyers check your profile when you connect — empty profiles get ignored.",
                    "done":  posts_published or posted_count >= 2,
                })

                # Step 5: First Smart Scan done (any pending or posted comments exist)
                has_comments = (
                    len(state.get("pending_comments", [])) > 0 or
                    len(state.get("posted_comments", [])) > 0
                )
                steps.append({
                    "id":    "scan",
                    "label": "Run your first Smart Scan",
                    "detail": "Go to Engage tab → Smart Scan. It finds the best posts to comment on, drafts the comments, and queues them for your approval.",
                    "done":  has_comments,
                })

                # Step 6: First connection request sent
                any_requested = any(
                    l.get("status") in ("requested","connected","messaged","replied","meeting")
                    for l in state.get("leads", {}).values()
                )
                steps.append({
                    "id":    "connect",
                    "label": "Send your first connection requests",
                    "detail": "Once you have 2+ posts live, click Connect in the dashboard. It sends up to 15 requests to your ICP leads.",
                    "done":  any_requested,
                })

                done_count = sum(1 for s in steps if s["done"])
                self._json_response({
                    "ok": True,
                    "steps": steps,
                    "done_count": done_count,
                    "total": len(steps),
                    "complete": done_count == len(steps),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/knowledge-base":
            try:
                kb = {}
                if os.path.exists(KB_FILE):
                    with open(KB_FILE) as f:
                        kb = json.load(f)
                self._json_response({"ok": True, "kb": kb})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/swipe-file":
            try:
                swipe = []
                if os.path.exists(SWIPE_FILE):
                    with open(SWIPE_FILE) as f:
                        swipe = json.load(f)
                self._json_response({"ok": True, "posts": swipe})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/post-queue":
            try:
                queue = {}
                if os.path.exists(QUEUE_FILE):
                    with open(QUEUE_FILE) as f:
                        queue = json.load(f)
                self._json_response({"ok": True, "queue": queue})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/linkedin/status":
            # Reports whether the LinkedIn session file exists and whether
            # automation is currently paused after a security challenge.
            try:
                from linkedin_client import PROFILE_DIR as _PD
                session_file = os.path.join(_PD, "state.json")
                self._json_response({
                    "ok":        True,
                    "connected": os.path.exists(session_file),
                    "pause":     _linkedin_pause_state(),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/onboarding":
            # Returns whether the first-run wizard has been dismissed/completed.
            try:
                data = {"complete": False, "dismissed": False}
                if os.path.exists(ONBOARD_FILE):
                    with open(ONBOARD_FILE) as f:
                        data = json.load(f)
                self._json_response({"ok": True, **data})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/version":
            try:
                ver = "0.9.1"
                vfile = os.path.join(BASE_DIR, "VERSION")
                if os.path.exists(vfile):
                    with open(vfile) as f:
                        ver = f.read().strip() or ver
                self._json_response({"ok": True, "version": ver})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/license" or path == "/api/license/status":
            try:
                self._json_response({"ok": True, **_license_state()})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/ai-ping":
            try:
                from ai_proxy import call_ai_fast
                call_ai_fast([{"role": "user", "content": "ping"}], max_tokens=5)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)})
            return

        if path == "/api/dashboard/chat/history":
            global _chat_history
            self._json_response({"ok": True, "history": _chat_history})
            return

        # Serve wizard.html on the dedicated /wizard route
        if path == "/wizard":
            self.path = "/wizard.html"
            return SimpleHTTPRequestHandler.do_GET(self)

        if path == "/landing":
            self.path = "/landing.html"
            return SimpleHTTPRequestHandler.do_GET(self)

        if path == "/demo":
            self.path = "/demo.html"
            return SimpleHTTPRequestHandler.do_GET(self)

        # Serve dashboard.html as the root, but gate on first-run wizard.
        # If the customer hasn't completed (or explicitly dismissed) the wizard,
        # 302 them to /wizard so they finish onboarding first.
        if path == "/" or path == "":
            try:
                onboarding_done = False
                if os.path.exists(ONBOARD_FILE):
                    with open(ONBOARD_FILE) as f:
                        ob = json.load(f)
                    onboarding_done = bool(ob.get("complete") or ob.get("dismissed"))
            except Exception:
                onboarding_done = False
            if not onboarding_done and os.path.exists(os.path.join(BASE_DIR, "wizard.html")):
                self.send_response(302)
                self.send_header("Location", "/wizard")
                self.end_headers()
                return
            self.path = "/dashboard.html"

        # ── State export / import (backup) ─────────────────────────────────────
        if path == "/api/state/export":
            try:
                from state_manager import load_state
                state = load_state()
                # Remove sensitive fields before export
                export = {k: v for k, v in state.items() if k != "settings"}
                data = json.dumps(export, indent=2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition", 'attachment; filename="influentia-backup.json"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data.encode("utf-8"))
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/state/import":
            # This is a GET-based import check — actual import is POST
            self._json_response({"error": "Use POST to import"}, 405)
            return

        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""

        if path == "/api/prompts/save":
            try:
                data = json.loads(body)
                # Save prompt files
                for fname in ["first_message.txt", "context.txt", "follow_up.txt",
                              "comment_style.txt", "dm_tone.txt"]:
                    if fname in data:
                        fpath = os.path.join(PROMPTS_DIR, fname)
                        with open(fpath, "w") as f:
                            f.write(data[fname])
                # Save offering
                if "offering" in data:
                    self._save_offering(data["offering"])
                self._json_response({"ok": True, "message": "Settings saved"})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/prompts/improve":
            # AI-assisted prompt editing: takes a natural-language instruction and
            # returns a suggested edit to the specified prompt file.
            try:
                data = json.loads(body) if body else {}
                prompt_name = data.get("prompt_name", "context.txt")
                instruction = data.get("instruction", "").strip()
                if not instruction:
                    self._json_response({"ok": False, "error": "No instruction provided"}, 400)
                    return

                # Read the current prompt
                fpath = os.path.join(PROMPTS_DIR, prompt_name)
                try:
                    with open(fpath, "r") as f:
                        current_prompt = f.read()
                except Exception:
                    current_prompt = ""

                meta_instruction = f"""You are a prompt editor for a LinkedIn outreach AI.
The user wants to improve the following prompt file ({prompt_name}) by making this change:

\"\"\"{instruction}\"\"\"

Current prompt:
---
{current_prompt}
---

Task:
1. Make the minimal targeted edit to fulfil the instruction. Do not rewrite the whole prompt.
2. Return a JSON object with exactly two keys:
   - "updated_prompt": the full updated prompt text (string)
   - "summary": one sentence describing what you changed and why (max 20 words)

Return only the JSON object. No markdown, no code fences."""

                result = _proxy_ai(
                    messages=[{"role": "user", "content": meta_instruction}],
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2000,
                )
                import re as _re
                raw = result.strip()
                # Strip markdown fences if present
                raw = _re.sub(r"^```(?:json)?\s*", "", raw)
                raw = _re.sub(r"\s*```$", "", raw)
                parsed = json.loads(raw)
                self._json_response({
                    "ok": True,
                    "prompt_name": prompt_name,
                    "updated_prompt": parsed["updated_prompt"],
                    "summary": parsed.get("summary", "Prompt updated."),
                    "original_prompt": current_prompt,
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/config/save":
            try:
                data = json.loads(body) if body else {}
                self._save_config_vars(data)
                # Reload the config module so other imports see the new values
                try:
                    import importlib, config as _cfg
                    importlib.reload(_cfg)
                except Exception:
                    pass
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/scan-keywords":
            # Returns structured engagement tiers for the dashboard to display.
            # The tiered strategy is also baked into comment._search_for_posts() —
            # this endpoint just surfaces the logic so the UI can explain it to the user.
            try:
                import random as _rand
                tiers = [
                    {
                        "key": "watering_hole",
                        "label": "Tier 1 — Watering holes",
                        "description": "Mid-tier creators (5K-50K followers) discussing B2B growth, LinkedIn strategy, founder content. Their audience = your buyers.",
                        "example_queries": [
                            "founder content strategy linkedin",
                            "B2B thought leadership linkedin",
                            "linkedin content system founder",
                            "video content B2B founders",
                            "personal brand ROI B2B",
                        ],
                        "weight": "60-70% of results",
                    },
                    {
                        "key": "adjacent_peer",
                        "label": "Tier 2 — Adjacent peers",
                        "description": "Brand strategists, B2B copywriters, positioning coaches. Same audience as you, different service. Good for cross-pollination.",
                        "example_queries": [
                            "B2B brand strategy consultant",
                            "copywriting B2B founders linkedin",
                            "positioning founder linkedin",
                            "messaging B2B agency owner",
                        ],
                        "weight": "20% of results",
                    },
                    {
                        "key": "icp_direct",
                        "label": "Tier 3 — ICP in pain",
                        "description": "Founders actively posting about content not working, LinkedIn visibility, credibility gaps. Direct proof-of-pain posts.",
                        "example_queries": [
                            "founder linkedin not getting traction",
                            "content not working B2B",
                            "credibility online B2B",
                            "expert founder invisible linkedin",
                        ],
                        "weight": "10% of results",
                    },
                ]
                # Rotate example queries for variety in the UI display
                for tier in tiers:
                    _rand.shuffle(tier["example_queries"])
                # Also return a flat keyword string for backward compat (scan still uses internal queries)
                all_examples = [q for t in tiers for q in t["example_queries"][:2]]
                self._json_response({"ok": True, "tiers": tiers, "keywords": ", ".join(all_examples)})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/blocklist":
            # GET-style POST: return full do-not-contact list with names from state
            try:
                from state_manager import load_state
                blocklist_file = os.path.join(BASE_DIR, "blocked_leads.json")
                blocked_urls = []
                if os.path.exists(blocklist_file):
                    with open(blocklist_file) as f:
                        blocked_urls = json.load(f)
                state = load_state()
                entries = []
                for url in blocked_urls:
                    lead = state["leads"].get(url, {})
                    entries.append({
                        "linkedin_url": url,
                        "name": lead.get("name") or url,
                        "title": lead.get("title", ""),
                        "company": lead.get("company", ""),
                    })
                # Also check for name-only blocks (no URL match in state)
                self._json_response({"ok": True, "blocked": entries})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/unblock-lead":
            try:
                data = json.loads(body) if body else {}
                url  = data.get("linkedin_url", "")
                if not url:
                    self._json_response({"ok": False, "error": "linkedin_url required"}, 400); return
                blocklist_file = os.path.join(BASE_DIR, "blocked_leads.json")
                blocked = []
                if os.path.exists(blocklist_file):
                    with open(blocklist_file) as f:
                        blocked = json.load(f)
                blocked = [u for u in blocked if u != url]
                with open(blocklist_file, "w") as f:
                    json.dump(blocked, f, indent=2)
                # Restore to pending in state if they were disqualified by block
                from state_manager import load_state, save_state
                state = load_state()
                if url in state["leads"] and state["leads"][url].get("status") == "disqualified":
                    note = state["leads"][url].get("status_note", "")
                    if "do not contact" in note.lower() or "blocked" in note.lower():
                        state["leads"][url]["status"] = "connected"
                        state["leads"][url]["status_note"] = "Unblocked via dashboard"
                        save_state(state)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/leads/search":
            # Search leads by name for the block UI
            try:
                from state_manager import load_state
                data    = json.loads(body) if body else {}
                query   = (data.get("q") or "").lower().strip()
                state   = load_state()
                results = []
                for url, lead in state["leads"].items():
                    if query and query not in (lead.get("name") or "").lower():
                        continue
                    results.append({
                        "linkedin_url": url,
                        "name":    lead.get("name", ""),
                        "title":   lead.get("title", ""),
                        "company": lead.get("company", ""),
                        "status":  lead.get("status", ""),
                    })
                results = sorted(results, key=lambda x: x["name"])[:20]
                self._json_response({"ok": True, "leads": results})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/block-lead":
            try:
                data = json.loads(body) if body else {}
                url = data.get("linkedin_url", "")
                if not url:
                    self._json_response({"ok": False, "error": "linkedin_url required"}, 400)
                    return
                blocklist_file = os.path.join(BASE_DIR, "blocked_leads.json")
                blocked = []
                if os.path.exists(blocklist_file):
                    with open(blocklist_file) as f:
                        blocked = json.load(f)
                if url not in blocked:
                    blocked.append(url)
                    with open(blocklist_file, "w") as f:
                        json.dump(blocked, f, indent=2)
                # Also disqualify in state
                from state_manager import load_state, set_status, save_state
                state = load_state()
                if url in state["leads"]:
                    set_status(state, url, "disqualified", note="Blocked via dashboard — do not contact")
                self._json_response({"ok": True, "blocked_count": len(blocked)})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/preflight-check":
            # Check if the system is properly configured before running outreach
            issues = []
            try:
                from config import YOUR_OFFERING
                if not YOUR_OFFERING or len(YOUR_OFFERING.strip()) < 50:
                    issues.append("YOUR_OFFERING is too short — add a proper description of your service")
            except ImportError as e:
                issues.append(f"Config import error: {e}")
            # Check knowledge base
            kb = {}
            if os.path.exists(KB_FILE):
                try:
                    with open(KB_FILE) as f:
                        kb = json.load(f)
                except Exception:
                    issues.append("knowledge_base.json exists but is invalid JSON")
            if not kb.get("origin_story"):
                issues.append("Knowledge base: origin story is empty")
            if not kb.get("your_process"):
                issues.append("Knowledge base: process description is empty")
            if not kb.get("brand_voice_notes"):
                issues.append("Knowledge base: brand voice notes are empty")
            # Check prompts exist
            for pf in ["first_message.txt", "follow_up.txt", "context.txt"]:
                fp = os.path.join(PROMPTS_DIR, pf)
                if not os.path.exists(fp):
                    issues.append(f"Missing prompt file: prompts/{pf}")
            # Check ICP profiles
            icp_file = os.path.join(BASE_DIR, "icp_settings.json")
            if os.path.exists(icp_file):
                try:
                    with open(icp_file) as f:
                        icps = json.load(f)
                    if not icps.get("profiles"):
                        issues.append("No ICP profiles configured — add at least one in Settings")
                except Exception:
                    issues.append("ICP settings file is corrupted")
            else:
                issues.append("No ICP profiles configured — add at least one in Settings")
            self._json_response({"ok": len(issues) == 0, "issues": issues})
            return

        if path == "/api/insights":
            try:
                from analytics import run_weekly_analysis, generate_weekly_report, get_funnel_stats
                from state_manager import load_state
                # Run fresh analysis (fast — pure Python, no API calls)
                state    = load_state()
                funnel   = get_funnel_stats(state)
                patterns = run_weekly_analysis()
                # Generate narrative only if there's enough data (saves API cost)
                if funnel.get("requested", 0) >= 3:
                    narrative = generate_weekly_report(patterns)
                else:
                    narrative = "Not enough data yet — patterns will appear after your first connection requests go out."
                self._json_response({
                    "ok":        True,
                    "funnel":    funnel,
                    "patterns":  patterns,
                    "narrative": narrative,
                    "data_quality": patterns.get("data_quality", "early"),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/preview-message":
            # Generate a preview of what the first message would look like for a lead
            try:
                data = json.loads(body) if body else {}
                url = data.get("linkedin_url", "")
                from state_manager import load_state
                state = load_state()
                lead = state["leads"].get(url)
                if not lead:
                    self._json_response({"ok": False, "error": "Lead not found"}, 404)
                    return
                from message_ai import generate_first_message, validate_message
                # Minimal profile data for preview (no Playwright needed)
                msg = generate_first_message(lead, {}, [])
                is_valid, reason = validate_message(msg)
                self._json_response({
                    "ok": True,
                    "message": msg,
                    "valid": is_valid,
                    "validation_reason": reason,
                    "lead_name": lead.get("name", ""),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/generate-icp":
            try:
                data = json.loads(body) if body else {}
                description = data.get("description", "").strip()
                offering    = data.get("offering", "").strip()
                if not description:
                    self._json_response({"ok": False, "error": "Please describe your ideal customer"}, 400)
                    return
                from lead_finder import generate_icp_from_description
                result = generate_icp_from_description(description, offering)
                self._json_response({"ok": True, **result})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/find-leads":
            try:
                data = json.loads(body) if body else {}
                # Support multiple job titles for multi-search
                job_titles = data.get("job_titles", [])
                if not job_titles and data.get("job_title"):
                    job_titles = [data["job_title"]]
                industry    = data.get("industry", "")
                location    = data.get("location", "")
                keywords    = data.get("keywords", "")
                count       = max(1, min(int(data.get("count", 20)), 50))
                campaign_id = data.get("campaign_id", "default")
                campaign_name = data.get("campaign_name", "").strip()
                filter_quality = data.get("filter_quality", True)

                if not job_titles and not industry:
                    self._json_response(
                        {"ok": False, "error": "Provide at least one job title or industry"}, 400
                    )
                    return

                from lead_finder import search_leads, score_leads_quality
                from state_manager import load_state, upsert_lead, save_state, create_campaign

                state = load_state()

                # Create new campaign if name provided
                if campaign_name:
                    camp = create_campaign(state, campaign_name)
                    campaign_id = camp["id"]

                # Multi-search: one search per job title, split count evenly
                all_leads = []
                seen = set()
                titles_to_search = job_titles[:4] if job_titles else [""]
                per_title = max(10, count // len(titles_to_search))

                for title in titles_to_search:
                    batch = search_leads(title, industry, location, keywords, per_title)
                    for lead in batch:
                        url = lead["linkedin_url"]
                        if url not in seen:
                            seen.add(url)
                            all_leads.append(lead)
                    if len(all_leads) >= count * 2:  # fetch extra for quality filtering
                        break

                # Quality filter: use Claude to score leads against ICP
                if filter_quality and all_leads:
                    # Build a richer ICP description so the scorer has good context
                    icp_parts = []
                    if job_titles:
                        icp_parts.append("Job titles: " + ", ".join(job_titles))
                    if industry:
                        icp_parts.append("Industry: " + industry)
                    if location:
                        icp_parts.append("Location: " + location)
                    if keywords:
                        icp_parts.append("Keywords: " + keywords)
                    icp_desc = " | ".join(icp_parts) if icp_parts else "B2B professional"
                    all_leads = score_leads_quality(all_leads, icp_desc, min_score=5)

                all_leads = all_leads[:count]

                # preview_only = just return results, don't save yet
                preview_only = data.get("preview_only", False)

                if preview_only:
                    # Mark which ones are already tracked so UI can show it
                    for lead in all_leads:
                        lead["already_tracked"] = lead["linkedin_url"] in state["leads"]
                    # Cache results to disk so they survive a server restart
                    cache = {
                        "leads":       all_leads,
                        "campaign_id": campaign_id,
                        "found":       len(all_leads),
                        "cached_at":   datetime.now().isoformat(),
                    }
                    try:
                        with open(os.path.join(BASE_DIR, ".last_search.json"), "w") as f:
                            json.dump(cache, f)
                    except Exception:
                        pass
                    self._json_response({
                        "ok":          True,
                        "found":       len(all_leads),
                        "leads":       all_leads,
                        "campaign_id": campaign_id,
                        "preview":     True,
                    })
                else:
                    # Legacy: add all immediately
                    added = 0
                    for lead in all_leads:
                        url = lead["linkedin_url"]
                        if url not in state["leads"]:
                            upsert_lead(state, lead, campaign_id=campaign_id)
                            added += 1
                    save_state(state)
                    self._json_response({
                        "ok":         True,
                        "found":      len(all_leads),
                        "added":      added,
                        "leads":      all_leads,
                        "campaign_id": campaign_id,
                    })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/add-leads":
            try:
                data = json.loads(body) if body else {}
                leads_to_add = data.get("leads", [])   # list of lead dicts
                campaign_id  = data.get("campaign_id", "default")
                from state_manager import load_state, upsert_lead, save_state
                state = load_state()
                added = 0
                for lead in leads_to_add:
                    url = lead.get("linkedin_url", "")
                    if url and url not in state["leads"]:
                        upsert_lead(state, lead, campaign_id=campaign_id)
                        added += 1
                save_state(state)
                self._json_response({"ok": True, "added": added})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/video-settings/save":
            try:
                data = json.loads(body) if body else {}
                vf = os.path.join(BASE_DIR, "video_settings.json")
                existing = json.load(open(vf)) if os.path.exists(vf) else {}
                existing.update({
                    "enabled":          bool(data.get("enabled", existing.get("enabled", False))),
                    "video_url":        str(data.get("video_url", existing.get("video_url", ""))).strip(),
                    "message_template": str(data.get("message_template", existing.get("message_template", "I also recorded a quick video for you: {video_link}"))).strip(),
                })
                json.dump(existing, open(vf, "w"), indent=2)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/icp/save":
            # Add or update a named ICP profile
            try:
                data = json.loads(body) if body else {}
                name = data.get("name", "").strip()
                if not name:
                    self._json_response({"ok": False, "error": "Profile name required"}, 400)
                    return
                if not data.get("job_titles") and not data.get("industries"):
                    self._json_response({"ok": False, "error": "Add at least one role or industry"}, 400)
                    return

                icp_file = os.path.join(BASE_DIR, "icp_settings.json")
                store = {"profiles": []}
                if os.path.exists(icp_file):
                    try:
                        store = json.load(open(icp_file))
                        if "profiles" not in store:
                            store = {"profiles": []}
                    except Exception:
                        store = {"profiles": []}

                # Update existing or append new
                profile_id = data.get("id") or name.lower().replace(" ", "_")
                existing = next((p for p in store["profiles"] if p["id"] == profile_id), None)
                if existing:
                    existing.update({
                        "name":        name,
                        "job_titles":  data.get("job_titles", []),
                        "industries":  data.get("industries", []),
                        "locations":   data.get("locations", []),
                        "keywords":    data.get("keywords", []),
                    })
                else:
                    store["profiles"].append({
                        "id":           profile_id,
                        "name":         name,
                        "job_titles":   data.get("job_titles", []),
                        "industries":   data.get("industries", []),
                        "locations":    data.get("locations", []),
                        "keywords":     data.get("keywords", []),
                        "last_used_at": None,
                        "leads_found":  0,
                    })

                json.dump(store, open(icp_file, "w"), indent=2)
                self._json_response({"ok": True, "profiles": store["profiles"]})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/icp/delete":
            try:
                data = json.loads(body) if body else {}
                profile_id = data.get("id", "")
                icp_file = os.path.join(BASE_DIR, "icp_settings.json")
                store = json.load(open(icp_file)) if os.path.exists(icp_file) else {"profiles": []}
                store["profiles"] = [p for p in store.get("profiles", []) if p["id"] != profile_id]
                json.dump(store, open(icp_file, "w"), indent=2)
                self._json_response({"ok": True, "profiles": store["profiles"]})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/campaigns/create":
            try:
                data = json.loads(body) if body else {}
                name = data.get("name", "").strip()
                description = data.get("description", "").strip()
                if not name:
                    self._json_response({"ok": False, "error": "Campaign name required"}, 400)
                    return
                from state_manager import load_state, create_campaign
                state = load_state()
                camp = create_campaign(state, name, description)
                self._json_response({"ok": True, "campaign": camp})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/generate-post":
            try:
                data       = json.loads(body) if body else {}
                pillar     = data.get("pillar", "growth")
                framework  = data.get("framework", "slay")
                hook_style = data.get("hook_style", "outcome")
                context    = data.get("context", "").strip()
                inspiration = data.get("inspiration", [])
                from config import YOUR_OFFERING, YOUR_NAME
                kb = {}
                try:
                    if os.path.exists(KB_FILE):
                        with open(KB_FILE) as f:
                            kb = json.load(f)
                except Exception:
                    kb = {}
                offering_clean = YOUR_OFFERING[:600].strip()
                pillar_instructions = {
                    "tam": (
                        "PILLAR: TAM (Total Addressable Market, Broad Reach)\n"
                        "AUDIENCE: Any founder, executive, or business owner. NOT specifically video/content people.\n"
                        "GOAL: Maximum reach. New eyes on the profile. Top of funnel.\n"
                        "TOPICS: Leadership lessons, hard-won business wisdom, entrepreneurship observations, "
                        "things founders consistently get wrong about growth, credibility, or positioning.\n"
                        "TONE: Universally relatable. Write as a founder talking to other founders. "
                        "The connection to video/brand is subtle or absent. These posts work for any founder.\n"
                        "EXAMPLE ANGLES:\n"
                        "- Most founders are brilliant at their craft and terrible at showing it online.\n"
                        "- After working with 40+ B2B founders, the ones who grow fastest all make one counterintuitive decision.\n"
                        "- I have sat in boardrooms, job sites, and factory floors filming founders tell their story.\n"
                        "The post should make any business owner stop scrolling and think: that is exactly my situation."
                    ),
                    "growth": (
                        "PILLAR: Growth (Niche Authority)\n"
                        "AUDIENCE: Founders, CEOs, business owners who care about brand, content, or online presence.\n"
                        "GOAL: Filter audience to ideal prospects. Position as the expert on founder content and brand storytelling.\n"
                        "TOPICS: Why most founder video content fails, how brand storytelling compounds, "
                        "what makes some founder brands magnetic, specific tactics for B2B content, "
                        "the difference between content that builds trust vs. wastes time.\n"
                        "TONE: Educational but specific. Give real frameworks away freely. Use 'how I' not 'how to'.\n"
                        "EXAMPLE ANGLES:\n"
                        "- We have produced brand content for 40+ founders. The ones that compound share one structural decision.\n"
                        "- How I turned 2 hours of on-site filming into a 12-month content engine for a construction company.\n"
                        "- The credibility gap is the number one silent killer of B2B growth. Here is exactly how it shows up.\n"
                        "The post should make a founder think: I need to know more about this person."
                    ),
                    "sales": (
                        "PILLAR: Sales (Direct Conversion)\n"
                        "AUDIENCE: Founders ready to invest in professional brand content who feel the problem acutely.\n"
                        "GOAL: Convert warm followers into discovery calls. Show undeniable proof.\n"
                        "TOPICS: Specific client transformations with real numbers, ROI of brand documentary, "
                        "what working together actually looks like, the credibility gap through a real story, "
                        "objections addressed through results.\n"
                        "TONE: Concrete. Specific. Let results speak. No hype. Proof sells.\n"
                        "EXAMPLE ANGLES:\n"
                        "- A mining company founder came to us with zero online presence. 18 months later, 3 referral clients from LinkedIn alone.\n"
                        "- What a 4-minute brand documentary actually does to inbound: a real breakdown.\n"
                        "- The J-Griff story: from 2M to 8M views in 18 months. Here is the exact content system we built.\n"
                        "End with a soft question or observation that invites DMs from ready buyers. No hard sell."
                    ),
                }
                framework_instructions = {
                    "slay": (
                        "FRAMEWORK: SLAY (Story / Lesson / Actionable / You)\n"
                        "S: Open mid-scene or with a specific real moment. Drop the reader into a situation. NOT a summary.\n"
                        "L: Share the lesson or insight that generalises beyond the specific story.\n"
                        "A: Give one concrete thing the reader can do, think differently about, or notice.\n"
                        "Y: End with a question or observation directed at the reader. Not 'what do you think?' "
                        "but something specific that makes them reflect on their own situation.\n"
                        "Each section flows naturally. Never label them. The structure is invisible."
                    ),
                    "pas": (
                        "FRAMEWORK: PAS (Problem / Agitate / Solution)\n"
                        "P: Name the specific problem clearly in the opening. Make the reader feel seen immediately.\n"
                        "A: Make them feel the cost of NOT solving it. Specific. Real consequences. Accurate, not dramatic.\n"
                        "S: Share what the solution looks like, Ermo's method, approach, or key insight. "
                        "Not a pitch. End with something actionable or a question that invites reflection."
                    ),
                }
                hook_instructions = {
                    "outcome":    "HOOK: Lead with a specific result that includes a number. Under 10 words. Creates instant curiosity. Example: We took a client from 0 to 3 referral clients in 12 months.",
                    "story":      "HOOK: Drop mid-scene. Start with a specific physical moment, a location, a conversation fragment, an unexpected observation. No setup or context. Example: It was 6am on a job site in Perth when the CEO said something I was not expecting.",
                    "contrarian": "HOOK: Challenge a widespread belief directly in the first line. Bold and specific. Example: Most founder video content is actively hurting their business. State the contrarian position without hedging.",
                    "curiosity":  "HOOK: Open a gap between what readers think they know and what is actually true. Example: Most founders do not realise their brand is doing the opposite of what they intend. Do not resolve the gap until mid-post.",
                    "question":   "HOOK: One sharp rhetorical question that hits a nerve for a founder. Example: Why do some founder brands compound while others stay invisible, even when the work is the same quality?",
                }
                kb_parts = []
                if kb.get("origin_story"):
                    kb_parts.append("Ermo's origin story: " + str(kb["origin_story"])[:300])
                if kb.get("client_results"):
                    results = "; ".join(str(r) for r in (kb["client_results"] or [])[:3])
                    kb_parts.append("Real client results to draw from: " + results)
                if kb.get("core_beliefs"):
                    beliefs = " | ".join(str(b) for b in (kb["core_beliefs"] or [])[:4])
                    kb_parts.append("Ermo's core beliefs: " + beliefs)
                if kb.get("your_process"):
                    kb_parts.append("What makes Authentik Studio different: " + str(kb["your_process"])[:200])
                if kb.get("brand_voice_notes"):
                    kb_parts.append("Brand voice notes: " + str(kb["brand_voice_notes"])[:200])
                kb_block = ""
                if kb_parts:
                    kb_block = "\n\n# Ermo's Knowledge Base (USE THESE to make the post specific and human):\n" + "\n".join("- " + p for p in kb_parts)
                context_block = ("\n\n# Context / notes to draw from:\n" + context) if context else ""
                inspiration_block = ""
                if inspiration:
                    examples = "\n".join("- " + p[:180] for p in inspiration[:4])
                    inspiration_block = "\n\n# Viral inspiration (study hook style / rhythm, DO NOT copy):\n" + examples
                prompt = (
                    "You are writing a high-performance LinkedIn post for Ermo, founder of Authentik Studio"
                    " — brand documentary and video production for B2B founders who need to close the gap"
                    " between their real-world expertise and how the market perceives them.\n\n"
                    "# What Ermo Does\n" + offering_clean[:500] + kb_block + "\n\n"
                    "# Your Task\n" + pillar_instructions.get(pillar, pillar_instructions["growth"]) + "\n\n"
                    "# Framework\n" + framework_instructions.get(framework, framework_instructions["slay"]) + "\n\n"
                    "# Hook\n" + hook_instructions.get(hook_style, hook_instructions["outcome"]) +
                    inspiration_block + context_block + "\n\n"
                    "# STRICT Writing Rules:\n"
                    "- Hook must be under 10 words, on its own line, no sentence before it\n"
                    "- NO em dashes. The single biggest AI tell. Use a period or comma instead.\n"
                    "- NO emojis of any kind\n"
                    "- NO 'Absolutely', 'Certainly', 'This resonates', 'Great question'\n"
                    "- NO 'game-changer', 'leveraging', 'impactful', 'actionable', 'seamlessly', 'genuinely rare'\n"
                    "- NO 'In today's landscape', 'At the end of the day', 'It goes without saying'\n"
                    "- NO hashtags in the post body\n"
                    "- NO exclamation marks\n"
                    "- Short sentences. One idea per sentence. Vary length for rhythm.\n"
                    "- Use blank lines between sections. No bullet points.\n"
                    "- Do NOT start the post with 'I'\n"
                    "- 150-250 words total\n"
                    "- Write in first person as Ermo\n"
                    "- Sound like a thoughtful founder who deeply understands content, not a marketer\n\n"
                    "Write ONLY the post. No preamble, no labels, no 'Here is a post:'."
                )
                post_text = _proxy_ai(
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-sonnet-4-6",
                    max_tokens=700,
                )
                self._json_response({"ok": True, "post": post_text, "pillar": pillar, "framework": framework})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/refine-post":
            try:
                data        = json.loads(body) if body else {}
                post_text   = data.get("post", "").strip()
                instruction = data.get("instruction", "").strip()
                if not post_text or not instruction:
                    self._json_response({"ok": False, "error": "post and instruction required"}, 400)
                    return
                prompt = (
                    "You are editing a LinkedIn post for Ermo (Authentik Studio).\n\n"
                    "Current post:\n---\n" + post_text + "\n---\n\n"
                    "Edit instruction: " + instruction + "\n\n"
                    "Apply the instruction precisely. Keep everything else identical.\n"
                    "Always: NO em dashes, NO emojis, NO buzzwords, short sentences, sound human.\n"
                    "Return ONLY the revised post."
                )
                refined = _proxy_ai(
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-sonnet-4-6",
                    max_tokens=700,
                )
                self._json_response({"ok": True, "post": refined})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/analyze-post":
            try:
                data      = json.loads(body) if body else {}
                post_text = data.get("post", "").strip()
                author    = data.get("author", "unknown")
                mode      = data.get("mode", "analyze")
                if not post_text:
                    self._json_response({"ok": False, "error": "post text required"}, 400)
                    return
                kb = {}
                try:
                    if os.path.exists(KB_FILE):
                        with open(KB_FILE) as f:
                            kb = json.load(f)
                except Exception:
                    pass
                if mode == "analyze":
                    prompt = (
                        "Analyze this high-performing LinkedIn post by " + author + " and explain exactly why it works.\n\n"
                        "Post:\n---\n" + post_text[:800] + "\n---\n\n"
                        "Break down:\n"
                        "1. HOOK: What makes the opening stop the scroll?\n"
                        "2. STRUCTURE: Framework used (SLAY / PAS / list / story / other)?\n"
                        "3. EMOTIONAL MECHANISM: What feeling does it create?\n"
                        "4. SPECIFICITY: What details make it credible?\n"
                        "5. ENDING: Why does the ending generate engagement?\n"
                        "6. STEAL-WORTHY: One element to adapt for a brand documentary/video production business.\n\n"
                        "Be specific. No fluff."
                    )
                else:
                    kb_str = ""
                    if kb.get("client_results"):
                        kb_str = "\nErmo's real client results: " + "; ".join(str(r) for r in (kb["client_results"] or [])[:2])
                    prompt = (
                        "Study this high-performing post by " + author + ". Use the same structure, hook style, and emotional arc "
                        "but rewrite it 100% for Ermo (Authentik Studio, brand documentary/video production for B2B founders).\n"
                        + kb_str + "\n\nOriginal:\n---\n" + post_text[:800] + "\n---\n\n"
                        "Rules: same structural approach, completely different content in Ermo's niche. "
                        "NO em dashes, NO emojis, NO buzzwords. 150-250 words. Return ONLY the adapted post."
                    )
                result_text = _proxy_ai(
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-sonnet-4-6",
                    max_tokens=800,
                )
                self._json_response({"ok": True, "result": result_text, "mode": mode})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # Note: GET /api/knowledge-base and GET /api/swipe-file are handled in do_GET

        if path == "/api/knowledge-base/save":
            try:
                kb = json.loads(body) if body else {}
                with open(KB_FILE, "w") as f:
                    json.dump(kb, f, indent=2)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/swipe-file/save":
            # Add a post to the swipe file
            try:
                data = json.loads(body) if body else {}
                post = data.get("post")
                if not post:
                    self._json_response({"ok": False, "error": "post required"}, 400)
                    return
                swipe = []
                if os.path.exists(SWIPE_FILE):
                    with open(SWIPE_FILE) as f:
                        swipe = json.load(f)
                # Avoid duplicates by URL
                if not any(p.get("url") == post.get("url") for p in swipe):
                    post["saved_at"] = datetime.utcnow().isoformat()
                    swipe.insert(0, post)
                if len(swipe) > 50:
                    swipe = swipe[:50]
                with open(SWIPE_FILE, "w") as f:
                    json.dump(swipe, f, indent=2)
                self._json_response({"ok": True, "count": len(swipe)})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/swipe-file/delete":
            try:
                data = json.loads(body) if body else {}
                url  = data.get("url", "")
                swipe = []
                if os.path.exists(SWIPE_FILE):
                    with open(SWIPE_FILE) as f:
                        swipe = json.load(f)
                swipe = [p for p in swipe if p.get("url") != url]
                with open(SWIPE_FILE, "w") as f:
                    json.dump(swipe, f, indent=2)
                self._json_response({"ok": True, "count": len(swipe)})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # Note: GET /api/post-queue is handled in do_GET

        if path == "/api/post-queue/save":
            # Save post queue from dashboard or scheduled task to file
            try:
                data = json.loads(body) if body else {}
                with open(QUEUE_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/generate-week-queue":
            # Generate a full week of 4 posts (2 TAM, 1 Growth, 1 Sales) for the queue
            try:
                from config import YOUR_OFFERING, YOUR_NAME
                kb = {}
                try:
                    if os.path.exists(KB_FILE):
                        with open(KB_FILE) as f:
                            kb = json.load(f)
                except Exception:
                    pass
                kb_parts = []
                if kb.get("origin_story"):
                    kb_parts.append("Origin story: " + str(kb["origin_story"])[:300])
                if kb.get("client_results"):
                    kb_parts.append("Client results: " + "; ".join(str(r) for r in (kb["client_results"] or [])[:3]))
                if kb.get("core_beliefs"):
                    kb_parts.append("Core beliefs: " + " | ".join(str(b) for b in (kb["core_beliefs"] or [])[:3]))
                if kb.get("your_process"):
                    kb_parts.append("Process/differentiation: " + str(kb["your_process"])[:200])
                kb_block = ("\n\nKnowledge base (USE for specificity):\n" + "\n".join("- " + p for p in kb_parts)) if kb_parts else ""

                queue_spec = [
                    {"pillar": "tam",    "framework": "slay",  "hook": "story",      "day": "Tuesday"},
                    {"pillar": "growth", "framework": "pas",   "hook": "outcome",    "day": "Wednesday"},
                    {"pillar": "tam",    "framework": "slay",  "hook": "contrarian", "day": "Thursday"},
                    {"pillar": "sales",  "framework": "pas",   "hook": "outcome",    "day": "Friday"},
                ]
                pillar_descs = {
                    "tam": "Any founder / executive. Leadership, business lessons, entrepreneurship observations. NOT specifically about video. Maximum reach.",
                    "growth": "Founders who care about brand, content, online presence. Video strategy, brand storytelling, content that compounds. 'How I' framing.",
                    "sales": "Founders ready to invest in brand content. Client transformations with real numbers, ROI of brand documentary, proof. Outcomes-focused.",
                }
                fw_descs = {
                    "slay": "SLAY: open mid-scene (S), share the lesson (L), give one actionable insight (A), end with a pointed question to the reader (Y).",
                    "pas": "PAS: name the specific problem (P), make the cost of not solving it feel real (A), reveal the solution or approach (S).",
                }
                hook_descs = {
                    "story": "Hook: drop mid-scene — a specific moment, location, conversation. No setup.",
                    "outcome": "Hook: lead with a specific result that includes a number. Under 10 words.",
                    "contrarian": "Hook: challenge a widespread belief directly. Bold, specific, no hedging.",
                }
                posts = []
                offering_short = YOUR_OFFERING[:500].strip()
                for spec in queue_spec:
                    prompt = (
                        "Write a high-performance LinkedIn post for Ermo, founder of Authentik Studio"
                        " — brand documentary and video production for B2B founders.\n\n"
                        "What Ermo does: " + offering_short + kb_block + "\n\n"
                        "PILLAR: " + pillar_descs[spec["pillar"]] + "\n"
                        "FRAMEWORK: " + fw_descs[spec["framework"]] + "\n"
                        "HOOK: " + hook_descs[spec["hook"]] + "\n\n"
                        "STRICT rules: NO em dashes, NO emojis, NO buzzwords (game-changer/leveraging/impactful),"
                        " NO exclamation marks, NO hashtags in body, short sentences, 150-250 words,"
                        " do NOT start with 'I', write in first person as Ermo."
                        " Write ONLY the post text."
                    )
                    post_text = _proxy_ai(
                        messages=[{"role": "user", "content": prompt}],
                        model="claude-sonnet-4-6",
                        max_tokens=700,
                    )
                    posts.append({
                        "pillar":    spec["pillar"],
                        "framework": spec["framework"],
                        "day":       spec["day"],
                        "text":      post_text,
                        "posted":    False,
                    })
                import datetime as _dt
                week_key = _dt.date.today().strftime("%Y-W%W")
                queue_data = {"weekKey": week_key, "posts": posts, "generatedAt": _dt.datetime.utcnow().isoformat()}
                with open(QUEUE_FILE, "w") as f:
                    json.dump(queue_data, f, indent=2)
                self._json_response({"ok": True, "posts": posts, "generated_at": queue_data["generatedAt"]})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/research-viral":
            # Search for viral LinkedIn posts in the brand/founder/video niche
            # via Influentia proxy — returns hooks + snippets for post inspiration
            try:
                import re as _re

                niche_queries = [
                    'site:linkedin.com/posts "brand documentary" OR "brand film" founder',
                    'site:linkedin.com/posts "founder story" video brand',
                    'site:linkedin.com/posts "brand storytelling" B2B results',
                    'site:linkedin.com/posts "video content" B2B founder marketing',
                    'site:linkedin.com/posts "thought leadership" video "brand"',
                ]

                seen_authors = set()
                posts = []
                for q in niche_queries:
                    try:
                        data = _proxy_search(q, count=10)
                        results = data.get("web", {}).get("results", [])
                    except Exception:
                        results = []
                    for r in results:
                        url = r.get("url", "")
                        if "linkedin.com/posts/" not in url:
                            continue
                        m = _re.search(r'linkedin\.com/posts/([^_/?#]+)', url)
                        slug = m.group(1) if m else url
                        if slug in seen_authors:
                            continue
                        seen_authors.add(slug)

                        desc = r.get("description", "") or ""
                        snippets = r.get("extra_snippets", [])
                        text = desc or (snippets[0] if snippets else "")
                        if len(text) < 40:
                            continue

                        hook = text.split(".")[0].strip()
                        if len(hook) < 20:
                            hook = text[:160].strip()

                        title = r.get("title", "")
                        author = _re.sub(r'\s+(on LinkedIn|LinkedIn Post|LinkedIn).*$', '', title, flags=_re.I).strip()

                        posts.append({
                            "url":    url,
                            "author": author or slug,
                            "hook":   hook[:200],
                            "text":   text[:400],
                        })
                        if len(posts) >= 10:
                            break
                    if len(posts) >= 10:
                        break

                self._json_response({"ok": True, "posts": posts})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/comments/action":
            try:
                data = json.loads(body) if body else {}
                comment_id = data.get("id", "")
                action     = data.get("action", "")   # approve | unapprove | skip | edit
                final_text = data.get("text", "")
                from state_manager import load_state, mark_comment
                state = load_state()
                status_map = {"approve": "approved", "unapprove": "pending", "skip": "skipped", "edit": "approved"}
                c = mark_comment(state, comment_id, status_map.get(action, action), final_text)
                self._json_response({"ok": bool(c), "comment": c})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/comments/refine":
            try:
                data         = json.loads(body) if body else {}
                comment_text = data.get("comment_text", "")
                post_text    = data.get("post_text", "")
                poster_name  = data.get("poster_name", "")
                instruction  = data.get("instruction", "make it more casual").strip()
                if not instruction:
                    instruction = "make it more casual and natural"

                from config import YOUR_OFFERING
                offering_line = YOUR_OFFERING[:300].split("\n")[0].strip().lstrip("#").strip()

                prompt = f"""You are a B2B professional ({offering_line}) who wrote this LinkedIn comment.

Post by {poster_name}:
"{post_text[:500]}"

Current comment:
"{comment_text}"

Instruction: {instruction}

Rewrite the comment following the instruction. Rules:
- 2-3 sentences max
- Sounds like a real person, NOT AI — casual, genuine, direct
- NEVER mention your services, company, or products
- Engage with one specific point from the post
- NO em dashes (—) — biggest AI tell, rewrite the sentence instead
- NO emojis of any kind
- NO "Absolutely", "Certainly", "Great point", "This resonates", "Couldn't agree more"
- NO "particularly compelling", "genuinely rare", "truly fascinating"
- NO hashtags, no exclamation marks used just to seem enthusiastic
- NO "Leveraging", "synergy", "game-changer", or other LinkedIn buzzwords
- NO long sentences with multiple clauses — short and punchy
- Write like a real person, not a content creator

Reply with ONLY the new comment text. No quotes, no preamble."""

                refined = _proxy_ai(
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-haiku-4-5-20251001",
                    max_tokens=150,
                )
                self._json_response({"ok": True, "refined_text": refined})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/replies/action":
            # approve | skip a pending reply draft
            try:
                data     = json.loads(body) if body else {}
                reply_id = data.get("id", "")
                action   = data.get("action", "")   # approve | skip
                edited   = data.get("text", "")
                from state_manager import load_state, mark_reply, add_message, set_status
                state = load_state()
                entry = mark_reply(state, reply_id, action, edited)
                if not entry:
                    self._json_response({"ok": False, "error": "Reply not found"}, 404)
                    return
                if action == "approve":
                    # Send via LinkedIn in a background thread
                    import threading
                    def _send():
                        try:
                            from linkedin_client import LinkedInClient
                            c = LinkedInClient()
                            text = entry.get("ai_draft", "")
                            url  = entry["linkedin_url"]
                            if c.send_message(url, text):
                                s2 = load_state()
                                add_message(s2, url, "ai", text, msg_type="reply")
                                mark_reply(s2, reply_id, "sent")
                                logging.info(f"Approved reply sent to {entry['lead_name']}")
                            c.close()
                        except Exception as ex:
                            logging.error(f"Failed to send approved reply: {ex}")
                    threading.Thread(target=_send, daemon=True).start()
                self._json_response({"ok": True, "entry": entry})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/settings/auto-reply":
            # Toggle auto_reply_enabled setting
            try:
                data    = json.loads(body) if body else {}
                enabled = bool(data.get("enabled", False))
                from state_manager import load_state, save_state
                state = load_state()
                if "settings" not in state:
                    state["settings"] = {}
                state["settings"]["auto_reply_enabled"] = enabled
                save_state(state)
                self._json_response({"ok": True, "auto_reply_enabled": enabled})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/test/dm":
            try:
                data     = json.loads(body) if body else {}
                messages = data.get("messages", [])   # [{role:"user"|"assistant", content:"..."}]

                # Convert to state_manager conversation format
                history = [
                    {"role": "ai" if m["role"] == "assistant" else "prospect",
                     "content": m["content"]}
                    for m in messages
                ]
                test_prospect = {
                    "name":    data.get("prospect_name", "Test Prospect"),
                    "title":   data.get("prospect_title", "Founder"),
                    "company": data.get("prospect_company", "Test Co"),
                    "sector":  "",
                }
                from message_ai import generate_reply
                reply = generate_reply(test_prospect, history)
                self._json_response({"ok": True, "reply": reply})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/leads/toggle-manual":
            # Toggle manual_mode on a lead. When manual_mode=True the AI stops
            # replying/following-up and the user can handle the conversation.
            try:
                data = json.loads(body) if body else {}
                url  = data.get("linkedin_url", "")
                if not url:
                    self._json_response({"ok": False, "error": "linkedin_url required"}, 400)
                    return
                from state_manager import load_state, save_state
                state = load_state()
                lead  = state["leads"].get(url)
                if not lead:
                    self._json_response({"ok": False, "error": "Lead not found"}, 404)
                    return
                # If caller sends explicit value use it, otherwise flip
                if "manual_mode" in data:
                    lead["manual_mode"] = bool(data["manual_mode"])
                else:
                    lead["manual_mode"] = not lead.get("manual_mode", False)
                save_state(state)
                self._json_response({
                    "ok":          True,
                    "manual_mode": lead["manual_mode"],
                    "name":        lead.get("name", ""),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/leads/set-warm":
            # Mark/unmark a lead as warm (showing genuine buying interest).
            try:
                data = json.loads(body) if body else {}
                url  = data.get("linkedin_url", "")
                if not url:
                    self._json_response({"ok": False, "error": "linkedin_url required"}, 400)
                    return
                from state_manager import load_state, save_state
                state = load_state()
                lead  = state["leads"].get(url)
                if not lead:
                    self._json_response({"ok": False, "error": "Lead not found"}, 404)
                    return
                if "warm" in data:
                    lead["warm"] = bool(data["warm"])
                else:
                    lead["warm"] = not lead.get("warm", False)
                save_state(state)
                self._json_response({
                    "ok":  True,
                    "warm": lead["warm"],
                    "name": lead.get("name", ""),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/test-keys":
            # Verify the active license can reach the Influentia AI proxy.
            # (API keys are no longer stored locally — they live in the worker.)
            try:
                ping = _proxy_ai(
                    messages=[{"role": "user", "content": "Reply with the single word: ok"}],
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4,
                )
                self._json_response({"ok": True, "results": {"proxy": {"ok": True, "reply": ping}}})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/feedback":
            # Collect feedback from the in-dashboard "Send Feedback" modal.
            # Body: {"note": str, "include_logs": bool, "page": str}.
            # Writes a timestamped JSON to ./feedback/ and returns a mailto: URL
            # pre-filled with the note so the tester can fire it to the author.
            try:
                data = json.loads(body) if body else {}
                note = (data.get("note") or "").strip()
                if not note:
                    self._json_response({"ok": False, "error": "A short note is required."}, 400)
                    return

                os.makedirs(FEEDBACK_DIR, exist_ok=True)
                ts       = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                fb_path  = os.path.join(FEEDBACK_DIR, f"feedback_{ts}.json")

                # Gather system info
                import platform as _plat
                sys_info = {
                    "os":       _plat.platform(),
                    "python":   sys.version.split()[0],
                    "time":     datetime.now().isoformat(),
                    "page":     data.get("page", ""),
                }

                payload = {
                    "note":         note,
                    "system":       sys_info,
                    "recent_logs":  [],
                    "recent_error": None,
                }

                # Include current task error if one is showing
                with _task_lock:
                    if _current_task and _current_task.get("error"):
                        payload["recent_error"] = {
                            "task":   _current_task.get("name"),
                            "error":  _current_task.get("error"),
                            "code":   _current_task.get("error_code"),
                        }

                if data.get("include_logs"):
                    # Last 200 lines from outreach_log.txt
                    log_path = os.path.join(BASE_DIR, LOG_FILE)
                    if os.path.exists(log_path):
                        try:
                            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                                lines = f.readlines()
                            payload["recent_logs"] = [l.rstrip() for l in lines[-200:]]
                        except Exception:
                            pass

                with open(fb_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)

                # Build a mailto URL the frontend can open to send it to us
                import urllib.parse as _up
                subject = f"[Influentia] Feedback — {sys_info['os'].split('-')[0]}"
                bodyparts = [
                    note,
                    "",
                    "---",
                    f"OS: {sys_info['os']}",
                    f"Python: {sys_info['python']}",
                    f"Time: {sys_info['time']}",
                ]
                if payload["recent_error"]:
                    bodyparts += ["", f"Last error: {payload['recent_error']['error']}"]
                if payload["recent_logs"]:
                    bodyparts += ["", "(Logs attached locally at " + fb_path + ")"]
                mailto = (
                    "mailto:feedback@influentia.io"
                    "?subject=" + _up.quote(subject) +
                    "&body=" + _up.quote("\n".join(bodyparts))
                )

                self._json_response({"ok": True, "saved": fb_path, "mailto": mailto})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/linkedin/resume":
            # Clear the LinkedIn pause flag (user has resolved the challenge).
            try:
                _clear_linkedin_pause()
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/linkedin/pause":
            # Manually pause automation. Used by the dashboard "Pause Automation"
            # safety button. Default: 24h.
            try:
                data = json.loads(body) if body else {}
                hours = int(data.get("hours", 24))
                reason = (data.get("reason") or "Paused by user.").strip()
                until = (datetime.now().timestamp() + hours * 3600)
                until_iso = datetime.fromtimestamp(until).isoformat()
                with open(PAUSE_FILE, "w") as f:
                    json.dump({
                        "reason": reason,
                        "until":  until_iso,
                        "set_at": datetime.now().isoformat(),
                        "manual": True,
                    }, f, indent=2)
                self._json_response({"ok": True, "until": until_iso})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/onboarding/complete":
            # Persist that the first-run wizard has been finished. Future reloads
            # will skip the modal unless the user clicks "Restart onboarding".
            # Also fires a background Reddit scan so the dashboard has fresh
            # leads ready by the time the customer lands on it — keeps the
            # wizard's "first signals in 60 seconds" promise honest.
            try:
                data = json.loads(body) if body else {}
                payload = {
                    "complete":  bool(data.get("complete", True)),
                    "dismissed": bool(data.get("dismissed", False)),
                    "finished_at": datetime.now().isoformat(),
                }
                with open(ONBOARD_FILE, "w") as f:
                    json.dump(payload, f, indent=2)

                # Fire-and-forget Reddit scan in a daemon thread.
                # Only kicks off if onboarding actually completed (not just dismissed).
                if payload["complete"] and not payload["dismissed"]:
                    def _bg_first_scan():
                        try:
                            from state_manager import load_state
                            from reddit_signal import scan_signals
                            st = load_state()
                            scan_signals(st)
                        except Exception as _e:
                            # Background scan must never crash the response
                            # path. If it fails, the customer can scan manually
                            # from the dashboard. Log and move on.
                            try:
                                print(f"[onboarding] background first-scan failed: {_e}")
                            except Exception:
                                pass
                    threading.Thread(target=_bg_first_scan, daemon=True).start()

                self._json_response({"ok": True, **payload})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/onboarding/reset":
            # Reopen the wizard (Settings → "Restart setup").
            try:
                if os.path.exists(ONBOARD_FILE):
                    os.remove(ONBOARD_FILE)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/preview-scan":
            # No-auth Reddit preview scan — called BEFORE license validation so new
            # users see real buyer signals before being asked to enter a license key.
            # Uses BRAVE_SEARCH_API_KEY from .env directly (no proxy needed).
            try:
                import re as _re2
                import urllib.request as _ureq
                import urllib.parse as _uparse
                import gzip as _gzip

                data = json.loads(body) if body else {}
                description = (data.get("description") or "").strip()
                if not description or len(description) < 10:
                    self._json_response({"ok": False, "error": "Please describe what you do."}, 400)
                    return

                brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
                if not brave_key:
                    try:
                        import importlib, sys as _sys
                        _cfg = importlib.import_module("config")
                        brave_key = getattr(_cfg, "BRAVE_SEARCH_API_KEY", "")
                    except Exception:
                        pass
                if not brave_key:
                    self._json_response({"ok": False, "error": "Search not available."}, 503)
                    return

                BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
                STOPWORDS = {
                    'i', 'we', 'help', 'helps', 'the', 'a', 'an', 'and', 'or', 'but',
                    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is',
                    'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                    'do', 'does', 'did', 'my', 'your', 'their', 'our', 'its', 'this',
                    'that', 'these', 'those', 'it', 'them', 'they', 'can', 'could',
                    'would', 'should', 'will', 'may', 'might', 'get', 'more', 'not',
                    'who', 'what', 'how', 'when', 'where', 'why', 'which', 'also',
                    'into', 'than', 'then', 'very', 'just', 'out', 'up', 'so', 'if',
                    'about', 'make', 'without', 'even', 'need', 'want', 'like',
                }
                words = _re2.sub(r'[^a-zA-Z0-9 ]', ' ', description.lower()).split()
                keywords = [w for w in words if w not in STOPWORDS and len(w) > 3][:8]

                queries = []
                if keywords:
                    queries.append(f'site:reddit.com {" ".join(keywords[:4])}')
                    if len(keywords) > 4:
                        queries.append(f'site:reddit.com {" ".join(keywords[2:6])}')
                # Fallback broad query using raw description
                desc_short = description[:80].rstrip()
                queries.append(f'site:reddit.com {desc_short}')
                queries = queries[:3]

                def _brave_req(query: str) -> list:
                    params = "?" + _uparse.urlencode({
                        "q": query, "count": 10, "freshness": "pm", "search_lang": "en",
                    })
                    req = _ureq.Request(
                        BRAVE_URL + params,
                        headers={
                            "Accept": "application/json",
                            "Accept-Encoding": "gzip",
                            "X-Subscription-Token": brave_key,
                        }
                    )
                    with _ureq.urlopen(req, timeout=15) as resp:
                        raw = resp.read()
                        if resp.info().get("Content-Encoding") == "gzip":
                            raw = _gzip.decompress(raw)
                        return json.loads(raw).get("web", {}).get("results", [])

                signals = []
                seen_urls: set = set()
                for q in queries:
                    try:
                        results = _brave_req(q)
                    except Exception as _e:
                        log.warning("preview-scan query failed: %s", _e)
                        continue
                    for r in results:
                        url = r.get("url", "")
                        if "reddit.com/r/" not in url or "/comments/" not in url:
                            continue
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        sub_m = _re2.search(r'reddit\.com/r/([^/]+)', url)
                        subreddit = sub_m.group(1) if sub_m else "reddit"
                        title = _re2.sub(r'\s*[-|]\s*Reddit\s*$', '', r.get("title", ""), flags=_re2.I).strip()
                        snippet = (r.get("description") or "")[:220]
                        age = r.get("age", "") or r.get("page_age", "") or ""
                        if len(title) < 10:
                            continue
                        signals.append({
                            "title": title,
                            "subreddit": subreddit,
                            "url": url,
                            "snippet": snippet,
                            "age": age,
                        })
                        if len(signals) >= 6:
                            break
                    if len(signals) >= 6:
                        break

                self._json_response({"ok": True, "signals": signals[:5]})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/business":
            # Screen 2: {biz_what, biz_who, goal, name, company, booking_link, voice}.
            # Saves ICP to knowledge_base.json and profile fields to .env config.
            try:
                data = json.loads(body) if body else {}
                biz_what = (data.get("biz_what") or "").strip()
                biz_who  = (data.get("biz_who")  or "").strip()
                goal     = (data.get("goal")     or "").strip()
                if not biz_what or not biz_who:
                    self._json_response({"ok": False, "error": "Both fields are required."}, 400)
                    return
                kb = {}
                if os.path.exists(KB_FILE):
                    try:
                        with open(KB_FILE) as f:
                            kb = json.load(f) or {}
                    except Exception:
                        kb = {}
                kb["business_what"]       = biz_what
                kb["business_who"]        = biz_who
                kb["wizard_goal"]         = goal
                kb["wizard_completed_at"] = datetime.now().isoformat()
                # Optional profile fields from wizard step 5
                voice = (data.get("voice") or "").strip()
                if voice:
                    kb["brand_voice_notes"] = voice
                with open(KB_FILE, "w") as f:
                    json.dump(kb, f, indent=2)
                # Save identity fields to .env config
                cfg_updates = {}
                if data.get("name"):        cfg_updates["YOUR_NAME"]      = data["name"].strip()
                if data.get("company"):     cfg_updates["YOUR_COMPANY"]   = data["company"].strip()
                if data.get("booking_link"): cfg_updates["YOUR_GOAL_LINK"] = data["booking_link"].strip()
                if cfg_updates:
                    self._save_config_vars(cfg_updates)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/reddit":
            # Screen 4: save Reddit opt-in preference and configure default subreddits.
            try:
                data   = json.loads(body) if body else {}
                optin  = data.get("optin", "yes")
                from state_manager import load_state, save_state
                st = load_state()
                settings = st.setdefault("reddit_settings", {})
                settings["daily_auto_draft"] = (optin == "yes")
                settings["daily_auto_post"]  = False  # always require approval on first run
                # Seed default subreddits if none configured yet
                if not settings.get("subreddits"):
                    settings["subreddits"] = [
                        "entrepreneur", "SaaS", "b2b_sales", "startups",
                        "smallbusiness", "marketing", "consulting", "freelance",
                        "agency", "B2BSaaS", "sales", "linkedin",
                    ]
                if not settings.get("queries"):
                    settings["queries"] = [
                        "looking for outreach tool",
                        "LinkedIn automation",
                        "cold outreach not working",
                        "how to get more clients",
                        "best way to find leads",
                        "struggling with prospecting",
                    ]
                save_state(st)
                self._json_response({"ok": True, "optin": optin})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/reddit-credentials":
            # Save REDDIT_USERNAME and REDDIT_PASSWORD to .env, then verify immediately.
            # Send disconnect:true to clear credentials.
            try:
                data     = json.loads(body) if body else {}
                username = (data.get("username") or "").strip()
                password = (data.get("password") or "")

                # Disconnect: remove credentials from .env and env
                if data.get("disconnect"):
                    for key in ("REDDIT_USERNAME", "REDDIT_PASSWORD"):
                        os.environ.pop(key, None)
                    env_path = os.path.join(BASE_DIR, ".env")
                    if os.path.exists(env_path):
                        with open(env_path) as f:
                            lines = f.readlines()
                        lines = [l for l in lines if not l.startswith(("REDDIT_USERNAME=", "REDDIT_PASSWORD="))]
                        with open(env_path, "w") as f:
                            f.writelines(lines)
                    self._json_response({"ok": True})
                    return

                if not username or not password:
                    self._json_response({"ok": False, "error": "Username and password are required."}, 400)
                    return
                env_path = os.path.join(BASE_DIR, ".env")
                lines = []
                if os.path.exists(env_path):
                    with open(env_path) as f:
                        lines = f.readlines()
                def _set_env(lines, key, value):
                    new_line = f"{key}={value}\n"
                    for i, line in enumerate(lines):
                        if line.startswith(f"{key}="):
                            lines[i] = new_line
                            return lines
                    lines.append(new_line)
                    return lines
                lines = _set_env(lines, "REDDIT_USERNAME", username)
                lines = _set_env(lines, "REDDIT_PASSWORD", password)
                with open(env_path, "w") as f:
                    f.writelines(lines)
                # Clear the old browser session so it logs in fresh with new account
                old_username = os.environ.get("REDDIT_USERNAME", "").strip()
                if old_username and old_username != username:
                    import shutil
                    profile_dir = os.path.join(BASE_DIR, "reddit_profile")
                    for candidate in [old_username, old_username.replace("@", "_at_")]:
                        old_session = os.path.join(profile_dir, candidate)
                        if os.path.exists(old_session):
                            shutil.rmtree(old_session, ignore_errors=True)
                            logging.info(f"Cleared old Reddit session for {old_username!r}")

                os.environ["REDDIT_USERNAME"] = username
                os.environ["REDDIT_PASSWORD"] = password
                self._json_response({
                    "ok": True,
                    "verified": True,
                    "warning": f"u/{username} saved. A browser will open briefly on first post to confirm login.",
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/verify":
            # Check whether Reddit credentials are stored — used by dashboard on tab load.
            # Does NOT call Reddit's API; actual login is confirmed on first post.
            try:
                username = os.environ.get("REDDIT_USERNAME", "").strip()
                password = os.environ.get("REDDIT_PASSWORD", "").strip()
                if username and password:
                    self._json_response({"ok": True, "verified": True, "username": username})
                else:
                    self._json_response({"ok": True, "verified": False})
            except Exception as e:
                self._json_response({"ok": False, "verified": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/linkedin-connect":
            # Start the real Playwright LinkedIn login flow.
            # Opens a visible browser, waits for login, saves session.
            try:
                result = start_login_flow()
                # If login was successful or already connected, copy profile to main client
                if result.get("connected") or result.get("ok"):
                    copy_wizard_profile_to_client()
                self._json_response(result)
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/wizard/linkedin-status":
            # Check LinkedIn login status (for polling from wizard)
            try:
                status = get_login_status()
                # If connected, ensure profile is copied to main client
                if status.get("connected"):
                    copy_wizard_profile_to_client()
                self._json_response({"ok": True, **status})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/license":
            # Activate a license key. Body: {"key": "XXXX-XXXX-..."}.
            # Validates with the Worker, caches locally.
            try:
                data = json.loads(body) if body else {}
                key  = (data.get("key") or "").strip()
                if not key:
                    self._json_response(
                        {"ok": False, "error": "License key is required."}, 400,
                    )
                    return
                # Normalize: strip spaces, uppercase
                key = key.replace(" ", "").upper()
                # If the key matches what's already saved locally, accept it
                # immediately (no worker call needed). This covers: owner bypass
                # keys, and the case where the worker isn't deployed yet.
                existing = _load_license() or {}
                if existing.get("key") == key and existing.get("tier") in ("active", "trial"):
                    self._json_response({"ok": True, **_license_state()})
                    return

                fresh = _check_license_with_worker(key)
                if fresh is None:
                    self._json_response({
                        "ok": False,
                        "error": "Could not reach the license server. Check your internet connection and try again.",
                        "error_code": "network",
                    }, 503)
                    return
                if not fresh.get("valid"):
                    reason = fresh.get("reason") or "not_found"
                    self._json_response({
                        "ok": False,
                        "error": "That license key isn't recognized. Copy it again from your receipt.",
                        "error_code": "bad_license",
                        "reason": reason,
                    }, 400)
                    return
                # Save cached copy
                lic = {
                    "key": key,
                    "email": fresh.get("email"),
                    "tier":  fresh.get("tier"),
                    "trial_ends_at": fresh.get("trial_ends_at"),
                    "current_period_end": fresh.get("current_period_end"),
                    "subscription_status": fresh.get("subscription_status"),
                    "last_checked_at": int(time.time()),
                }
                _save_license(lic)
                self._json_response({"ok": True, **_license_state()})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/license/refresh":
            # Force a revalidation with the worker (ignores the 12h cache).
            try:
                lic = _load_license() or {}
                key = lic.get("key")
                if not key:
                    self._json_response(
                        {"ok": False, "error": "No license to refresh."}, 400,
                    )
                    return
                fresh = _check_license_with_worker(key)
                if fresh is None:
                    self._json_response({
                        "ok": False,
                        "error": "License server unreachable.",
                        "error_code": "network",
                    }, 503)
                    return
                if fresh.get("valid"):
                    lic.update({
                        "email": fresh.get("email", lic.get("email")),
                        "tier":  fresh.get("tier"),
                        "trial_ends_at": fresh.get("trial_ends_at"),
                        "current_period_end": fresh.get("current_period_end"),
                        "subscription_status": fresh.get("subscription_status"),
                        "last_checked_at": int(time.time()),
                    })
                    _save_license(lic)
                else:
                    lic["tier"] = "revoked"
                    lic["last_checked_at"] = int(time.time())
                    _save_license(lic)
                self._json_response({"ok": True, **_license_state()})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/license/remove":
            # Sign out — delete cached license. Useful for support / testing.
            try:
                if os.path.exists(LICENSE_FILE):
                    os.remove(LICENSE_FILE)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # ── Hot-reload endpoint — reloads Python modules without server restart ──
        if path == "/api/reload":
            try:
                import importlib, sys
                mods = ["reddit_client", "reddit_signal", "state_manager",
                        "ai_proxy", "config", "comment", "message_ai"]
                reloaded = []
                for name in mods:
                    if name in sys.modules:
                        importlib.reload(sys.modules[name])
                        reloaded.append(name)
                self._json_response({"ok": True, "reloaded": reloaded})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # ── Reddit Signal + Engage endpoints ─────────────────────────────────

        if path == "/api/reddit/icp":
            # GET-style POST — returns the available ICP presets and which is active.
            # Used by the Reddit-tab banner so customers always know what we're scanning for.
            try:
                from state_manager import load_state
                from reddit_signal import ICP_PRESETS
                state = load_state()
                settings = state.get("reddit_settings", {})
                active = settings.get("active_icp", "authentik")
                if active not in ICP_PRESETS and active != "custom":
                    active = "authentik"
                presets = []
                for k, v in ICP_PRESETS.items():
                    presets.append({
                        "id":          k,
                        "label":       v["label"],
                        "description": v["description"],
                        "subreddit_count": len(v["subreddits"]),
                        "query_count":     len(v["queries"]),
                    })
                # Always include "custom" as an option so users can override
                presets.append({
                    "id":          "custom",
                    "label":       "Custom",
                    "description": "Use your own subreddits, queries, and (optionally) scoring criteria.",
                    "subreddit_count": len(settings.get("subreddits") or []),
                    "query_count":     len(settings.get("queries") or []),
                })
                self._json_response({"ok": True, "active": active, "presets": presets})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/scan":
            # Scan subreddits for new signals. No body params needed.
            try:
                import traceback as _tb
                from state_manager import load_state
                from reddit_signal import scan_signals
                state = load_state()
                new_signals = scan_signals(state)
                total_in_state = len(state.get("reddit_signals", []))
                raw_found = state.pop("_reddit_last_raw", 0)
                new_scores = [s.get("relevance", 0) for s in new_signals if s.get("relevance")]
                avg_new_score = round(sum(new_scores) / len(new_scores), 1) if new_scores else None
                self._json_response({
                    "ok": True,
                    "new_count": len(new_signals),
                    "total_count": total_in_state,
                    "raw_found": raw_found,
                    "avg_new_score": avg_new_score,
                    "signals": new_signals,
                })
            except Exception as e:
                import traceback as _tb
                self._json_response({"ok": False, "error": str(e),
                                     "detail": _tb.format_exc()}, 500)
            return

        if path == "/api/reddit/signals":
            # Return current signals list (GET-style POST for consistency)
            try:
                from state_manager import load_state
                state = load_state()
                signals = state.get("reddit_signals", [])
                # Enrich: mark which have pending/posted comments
                pending_ids = {c["post_id"] for c in state.get("reddit_pending_comments", [])}
                posted_ids  = {c["post_id"] for c in state.get("reddit_posted_comments", [])}
                for s in signals:
                    if s["post_id"] in posted_ids:
                        s["comment_status"] = "posted"
                    elif s["post_id"] in pending_ids:
                        s["comment_status"] = "pending"
                    else:
                        s["comment_status"] = "none"
                # ── Quality stats ─────────────────────────────────────────────
                scores = [s.get("relevance", 0) for s in signals if s.get("relevance")]
                hot    = [s for s in signals if (s.get("relevance") or 0) >= 8]
                avg_score = round(sum(scores) / len(scores), 1) if scores else None
                # Top queries: count matched_queries occurrences across all signals
                from collections import Counter
                query_counts: Counter = Counter()
                for s in signals:
                    for q in (s.get("matched_queries") or []):
                        query_counts[q] += 1
                top_queries = [{"query": q, "count": c}
                                for q, c in query_counts.most_common(8)]
                # Top subreddits
                sub_counts: Counter = Counter(s.get("subreddit", "") for s in signals)
                top_subreddits = [{"subreddit": r, "count": c}
                                   for r, c in sub_counts.most_common(5) if r]
                quality = {
                    "total":          len(signals),
                    "hot_count":      len(hot),
                    "avg_score":      avg_score,
                    "top_queries":    top_queries,
                    "top_subreddits": top_subreddits,
                }
                from datetime import datetime as _dts
                _today_s = _dts.utcnow().strftime("%Y-%m-%d")
                posted_today = sum(
                    1 for c in state.get("reddit_posted_comments", [])
                    if c.get("posted_at", "").startswith(_today_s)
                )
                daily_cap = int(state.get("reddit_settings", {}).get("daily_post_cap", 5))
                auto_scan_enabled  = bool(state.get("reddit_settings", {}).get("auto_scan_enabled"))
                auto_scan_interval = int(state.get("reddit_settings", {}).get("auto_scan_interval_mins", 30))
                self._json_response({
                    "ok": True,
                    "signals": signals,
                    "last_scan_at": state.get("reddit_last_scan_at"),
                    "quality": quality,
                    "posted_today": posted_today,
                    "daily_cap": daily_cap,
                    "slots_left": max(0, daily_cap - posted_today),
                    "auto_scan_enabled":  auto_scan_enabled,
                    "auto_scan_interval": auto_scan_interval,
                    "next_auto_scan_at":  state.get("_next_auto_scan_at"),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/signals/mark-seen":
            # Clear is_new flag on all signals (called after user views fresh scan results)
            try:
                from state_manager import load_state, save_state
                state = load_state()
                for s in state.get("reddit_signals", []):
                    s["is_new"] = False
                save_state(state)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/draft-comment":
            # Generate an AI comment draft for a signal and queue it for approval.
            try:
                data      = json.loads(body) if body else {}
                signal_id = data.get("signal_id", "")
                from state_manager import load_state
                from reddit_signal import generate_reddit_comment, add_reddit_pending_comment
                state = load_state()
                signal = next((s for s in state.get("reddit_signals", [])
                               if s["id"] == signal_id), None)
                if not signal:
                    self._json_response({"ok": False, "error": "Signal not found"}, 404)
                    return
                draft = generate_reddit_comment(signal, state)
                entry = add_reddit_pending_comment(state, signal, draft)
                self._json_response({"ok": True, "entry": entry})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/comment/action":
            # approve | skip | edit a pending Reddit comment draft.
            try:
                data      = json.loads(body) if body else {}
                comment_id = data.get("id", "")
                action     = data.get("action", "")    # approve | skip | edit
                final_text = data.get("text", "")
                from state_manager import load_state
                from reddit_signal import mark_reddit_comment
                state = load_state()
                # map action → status
                status_map = {
                    "approve": "approved",
                    "skip":    "skipped",
                    "edit":    "approved",
                }
                c = mark_reddit_comment(state, comment_id,
                                        status_map.get(action, action),
                                        final_text)
                self._json_response({"ok": bool(c), "comment": c})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/auto_draft":
            # Toggle the daily auto-draft scheduler. Body: {"enabled": true|false}.
            # When enabled, the 8 AM job scans + drafts up to 3 replies per day on
            # high-score signals, queued for manual review & post. Default: off.
            try:
                from state_manager import load_state, save_state
                data    = json.loads(body) if body else {}
                enabled = bool(data.get("enabled"))
                state   = load_state()
                state.setdefault("reddit_settings", {})["daily_auto_draft"] = enabled
                save_state(state)
                self._json_response({
                    "ok": True,
                    "enabled": enabled,
                    "message": ("Daily auto-draft enabled. Up to 3 reply drafts "
                                "will queue for review at 8 AM each day.") if enabled else
                               "Daily auto-draft disabled.",
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/comments/clear-all":
            # Wipe all pending + skipped comments for a fresh start
            try:
                from state_manager import load_state, save_state
                state = load_state()
                removed = len([c for c in state.get("pending_comments", [])
                               if c.get("status") in ("pending", "skipped", "approved")])
                state["pending_comments"] = [
                    c for c in state.get("pending_comments", [])
                    if c.get("status") == "posted"
                ]
                save_state(state)
                self._json_response({"ok": True, "removed": removed})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/comments/purge-stale":
            try:
                from state_manager import load_state, purge_stale_pending_comments
                state   = load_state()
                removed = purge_stale_pending_comments(state, max_age_days=14)
                self._json_response({"ok": True, "removed": removed})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/linkedin/auto-post-comments":
            # Toggle LinkedIn comment auto-post. Body: {"enabled": bool}
            # When on: after Smart Scan drafts comments they are immediately
            # approved and posted — no manual review step.
            try:
                from state_manager import load_state, save_state
                data    = json.loads(body) if body else {}
                enabled = bool(data.get("enabled"))
                state   = load_state()
                state.setdefault("linkedin_settings", {})["auto_post_comments"] = enabled
                save_state(state)
                self._json_response({"ok": True, "enabled": enabled})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/auto-scan":
            # Toggle continuous background scanner. Body: {"enabled": bool, "interval_mins": int}
            try:
                from state_manager import load_state, save_state
                data     = json.loads(body) if body else {}
                enabled  = bool(data.get("enabled"))
                interval = max(10, min(120, int(data.get("interval_mins", 30))))
                state    = load_state()
                state.setdefault("reddit_settings", {})["auto_scan_enabled"]    = enabled
                state.setdefault("reddit_settings", {})["auto_scan_interval_mins"] = interval
                if not enabled:
                    state.pop("_next_auto_scan_at", None)
                save_state(state)
                if enabled:
                    _start_continuous_scanner()
                else:
                    _continuous_scan_stop.set()
                self._json_response({"ok": True, "enabled": enabled, "interval_mins": interval})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/auto_post":
            # Toggle auto-posting of reddit comments (skips the approval queue).
            # Body: {"enabled": true|false}. When on, high-score signals get
            # drafted AND posted automatically — no manual review.
            try:
                from state_manager import load_state, save_state
                data    = json.loads(body) if body else {}
                enabled = bool(data.get("enabled"))
                state   = load_state()
                state.setdefault("reddit_settings", {})["daily_auto_post"] = enabled
                save_state(state)
                self._json_response({
                    "ok": True,
                    "enabled": enabled,
                    "message": ("Auto-post enabled. Score 8+ signals will be posted automatically "
                                "throughout the day as they are found — no manual review.") if enabled else
                               "Auto-post disabled — comments queue for your approval.",
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/auto_reply":
            # Toggle auto-reply to Reddit inbox replies on our posted comments.
            # Body: {"enabled": true|false} and/or {"daily_cap": 5}
            try:
                from state_manager import load_state, save_state
                data   = json.loads(body) if body else {}
                state  = load_state()
                rs     = state.setdefault("reddit_settings", {})
                if "enabled" in data:
                    rs["auto_reply_replies"] = bool(data["enabled"])
                if "daily_cap" in data:
                    rs["auto_reply_daily_cap"] = max(1, min(int(data["daily_cap"]), 20))
                save_state(state)
                self._json_response({
                    "ok": True,
                    "auto_reply_replies": rs.get("auto_reply_replies", False),
                    "auto_reply_daily_cap": rs.get("auto_reply_daily_cap", 3),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/icp/set":
            # Switch the active ICP preset. Body: {"active_icp": "authentik"|"influentia"|"custom"}.
            # When switching, we DO NOT clobber custom subreddits/queries the user
            # may have added — they remain in settings and override the preset's
            # defaults. To reset, the UI sends an explicit clear flag.
            try:
                from state_manager import load_state, save_state
                from reddit_signal import ICP_PRESETS
                data       = json.loads(body) if body else {}
                new_active = (data.get("active_icp") or "").strip()
                clear      = bool(data.get("clear_custom"))
                if new_active not in ICP_PRESETS and new_active != "custom":
                    self._json_response({
                        "ok": False,
                        "error": f"Unknown ICP preset '{new_active}'. Pick one of: " +
                                 ", ".join(ICP_PRESETS.keys()) + ", custom.",
                    }, 400)
                    return
                state = load_state()
                settings = state.setdefault("reddit_settings", {})
                settings["active_icp"] = new_active
                if clear:
                    settings["subreddits"] = []
                    settings["queries"]    = []
                save_state(state)
                # Echo back the now-active preset so the UI can refresh its banner.
                preset = ICP_PRESETS.get(new_active, {})
                self._json_response({
                    "ok":     True,
                    "active": new_active,
                    "label":  preset.get("label", "Custom"),
                    "description": preset.get("description", ""),
                })
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/comment/post":
            # Post an approved comment via a subprocess (avoids Playwright asyncio conflict).
            try:
                data       = json.loads(body) if body else {}
                comment_id = data.get("id", "")
                from state_manager import load_state
                from datetime import datetime as _dtt2
                state = load_state()

                # Daily safety cap — configurable, default 5
                _today2     = _dtt2.utcnow().strftime("%Y-%m-%d")
                _daily_cap  = int(state.get("reddit_settings", {}).get("daily_post_cap", 5))
                _posted_today = sum(
                    1 for c in state.get("reddit_posted_comments", [])
                    if (c.get("posted_at") or c.get("created_at") or "")[:10] == _today2
                )
                if _posted_today >= _daily_cap:
                    self._json_response({
                        "ok": False,
                        "error": f"Daily limit reached — {_posted_today}/{_daily_cap} Reddit comments posted today. Increase the cap in Reddit settings or try again tomorrow."
                    }, 429)
                    return

                entry = next((c for c in state.get("reddit_pending_comments", [])
                              if c["id"] == comment_id), None)
                if not entry:
                    self._json_response({"ok": False, "error": "Comment not found"}, 404)
                    return
                text     = entry.get("final_text") or entry.get("draft_text", "")
                fullname = entry.get("post_fullname", "")
                if not fullname:
                    self._json_response({
                        "ok": False,
                        "error": "Can't find the original Reddit post. "
                                 "Try regenerating the draft from the Reddit tab."
                    }, 400)
                    return
                if not text:
                    self._json_response({
                        "ok": False, "error": "Comment text is empty. Edit the draft and try again."
                    }, 400)
                    return

                # Run Playwright in a subprocess to avoid asyncio conflicts
                try:
                    _run_reddit_post_subprocess(comment_id, fullname, text)
                except RuntimeError as post_err:
                    msg = str(post_err)
                    low = msg.lower()
                    if "ratelimit" in low or "429" in low:
                        code, friendly = "rate_limited", "Reddit is rate-limiting — wait 5–10 min and try again."
                    elif "locked" in low:
                        code, friendly = "locked", "That Reddit post is locked."
                    elif "deleted" in low or "404" in low:
                        code, friendly = "deleted", "The Reddit post was deleted."
                    elif "comment box" in low or "submit button" in low:
                        code, friendly = "ui_changed", "Reddit's UI changed — try again in a moment."
                    else:
                        code, friendly = "unexpected", msg
                    self._json_response({"ok": False, "code": code, "error": friendly, "detail": msg}, 502)
                    return

                # Reload state to get the updated comment_fullname written by subprocess
                state = load_state()
                posted = next((c for c in state.get("reddit_posted_comments", [])
                               if c["id"] == comment_id), None)
                fullname_out = posted.get("comment_fullname", "") if posted else ""
                self._json_response({"ok": True, "comment_fullname": fullname_out})
            except Exception as e:
                import traceback as _tb
                logging.error("Reddit post failure: %s", _tb.format_exc())
                self._json_response({
                    "ok": False, "code": "unexpected",
                    "error": "Something unexpected went wrong. Try again or email support@influentia.io.",
                    "detail": str(e),
                    "trace":  _tb.format_exc().splitlines()[-3:],
                }, 500)
            return

        if path == "/api/reddit/comment/refine":
            # AI-refine a Reddit comment draft with a user instruction.
            try:
                data        = json.loads(body) if body else {}
                comment_text = data.get("comment_text", "")
                post_text   = data.get("post_text", "")
                subreddit   = data.get("subreddit", "")
                instruction = data.get("instruction", "make it more casual").strip()
                if not instruction:
                    instruction = "make it more casual and natural"

                prompt = f"""You wrote this Reddit comment for r/{subreddit}:
"{comment_text}"

Original post context:
"{post_text[:400]}"

Instruction: {instruction}

Rewrite the comment following the instruction. Rules:
- 3-5 sentences max
- Sound like a real Reddit user, not a marketer or consultant
- NEVER mention your company or services
- NO em dashes (—), NO bullet lists, NO emojis unless the original post had them
- NO "Happy to help", "Great question", or other LinkedIn-style openers
- Keep the specific value or insight from the original

Reply with ONLY the new comment text. No quotes, no preamble."""

                refined = _proxy_ai(
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                )
                self._json_response({"ok": True, "refined_text": refined})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/comments":
            # Return pending + posted Reddit comments.
            try:
                from state_manager import load_state
                state = load_state()
                pending = [c for c in state.get("reddit_pending_comments", [])
                           if c["status"] in ("pending", "approved")]
                posted  = state.get("reddit_posted_comments", [])[-30:]
                self._json_response({"ok": True, "pending": pending, "posted": posted})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/replies":
            # Check Reddit inbox for new replies to our posted comments.
            try:
                from state_manager import load_state
                from reddit_signal import check_reddit_replies
                state = load_state()
                new_replies = check_reddit_replies(state)
                pending_replies = [r for r in state.get("reddit_reply_queue", [])
                                   if r["status"] == "pending"]
                self._json_response({"ok": True, "new": len(new_replies),
                                     "pending_replies": pending_replies})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/reply/action":
            # dismiss or reply to a Reddit inbox reply.
            try:
                data     = json.loads(body) if body else {}
                reply_id = data.get("id", "")
                action   = data.get("action", "")    # reply | dismiss
                text     = data.get("text", "")
                from state_manager import load_state, save_state
                state = load_state()
                entry = next((r for r in state.get("reddit_reply_queue", [])
                              if r["id"] == reply_id), None)
                if not entry:
                    self._json_response({"ok": False, "error": "Reply not found"}, 404)
                    return
                if action == "dismiss":
                    entry["status"] = "dismissed"
                    save_state(state)
                    self._json_response({"ok": True})
                    return
                if action == "reply":
                    from reddit_client import get_reddit_client
                    client = get_reddit_client()
                    fullname = entry.get("reply_id", "")
                    client.reply_to_comment(fullname, text)
                    entry["status"] = "replied"
                    entry["replied_at"] = datetime.now().isoformat()
                    save_state(state)
                    self._json_response({"ok": True})
                    return
                self._json_response({"ok": False, "error": f"Unknown action: {action}"}, 400)
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/reply/draft":
            # AI-generate a draft reply for a Reddit inbox message.
            try:
                data     = json.loads(body) if body else {}
                reply_id = data.get("id", "")
                from state_manager import load_state, save_state
                from reddit_signal import generate_reddit_reply
                state = load_state()
                entry = next((r for r in state.get("reddit_reply_queue", [])
                              if r["id"] == reply_id), None)
                if not entry:
                    self._json_response({"ok": False, "error": "Reply not found"}, 404)
                    return
                draft = generate_reddit_reply(entry, state)
                entry["ai_draft"] = draft
                save_state(state)
                self._json_response({"ok": True, "draft": draft})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/settings":
            # Save Reddit scan settings (subreddits, queries, daily_post_cap).
            try:
                data = json.loads(body) if body else {}
                from state_manager import load_state, save_state
                state = load_state()
                settings = state.setdefault("reddit_settings", {})
                if "subreddits" in data:
                    settings["subreddits"] = [s.strip() for s in data["subreddits"]
                                              if s.strip()]
                if "queries" in data:
                    settings["queries"] = [q.strip() for q in data["queries"]
                                           if q.strip()]
                if "auto_post" in data:
                    settings["auto_post"] = bool(data["auto_post"])
                if "daily_post_cap" in data:
                    cap = int(data["daily_post_cap"])
                    settings["daily_post_cap"] = max(1, min(cap, 20))
                save_state(state)
                self._json_response({"ok": True, "reddit_settings": settings})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/reddit/run-now":
            # Run the full pipeline on demand: scan + draft top signals.
            # Same logic as the 8 AM job but skips the "already ran today" guard.
            try:
                from state_manager import load_state, save_state
                from reddit_signal import scan_signals, generate_reddit_comment, add_reddit_pending_comment
                from datetime import datetime as _dtn, timedelta as _tdelta

                state    = load_state()
                settings = state.get("reddit_settings", {})

                # 1. Scan
                new_signals = scan_signals(state)
                logging.info(f"[run-now] scan added {len(new_signals)} new signals")

                # 2. Pick eligible signals (score >= 8, new, recent)
                state   = load_state()
                signals = state.get("reddit_signals", [])
                cutoff  = (_dtn.utcnow() - _tdelta(days=7)).timestamp()
                eligible = sorted(
                    [s for s in signals
                     if s.get("relevance", 0) >= 8
                     and s.get("status") == "new"
                     and (s.get("created_utc") or 0) >= cutoff],
                    key=lambda s: s.get("relevance", 0), reverse=True,
                )

                daily_cap = int(settings.get("daily_post_cap", 5))
                today_str = _dtn.utcnow().strftime("%Y-%m-%d")
                posted_today = sum(
                    1 for c in state.get("reddit_posted_comments", [])
                    if (c.get("posted_at") or c.get("created_at") or "")[:10] == today_str
                )
                slots_left = max(0, daily_cap - posted_today)
                to_draft   = eligible[:slots_left] if slots_left else eligible[:daily_cap]

                drafted = 0
                for signal in to_draft:
                    try:
                        draft = generate_reddit_comment(signal, state)
                        if draft and draft.strip():
                            add_reddit_pending_comment(state, signal, draft.strip())
                            drafted += 1
                            state = load_state()
                            time.sleep(1)
                    except Exception as sig_err:
                        logging.warning(f"[run-now] draft failed for signal {signal.get('id')}: {sig_err}")

                msg = (f"Scanned and drafted {drafted} comment{'s' if drafted != 1 else ''}."
                       if drafted else
                       f"Scanned — no new high-score signals to draft right now "
                       f"({len(new_signals)} new signal{'s' if len(new_signals) != 1 else ''} found, none scored 8+).")
                self._json_response({
                    "ok": True,
                    "new_signals": len(new_signals),
                    "drafted": drafted,
                    "message": msg,
                })
            except Exception as e:
                import traceback as _tb
                self._json_response({"ok": False, "error": str(e), "detail": _tb.format_exc()}, 500)
            return

        if path == "/api/dashboard/chat":
            # AI assistant chat: accepts natural-language instructions to change
            # prompt files and config settings. Returns AI reply + applied actions.
            # Body: {"message": str, "history": [{role, content}]}
            try:
                import json as _json, os as _os, re as _re
                from state_manager import load_state, save_state as _save_state_

                data    = _json.loads(body) if body else {}
                message = data.get("message", "").strip()
                history = data.get("history", [])
                if not message:
                    self._json_response({"ok": False, "error": "No message provided"}, 400)
                    return

                # Read all prompt files
                prompt_files = [
                    "first_message.txt", "context.txt", "follow_up.txt",
                    "follow_up_2.txt", "dm_tone.txt", "comment_style.txt",
                ]
                prompts_state = {}
                for fname in prompt_files:
                    fpath = _os.path.join(PROMPTS_DIR, fname)
                    try:
                        with open(fpath) as f:
                            prompts_state[fname] = f.read()
                    except FileNotFoundError:
                        prompts_state[fname] = ""

                # Read config + offering
                config_vars = self._read_config_vars()
                offering = self._read_offering()

                # Build system prompt
                sys_lines = [
                    "You are a helpful AI assistant for Influentia, a LinkedIn+Reddit outreach tool.",
                    "The user can ask you to change how messages sound, update tone, modify prompts, etc.",
                    "",
                    "Current config values:",
                ]
                for k, v in config_vars.items():
                    sys_lines.append(f"- {k} = {v}")
                sys_lines.append(f"- YOUR_OFFERING = {offering[:300] if offering else 'not set'}...")
                sys_lines.append("")
                sys_lines.append("Prompt files you can edit:")
                for fname in prompt_files:
                    content = prompts_state.get(fname, "")
                    sys_lines.append(f"\n--- {fname} ---")
                    sys_lines.append(content[:400] if content else "(empty)")
                sys_lines.append("""

You can take these actions when the user asks:
1. Update a prompt file: {"type": "update_prompt", "file": "filename.txt", "new_content": "full new content"}
2. Update a config var:     {"type": "update_config", "key": "YOUR_NAME", "value": "new value"}
3. Just chat:               send no actions, only a text reply

Rules:
- Be helpful, concise, friendly. You are assisting a business user.
- When updating prompts, make minimal targeted edits to fulfil the request.
  Do not rewrite the whole prompt unless the user asks for that.
- Always explain what you changed and why in 'reply'.
- Return a JSON object with:
  - "reply": your conversational response (string)
  - "actions": array of action objects (can be empty)

Return ONLY valid JSON. No markdown fences. No other text.""")
                system_prompt = "\n".join(sys_lines)

                # Build messages from history + new message
                messages = [{"role": h["role"], "content": h["content"]} for h in history]
                messages.append({"role": "user", "content": message})

                result = _proxy_ai(
                    messages=messages,
                    system=system_prompt,
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2000,
                )

                raw = result.strip()
                raw = _re.sub(r"^```(?:json)?\s*", "", raw)
                raw = _re.sub(r"\s*```$", "", raw)
                parsed = _json.loads(raw)

                reply_text = parsed.get("reply", "")
                actions = parsed.get("actions", [])

                # Apply actions
                applied_actions = []
                for action in actions:
                    action_type = action.get("type", "")
                    if action_type == "update_prompt":
                        fname = action.get("file", "")
                        new_content = action.get("new_content", "")
                        if fname in prompt_files and new_content:
                            fpath = _os.path.join(PROMPTS_DIR, fname)
                            with open(fpath, "w") as f:
                                f.write(new_content)
                            applied_actions.append({
                                "type": "update_prompt",
                                "file": fname,
                                "summary": f"Updated {fname}",
                            })
                    elif action_type == "update_config":
                        key = action.get("key", "")
                        value = action.get("value", "")
                        if key in self._CONFIG_VARS:
                            self._save_config_vars({key: value})
                            try:
                                import importlib, config as _cfg
                                importlib.reload(_cfg)
                            except Exception:
                                pass
                            applied_actions.append({
                                "type": "update_config",
                                "key": key,
                                "summary": f"Updated {key} to {value}",
                            })

                # Update in-memory conversation history
                global _chat_history
                _chat_history.append({"role": "user", "content": message})
                _chat_history.append({"role": "assistant", "content": reply_text})
                if len(_chat_history) > 40:
                    _chat_history = _chat_history[-40:]

                self._json_response({
                    "ok": True,
                    "reply": reply_text,
                    "actions": applied_actions,
                    "history": _chat_history,
                })
            except _json.JSONDecodeError:
                self._json_response({"ok": False, "error": "AI response was not valid JSON"}, 500)
            except Exception as e:
                import traceback as _tb
                self._json_response({"ok": False, "error": str(e), "detail": _tb.format_exc()}, 500)
            return

        if path == "/api/state/import":
            try:
                data = json.loads(body)
                if not isinstance(data, dict):
                    self._json_response({"error": "Invalid format — expected JSON object"}, 400)
                    return
                # Validate minimum structure
                if "leads" not in data and "campaigns" not in data:
                    self._json_response({"error": "Invalid backup — no leads or campaigns found"}, 400)
                    return
                from state_manager import save_state
                # Merge with existing state rather than full replace to preserve settings
                from state_manager import load_state
                current = load_state()
                # Restore leads
                if "leads" in data:
                    current["leads"] = data["leads"]
                if "campaigns" in data:
                    current["campaigns"] = data["campaigns"]
                if "reddit_signals" in data:
                    current["reddit_signals"] = data["reddit_signals"]
                if "pending_comments" in data:
                    current["pending_comments"] = data["pending_comments"]
                if "posted_comments" in data:
                    current["posted_comments"] = data["posted_comments"]
                if "pending_replies" in data:
                    current["pending_replies"] = data["pending_replies"]
                if "reddit_pending_comments" in data:
                    current["reddit_pending_comments"] = data["reddit_pending_comments"]
                if "reddit_posted_comments" in data:
                    current["reddit_posted_comments"] = data["reddit_posted_comments"]
                if "reddit_reply_queue" in data:
                    current["reddit_reply_queue"] = data["reddit_reply_queue"]
                if "reddit_settings" in data:
                    current["reddit_settings"] = data["reddit_settings"]
                save_state(current)
                lead_count = len(current.get("leads", {}))
                self._json_response({"ok": True, "message": f"Restored {lead_count} leads"})
            except json.JSONDecodeError:
                self._json_response({"error": "Invalid JSON"}, 400)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        self._json_response({"error": "Not found"}, 404)

    # ── Config read / write helpers (now backed by .env, not config.py) ──────

    _CONFIG_VARS = [
        "YOUR_NAME", "YOUR_COMPANY", "YOUR_GOAL", "YOUR_GOAL_LINK", "YOUR_WEBSITE",
    ]

    def _parse_env_file(self, path=ENV_FILE):
        """Return {key: value} from a .env-style file. Missing file returns {}."""
        result = {}
        if not os.path.exists(path):
            return result
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    result[key] = value
        except Exception:
            pass
        return result

    def _read_config_vars(self):
        """Read user-facing config variables from .env (with safe fallbacks)."""
        env = self._parse_env_file()
        return {var: env.get(var, "") for var in self._CONFIG_VARS}

    def _save_config_vars(self, updates: dict):
        """
        Update user-facing config variables in .env. Values are written as
        KEY=value with no quoting. If .env does not exist yet, it is created
        from .env.example (or a minimal template).
        """
        if not os.path.exists(ENV_FILE):
            # Bootstrap from example if we can, otherwise start empty
            if os.path.exists(ENV_EXAMPLE):
                try:
                    with open(ENV_EXAMPLE, "r", encoding="utf-8") as src, \
                         open(ENV_FILE, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
                except Exception:
                    open(ENV_FILE, "w").close()
            else:
                open(ENV_FILE, "w").close()

        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        def _format_line(key, value):
            safe = str(value).replace("\n", " ").replace("\r", " ")
            return f"{key}={safe}\n"

        remaining = dict(updates)
        new_lines = []
        for raw in lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                new_lines.append(raw)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in remaining and key in self._CONFIG_VARS:
                new_lines.append(_format_line(key, remaining.pop(key)))
            else:
                new_lines.append(raw)

        # Any keys not yet present get appended
        if remaining:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            for key, val in remaining.items():
                if key in self._CONFIG_VARS:
                    new_lines.append(_format_line(key, val))

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Also update the live os.environ so in-process imports see new values
        for key, val in updates.items():
            if key in self._CONFIG_VARS and val is not None:
                os.environ[key] = str(val)

    def _read_offering(self):
        """Read YOUR_OFFERING from config.py."""
        try:
            with open(CONFIG_FILE, "r") as f:
                content = f.read()
            import re
            match = re.search(r'YOUR_OFFERING\s*=\s*"""(.*?)"""', content, re.DOTALL)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return ""

    def _save_offering(self, new_offering):
        """Update YOUR_OFFERING in config.py."""
        with open(CONFIG_FILE, "r") as f:
            content = f.read()
        import re
        new_block = f'YOUR_OFFERING = """\n{new_offering}\n"""'
        content = re.sub(r'YOUR_OFFERING\s*=\s*""".*?"""', new_block, content, flags=re.DOTALL)
        with open(CONFIG_FILE, "w") as f:
            f.write(content)

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE_PATH):
                with open(STATE_FILE_PATH, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"leads": {}}

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Suppress default access logs to keep terminal clean
        pass


# ── Scheduled runs ────────────────────────────────────────────────────────────
# Full morning routine: every step
_MORNING_STEPS = [
    "find_leads", "withdraw", "scan_posts",
    "connect", "check", "sync_connections",
    "send", "reply", "followup",
]
# Mid-day & evening: just detect acceptances + send DMs + reply
_CHECKUP_STEPS = ["check", "sync_connections", "send", "reply"]
# Checkup + post any approved comments queued since morning
_CHECKUP_WITH_COMMENTS = ["check", "sync_connections", "send", "reply", "post_comments"]

# (hour, steps) — runs once per day at each hour within a 30-min window
# Steps can be string command names (LinkedIn-side) or Python callables (Reddit-side).
_SCHEDULE = [
    (8,  ["_reddit_daily_draft_marker"]),  # 8 AM  — Reddit scan + auto-draft (gated by setting)
    (9,  _MORNING_STEPS),                  # 9 AM  — full LinkedIn routine (includes scan_posts)
    (10, ["post_comments"]),               # 10 AM — post first batch of approved comments (max 2)
    (13, _CHECKUP_WITH_COMMENTS),          # 1 PM  — post next batch + catch lunchtime acceptances
    (18, _CHECKUP_WITH_COMMENTS),          # 6 PM  — post final batch + catch end-of-day acceptances
]
# Marker is replaced with the live callable below so the schedule list stays
# JSON-serialisable for any UI that reads it.
_WINDOW_MINS = 30   # fire if we're within 30 min past the hour

# Tracks which (date, hour) slots have already fired  e.g. {"2026-04-02_9", ...}
_fired_slots: set = set()


def _load_fired_slots() -> set:
    """Load persisted fired-slot keys from disk (survives restarts)."""
    try:
        if os.path.exists(SCHEDULER_FIRED_FILE):
            with open(SCHEDULER_FIRED_FILE, "r") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        pass
    return set()


def _save_fired_slots(slots: set) -> None:
    """Persist fired-slot keys so we don't re-fire after a restart."""
    try:
        # Only keep slots from the last 2 days to avoid the file growing forever
        today = datetime.now().strftime("%Y-%m-%d")
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        pruned = {s for s in slots if s.startswith(today) or s.startswith(yesterday)}
        with open(SCHEDULER_FIRED_FILE, "w") as f:
            json.dump(sorted(pruned), f)
    except Exception:
        pass


def _reddit_daily_draft():
    """
    Daily Reddit job: scan + auto-draft (or auto-post) on top-scoring signals.

    Gated by state['reddit_settings']['daily_auto_draft'] (default: off).
    Drafts up to 3 replies per day on signals with relevance >= 8 that
    don't already have a draft.

    If state['reddit_settings']['daily_auto_post'] is also on, the
    drafted comments are posted automatically (no manual approval step).

    NOTE: Posting runs in a SEPARATE subprocess using the browser-based
    Playwright client. This avoids asyncio conflicts between Playwright's
    synchronous API and the server's event loop.
    """
    try:
        from state_manager import load_state, save_state
        from reddit_signal import (
            scan_signals,
            generate_reddit_comment,
            add_reddit_pending_comment,
        )
        state = load_state()

        # Guard: only run once per calendar day, even across restarts
        from datetime import timezone as _tz, datetime as _dt
        today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
        if state.get("_reddit_draft_last_date") == today:
            logging.info("⏰ [reddit_daily_draft] already ran today — skipping")
            return

        settings = state.get("reddit_settings", {})
        if not settings.get("daily_auto_draft"):
            logging.info("⏰ [reddit_daily_draft] skipped — toggle off in Reddit settings")
            return

        auto_post = settings.get("daily_auto_post", False)
        if auto_post:
            logging.info("⏰ [reddit_daily_draft] auto-post is ON — comments will post without review")

        # 1. Run a fresh scan against the active ICP preset.
        new_signals = scan_signals(state)
        logging.info(f"⏰ [reddit_daily_draft] scan added {len(new_signals)} new signals")

        # 2. Refresh state after scan, then pick top eligible signals.
        state   = load_state()
        signals = state.get("reddit_signals", [])
        # Eligible: score >= 8, status == 'new' (not yet drafted/commented/dismissed),
        # and posted within the last 7 days (don't draft on stale leads).
        from datetime import datetime as _dt, timedelta as _td
        cutoff_ts = (_dt.utcnow() - _td(days=7)).timestamp()
        eligible  = [
            s for s in signals
            if s.get("relevance", 0) >= 8
            and s.get("status") == "new"
            and (s.get("created_utc") or 0) >= cutoff_ts
        ]
        eligible.sort(key=lambda s: s.get("relevance", 0), reverse=True)

        REDDIT_DAILY_CAP = int(settings.get("daily_post_cap", 5))

        # Count Reddit comments already posted today (manual or auto)
        from datetime import datetime as _dtt
        _today_str = _dtt.utcnow().strftime("%Y-%m-%d")
        posted_today = sum(
            1 for c in state.get("reddit_posted_comments", [])
            if (c.get("posted_at") or c.get("created_at") or "")[:10] == _today_str
        )
        if posted_today >= REDDIT_DAILY_CAP:
            logging.info(f"⏰ [reddit_daily_draft] already posted {posted_today} Reddit comments today — skipping auto-post")
            auto_post = False

        drafted = 0
        posted  = 0

        for signal in eligible[:REDDIT_DAILY_CAP]:    # cap drafts at daily limit
            try:
                draft = generate_reddit_comment(signal, state)
                if not draft or not draft.strip():
                    continue

                entry = add_reddit_pending_comment(state, signal, draft.strip())
                drafted += 1
                state = load_state()
                time.sleep(2)

                # Auto-post via subprocess (avoids Playwright asyncio conflict)
                if auto_post and entry and (posted_today + posted) < REDDIT_DAILY_CAP:
                    post_fullname = signal.get("post_fullname", "")
                    if post_fullname:
                        try:
                            _run_reddit_post_subprocess(entry.get("id", ""), post_fullname, draft.strip())
                            posted += 1
                            logging.info(f"⏰ [reddit_daily_draft] auto-posted on {post_fullname}")
                        except Exception as post_err:
                            logging.warning(f"⏰ [reddit_daily_draft] auto-post failed: {post_err}")
                            time.sleep(30)

            except Exception as e:
                logging.warning(f"⏰ [reddit_daily_draft] draft failed for {signal.get('id')}: {e}")

        logging.info(f"⏰ [reddit_daily_draft] queued {drafted} draft(s), auto-posted {posted}")
        # Mark today as done so restarts/multiple triggers don't re-run
        state = load_state()
        state["_reddit_draft_last_date"] = _dt.utcnow().strftime("%Y-%m-%d")
        save_state(state)
    except Exception as e:
        logging.error(f"⏰ [reddit_daily_draft] crashed: {e}")


def _reddit_auto_reply():
    """
    Auto-reply to Reddit inbox replies on our posted comments.
    Called from _reddit_continuous_scanner() after each scan cycle.
    Gated by state['reddit_settings']['auto_reply_replies'] (default off).
    Respects auto_reply_daily_cap (default 3/day).
    """
    try:
        from state_manager import load_state, save_state
        from reddit_signal import check_reddit_replies, generate_reddit_reply
        from reddit_client import RedditClient
        import time as _time
        from datetime import datetime as _dts
        state = load_state()
        rs = state.get("reddit_settings", {})
        if not rs.get("auto_reply_replies"):
            return

        # Fetch new inbox replies
        check_reddit_replies(state)
        state = load_state()

        reddit_username = os.environ.get("REDDIT_USERNAME", "").strip().lower()
        today_str = _dts.utcnow().strftime("%Y-%m-%d")
        daily_cap = int(rs.get("auto_reply_daily_cap", 3))

        # Count today's already-replied entries
        queue = state.get("reddit_reply_queue", [])
        replied_today = sum(
            1 for r in queue
            if r.get("status") == "replied"
            and (r.get("replied_at") or "")[:10] == today_str
        )

        pending = [r for r in queue if r.get("status") == "pending"]
        if not pending:
            return

        posted = 0
        for reply in pending:
            if posted >= daily_cap or (replied_today + posted) >= daily_cap:
                break

            # Safety: skip very short replies (likely "thanks", "cool")
            if len(reply.get("body", "").strip()) < 20:
                reply["status"] = "dismissed"
                reply["dismiss_reason"] = "too_short"
                save_state(state)
                state = load_state()
                logging.info(f"🔄 [auto-reply] skipped short reply from {reply.get('author')}")
                continue

            # Safety: don't reply to our own comments
            if reply.get("author", "").lower() == reddit_username:
                reply["status"] = "dismissed"
                reply["dismiss_reason"] = "self_reply"
                save_state(state)
                state = load_state()
                continue

            try:
                draft = generate_reddit_reply(reply, state)
                if not draft or not draft.strip():
                    reply["status"] = "dismissed"
                    reply["dismiss_reason"] = "empty_draft"
                    save_state(state)
                    state = load_state()
                    continue

                client = RedditClient()
                client.reply_to_comment(reply.get("reply_id", ""), draft)
                client.close()

                reply["status"] = "replied"
                reply["replied_at"] = _dts.utcnow().isoformat()
                reply["ai_draft"] = draft
                save_state(state)
                state = load_state()
                posted += 1
                logging.info(f"🔄 [auto-reply] replied to {reply.get('author')}")
                _time.sleep(5)

            except Exception as e:
                logging.warning(f"🔄 [auto-reply] failed for {reply.get('author')}: {e}")
                _time.sleep(10)

        if posted:
            logging.info(f"🔄 [auto-reply] cycle done — {posted} auto-replied")

    except Exception as e:
        logging.error(f"🔄 [auto-reply] crashed: {e}")


_continuous_scan_thread = None
_continuous_scan_stop   = threading.Event()

def _reddit_continuous_scanner():
    """
    Background thread: scans Reddit every N minutes (default 30).
    Gated by state['reddit_settings']['auto_scan_enabled'].

    On each scan:
      - Finds new signals as usual
      - "Hot right now" signals (< 2h old, score >= 8): drafted + auto-posted
        immediately if daily_auto_post is on and cap not reached
      - Respects daily_post_cap at all times
      - Records next_scan_at in state so the dashboard can show a countdown
    """
    import time as _time
    from datetime import datetime as _dts, timedelta as _tdd, timezone as _tzs
    logging.info("🔄 [auto-scan] Continuous scanner thread started")

    while not _continuous_scan_stop.is_set():
        try:
            from state_manager import load_state, save_state
            state    = load_state()
            settings = state.get("reddit_settings", {})

            if not settings.get("auto_scan_enabled"):
                # Setting was turned off — clear next_scan_at and exit thread
                state.pop("_next_auto_scan_at", None)
                save_state(state)
                logging.info("🔄 [auto-scan] disabled — thread exiting")
                return

            interval_mins = int(settings.get("auto_scan_interval_mins", 30))
            last_at_str   = state.get("_last_auto_scan_at", "")

            # Check if enough time has passed since last scan
            now_utc = _dts.now(_tzs.utc).replace(tzinfo=None)
            if last_at_str:
                try:
                    last_at = _dts.fromisoformat(last_at_str)
                    if (now_utc - last_at).total_seconds() < interval_mins * 60:
                        # Update next_scan_at for dashboard countdown
                        next_at = last_at + _tdd(minutes=interval_mins)
                        state["_next_auto_scan_at"] = next_at.isoformat()
                        save_state(state)
                        _continuous_scan_stop.wait(30)   # sleep 30s then re-check
                        continue
                except Exception:
                    pass

            logging.info(f"🔄 [auto-scan] Starting scan (interval: {interval_mins}m)")
            state["_last_auto_scan_at"] = now_utc.isoformat()
            state["_next_auto_scan_at"] = (now_utc + _tdd(minutes=interval_mins)).isoformat()
            save_state(state)

            from reddit_signal import scan_signals, generate_reddit_comment, add_reddit_pending_comment
            new_signals = scan_signals(state)
            logging.info(f"🔄 [auto-scan] scan added {len(new_signals)} new signals")

            state    = load_state()
            settings = state.get("reddit_settings", {})
            auto_post = settings.get("daily_auto_post", False)
            daily_cap = int(settings.get("daily_post_cap", 5))

            today_str = _dts.utcnow().strftime("%Y-%m-%d")
            posted_today = sum(
                1 for c in state.get("reddit_posted_comments", [])
                if (c.get("posted_at") or c.get("created_at") or "")[:10] == today_str
            )

            if posted_today >= daily_cap:
                logging.info(f"🔄 [auto-scan] daily cap reached ({posted_today}/{daily_cap}) — no auto-posts this cycle")
                _continuous_scan_stop.wait(60)
                continue

            # Eligible: score >= 8, still new, not already drafted/posted,
            # and posted within the last 7 days (avoid stale threads).
            stale_cutoff = (_dts.utcnow() - _tdd(days=7)).timestamp()
            pending_ids = {c.get("post_id") for c in state.get("reddit_pending_comments", [])}
            posted_ids  = {c.get("post_id") for c in state.get("reddit_posted_comments", [])}
            skip_ids    = pending_ids | posted_ids
            eligible_signals = [
                s for s in state.get("reddit_signals", [])
                if s.get("relevance", 0) >= 8
                and s.get("status") == "new"
                and (s.get("created_utc") or 0) >= stale_cutoff
                and s.get("post_id") not in skip_ids
            ]
            eligible_signals.sort(key=lambda s: s.get("relevance", 0), reverse=True)

            slots = daily_cap - posted_today
            posted = 0
            for signal in eligible_signals[:slots]:
                try:
                    draft = generate_reddit_comment(signal, state)
                    if not draft or not draft.strip():
                        continue
                    entry = add_reddit_pending_comment(state, signal, draft.strip())
                    state = load_state()
                    if auto_post and entry:
                        pf = signal.get("post_fullname", "")
                        if pf:
                            try:
                                _run_reddit_post_subprocess(entry.get("id", ""), pf, draft.strip())
                                posted += 1
                                logging.info(f"🔄 [auto-scan] posted on {pf} (score {signal.get('relevance')})")
                                _time.sleep(90)   # space posts ~90s apart
                            except Exception as pe:
                                logging.warning(f"🔄 [auto-scan] post failed: {pe}")
                except Exception as se:
                    logging.warning(f"🔄 [auto-scan] draft failed: {se}")

            logging.info(f"🔄 [auto-scan] cycle done — {posted} auto-posted")

            # ── Auto-reply to Reddit inbox replies ──────────────────────────
            try:
                _reddit_auto_reply()
            except Exception as auto_reply_err:
                logging.error(f"🔄 [auto-scan] auto-reply failed: {auto_reply_err}")

        except Exception as e:
            logging.error(f"🔄 [auto-scan] crashed: {e}")

        _continuous_scan_stop.wait(30)   # check every 30s whether interval has elapsed


def _start_continuous_scanner():
    """Start (or restart) the continuous scanner thread if enabled in state."""
    global _continuous_scan_thread, _continuous_scan_stop
    from state_manager import load_state
    try:
        state = load_state()
        if not state.get("reddit_settings", {}).get("auto_scan_enabled"):
            return
    except Exception:
        return
    if _continuous_scan_thread and _continuous_scan_thread.is_alive():
        return
    _continuous_scan_stop.clear()
    _continuous_scan_thread = threading.Thread(target=_reddit_continuous_scanner, daemon=True)
    _continuous_scan_thread.start()
    logging.info("🔄 [auto-scan] thread launched")


def _run_reddit_post_subprocess(entry_id: str, post_fullname: str, text: str):
    """Post a single Reddit comment in a separate subprocess to avoid Playwright
    asyncio conflicts with the server's event loop."""
    import subprocess
    import json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(script_dir, "post_single_comment.py")

    # Write job to a temp file so the subprocess can pick it up
    job = {"entry_id": entry_id, "post_fullname": post_fullname, "text": text}
    job_file = os.path.join(script_dir, ".reddit_pending_job.json")
    with open(job_file, "w") as f:
        json.dump(job, f)

    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, timeout=300, cwd=script_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:2000])
    logging.info(f"⏰ [subprocess] comment posted: {result.stdout.strip()}")


def _run_steps(steps: list, label: str):
    """Run a sequence of command steps, waiting for each to finish.
    A step can be either:
      - a string main.py command name (LinkedIn-side jobs), or
      - a Python callable (Reddit-side jobs that don't shell out to main.py)
    """
    logging.info(f"⏰ Scheduler [{label}]: starting — {steps}")
    for step in steps:
        # ── Direct Python callable path ──────────────────────────────────
        if callable(step):
            try:
                step()
            except Exception as e:
                logging.warning(f"⏰ [{label}] callable {step.__name__} failed: {e}")
            continue

        # ── main.py command path (existing) ─────────────────────────────
        for _ in range(24):   # wait up to 2 min for any prior task
            with _task_lock:
                busy = _current_task and _current_task.get("running")
            if not busy:
                break
            time.sleep(5)

        ok, msg = _run_command(step)
        if ok:
            logging.info(f"⏰ [{label}] started '{step}'")
            time.sleep(10)
            for _ in range(360):   # wait up to 30 min for this step
                with _task_lock:
                    busy = _current_task and _current_task.get("running")
                if not busy:
                    break
                time.sleep(5)
        else:
            logging.warning(f"⏰ [{label}] could not start '{step}': {msg}")
            time.sleep(15)
    logging.info(f"⏰ Scheduler [{label}]: done.")


def _get_missed_slots(today: str, current_hour: int, fired: set) -> list:
    """
    Return any scheduled slots from today that should have run by now
    but haven't fired yet — in chronological order.
    Only slots whose scheduled hour is strictly in the past are caught up
    (we don't catch up slots scheduled for the current or future hour,
    those fire normally within their window).
    """
    missed = []
    for hour, steps in _SCHEDULE:
        slot_key = f"{today}_{hour}"
        if hour < current_hour and slot_key not in fired:
            missed.append((hour, steps, slot_key))
    return missed


def _daily_scheduler():
    """
    Background thread: fires scheduled runs automatically.
    9 AM  → full routine (find leads, connect, check, sync, send, reply, followup)
    10 AM → post approved Engage comments
    1 PM  → quick check (check, sync, send, reply)
    6 PM  → quick check (check, sync, send, reply)

    Catch-up logic: if the Mac was asleep or the server was off during a
    scheduled slot, the missed run fires automatically when the server starts
    or the Mac wakes up. Only one catch-up runs at a time (most recent missed
    slot first, to avoid overwhelming LinkedIn with back-to-back runs).
    """
    global _fired_slots

    # Restore fired slots from disk — safe across app restarts
    _fired_slots = _load_fired_slots()

    _last_wake_check = datetime.now()   # track clock jumps (= wake from sleep)

    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            minute_of_day = now.hour * 60 + now.minute

            # ── Detect wake from sleep ───────────────────────────────────────
            # If more than 2 minutes passed between ticks, the Mac was probably
            # sleeping. Treat this the same as a fresh startup.
            elapsed_since_last = (now - _last_wake_check).total_seconds()
            just_woke = elapsed_since_last > 120
            _last_wake_check = now

            if just_woke:
                logging.info(f"⏰ Wake-from-sleep detected ({elapsed_since_last/60:.0f} min gap) — checking for missed slots")

            # ── Catch up any missed slots from today ─────────────────────────
            missed = _get_missed_slots(today, now.hour, _fired_slots)
            if missed:
                # Run the most-recently-missed slot (last in chronological list)
                # so the day's state is as current as possible.
                hour, steps, slot_key = missed[-1]
                _fired_slots.add(slot_key)
                _save_fired_slots(_fired_slots)
                label = f"{hour:02d}:00 (catch-up)"
                logging.info(f"⏰ Catching up missed slot: {label}")
                threading.Thread(
                    target=_run_steps, args=(steps, label), daemon=True
                ).start()
                # Don't process anything else this tick — let it finish first
                time.sleep(60)
                continue

            # ── Normal real-time window check ────────────────────────────────
            for hour, steps in _SCHEDULE:
                slot_key = f"{today}_{hour}"
                slot_start = hour * 60
                in_window = slot_start <= minute_of_day <= slot_start + _WINDOW_MINS

                if in_window and slot_key not in _fired_slots:
                    _fired_slots.add(slot_key)
                    _save_fired_slots(_fired_slots)
                    label = f"{hour:02d}:00"
                    threading.Thread(
                        target=_run_steps, args=(steps, label), daemon=True
                    ).start()
                    break   # only start one slot per tick

        except Exception as e:
            logging.warning(f"Scheduler error: {e}")

        time.sleep(60)   # check once per minute


def _print_startup_banner():
    """Print a friendly startup banner with config health info."""
    try:
        import config as _cfg
        problems = _cfg.validate_config(strict=False)
    except Exception as e:
        problems = [f"Could not import config.py: {e}"]

    health = "✓  Config looks good" if not problems else f"⚠  {len(problems)} setup issue(s)"

    banner = f"""
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║   ✦  Influentia                                       ║
║   Running at: http://localhost:{PORT}                  ║
║                                                       ║
║   Open the URL above in your browser.                 ║
║   Press Ctrl+C to stop.                               ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
  {health}
"""
    print(banner)

    if problems:
        print("  First-time setup needed. Open the dashboard and")
        print("  the onboarding wizard will walk you through it:")
        for p in problems[:6]:
            print(f"    • {p}")
        print()


def main():
    # First, make sure state exists
    if not os.path.exists(STATE_FILE_PATH):
        # Run a quick status to initialize state
        original_argv = sys.argv[:]
        sys.argv = ["main.py", "status"]
        try:
            import main as main_module
            main_module.cmd_status()
        except Exception:
            pass
        sys.argv = original_argv

    # If .env is missing but .env.example exists, bootstrap a copy so the
    # user has a file to edit from the onboarding wizard (no keys filled in).
    if not os.path.exists(ENV_FILE) and os.path.exists(ENV_EXAMPLE):
        try:
            with open(ENV_EXAMPLE, "r", encoding="utf-8") as src, \
                 open(ENV_FILE, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            print("[setup] Created .env from .env.example — fill in your keys in the dashboard.")
        except Exception as e:
            print(f"[setup] Could not create .env: {e}", file=sys.stderr)

    # Resolve scheduler markers → live callables (kept marker-string in
    # _SCHEDULE so any introspection that JSON-serialises it stays clean).
    for i, (hour, steps) in enumerate(list(_SCHEDULE)):
        new_steps = [_reddit_daily_draft if s == "_reddit_daily_draft_marker" else s for s in steps]
        _SCHEDULE[i] = (hour, new_steps)

    # Start the daily 9 AM scheduler in the background
    scheduler_thread = threading.Thread(target=_daily_scheduler, daemon=True)
    scheduler_thread.start()

    # Start continuous Reddit scanner if it was enabled before this restart
    _start_continuous_scanner()

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("localhost", PORT), DashboardHandler)
    _print_startup_banner()

    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
