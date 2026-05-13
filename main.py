#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# main.py  —  LinkedIn outreach orchestration
#
# Commands:
#   python main.py scan         → Detect already-connected leads (no messages)
#   python main.py connect      → Send connection requests (once/day, max 15)
#   python main.py check        → Detect new acceptances (no messages)
#   python main.py send         → Send first messages to connected leads
#   python main.py reply        → Check inbox and reply to prospects
#   python main.py followup     → Send follow-ups to non-responders (after X days)
#   python main.py add <url>    → Add a new lead by LinkedIn URL
#   python main.py preview      → Preview messages WITHOUT sending (dry run)
#   python main.py status       → Dashboard: lead statuses + active conversations
#   python main.py loop         → Auto-run check + reply + followup every N hours
# ─────────────────────────────────────────────────────────────────────────────
import sys
import time
import json
import logging
from typing import Optional
from datetime import datetime, timedelta

from config import (
    MAX_CONNECTION_REQUESTS_PER_DAY,
    MAX_MESSAGES_PER_DAY,
    POLL_INTERVAL_HOURS,
    FOLLOW_UP_AFTER_DAYS,
    MAX_FOLLOW_UPS,
    LOG_FILE_PATH,
    EXCLUDED_LOCATIONS,
)
from state_manager import (
    load_state, save_state, upsert_lead, set_status, add_message,
    get_conversation, leads_by_status, print_summary,
    add_pending_reply,
    STATUS_PENDING, STATUS_REQUESTED, STATUS_CONNECTED,
    STATUS_MESSAGED, STATUS_REPLIED, STATUS_MEETING, STATUS_DISQUALIFIED,
    STATUS_WITHDRAWN,
)
from leads_loader import sync_leads_to_state
from linkedin_client import LinkedInClient, StopSignal
from message_ai import (
    generate_first_message, generate_reply, generate_follow_up,
    generate_goodbye, classify_conversation_status, validate_message,
)

# ── Do Not Contact list ──────────────────────────────────────────────────────
import os as _os, json as _json
_BLOCKLIST_FILE = _os.path.join(_os.path.dirname(__file__), "blocked_leads.json")

def _load_blocklist() -> set:
    try:
        with open(_BLOCKLIST_FILE) as f:
            return set(_json.load(f))
    except Exception:
        return set()

def _save_blocklist(blocked: set):
    with open(_BLOCKLIST_FILE, "w") as f:
        _json.dump(sorted(blocked), f, indent=2)

def _is_blocked(linkedin_url: str) -> bool:
    return linkedin_url in _load_blocklist()

def block_lead(linkedin_url: str):
    bl = _load_blocklist()
    bl.add(linkedin_url)
    _save_blocklist(bl)


def _is_excluded_location(lead: dict) -> bool:
    """Return True if a lead's location/company text matches any EXCLUDED_LOCATIONS entry."""
    if not EXCLUDED_LOCATIONS:
        return False
    check_fields = " ".join(filter(None, [
        lead.get("location", ""),
        lead.get("country", ""),
        lead.get("title", ""),
        lead.get("company", ""),
        lead.get("headline", ""),
    ])).lower()
    for excl in EXCLUDED_LOCATIONS:
        if excl.lower() in check_fields:
            return True
    # If Netherlands is an excluded location, also detect Dutch-language profiles
    # (many Dutch profiles have no English location string but write in Dutch).
    nl_excluded = any(e.lower() in ("netherlands", "nederland", "dutch", "nl", "holland")
                      for e in EXCLUDED_LOCATIONS)
    if nl_excluded:
        # Common Dutch function words that don't appear in English/French/German
        dutch_markers = [" bij ", " bij\n", "dagvoorzitter", "kerntalenten",
                         "buurtsport", " directeur bij ", " voor ceo", "radio 538",
                         "lurvink", "lichtenvoorde", "meppel", " groep b.v",
                         "mbo ", "hbo ", "hbo-", "van de ", " bij de ", "aanjaag"]
        for marker in dutch_markers:
            if marker in check_fields:
                return True
    return False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

def _get_limit() -> Optional[int]:
    """Parse --limit N from command line args."""
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
    return None


def _count_messages_sent_today(state: dict) -> int:
    """
    Count cold outreach messages sent today.

    Counting rules:
    - msg_type="outreach" or "follow_up" → counts (tool-sent outreach)
    - msg_type="" or None (legacy, no tag) → counts conservatively
    - msg_type="reply"   → excluded (AI reply to engaged prospect)
    - msg_type="manual"  → excluded (user sent manually, not the tool)
    """
    today = datetime.utcnow().date().isoformat()
    count = 0
    for lead in state["leads"].values():
        for msg in lead.get("messages", []):
            if msg.get("role") != "ai":
                continue
            if (msg.get("ts") or "")[:10] != today:
                continue
            mt = msg.get("msg_type", "")
            # Explicitly skip replies and manually-sent messages
            if mt in ("reply", "manual"):
                continue
            count += 1
    return count


def _make_client() -> "LinkedInClient":
    """
    Create a LinkedInClient, converting cookie/session errors into a clean
    log message so the dashboard shows something useful instead of a traceback.
    """
    try:
        return LinkedInClient()
    except RuntimeError as e:
        log.error("=" * 60)
        for line in str(e).splitlines():
            log.error(line)
        log.error("=" * 60)
        raise SystemExit(1)


def _can_send_message(state: dict) -> bool:
    sent_today = _count_messages_sent_today(state)
    if sent_today >= MAX_MESSAGES_PER_DAY:
        log.warning(f"Daily message limit reached ({sent_today}/{MAX_MESSAGES_PER_DAY}). Stopping.")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION NOTE — short personalised note to improve accept rate
# ─────────────────────────────────────────────────────────────────────────────
_NOTE_CACHE: dict = {}   # url → note, so we only generate once per lead

def _generate_connection_note(lead: dict, posts: list = None) -> str:
    """
    Generate a short, warm connection note (≤280 chars) using the AI proxy.
    If recent posts are provided, the note opens with a specific hook from them.
    Falls back to empty string on any error so the connect step never blocks.
    """
    url = lead.get("linkedin_url", "")
    if url in _NOTE_CACHE:
        return _NOTE_CACHE[url]

    name    = (lead.get("name") or "").strip().split()[0] or "there"   # first name only
    title   = (lead.get("title") or lead.get("headline") or "").strip()
    company = (lead.get("company") or "").strip()

    context_parts = []
    if title:
        context_parts.append(f"their title is: {title}")
    if company:
        context_parts.append(f"they work at: {company}")
    context_str = " | ".join(context_parts) if context_parts else "no extra details available"

    # Build activity context from recent posts — the most powerful hook source
    activity_block = ""
    if posts:
        snippets = []
        for p in (posts or [])[:2]:
            text = (p.get("commentary", {}) or {}).get("text", "")
            if isinstance(text, dict):
                text = text.get("text", "")
            if isinstance(text, str) and text.strip():
                snippets.append(text.strip()[:220])
        if snippets:
            activity_block = "\n\nTheir recent LinkedIn posts:\n" + "\n---\n".join(snippets)

    hook_instruction = (
        "If one of their posts touches a specific topic, observation, or decision "
        "that is genuinely interesting, open with a brief real reaction to it — "
        "not a compliment, just an honest observation from someone who actually read it. "
        "Otherwise use a specific detail from their title or company as the hook."
        if activity_block else
        "Use a specific detail from their title or company as the hook."
    )

    prompt = (
        f"Write a LinkedIn connection note from Ermo (founder, Authentik Studio — brand video for B2B founders). "
        f"Recipient first name: {name}. Profile context: {context_str}.{activity_block}\n\n"
        f"{hook_instruction} "
        f"Rules: Max 280 characters (STRICT). No pitch, no ask. Sound like a real person. "
        f"One sentence. Do NOT start with 'Hi', 'Hey', or any salutation. "
        f"No em dashes. No exclamation marks. No emojis. "
        f"Reply with ONLY the note text."
    )

    try:
        from ai_proxy import call_ai as _call_ai
        result = _call_ai(
            messages=[{"role": "user", "content": prompt}],
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
        )
        note = (result or "").strip()
        # Hard-truncate just in case
        if len(note) > 280:
            note = note[:277] + "..."
        _NOTE_CACHE[url] = note
        return note
    except Exception as e:
        log.warning(f"Could not generate connection note for {name}: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# SCAN — Detect which leads are already connected (does NOT send messages)
# ─────────────────────────────────────────────────────────────────────────────
def cmd_scan():
    import time as _time
    from linkedin_client import _check_stop
    limit = _get_limit()
    state  = sync_leads_to_state()
    client = _make_client()

    # Hard wall: abort gracefully after 8 minutes so the server never auto-resets us
    _SCAN_TIMEOUT_SECONDS = 480  # 8 min
    _scan_start = _time.monotonic()

    def _scan_timed_out() -> bool:
        elapsed = _time.monotonic() - _scan_start
        if elapsed > _SCAN_TIMEOUT_SECONDS:
            log.warning(
                f"Scan timeout reached ({elapsed:.0f}s) — stopping early to stay "
                f"responsive. Run Scan again to continue checking remaining leads."
            )
            return True
        return False

    try:
        to_check = [
            r for r in state["leads"].values()
            if r["status"] in {STATUS_PENDING, STATUS_REQUESTED}
        ]
        if limit:
            to_check = to_check[:limit]
            log.info(f"Limit set to {limit} leads.")

        log.info(f"Scanning {len(to_check)} leads for existing connections…")
        already_connected = []

        _check_stop()  # bail immediately if user already clicked Stop

        # Step 1: Try bulk check via connections page (single page load)
        my_connections = client.get_my_connections(limit=500)
        if my_connections:
            log.info(f"Bulk-checking against {len(my_connections)} of your connections…")
            remaining = []
            for lead in to_check:
                url = lead["linkedin_url"]
                public_id = client._extract_public_id(url)
                if public_id and public_id in my_connections:
                    log.info(f"  ✓ {lead['name']} ({lead['company']}) — connected")
                    set_status(state, url, STATUS_CONNECTED, note="Already connected (scan)")
                    already_connected.append(lead)
                else:
                    remaining.append(lead)
            to_check = remaining
            log.info(f"Bulk check found {len(already_connected)} connected, {len(remaining)} still to check individually.")
        else:
            log.info("Bulk connection fetch returned nothing — will check leads individually.")

        # Step 2: Check remaining leads individually (cap at 15 per run to avoid timeout)
        # Any unchecked leads will be picked up next time Scan runs.
        MAX_INDIVIDUAL_CHECKS = 15
        if len(to_check) > MAX_INDIVIDUAL_CHECKS:
            log.info(
                f"Capping individual checks at {MAX_INDIVIDUAL_CHECKS} this run "
                f"({len(to_check)} remaining — rest will be checked next Scan)."
            )
            to_check = to_check[:MAX_INDIVIDUAL_CHECKS]

        if to_check:
            log.info(f"Checking {len(to_check)} remaining leads individually…")
            for lead in to_check:
                _check_stop()          # respect the Stop button
                if _scan_timed_out():  # hard wall — don't hang past 8 min
                    break
                url = lead["linkedin_url"]
                log.info(f"Checking: {lead['name']} ({lead['company']})")
                try:
                    status = client.check_connection_status(url)
                except Exception as e:
                    log.warning(f"Could not check {lead['name']}: {e} — skipping")
                    continue
                log.info(f"  → {status}")
                if status == "connected":
                    set_status(state, url, STATUS_CONNECTED, note="Already connected (scan)")
                    already_connected.append(lead)

        log.info(f"Scan complete. Found {len(already_connected)} connected leads.")
        log.info(f"Use 'Preview' to see what messages would be sent, then 'Send' to send them.")
        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# SEND — Send first messages to connected leads (after you've previewed them)
# ─────────────────────────────────────────────────────────────────────────────
_SEND_TIMEOUT = 45 * 60  # 45 minutes max for the entire send step

def cmd_send():
    limit = _get_limit()
    state  = sync_leads_to_state()
    client = _make_client()
    _t0 = time.time()

    try:
        connected = leads_by_status(state, STATUS_CONNECTED)
        if limit:
            connected = connected[:limit]

        if not connected:
            log.info("No connected leads waiting for first message.")
            return

        # Pre-screen: auto-disqualify any connected leads that match excluded locations
        # (catches leads that slipped in before the exclusion check was added)
        for lead in connected[:]:
            if _is_excluded_location(lead):
                url = lead.get("linkedin_url", "")
                log.info(f"Auto-disqualifying {lead.get('name','?')} — excluded location detected in send queue")
                set_status(state, url, STATUS_DISQUALIFIED,
                           note="Auto-disqualified: excluded location detected at send time")
                connected.remove(lead)

        log.info(f"Sending first messages to {len(connected)} connected leads…")
        sent = 0
        for lead in connected:
            if not _can_send_message(state):
                break
            elapsed = time.time() - _t0
            if elapsed > _SEND_TIMEOUT:
                log.warning(f"Send timeout reached ({elapsed/60:.0f} min) — stopping early. Remaining leads will be tried next run.")
                break
            url = lead["linkedin_url"]
            sent_before = sum(1 for m in lead.get("messages", []) if m.get("role") == "ai")
            _send_first_message(client, state, lead)
            sent_after = sum(1 for m in state["leads"][url].get("messages", []) if m.get("role") == "ai")
            if sent_after > sent_before:
                sent += 1

        log.info(f"Done. Sent {sent} first message(s) this run.")
        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# CONNECT — Send connection requests
# ─────────────────────────────────────────────────────────────────────────────
_CONNECT_FAIL_LIMIT = 3   # skip a lead permanently after this many connect failures

def cmd_connect():
    import time as _time
    from linkedin_client import _check_stop
    limit   = _get_limit()
    state   = sync_leads_to_state()
    client  = _make_client()

    # Hard wall: stop after 7 minutes so the watchdog never triggers
    _CONNECT_TIMEOUT = 420  # 7 min
    _start = _time.monotonic()

    def _timed_out() -> bool:
        elapsed = _time.monotonic() - _start
        if elapsed > _CONNECT_TIMEOUT:
            log.warning(f"Connect timeout reached ({elapsed:.0f}s) — stopping early. "
                        f"Remaining leads will be tried tomorrow.")
            return True
        return False

    try:
        pending = leads_by_status(state, STATUS_PENDING)
        requested_today = _count_requested_today(state)
        slots_left = MAX_CONNECTION_REQUESTS_PER_DAY - requested_today

        if limit:
            slots_left = min(slots_left, limit)

        if slots_left <= 0:
            log.warning(f"Daily limit reached ({MAX_CONNECTION_REQUESTS_PER_DAY}/day). Run tomorrow.")
            return

        log.info(f"{len(pending)} pending. Sending up to {slots_left} today.")
        sent = 0
        skipped_failures = 0

        for lead in pending:
            _check_stop()
            if _timed_out():
                break
            if sent >= slots_left:
                log.info(f"Limit reached. {len(pending)-sent} remain for tomorrow.")
                break

            url = lead["linkedin_url"]

            # Skip leads that have failed to connect too many times
            connect_fails = lead.get("connect_failures", 0)
            if connect_fails >= _CONNECT_FAIL_LIMIT:
                log.info(f"Skipping {lead['name']} — {connect_fails} failed connect attempts, "
                         f"marking disqualified.")
                set_status(state, url, STATUS_DISQUALIFIED,
                           note=f"Could not find Connect button after {connect_fails} attempts")
                skipped_failures += 1
                continue

            # Fetch recent posts before writing the note — gives the AI a specific hook
            # rather than relying on title/company alone. Also cached in state so the
            # first-message step can reuse them without a second page load.
            posts = []
            try:
                posts = client.get_profile_posts(url, count=3)
                if posts:
                    log.info(f"  {len(posts)} recent post(s) found for {lead['name']} — using as hook")
                    state["leads"][url]["cached_posts"] = posts
                else:
                    log.info(f"  No recent posts for {lead['name']} — note will use profile context only")
            except Exception as _pe:
                log.debug(f"  Post fetch failed for {lead['name']}: {_pe}")

            note = _generate_connection_note(lead, posts=posts)
            log.info(f"Connecting: {lead['name']} ({lead['company']})" + (f" — note: {note[:60]}…" if note else ""))
            if client.send_connection_request(url, message=note):
                set_status(state, url, STATUS_REQUESTED,
                           note=f"Requested {datetime.utcnow().date()}")
                # Clear any previous failure count on success
                lead.pop("connect_failures", None)
                sent += 1
            else:
                # Increment failure counter
                lead["connect_failures"] = connect_fails + 1
                log.warning(f"Could not connect to {lead['name']} "
                            f"(failure {lead['connect_failures']}/{_CONNECT_FAIL_LIMIT})")

        from state_manager import save_state
        save_state(state)
        log.info(f"Done. Sent {sent} connection requests. "
                 f"{skipped_failures} leads skipped (repeated failures).")
        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# SYNC CONNECTIONS — Pick up all recent connections, not just tracked leads
# ─────────────────────────────────────────────────────────────────────────────
def cmd_sync_connections(state: dict = None, client=None, prefetched_connection_slugs: set = None) -> int:
    """
    Scrape LinkedIn connections page for anyone who connected in the last 7 days.
    Add them to state as STATUS_CONNECTED if they're not already tracked.
    Returns the number of new leads added.

    Can be called standalone OR from cmd_check (sharing client/state).
    prefetched_connection_slugs: if provided (from cmd_check's bulk step),
    skip the redundant get_my_connections() call in the slug fallback.
    """
    _own_client = client is None
    if state is None:
        state = sync_leads_to_state()
    if client is None:
        client = _make_client()

    def _process_connection(conn: dict, source: str) -> bool:
        """Add/upgrade one connection. Returns True if it was a new add."""
        url  = conn["url"]
        name = conn.get("name", "Unknown")

        if url in state["leads"]:
            lead = state["leads"][url]
            if lead["status"] == STATUS_REQUESTED:
                set_status(state, url, STATUS_CONNECTED,
                           note=f"Accepted (detected via {source})")
                log.info(f"Upgraded to connected: {lead['name']} [{source}]")
            return False  # already tracked

        # Brand-new connection — add to pipeline
        lead_data = {
            "linkedin_url": url,
            "name":         name,
            "title":        conn.get("title", ""),
            "company":      conn.get("company", ""),
            "sector":       "",
        }
        if _is_excluded_location(lead_data):
            log.info(f"Skipping {name} — excluded location")
            return False

        upsert_lead(state, lead_data)
        set_status(state, url, STATUS_CONNECTED,
                   note=f"Added via {source}")
        log.info(f"New connection added: {name} ({conn.get('title','')} @ {conn.get('company','')})")
        return True

    try:
        added = 0
        upgraded = 0

        # ── Source 1: Notifications page ("X accepted your invitation") ──────
        # Most direct — explicitly lists acceptances for our outgoing requests.
        log.info("Checking notifications for accepted connection requests…")
        notif_accepted = client.get_accepted_from_notifications()
        for conn in notif_accepted:
            was_new = _process_connection(conn, "notifications")
            if was_new:
                added += 1
            else:
                upgraded += 1

        # ── Source 2: Connections page (catches organic adds + any misses) ───
        log.info("Scanning connections page for any remaining new connections…")
        recent = client.get_recent_connections_rich()
        page_added = 0
        for conn in recent:
            was_new = _process_connection(conn, "connections page")
            if was_new:
                added += 1
                page_added += 1

        # ── Source 3: Slug-based fallback (catches what rich scraper misses) ──
        # get_my_connections() reliably returns slugs even when the card-parsing
        # JS fails. Compare against state.json — any unknown slug = new connection.
        # When called from cmd_check, prefetched_connection_slugs is already available —
        # use it directly to avoid a redundant (and slow) connections page fetch.
        if page_added == 0:
            log.info("Rich scraper found 0 — running slug-based fallback check…")
            known_slugs = set()
            for url in state["leads"]:
                slug = client._extract_public_id(url)
                if slug:
                    known_slugs.add(slug)

            if prefetched_connection_slugs is not None:
                log.info(f"Using {len(prefetched_connection_slugs)} prefetched slugs (skipping redundant fetch).")
                all_connection_slugs = prefetched_connection_slugs
            else:
                all_connection_slugs = client.get_my_connections(limit=500)
            new_slugs = all_connection_slugs - known_slugs

            if new_slugs:
                log.info(f"Slug fallback found {len(new_slugs)} unknown connection(s) — fetching profiles…")
                from linkedin_client import _check_stop
                for slug in sorted(new_slugs):
                    _check_stop()
                    url = f"https://www.linkedin.com/in/{slug}"
                    try:
                        profile = client.get_profile(url) or {}
                        name    = profile.get("full_name") or slug
                        title   = profile.get("headline", "")
                        location = profile.get("locationName", "") or profile.get("location", "")
                        company = ""
                        exp     = profile.get("experience", [])
                        if exp:
                            company = exp[0].get("company", "")
                    except Exception:
                        name, title, company, location = slug, "", "", ""

                    conn = {"url": url, "name": name, "title": title, "company": company, "location": location}
                    was_new = _process_connection(conn, "slug fallback")
                    if was_new:
                        added += 1
                        log.info(f"  + Added via slug fallback: {name}")
            else:
                log.info("Slug fallback: no new connections found.")

        from state_manager import save_state
        save_state(state)

        log.info(
            f"Sync complete — {added} new connection(s) added, "
            f"{upgraded} upgraded from Requested→Connected. "
            f"(notifications: {len(notif_accepted)}, page: {len(recent)})"
        )
        return added + upgraded

    finally:
        if _own_client:
            client.close()


# ─────────────────────────────────────────────────────────────────────────────
# CHECK — Detect accepted connections (does NOT send messages)
# ─────────────────────────────────────────────────────────────────────────────
def cmd_check():
    import time as _time
    from linkedin_client import _check_stop

    state  = sync_leads_to_state()
    client = _make_client()

    # Hard wall: abort at 8 min so the server's 600s watchdog never fires
    _CHECK_TIMEOUT = 480
    _check_start = _time.monotonic()

    def _check_timed_out(label: str = "") -> bool:
        elapsed = _time.monotonic() - _check_start
        if elapsed > _CHECK_TIMEOUT:
            log.warning(
                f"Check timeout reached ({elapsed:.0f}s){' — before ' + label if label else ''} "
                f"— stopping early. Run Check again to continue."
            )
            return True
        return False

    try:
        requested = leads_by_status(state, STATUS_REQUESTED)
        log.info(f"Checking {len(requested)} requested leads for acceptance…")

        newly_accepted = 0

        # ── Step 1: Bulk check via connections page (one page load, fast) ──
        # Use whatever connections the page loaded — even a small set catches
        # people who just accepted. We also pass these slugs to cmd_sync_connections
        # later to avoid a redundant (slow) second fetch of the same data.
        my_connections = client.get_my_connections(limit=500)
        remaining = []

        if my_connections:
            log.info(f"Bulk-checking {len(requested)} leads against {len(my_connections)} loaded connections…")
            for lead in requested:
                url = lead["linkedin_url"]
                public_id = client._extract_public_id(url)
                if public_id and public_id in my_connections:
                    log.info(f"  ✓ Accepted: {lead['name']}")
                    set_status(state, url, STATUS_CONNECTED, note="Accepted (bulk check)")
                    newly_accepted += 1
                else:
                    remaining.append(lead)
            log.info(f"Bulk check: {newly_accepted} newly accepted, {len(remaining)} still unconfirmed.")
            if len(my_connections) < 50:
                log.info(
                    f"  (Connections page loaded {len(my_connections)} — "
                    "individual profile checks will cover the rest)"
                )
        else:
            remaining = list(requested)
            log.warning("Could not load connections page — falling back to individual profile checks.")

        # ── Step 2: Individual profile checks (rotating round-robin) ────────
        # Visit each unconfirmed lead's profile to look for the 1st-degree badge.
        # We rotate the check order each run so all 100+ leads get covered evenly
        # rather than always re-checking the same first 20.
        # When a lead shows "none" multiple times it means the request was likely
        # declined or expired — we reset it to STATUS_PENDING so it can be retried.
        MAX_INDIVIDUAL = 20
        NONE_RESET_THRESHOLD = 1   # "none" = Connect button visible = request never went through; recycle immediately

        if remaining and not _check_timed_out("individual checks"):
            # Sort by least-recently individually checked so stale leads get priority.
            # Leads with no last_individual_check timestamp come first.
            remaining.sort(key=lambda l: l.get("last_individual_check", ""))

            to_check_individual = remaining[:MAX_INDIVIDUAL]
            log.info(
                f"Checking {len(to_check_individual)} leads individually "
                f"(cap {MAX_INDIVIDUAL}/run, {len(remaining) - len(to_check_individual)} deferred to next run)…"
            )
            for lead in to_check_individual:
                _check_stop()
                if _check_timed_out("mid-individual"):
                    break
                url = lead["linkedin_url"]
                t0 = _time.monotonic()
                try:
                    status = client.check_connection_status(url, fast=True)
                    elapsed = _time.monotonic() - t0
                    log.info(f"  {lead['name']}: {status} ({elapsed:.1f}s)")

                    rec = state["leads"].get(url, {})
                    # Record that we checked this lead (for round-robin rotation)
                    rec["last_individual_check"] = datetime.utcnow().isoformat()

                    if status == "connected":
                        set_status(state, url, STATUS_CONNECTED, note="Accepted (profile check)")
                        newly_accepted += 1
                        rec.pop("check_none_count", None)   # reset on acceptance

                    elif status == "none":
                        # "none" means the profile shows 2nd/3rd degree but no pending request.
                        # This usually means the request was declined or expired.
                        # After NONE_RESET_THRESHOLD consecutive "none" results, reset to
                        # STATUS_PENDING so it can be re-requested (or manually reviewed).
                        none_count = rec.get("check_none_count", 0) + 1
                        rec["check_none_count"] = none_count
                        log.info(
                            f"  {lead['name']}: request not found on profile "
                            f"(none×{none_count} — may be declined/expired)"
                        )
                        if none_count >= NONE_RESET_THRESHOLD:
                            set_status(state, url, STATUS_PENDING,
                                       note=f"Reset: request appears declined or expired ({none_count} none-checks)")
                            rec["check_none_count"] = 0
                            log.info(
                                f"  → Reset {lead['name']} to Pending "
                                f"(request likely declined/expired after {none_count} checks)"
                            )

                    else:
                        # "pending" or "unknown" — leave as STATUS_REQUESTED, try again next run
                        rec.pop("check_none_count", None)   # consecutive none streak broken

                except Exception as e:
                    log.warning(f"  Could not check {lead['name']}: {e} — skipping")

        # ── Step 3: Sync connections page to catch organic adds ──────────────
        # Pass my_connections (already fetched in Step 1) to avoid a redundant
        # get_my_connections() call inside cmd_sync_connections's slug fallback.
        # This is the key fix for the 600s timeout — without it, connections are
        # fetched twice (or three times) in the same run.
        if not _check_timed_out("sync step"):
            log.info("Syncing connections page for organic/missed connections…")
            synced = cmd_sync_connections(
                state=state,
                client=client,
                prefetched_connection_slugs=my_connections,
            )
        else:
            synced = 0

        from state_manager import save_state
        save_state(state)

        connected = leads_by_status(state, STATUS_CONNECTED)
        log.info(
            f"Check complete. {newly_accepted} newly accepted, "
            f"{synced} organic/new connections added, "
            f"{len(connected)} total connected awaiting first message."
        )
        log.info("Use 'Send' to message them.")
        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Out-of-office / auto-reply detector
# ─────────────────────────────────────────────────────────────────────────────
_OOO_PATTERNS = [
    # Out of office
    "out of office", "out of the office", "ooo:", "i'm currently out",
    "i am currently out", "currently out of", "away from the office",
    "away until", "back on", "back in the office", "returning on",
    "returning ", "will return", "i'll be back", "i will be back",
    # Auto-reply headers
    "automatic reply:", "auto reply:", "auto-reply:", "autoreply:",
    "this is an automated", "this is an automatic",
    "do not reply to this", "do not reply to this message",
    "please do not respond", "noreply@", "no-reply@",
    # Vacation / leave
    "on vacation", "on annual leave", "on leave until",
    "on holiday", "on maternity leave", "on paternity leave",
    "on parental leave", "on sabbatical",
]

def _is_out_of_office(text: str) -> bool:
    """Return True if the message looks like an automated OOO / auto-reply."""
    lower = text.lower()
    return any(pat in lower for pat in _OOO_PATTERNS)


# REPLY — Check inbox and reply to prospects
# ─────────────────────────────────────────────────────────────────────────────
def cmd_reply():
    state  = load_state()
    client = _make_client()

    try:
        now_utc = datetime.utcnow()
        active_leads = []
        for r in state["leads"].values():
            if r["status"] not in {STATUS_MESSAGED, STATUS_REPLIED}:
                continue
            # Skip leads where ANY outbound message was sent within the last 4 hours.
            # The autopilot runs send/followup→reply back-to-back, and the scraper can
            # mis-classify our own just-sent message as a prospect reply, causing a
            # second AI message to fire immediately. We check both the first message
            # and the most recent AI message to catch follow-up races too.
            history = get_conversation(state, r["linkedin_url"])
            ai_messages = [m for m in history if m["role"] == "ai"]
            timestamps_to_check = [r.get("first_message_at", "")]
            if ai_messages:
                timestamps_to_check.append(ai_messages[-1].get("ts", ""))
            skip = False
            for ts in timestamps_to_check:
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    hours_elapsed = (now_utc - dt.replace(tzinfo=None)).total_seconds() / 3600
                    if hours_elapsed < 4:
                        log.info(
                            f"Skipping {r['name']} — last outbound message sent only "
                            f"{hours_elapsed:.1f}h ago (min 4h before reply check)."
                        )
                        skip = True
                        break
                except (ValueError, TypeError):
                    pass
            if skip:
                continue
            active_leads.append(r)
        log.info(f"Checking inbox for {len(active_leads)} active conversations…")

        tracked_urls = [r["linkedin_url"] for r in active_leads]
        updated = client.get_all_conversations_with_replies(tracked_urls)

        for url, linkedin_msgs in updated.items():
            if not _can_send_message(state):
                break
            lead = state["leads"][url]

            # ── HARD 24-HOUR COOLDOWN ────────────────────────────────────────
            # After we send a reply to a lead, we set last_ai_reply_at. This
            # timestamp check is the nuclear guard: it does NOT depend on LinkedIn
            # scraping accuracy, message comparison, or any other heuristic.
            # Even if get_conversation() returns garbage, this prevents more than
            # one AI reply per lead per day.
            last_reply_ts = lead.get("last_ai_reply_at", "")
            if last_reply_ts:
                try:
                    reply_dt = datetime.fromisoformat(
                        last_reply_ts.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    hours_since = (now_utc - reply_dt).total_seconds() / 3600
                    if hours_since < 24:
                        log.info(
                            f"Skipping {lead['name']} — already replied "
                            f"{hours_since:.0f}h ago (24h cooldown)."
                        )
                        continue
                except (ValueError, TypeError):
                    pass

            # ── Block / do-not-contact guard ───────────────────────────────
            if _is_blocked(url):
                log.info(f"Skipping reply for {lead['name']} — on do-not-contact list")
                continue

            # ── Manual mode guard ──────────────────────────────────────────
            # User has taken over this conversation — AI stays silent.
            if lead.get("manual_mode"):
                log.info(f"Skipping {lead['name']} — manual mode active (user is handling this).")
                continue

            stored = get_conversation(state, url)
            stored_prospect_count = sum(1 for m in stored if m["role"] == "prospect")
            new_prospect_msgs = [m for m in linkedin_msgs if m["sender"] == "them"]

            if len(new_prospect_msgs) > stored_prospect_count:
                latest = new_prospect_msgs[-1]["text"]

                # ── Duplicate-send guard (FUZZY) ──────────────────────────
                # If the "reply" text is identical OR ~similar to a message WE
                # already sent, the scraper mis-classified our own bubble as
                # theirs. We normalise (smart quotes, em dashes, ellipsis,
                # whitespace, unicode case) and use difflib similarity ≥ 0.85
                # before treating it as a real reply. This catches the bug
                # where Influentia "answers its own question" because LinkedIn
                # rendered our message with a subtly different ellipsis char.
                import re, unicodedata
                from difflib import SequenceMatcher

                def _normalise_for_compare(s: str) -> str:
                    if not s:
                        return ""
                    # Unicode-fold (smart quotes → straight, em dash → hyphen, …)
                    s = unicodedata.normalize("NFKC", s)
                    s = (s.replace("‘", "'").replace("’", "'")
                          .replace("“", '"').replace("”", '"')
                          .replace("–", "-").replace("—", "-")
                          .replace("…", "..."))
                    # Lowercase + collapse whitespace + strip non-alphanum at edges
                    s = re.sub(r"\s+", " ", s.lower()).strip()
                    return s

                latest_n   = _normalise_for_compare(latest)
                # Check against ALL stored messages (both "ai" and "prospect") so that
                # previously mis-classified echoes of our own text are also caught.
                our_n_list = [_normalise_for_compare(m["content"])
                              for m in stored if m["role"] == "ai" and m.get("content")]
                all_stored_n = [_normalise_for_compare(m["content"])
                                for m in stored if m.get("content")]

                def _looks_like_ours(candidate: str) -> bool:
                    if not candidate:
                        return False
                    for ours in our_n_list:
                        if not ours:
                            continue
                        if candidate == ours:
                            return True
                        if candidate in ours or ours in candidate:
                            return True
                        if SequenceMatcher(None, candidate, ours).ratio() >= 0.85:
                            return True
                    return False

                def _already_stored(candidate: str) -> bool:
                    """True if this exact text is already in our stored history."""
                    if not candidate:
                        return False
                    for prev in all_stored_n:
                        if prev and (candidate == prev or
                                     SequenceMatcher(None, candidate, prev).ratio() >= 0.92):
                            return True
                    return False

                if _looks_like_ours(latest_n):
                    log.warning(
                        f"Skipping false reply from {lead['name']} — text matches "
                        f"one of our own sent messages (scraper artifact)."
                    )
                    continue

                if _already_stored(latest_n):
                    log.warning(
                        f"Skipping duplicate message from {lead['name']} — "
                        f"this exact text is already in stored history (re-scrape artifact)."
                    )
                    continue

                # ── Suspicious-timing guard ───────────────────────────────
                ai_messages_so_far = [m for m in stored if m["role"] == "ai"]
                if ai_messages_so_far:
                    last_ai_ts = ai_messages_so_far[-1].get("ts", "")
                    try:
                        if last_ai_ts:
                            last_ai_dt = datetime.fromisoformat(
                                last_ai_ts.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                            mins_since = (now_utc - last_ai_dt).total_seconds() / 60.0
                            if 0 <= mins_since < 30:
                                log.warning(
                                    f"Skipping suspicious early reply from {lead['name']} "
                                    f"— arrived only {mins_since:.0f} min after our last "
                                    f"message. Likely scraper artifact, not a real reply."
                                )
                                continue
                    except (ValueError, TypeError):
                        pass

                # ── Runaway-conversation guard (hard ratio) ───────────────
                # Count total AI messages vs total prospect messages stored.
                # If we've sent 3+ more messages than they have, something is
                # wrong regardless of what the stored roles show — auto-pause.
                ai_count       = sum(1 for m in stored if m.get("role") == "ai")
                prospect_count = sum(1 for m in stored if m.get("role") == "prospect")
                if ai_count - prospect_count >= 3:
                    log.error(
                        f"Runaway-conversation guard tripped for {lead['name']} — "
                        f"{ai_count} AI messages vs {prospect_count} prospect messages. "
                        f"Setting manual_mode=True until reviewed."
                    )
                    state["leads"][url]["manual_mode"] = True
                    state["leads"][url]["manual_mode_reason"] = (
                        f"Auto-paused: {ai_count} outbound vs {prospect_count} prospect "
                        f"messages — AI sent 3+ more than prospect replied. "
                        f"Review conversation and toggle manual_mode off when ready."
                    )
                    save_state(state)
                    continue

                log.info(f"Reply from {lead['name']}: {latest[:80]}…")
                add_message(state, url, "prospect", latest)
                set_status(state, url, STATUS_REPLIED)

                full_history = get_conversation(state, url)

                # ── Out-of-office / auto-reply guard ──────────────────────
                # If their message looks like an automated OOO, don't reply —
                # just log it and leave the lead in STATUS_REPLIED so we'll
                # check again next cycle when they're back.
                if _is_out_of_office(latest):
                    log.info(
                        f"OOO/auto-reply detected from {lead['name']} — "
                        f"skipping reply, will check again next cycle."
                    )
                    # Store a note so the dashboard can show it
                    rec = state["leads"].get(url, {})
                    rec["ooo_detected_at"] = datetime.utcnow().isoformat()
                    rec["ooo_message_preview"] = latest[:120]
                    save_state(state)
                    continue

                # Classify BEFORE generating reply — so we send a goodbye
                # instead of another push when someone signals they're done
                pre_status = classify_conversation_status(lead, full_history)

                if pre_status == "not_interested":
                    ai_reply = generate_goodbye(lead)
                    log.info(f"Prospect not interested — sending goodbye: {ai_reply}")
                    if client.send_message(url, ai_reply):
                        add_message(state, url, "ai", ai_reply, msg_type="reply")
                        state["leads"][url]["last_ai_reply_at"] = datetime.utcnow().isoformat()
                        save_state(state)
                        set_status(state, url, STATUS_DISQUALIFIED, note="Not interested")
                elif pre_status == "meeting_booked":
                    # They booked without us prompting — just log it, no extra message
                    set_status(state, url, STATUS_MEETING, note="Meeting booked!")
                    log.info(f"MEETING BOOKED: {lead['name']}!")
                else:
                    ai_reply = generate_reply(lead, full_history)
                    log.info(f"AI reply: {ai_reply}")
                    auto_reply = state.get("settings", {}).get("auto_reply_enabled", False)
                    if auto_reply:
                        if client.send_message(url, ai_reply):
                            add_message(state, url, "ai", ai_reply, msg_type="reply")
                            # Set 24h hard cooldown — prevents ANY further AI replies
                            # to this lead regardless of LinkedIn scrape results.
                            state["leads"][url]["last_ai_reply_at"] = datetime.utcnow().isoformat()
                            save_state(state)
                            # Re-classify after sending to catch a booking that just happened
                            post_status = classify_conversation_status(lead, get_conversation(state, url))
                            if post_status == "meeting_booked":
                                set_status(state, url, STATUS_MEETING, note="Meeting booked!")
                    else:
                        # Record the AI draft immediately so the next cmd_reply run
                        # sees this conversation as "recently replied to" — prevents
                        # a second AI reply firing before the pending one is approved.
                        add_message(state, url, "ai", ai_reply, msg_type="pending")
                        add_pending_reply(state, url, lead["name"], latest, ai_reply)
                        log.info(f"Reply draft queued for {lead['name']} — approval required in Engage tab.")

        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# FOLLOWUP — Send follow-ups to non-responders
# ─────────────────────────────────────────────────────────────────────────────
def cmd_followup():
    if MAX_FOLLOW_UPS <= 0:
        log.info("Follow-ups disabled (MAX_FOLLOW_UPS = 0). Skipping.")
        return

    state  = load_state()
    client = _make_client()

    try:
        messaged = leads_by_status(state, STATUS_MESSAGED)
        log.info(f"Checking {len(messaged)} messaged leads for follow-up eligibility…")
        now = datetime.utcnow()

        for lead in messaged:
            if not _can_send_message(state):
                break
            url = lead["linkedin_url"]

            # ── Block / do-not-contact guard ───────────────────────────────
            if _is_blocked(url):
                log.info(f"Skipping follow-up for {lead['name']} — on do-not-contact list")
                continue

            # ── Manual mode guard ──────────────────────────────────────────
            if lead.get("manual_mode"):
                log.info(f"Skipping follow-up for {lead['name']} — manual mode active.")
                continue

            history = get_conversation(state, url)

            ai_messages = [m for m in history if m["role"] == "ai"]
            follow_up_count = max(0, len(ai_messages) - 1)  # follow-ups sent so far

            if follow_up_count >= MAX_FOLLOW_UPS:
                continue

            # Use absolute time from first message for consistent day 3 / day 7 timing
            first_msg_ts = lead.get("first_message_at", "")
            if ai_messages:
                first_msg_ts = ai_messages[0].get("ts", first_msg_ts)
            if not first_msg_ts:
                continue

            try:
                first_date = datetime.fromisoformat(first_msg_ts.replace("Z", "+00:00"))
                days_since_first = (now - first_date.replace(tzinfo=None)).days
            except (ValueError, TypeError):
                continue

            # Follow-up 1: after FOLLOW_UP_AFTER_DAYS (default 3)
            # Follow-up 2: after FOLLOW_UP_AFTER_DAYS * 2 + 1 (default 7)
            fu_number = follow_up_count + 1
            required_days = FOLLOW_UP_AFTER_DAYS if fu_number == 1 else FOLLOW_UP_AFTER_DAYS * 2 + 1
            if days_since_first < required_days:
                continue

            first_msg = ai_messages[0]["content"] if ai_messages else ""

            # ── LinkedIn duplicate check ──────────────────────────────────────
            # Before sending a follow-up, verify on LinkedIn that we haven't
            # already messaged this lead (catches state corruption / manual sends).
            try:
                live_convo = client.get_conversation(url)
                live_our_msgs = [m for m in (live_convo or []) if m.get("sender") == "me"]
                # Count how many messages we've sent on LinkedIn vs local state
                stored_ai_count = len(ai_messages)
                if len(live_our_msgs) > stored_ai_count:
                    log.info(
                        f"Skipping follow-up for {lead['name']} — LinkedIn shows "
                        f"{len(live_our_msgs)} messages from us vs {stored_ai_count} in state. "
                        f"Importing missing messages."
                    )
                    # Import any missing messages
                    for m in (live_convo or []):
                        if m.get("sender") == "me":
                            add_message(state, url, "ai", m.get("text", ""), msg_type="manual")
                    continue
            except Exception as e:
                log.warning(f"Could not verify conversation for {lead['name']} ({e}) — proceeding")

            log.info(f"Follow-up {fu_number} for {lead['name']} ({days_since_first} days since first msg)")
            follow_up = generate_follow_up(lead, days_since_first, first_msg, follow_up_number=fu_number)
            log.info(f"Follow-up: {follow_up}")

            result = client.send_message(url, follow_up)
            if result == "not_connected":
                log.warning(
                    f"Skipping follow-up for {lead['name']} — no longer a 1st-degree connection. "
                    f"Keeping status as 'messaged'."
                )
                continue
            if result:
                add_message(state, url, "ai", follow_up, msg_type="follow_up")
                log.info(f"Follow-up sent to {lead['name']}")

        print_summary(state)
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# ADD — Add a new lead by LinkedIn URL
# ─────────────────────────────────────────────────────────────────────────────
def cmd_add():
    if len(sys.argv) < 3:
        print("Usage: python main.py add <linkedin_url>")
        print("Example: python main.py add https://www.linkedin.com/in/johndoe")
        return

    url = sys.argv[2].strip()
    if "linkedin.com/in/" not in url:
        print(f"Invalid LinkedIn URL: {url}")
        return

    state  = load_state()
    client = _make_client()

    try:
        if url in state["leads"]:
            print(f"Already tracking: {state['leads'][url]['name']}")
            return

        log.info(f"Fetching profile: {url}")
        profile = client.get_profile(url)
        if not profile:
            print(f"Could not fetch profile: {url}")
            return

        name    = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
        title   = profile.get("headline", "")
        company = ""
        for exp in (profile.get("experience", []) or []):
            end_date = (exp.get("timePeriod", {}) or {}).get("endDate") if isinstance(exp.get("timePeriod"), dict) else None
            if not end_date:
                company = exp.get("companyName", "") or ""
                break

        lead = {
            "linkedin_url": url,
            "name": name,
            "title": title,
            "company": company,
            "sector": "",
            "email": "",
        }
        upsert_lead(state, lead)
        save_state(state)
        print(f"Added: {name} — {title} at {company}")
        print(f"Run 'python main.py connect' to send them a connection request.")
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW — Dry run: show messages that WOULD be sent, without sending
# ─────────────────────────────────────────────────────────────────────────────
def cmd_preview():
    """
    Preview mode — scrapes real LinkedIn profile data (like Kakiyo) to
    generate highly personalized messages, but does NOT send anything.
    Opens a browser and visits profiles with full safety delays.
    """
    limit = _get_limit()
    state  = sync_leads_to_state()
    client = _make_client()

    try:
        connected = leads_by_status(state, STATUS_CONNECTED)

        log.info("═══ PREVIEW MODE — reads profiles, does NOT send messages ═══")

        if connected:
            if limit:
                connected = connected[:limit]
            log.info(f"── {len(connected)} connected leads — generating first messages ──")
            for lead in connected:
                url = lead["linkedin_url"]
                log.info(f"Fetching profile for preview: {lead['name']}")
                profile_data = client.get_profile(url) or {}
                posts = client.get_profile_posts(url, count=3)
                first_msg = generate_first_message(lead, profile_data, posts)
                log.info(f"TO:  {lead['name']} ({lead['company']})")
                log.info(f"MSG: {first_msg}")

        messaged = leads_by_status(state, STATUS_MESSAGED)
        now = datetime.utcnow()
        followup_due = []
        for lead in messaged:
            history = get_conversation(state, lead["linkedin_url"])
            ai_msgs = [m for m in history if m["role"] == "ai"]
            if len(ai_msgs) - 1 >= MAX_FOLLOW_UPS:
                continue
            last_ts = ai_msgs[-1].get("ts", "") if ai_msgs else ""
            if last_ts:
                try:
                    days = (now - datetime.fromisoformat(last_ts.replace("Z", "+00:00")).replace(tzinfo=None)).days
                    if days >= FOLLOW_UP_AFTER_DAYS:
                        followup_due.append((lead, days, ai_msgs[0]["content"] if ai_msgs else ""))
                except (ValueError, TypeError):
                    pass

        if followup_due:
            log.info(f"── {len(followup_due)} leads eligible for follow-up ──")
            for lead, days, first_msg in followup_due:
                fu = generate_follow_up(lead, days, first_msg)
                log.info(f"TO:  {lead['name']} ({days} days, no reply)")
                log.info(f"MSG: {fu}")

        if not connected and not followup_due:
            log.info("Nothing to preview right now — no connected leads awaiting a first message.")
            log.info("Tip: run Scan or Check first to detect accepted connections, then Preview.")

        log.info("═══ Preview complete — no messages were sent ═══")
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# STATUS — Dashboard
# ─────────────────────────────────────────────────────────────────────────────
def cmd_status():
    state = sync_leads_to_state()
    print_summary(state)

    active = [r for r in state["leads"].values()
              if r["status"] in {STATUS_REPLIED, STATUS_MESSAGED}]
    if active:
        print("─── Active Conversations ────────────────────────────────")
        for r in active:
            history = r.get("messages", [])
            status_emoji = "💬" if r["status"] == STATUS_REPLIED else "⏳"
            print(f"\n  {status_emoji} {r['name']} ({r['company']}) — {r['status']}")
            for m in history[-4:]:
                who = "  YOU " if m["role"] == "ai" else "  THEM"
                print(f"    {who}: {m['content'][:80]}")

    meetings = leads_by_status(state, STATUS_MEETING)
    if meetings:
        print("\n─── Meetings Booked ─────────────────────────────────────")
        for r in meetings:
            print(f"  ✓ {r['name']} — {r['company']}")

    disqualified = leads_by_status(state, STATUS_DISQUALIFIED)
    if disqualified:
        print(f"\n  ({len(disqualified)} leads disqualified)")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# LOOP — Auto-run
# ─────────────────────────────────────────────────────────────────────────────
def cmd_loop():
    log.info(f"Loop mode. Polling every {POLL_INTERVAL_HOURS}h. Ctrl+C to stop.")
    while True:
        try:
            log.info("─── Check cycle ───")
            cmd_check()
            log.info("─── Reply cycle ───")
            cmd_reply()
            log.info("─── Follow-up cycle ───")
            cmd_followup()
        except KeyboardInterrupt:
            log.info("Loop stopped by user.")
            break
        except Exception as e:
            log.error(f"Loop cycle error: {e}")

        next_run = datetime.now() + timedelta(hours=POLL_INTERVAL_HOURS)
        log.info(f"Next run at {next_run.strftime('%H:%M')}. Sleeping…")
        try:
            time.sleep(POLL_INTERVAL_HOURS * 3600)
        except KeyboardInterrupt:
            log.info("Loop stopped by user.")
            break


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
MAX_SEND_FAILURES = 5   # disqualify lead after this many consecutive send failures
MAX_SEND_FAILURES_PER_DAY = 2  # stop trying a lead after 2 failures in one day (likely rate-limited)

def _send_first_message(client, state, lead):
    """Generate and send a first message to a connected lead."""
    url = lead["linkedin_url"]

    # Block list check
    if _is_blocked(url):
        log.info(f"Skipping {lead['name']} — on the blocked/do-not-contact list")
        return

    # Location exclusion check (uses stored lead data)
    if _is_excluded_location(lead):
        log.info(f"Skipping {lead['name']} — excluded location ({lead.get('location','?')})")
        return

    # ── Status guard: never send if already messaged or beyond ──────────────
    # This is the PRIMARY guard against duplicate sends. Even if the LinkedIn
    # conversation check below is skipped or fails, this prevents re-sending
    # to any lead that has already received a message (AI or manual).
    current_status = lead.get("status", "")
    if current_status in (STATUS_MESSAGED, STATUS_REPLIED, STATUS_MEETING, STATUS_DISQUALIFIED):
        log.info(f"Skipping {lead['name']} — status is '{current_status}', already messaged or beyond")
        return

    # ── LinkedIn conversation check (ALWAYS run, not just when local state is empty) ──
    # Check LinkedIn directly for any messages from us. This catches:
    # 1. Manual sends the local state doesn't know about
    # 2. Sends from a previous run whose state was lost/corrupted
    # 3. Any scenario where local state says "connected" but LinkedIn shows messages
    try:
        live_convo = client.get_conversation(url)
        our_msgs = [m for m in (live_convo or []) if m.get("sender") == "me"]
        if our_msgs:
            log.info(
                f"Skipping first message for {lead['name']} — "
                f"LinkedIn conversation already has {len(our_msgs)} message(s) from us. "
                f"Marking as messaged and importing conversation."
            )
            # Import the existing conversation — tag manual sends as "manual"
            # so they are NOT counted against the daily outreach limit
            for m in (live_convo or []):
                if m.get("sender") == "me":
                    add_message(state, url, "ai", m.get("text", ""), msg_type="manual")
                elif m.get("sender") == "them":
                    add_message(state, url, "prospect", m.get("text", ""))
            set_status(state, url, STATUS_MESSAGED, note="Message(s) detected on LinkedIn — imported")
            return
    except Exception as e:
        log.warning(f"Could not pre-check conversation for {lead['name']} ({e}) — proceeding with send")

    log.info(f"Generating first message for {lead['name']}…")
    profile_data = client.get_profile(url) or {}
    if not profile_data:
        log.warning(f"⚠ No profile data returned for {lead['name']} — message will use lead record only (less personalised)")

    # Correct the stored name if the live profile gives a different one.
    # This prevents wrong-name messages when source data had a name/URL mismatch.
    live_first = (profile_data.get("firstName") or "").strip()
    live_last  = (profile_data.get("lastName") or "").strip()
    live_full  = f"{live_first} {live_last}".strip()
    if live_full and live_full.lower() != lead.get("name", "").strip().lower():
        old_name = lead.get("name", "")
        lead["name"] = live_full
        state["leads"][url]["name"] = live_full
        log.info(f"Name corrected: {old_name!r} → {live_full!r} (from live profile)")

    # Use posts cached during the connect step if available — saves a page load.
    # Fall back to a fresh fetch otherwise (e.g. manual triggers or older leads).
    cached_posts = (state.get("leads", {}).get(url) or {}).get("cached_posts")
    if cached_posts is not None:
        posts = cached_posts
        log.info(f"Using {len(posts)} cached post(s) from connect step for {lead['name']}")
    else:
        posts = client.get_profile_posts(url, count=5)
    if not posts:
        log.warning(f"⚠ No recent posts found for {lead['name']} — message will rely on profile data only")

    # Skip leads with thin profile data — prevents Claude from refusing to write a message
    has_company = bool(lead.get("company") or profile_data.get("companyName"))
    has_posts = bool(posts)
    has_summary = bool(profile_data.get("summary"))
    if not has_company and not has_posts and not has_summary:
        log.info(f"Skipping {lead['name']} — insufficient profile data (no company, posts, or summary)")
        set_status(state, url, STATUS_DISQUALIFIED, note="Insufficient profile data for personalization")
        return

    # Also check live profile location in case lead record was incomplete
    live_location = profile_data.get("location", "")
    if live_location:
        merged = dict(lead)
        merged["location"] = live_location
        if _is_excluded_location(merged):
            log.info(f"Skipping {lead['name']} — excluded location from live profile ({live_location})")
            return
    first_msg = generate_first_message(lead, profile_data, posts)

    # ── Video outreach: append personalised link if enabled ───────────────────
    try:
        _vs_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "video_settings.json")
        if _os.path.exists(_vs_file):
            import json as _json
            _vs = _json.load(open(_vs_file))
            if _vs.get("enabled") and _vs.get("video_url"):
                from ai_proxy import _load_license_key
                import urllib.request as _ur, urllib.error as _ue
                _license = _load_license_key()
                _payload = _json.dumps({
                    "license_key":       _license,
                    "lead_name":         lead.get("name", ""),
                    "lead_company":      lead.get("company", ""),
                    "lead_linkedin_url": url,
                    "video_url":         _vs["video_url"],
                }).encode()
                _req = _ur.Request(
                    "https://outreach-pilot-api-production.plain-king-ead0.workers.dev/api/video/create",
                    data=_payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    },
                    method="POST",
                )
                with _ur.urlopen(_req, timeout=10) as _resp:
                    _vdata = _json.loads(_resp.read())
                if _vdata.get("ok") and _vdata.get("landing_url"):
                    _template = _vs.get("message_template", "I also recorded a quick video for you: {video_link}")
                    _video_line = _template.replace("{video_link}", _vdata["landing_url"])
                    first_msg = first_msg.rstrip() + "\n\n" + _video_line
                    log.info(f"Video link appended for {lead['name']}: {_vdata['landing_url']}")
    except Exception as _ve:
        log.warning(f"Video link generation failed for {lead.get('name','?')} — sending without it: {_ve}")

    log.info(f"Message: {first_msg}")

    # Validate before sending
    is_valid, reason = validate_message(first_msg)
    if not is_valid:
        log.warning(f"Message failed validation for {lead['name']}: {reason}. Regenerating...")
        first_msg = generate_first_message(lead, profile_data, posts)
        is_valid, reason = validate_message(first_msg)
        if not is_valid:
            log.error(f"Message STILL invalid after retry for {lead['name']}: {reason}. Skipping.")
            return

    send_result = client.send_message(url, first_msg)

    if send_result == "not_connected":
        # Lead was wrongly marked connected — revert to requested so it gets re-checked
        set_status(state, url, STATUS_REQUESTED, note="Reverted: not a 1st-degree connection at send time")
        rec = state["leads"].get(url, {})
        rec.pop("send_failures", None)
        from state_manager import save_state
        save_state(state)
        log.info(f"↩ Reverted {lead['name']} to requested — not actually connected")
        return

    if send_result:
        set_status(state, url, STATUS_MESSAGED)
        add_message(state, url, "ai", first_msg, msg_type="outreach")
        # Clear any previous failure count on success
        rec = state["leads"].get(url, {})
        rec.pop("send_failures", None)
        from state_manager import save_state
        save_state(state)
        log.info(f"✓ Sent to {lead['name']}")
    else:
        # Track consecutive failures — disqualify only after MAX_SEND_FAILURES across
        # multiple days. If 2+ failures happen on the same day, LinkedIn is likely
        # rate-limiting temporarily — skip for today without penalising the lead.
        rec = state["leads"].get(url, {})
        today = datetime.utcnow().date().isoformat()
        failures_today = rec.get("send_failures_today", 0) + 1
        if (rec.get("last_send_failure_at") or "")[:10] != today:
            failures_today = 1  # reset daily counter on a new day
        rec["send_failures_today"] = failures_today
        rec["last_send_failure_at"] = datetime.utcnow().isoformat()

        if failures_today >= MAX_SEND_FAILURES_PER_DAY:
            log.warning(
                f"✗ {lead['name']} failed {failures_today}x today — "
                f"likely rate-limited. Skipping for today, will retry tomorrow."
            )
            from state_manager import save_state
            save_state(state)
            return  # don't increment overall failure counter for rate-limit days

        failures = rec.get("send_failures", 0) + 1
        rec["send_failures"] = failures
        from state_manager import save_state
        save_state(state)
        log.warning(f"✗ Failed to send to {lead['name']} (failure {failures}/{MAX_SEND_FAILURES})")
        if failures >= MAX_SEND_FAILURES:
            set_status(state, url, STATUS_DISQUALIFIED,
                       note=f"Disqualified: message send failed {failures} times across multiple days")
            log.warning(f"  → Disqualified {lead['name']} after {failures} send failures")


def _count_requested_today(state: dict) -> int:
    today = datetime.utcnow().date().isoformat()
    return sum(
        1 for r in state["leads"].values()
        if (r.get("request_sent_at") or "")[:10] == today
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def cmd_scan_posts():
    """Scan LinkedIn feed for posts by ICP people and queue AI comments."""
    # Read optional --keywords argument passed from the server
    kw = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--keywords" and i + 1 < len(sys.argv):
            kw = sys.argv[i + 1]
            break
    from comment import cmd_scan_posts as _scan
    _scan(icp_description=kw)


def cmd_post_comments():
    """Post all approved comments (max 5/day)."""
    from comment import cmd_post_approved_comments
    cmd_post_approved_comments()


# ─────────────────────────────────────────────────────────────────────────────
# FIND LEADS — Auto-refill pipeline from saved ICP settings
# ─────────────────────────────────────────────────────────────────────────────
FIND_LEADS_MIN_PENDING   = 30   # only search when pipeline drops below this
FIND_LEADS_COOLDOWN_DAYS = 3    # minimum days between searches (per profile)
FIND_LEADS_PER_RUN       = 20   # max leads to add per auto-run

def _pick_next_icp_profile(profiles: list) -> Optional[dict]:
    """
    Pick the profile to use next using least-recently-used rotation.
    Profiles never used come first. Among used ones, oldest last_used_at wins.
    Returns None if no eligible profile found.
    """
    eligible = []
    cutoff = datetime.utcnow() - timedelta(days=FIND_LEADS_COOLDOWN_DAYS)
    for p in profiles:
        last = p.get("last_used_at")
        if last is None:
            eligible.append((datetime.min, p))   # never used → highest priority
        else:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt < cutoff:
                    eligible.append((last_dt, p))
            except ValueError:
                eligible.append((datetime.min, p))

    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])   # oldest first
    return eligible[0][1]


def cmd_find_leads():
    """
    Auto-refill the lead pipeline using saved ICP profiles (round-robin rotation).
    Picks the profile least recently used and runs a search with it.
    Only runs when pending leads < FIND_LEADS_MIN_PENDING.
    Each profile respects a FIND_LEADS_COOLDOWN_DAYS cooldown independently.
    Safe: only touches Brave Search — LinkedIn never sees this step.
    """
    import os
    from lead_finder import search_leads, score_leads_quality
    from state_manager import load_state, upsert_lead, save_state, leads_by_status

    state   = load_state()
    pending = leads_by_status(state, STATUS_PENDING)

    if len(pending) >= FIND_LEADS_MIN_PENDING:
        log.info(f"Pipeline has {len(pending)} pending leads — no search needed (min: {FIND_LEADS_MIN_PENDING}).")
        return

    # Load saved ICP profiles
    icp_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "icp_settings.json")
    if not _os.path.exists(icp_file):
        log.info("No ICP profiles saved. Go to Find Leads → set up your targeting first.")
        return

    store    = json.load(open(icp_file))
    profiles = store.get("profiles", [])
    if not profiles:
        log.info("No ICP profiles found. Add profiles in the Find Leads tab.")
        return

    profile = _pick_next_icp_profile(profiles)
    if profile is None:
        log.info(f"All ICP profiles on cooldown ({FIND_LEADS_COOLDOWN_DAYS}-day minimum between searches). Skipping.")
        return

    job_titles = profile.get("job_titles", [])
    industries = profile.get("industries", [])
    locations  = profile.get("locations", [])
    keywords   = profile.get("keywords", [])

    if not job_titles and not industries:
        log.info(f"Profile '{profile['name']}' has no roles or industries. Skipping.")
        return

    log.info(f"Pipeline low ({len(pending)} pending). Searching with profile: '{profile['name']}'")
    log.info(f"  Roles: {job_titles} | Industries: {industries} | Location: {locations}")

    industry_str  = ", ".join(industries)
    keywords_str  = " ".join(keywords)
    titles_to_use = job_titles[:4] if job_titles else [""]

    # Search per-location so we control the mix rather than leaving it to Brave.
    # Weight: first location gets 50% of budget, second 35%, rest share the remainder.
    _loc_weights = [0.50, 0.35, 0.15]
    loc_budgets  = {}
    for i, loc in enumerate(locations):
        weight = _loc_weights[i] if i < len(_loc_weights) else 0.15 / max(1, len(locations) - 2)
        loc_budgets[loc] = max(5, int(FIND_LEADS_PER_RUN * weight))
    if not locations:
        loc_budgets[""] = FIND_LEADS_PER_RUN  # fallback: no location filter

    log.info(f"  Location budgets: { {k: v for k, v in loc_budgets.items()} }")

    all_new   = []
    seen_urls = set(state["leads"].keys())

    location_str = ", ".join(locations) if locations else ""  # define before loop for logging/scoring below

    for loc, loc_count in loc_budgets.items():
        per_title = max(5, loc_count // max(1, len(titles_to_use)))
        for title in titles_to_use:
            batch = search_leads(title, industry_str, loc, keywords_str, per_title)
            for lead in batch:
                if lead["linkedin_url"] not in seen_urls:
                    seen_urls.add(lead["linkedin_url"])
                    all_new.append(lead)
        if len(all_new) >= FIND_LEADS_PER_RUN * 2:
            break

    # Filter out leads from excluded locations (e.g. Netherlands)
    if EXCLUDED_LOCATIONS and all_new:
        before = len(all_new)
        all_new = [l for l in all_new if not _is_excluded_location(l)]
        dropped = before - len(all_new)
        if dropped:
            log.info(f"Excluded {dropped} lead(s) matching location filter: {EXCLUDED_LOCATIONS}")

    # Quality-score with Claude — filter out poor ICP matches
    if all_new:
        icp_desc = " | ".join(filter(None, [
            "Job titles: " + ", ".join(job_titles) if job_titles else "",
            "Industry: "   + industry_str           if industry_str else "",
            "Location: "   + location_str           if location_str else "",
        ]))
        all_new = score_leads_quality(all_new, icp_desc or "B2B professional", min_score=5)

    # Pattern-score with learned historical data — prioritise leads that look like
    # past converters (high reply/meeting rate). Falls back to 5 if data is thin.
    try:
        from analytics import score_lead, _load_patterns
        _patterns = _load_patterns()
        for lead in all_new:
            lead["pattern_score"] = score_lead(lead, _patterns)
        # Sort: best pattern match first, then take the run limit
        all_new.sort(key=lambda l: l.get("pattern_score", 5), reverse=True)
        top_scores = [l.get("pattern_score", 5) for l in all_new[:5]]
        log.info(f"Pattern scores (top 5): {top_scores}")
    except Exception as e:
        log.warning(f"Pattern scoring skipped: {e}")

    all_new = all_new[:FIND_LEADS_PER_RUN]

    added = 0
    for lead in all_new:
        upsert_lead(state, lead, campaign_id=f"icp_{profile['id']}")
        added += 1
    save_state(state)

    # Mark this profile as used and update stats
    profile["last_used_at"] = datetime.utcnow().isoformat()
    profile["leads_found"]  = profile.get("leads_found", 0) + added
    json.dump(store, open(icp_file, "w"), indent=2)

    log.info(f"Find leads complete — '{profile['name']}': added {added} leads. "
             f"Total from this profile: {profile['leads_found']}.")


# ─────────────────────────────────────────────────────────────────────────────
# WITHDRAW — Withdraw stale connection requests (older than WITHDRAW_AFTER_DAYS)
# ─────────────────────────────────────────────────────────────────────────────
WITHDRAW_AFTER_DAYS = 21  # withdraw requests older than 3 weeks

def cmd_withdraw():
    """Withdraw connection requests that haven't been accepted in WITHDRAW_AFTER_DAYS days."""
    state  = load_state()
    client = _make_client()

    try:
        requested = leads_by_status(state, STATUS_REQUESTED)
        cutoff = datetime.utcnow() - timedelta(days=WITHDRAW_AFTER_DAYS)

        stale_leads = []
        for lead in requested:
            sent_at_str = lead.get("request_sent_at")
            if sent_at_str:
                try:
                    sent_at = datetime.fromisoformat(sent_at_str)
                    if sent_at < cutoff:
                        stale_leads.append(lead)
                except ValueError:
                    pass
            # If we have no timestamp but lead is old (added before timestamping), skip
            # so we don't accidentally withdraw requests that were just sent

        if not stale_leads:
            log.info(f"No stale requests found (none older than {WITHDRAW_AFTER_DAYS} days).")
            return

        log.info(f"Found {len(stale_leads)} stale requests to withdraw (older than {WITHDRAW_AFTER_DAYS} days).")
        stale_urls = [l["linkedin_url"] for l in stale_leads]

        withdrawn_ids = client.withdraw_old_invitations(stale_urls)

        # Mark withdrawn leads back to pending so they can be retried later
        for lead in stale_leads:
            pid = lead["linkedin_url"].rstrip("/").split("/")[-1].lower()
            if pid in [w.lower() for w in withdrawn_ids]:
                set_status(state, lead["linkedin_url"], STATUS_WITHDRAWN,
                           note=f"Withdrawn after {WITHDRAW_AFTER_DAYS} days — eligible for retry")
                log.info(f"Marked withdrawn: {lead['name']}")

        log.info(f"Withdraw complete. {len(withdrawn_ids)} requests withdrawn.")
        print_summary(state)
    finally:
        client.close()


COMMANDS = {
    "scan":               cmd_scan,
    "connect":            cmd_connect,
    "check":              cmd_check,
    "sync_connections":   cmd_sync_connections,  # standalone connections sync
    "send":               cmd_send,
    "reply":              cmd_reply,
    "followup":           cmd_followup,
    "add":                cmd_add,
    "preview":            cmd_preview,
    "status":             cmd_status,
    "loop":               cmd_loop,
    "scan_posts":         cmd_scan_posts,
    "post_comments":      cmd_post_comments,
    "withdraw":           cmd_withdraw,
    "find_leads":         cmd_find_leads,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in COMMANDS:
        print(f"Unknown command: '{cmd}'")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    try:
        COMMANDS[cmd]()
    except StopSignal:
        log.info("Stopped by user.")
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
