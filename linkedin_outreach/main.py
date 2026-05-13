#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# main.py  —  Orchestration: connect → detect → message → reply → book
#
# Usage:
#   python main.py connect    → Send connection requests to pending leads (once/day)
#   python main.py check      → Check for accepted connections + send first messages
#   python main.py reply      → Check inbox and reply to prospects
#   python main.py status     → Print current lead status summary
#   python main.py loop       → Run check + reply in a loop every N hours (daemon mode)
# ─────────────────────────────────────────────────────────────────────────────
import sys
import time
import logging
from datetime import datetime, timedelta

from config import (
    MAX_CONNECTION_REQUESTS_PER_DAY,
    POLL_INTERVAL_HOURS,
    LOG_FILE_PATH,
)
from state_manager import (
    load_state, save_state, upsert_lead, set_status, add_message,
    get_conversation, leads_by_status, print_summary,
    STATUS_PENDING, STATUS_REQUESTED, STATUS_CONNECTED,
    STATUS_MESSAGED, STATUS_REPLIED, STATUS_MEETING, STATUS_DISQUALIFIED,
)
from leads_loader import sync_leads_to_state
from linkedin_client import LinkedInClient
from message_ai import generate_first_message, generate_reply, classify_conversation_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Send connection requests
# ─────────────────────────────────────────────────────────────────────────────
def cmd_connect():
    """Send connection requests to PENDING leads (respects daily limit)."""
    state   = sync_leads_to_state()
    client  = LinkedInClient()
    pending = leads_by_status(state, STATUS_PENDING)

    # Don't exceed the daily limit
    requested_today = _count_requested_today(state)
    slots_left = MAX_CONNECTION_REQUESTS_PER_DAY - requested_today

    if slots_left <= 0:
        log.warning(f"Daily connection limit reached ({MAX_CONNECTION_REQUESTS_PER_DAY}/day). "
                    "Run again tomorrow.")
        return

    log.info(f"{len(pending)} pending leads. Sending up to {slots_left} requests today.")

    sent = 0
    for lead in pending:
        if sent >= slots_left:
            log.info(f"Daily limit reached. {len(pending)-sent} leads remain for tomorrow.")
            break

        url = lead["linkedin_url"]
        log.info(f"Sending connection request to: {lead['name']} ({lead['company']})")

        # No connection note — cleaner and higher acceptance rate
        success = client.send_connection_request(url, message="")
        if success:
            set_status(state, url, STATUS_REQUESTED,
                       note=f"Connection request sent {datetime.utcnow().date()}")
            sent += 1
        else:
            log.warning(f"Failed to send request to {lead['name']} — will retry next run.")

    log.info(f"Done. Sent {sent} connection requests today.")
    print_summary(state)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Detect accepted connections + send first messages
# ─────────────────────────────────────────────────────────────────────────────
def cmd_check():
    """
    Check which connection requests were accepted, then send
    a personalised first message to each newly connected lead.
    """
    state  = sync_leads_to_state()
    client = LinkedInClient()

    # Get newly accepted connections from LinkedIn
    new_connections = client.get_pending_connections()
    accepted_public_ids = set()
    for conn in new_connections:
        pid = (conn.get("miniProfile") or {}).get("publicIdentifier", "")
        if pid:
            accepted_public_ids.add(pid)

    log.info(f"Found {len(accepted_public_ids)} recently accepted connections on LinkedIn.")

    # Match against our REQUESTED leads
    requested = leads_by_status(state, STATUS_REQUESTED)
    for lead in requested:
        url = lead["linkedin_url"]
        public_id = url.rstrip("/").split("/")[-1]

        if public_id in accepted_public_ids:
            log.info(f"Connection accepted: {lead['name']} ({lead['company']})")
            set_status(state, url, STATUS_CONNECTED, note="Connection accepted")
        else:
            # Also check if we can now message them (belt-and-suspenders)
            pass

    # Send first message to all newly CONNECTED (not yet messaged) leads
    connected = leads_by_status(state, STATUS_CONNECTED)
    log.info(f"{len(connected)} connected leads awaiting first message.")

    for lead in connected:
        url = lead["linkedin_url"]
        log.info(f"Generating first message for {lead['name']}…")

        # Fetch full profile + recent posts for personalisation
        profile_data = client.get_profile(url) or {}
        posts        = client.get_profile_posts(url, count=5)

        # Generate personalised icebreaker via Claude
        first_msg = generate_first_message(lead, profile_data, posts)
        log.info(f"Generated message: {first_msg}")

        # Send it
        success = client.send_message(url, first_msg)
        if success:
            set_status(state, url, STATUS_MESSAGED)
            add_message(state, url, "ai", first_msg)
            log.info(f"First message sent to {lead['name']}.")
        else:
            log.warning(f"Failed to send message to {lead['name']}.")

    print_summary(state)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Check inbox and reply to prospects
# ─────────────────────────────────────────────────────────────────────────────
def cmd_reply():
    """
    Poll inbox for replies from tracked leads.
    For each new reply, generate an AI response and send it.
    """
    state  = load_state()
    client = LinkedInClient()

    # Leads we've messaged but haven't disqualified or booked yet
    active_statuses = {STATUS_MESSAGED, STATUS_REPLIED}
    active_leads = [
        r for r in state["leads"].values()
        if r["status"] in active_statuses
    ]

    log.info(f"Checking inbox for {len(active_leads)} active conversations…")

    tracked_urls = [r["linkedin_url"] for r in active_leads]
    updated_convos = client.get_all_conversations_with_replies(tracked_urls)

    for url, linkedin_messages in updated_convos.items():
        lead = state["leads"][url]
        stored_history = get_conversation(state, url)

        # Find messages we haven't processed yet
        # (compare by length — simple but effective for 20 contacts)
        stored_ai_count    = sum(1 for m in stored_history if m["role"] == "ai")
        stored_prospect_count = sum(1 for m in stored_history if m["role"] == "prospect")

        new_prospect_messages = [
            m for m in linkedin_messages
            if m["sender"] == "them"
        ]

        if len(new_prospect_messages) > stored_prospect_count:
            # There are new replies — get the latest one
            latest_reply = new_prospect_messages[-1]["text"]
            log.info(f"New reply from {lead['name']}: {latest_reply[:80]}…")

            # Update our stored conversation
            add_message(state, url, "prospect", latest_reply)
            set_status(state, url, STATUS_REPLIED)

            # Get full updated history and generate AI reply
            full_history = get_conversation(state, url)
            ai_reply = generate_reply(lead, full_history)
            log.info(f"AI reply: {ai_reply}")

            # Send the reply
            success = client.send_message(url, ai_reply)
            if success:
                add_message(state, url, "ai", ai_reply)
                log.info(f"Reply sent to {lead['name']}.")

                # Check if conversation reached a conclusion
                updated_history = get_conversation(state, url)
                status = classify_conversation_status(lead, updated_history)
                log.info(f"Conversation status for {lead['name']}: {status}")

                if status == "meeting_booked":
                    set_status(state, url, STATUS_MEETING,
                               note="Meeting booked by AI.")
                    log.info(f"🎉 MEETING BOOKED with {lead['name']}!")
                elif status == "not_interested":
                    set_status(state, url, STATUS_DISQUALIFIED,
                               note="Prospect not interested. AI exited gracefully.")
                    log.info(f"Lead disqualified: {lead['name']}")
            else:
                log.warning(f"Failed to send reply to {lead['name']}.")

    print_summary(state)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS command
# ─────────────────────────────────────────────────────────────────────────────
def cmd_status():
    state = sync_leads_to_state()
    print_summary(state)

    # Print detailed view of active conversations
    active = [r for r in state["leads"].values()
              if r["status"] in {STATUS_REPLIED, STATUS_MESSAGED}]
    if active:
        print("\n─── Active Conversations ────────────────────────────────")
        for r in active:
            history = r.get("messages", [])
            print(f"\n  {r['name']} ({r['company']}) — {r['status']}")
            for m in history[-4:]:  # show last 4 messages
                who = "YOU " if m["role"] == "ai" else "THEM"
                print(f"    {who}: {m['content'][:80]}")

    # Print meetings
    meetings = leads_by_status(state, STATUS_MEETING)
    if meetings:
        print("\n─── 🎉 Meetings Booked ──────────────────────────────────")
        for r in meetings:
            print(f"  ✓ {r['name']} — {r['company']}")


# ─────────────────────────────────────────────────────────────────────────────
# LOOP command  (daemon mode)
# ─────────────────────────────────────────────────────────────────────────────
def cmd_loop():
    """Run check + reply every POLL_INTERVAL_HOURS hours continuously."""
    log.info(f"Starting loop mode. Polling every {POLL_INTERVAL_HOURS} hours. "
             "Press Ctrl+C to stop.")
    while True:
        log.info("─── Running check cycle ───")
        cmd_check()
        log.info("─── Running reply cycle ───")
        cmd_reply()
        next_run = datetime.now() + timedelta(hours=POLL_INTERVAL_HOURS)
        log.info(f"Next run at {next_run.strftime('%H:%M')}. Sleeping…")
        time.sleep(POLL_INTERVAL_HOURS * 3600)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _count_requested_today(state: dict) -> int:
    """Count how many connection requests were sent today."""
    today = datetime.utcnow().date().isoformat()
    return sum(
        1 for r in state["leads"].values()
        if r.get("request_sent_at", "")[:10] == today
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
COMMANDS = {
    "connect": cmd_connect,
    "check":   cmd_check,
    "reply":   cmd_reply,
    "status":  cmd_status,
    "loop":    cmd_loop,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
