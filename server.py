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

PORT = 5555
LOG_FILE = "outreach_log.txt"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_FILE = os.path.join(BASE_DIR, ".stop_signal")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.py")
ENV_FILE    = os.path.join(BASE_DIR, ".env")
ENV_EXAMPLE = os.path.join(BASE_DIR, ".env.example")
KB_FILE    = os.path.join(BASE_DIR, "knowledge_base.json")
SWIPE_FILE = os.path.join(BASE_DIR, "swipe_file.json")
QUEUE_FILE = os.path.join(BASE_DIR, "post_queue.json")

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

    return ("error", f"Task failed: {msg}", "retry")


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


# ── License / billing ─────────────────────────────────────────────────────────
# Outreach Pilot uses a hosted license backend (Cloudflare Worker + D1 + Stripe).
# The local app stores a cached copy of the license state in .license.json and
# revalidates with the worker every 12h. If the license is missing, expired, or
# the trial has run out, /api/run/* endpoints are blocked with HTTP 402.
LICENSE_FILE        = os.path.join(BASE_DIR, ".license.json")
LICENSE_WORKER_URL  = os.environ.get(
    "LICENSE_WORKER_URL",
    "https://outreach-pilot-api-production.plain-king-ead0.workers.dev",
).rstrip("/")
LICENSE_CACHE_TTL_S = 12 * 60 * 60  # 12 hours
UPGRADE_URL_BASE    = "https://outreachpilot.app/account"


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

    allow_runs = tier in ("trial", "active") and sub_st != "canceled"

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
            if campaign_filter and campaign_filter != "all":
                filtered = {k: v for k, v in state["leads"].items()
                            if v.get("campaign_id") == campaign_filter}
                out = dict(state)
                out["leads"] = filtered
                out["messages_sent_today"] = _sent_today
                out["max_messages_per_day"] = MAX_MESSAGES_PER_DAY
                self._json_response(out)
            else:
                out = dict(state)
                out["messages_sent_today"] = _sent_today
                out["max_messages_per_day"] = MAX_MESSAGES_PER_DAY
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
            from state_manager import load_state, mark_comment, save_state
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

        if path.startswith("/api/run/"):
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
                    "label": "Add your API keys and identity",
                    "detail": "Open Settings → Account. Paste your Claude and Brave Search API keys and set your name, company, goal and booking link. Everything is stored locally in .env.",
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

        if path == "/api/license":
            try:
                self._json_response({"ok": True, **_license_state()})
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)
            return

        # Serve dashboard.html as the root
        if path == "/" or path == "":
            self.path = "/dashboard.html"

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
                subject = f"[Outreach Pilot] Feedback — {sys_info['os'].split('-')[0]}"
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
                    "mailto:feedback@outreachpilot.local"
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
            try:
                data = json.loads(body) if body else {}
                payload = {
                    "complete":  bool(data.get("complete", True)),
                    "dismissed": bool(data.get("dismissed", False)),
                    "finished_at": datetime.now().isoformat(),
                }
                with open(ONBOARD_FILE, "w") as f:
                    json.dump(payload, f, indent=2)
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

# (hour, steps) — runs once per day at each hour within a 30-min window
_SCHEDULE = [
    (9,  _MORNING_STEPS),          # 9 AM  — full daily routine
    (10, ["post_comments"]),        # 10 AM — post any approved Engage comments
    (13, _CHECKUP_STEPS),          # 1 PM  — catch lunchtime acceptances
    (18, _CHECKUP_STEPS),   # 6 PM  — catch end-of-day acceptances
]
_WINDOW_MINS = 30   # fire if we're within 30 min past the hour

# Tracks which (date, hour) slots have already fired  e.g. {"2026-04-02_9", ...}
_fired_slots: set = set()


def _run_steps(steps: list, label: str):
    """Run a sequence of command steps, waiting for each to finish."""
    logging.info(f"⏰ Scheduler [{label}]: starting — {steps}")
    for step in steps:
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


def _daily_scheduler():
    """
    Background thread: fires scheduled runs automatically.
    9 AM  → full routine (find leads, connect, check, sync, send, reply, followup)
    1 PM  → quick check (check, sync, send, reply)
    6 PM  → quick check (check, sync, send, reply)
    Won't double-fire within the same slot.
    """
    global _fired_slots

    # On startup mark today's already-elapsed slots as fired if log has today's activity
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        log_path = os.path.join(BASE_DIR, LOG_FILE)
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                content = f.read()
            now_h = datetime.now().hour
            for hour, _ in _SCHEDULE:
                if hour <= now_h and today_str in content:
                    _fired_slots.add(f"{today_str}_{hour}")
    except Exception:
        pass

    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            minute_of_day = now.hour * 60 + now.minute

            for hour, steps in _SCHEDULE:
                slot_key = f"{today}_{hour}"
                slot_start = hour * 60
                in_window = slot_start <= minute_of_day <= slot_start + _WINDOW_MINS

                if in_window and slot_key not in _fired_slots:
                    _fired_slots.add(slot_key)
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
║   ✦  Outreach Pilot                                   ║
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

    # Start the daily 9 AM scheduler in the background
    scheduler_thread = threading.Thread(target=_daily_scheduler, daemon=True)
    scheduler_thread.start()

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
