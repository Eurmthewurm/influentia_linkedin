# ─────────────────────────────────────────────────────────────────────────────
# state_manager.py  —  Tracks every lead's status and conversation history
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
from datetime import datetime
from config import STATE_FILE_PATH

# Lead lifecycle statuses
STATUS_PENDING     = "pending"          # not yet sent a connection request
STATUS_REQUESTED   = "requested"        # connection request sent
STATUS_CONNECTED   = "connected"        # connection accepted
STATUS_MESSAGED    = "messaged"         # first message sent
STATUS_REPLIED     = "replied"          # prospect replied (conversation active)
STATUS_MEETING     = "meeting_booked"   # meeting booked — done!
STATUS_DISQUALIFIED = "disqualified"    # not interested — AI exited gracefully


def _now():
    return datetime.utcnow().isoformat()


def load_state() -> dict:
    """Load state from disk, or return empty state if first run."""
    if os.path.exists(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r") as f:
            return json.load(f)
    return {"leads": {}, "created_at": _now()}


def save_state(state: dict):
    """Persist state to disk."""
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_lead(state: dict, linkedin_url: str) -> dict:
    """Get a lead's state record by LinkedIn URL."""
    return state["leads"].get(linkedin_url, {})


def upsert_lead(state: dict, lead: dict):
    """Create or update a lead's state record. lead must have 'linkedin_url'."""
    url = lead["linkedin_url"]
    if url not in state["leads"]:
        state["leads"][url] = {
            "linkedin_url":   url,
            "name":           lead.get("name", ""),
            "title":          lead.get("title", ""),
            "company":        lead.get("company", ""),
            "sector":         lead.get("sector", ""),
            "email":          lead.get("email", ""),
            "status":         STATUS_PENDING,
            "request_sent_at":  None,
            "connected_at":     None,
            "first_message_at": None,
            "last_activity_at": None,
            "messages":         [],   # full conversation log
            "notes":            "",
        }
    # Merge any provided fields
    for k, v in lead.items():
        if k in state["leads"][url] and v is not None:
            state["leads"][url][k] = v
    return state["leads"][url]


def set_status(state: dict, linkedin_url: str, new_status: str, note: str = ""):
    """Update a lead's status."""
    rec = state["leads"].get(linkedin_url)
    if rec:
        rec["status"] = new_status
        rec["last_activity_at"] = _now()
        if note:
            rec["notes"] += f"\n[{_now()}] {note}"
        ts_map = {
            STATUS_REQUESTED:  "request_sent_at",
            STATUS_CONNECTED:  "connected_at",
            STATUS_MESSAGED:   "first_message_at",
        }
        if new_status in ts_map:
            rec[ts_map[new_status]] = _now()
        save_state(state)


def add_message(state: dict, linkedin_url: str, role: str, content: str):
    """Append a message to the conversation log. role = 'ai' | 'prospect'."""
    rec = state["leads"].get(linkedin_url)
    if rec:
        rec["messages"].append({"role": role, "content": content, "ts": _now()})
        rec["last_activity_at"] = _now()
        save_state(state)


def get_conversation(state: dict, linkedin_url: str) -> list:
    """Return the full conversation history for a lead."""
    return state["leads"].get(linkedin_url, {}).get("messages", [])


def leads_by_status(state: dict, status: str) -> list:
    """Return all leads with a given status."""
    return [r for r in state["leads"].values() if r["status"] == status]


def print_summary(state: dict):
    """Print a quick status overview to console."""
    leads = state["leads"].values()
    counts = {}
    for r in leads:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n─── Lead Status Summary ───────────────────────────────")
    for s in [STATUS_PENDING, STATUS_REQUESTED, STATUS_CONNECTED,
              STATUS_MESSAGED, STATUS_REPLIED, STATUS_MEETING, STATUS_DISQUALIFIED]:
        n = counts.get(s, 0)
        bar = "█" * n
        print(f"  {s:<20} {bar} {n}")
    print("────────────────────────────────────────────────────────\n")
