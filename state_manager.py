# ─────────────────────────────────────────────────────────────────────────────
# state_manager.py  —  Tracks every lead's status and conversation history
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import uuid
from datetime import datetime
from config import STATE_FILE_PATH

STATUS_PENDING      = "pending"
STATUS_REQUESTED    = "requested"
STATUS_CONNECTED    = "connected"
STATUS_MESSAGED     = "messaged"
STATUS_REPLIED      = "replied"
STATUS_MEETING      = "meeting_booked"
STATUS_DISQUALIFIED = "disqualified"
STATUS_WITHDRAWN    = "withdrawn"


def _now():
    return datetime.utcnow().isoformat()


def load_state() -> dict:
    """Load state from disk. Auto-migrates to add campaigns + comments."""
    if os.path.exists(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r") as f:
            state = json.load(f)
    else:
        state = {"leads": {}, "created_at": _now()}

    # Campaigns migration
    if "campaigns" not in state:
        state["campaigns"] = {
            "default": {
                "id": "default", "name": "Default",
                "created_at": _now(),
                "description": "Leads before campaigns were introduced",
            }
        }
    for lead in state["leads"].values():
        if "campaign_id" not in lead:
            lead["campaign_id"] = "default"

    # Comment tracking migration
    if "pending_comments" not in state:
        state["pending_comments"] = []
    if "posted_comments" not in state:
        state["posted_comments"] = []

    return state


def save_state(state: dict):
    """Atomic write: write to temp file first, then rename. Prevents corruption on crash."""
    tmp = STATE_FILE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE_PATH)  # atomic on POSIX


# ── Campaigns ─────────────────────────────────────────────────────────────────

def create_campaign(state: dict, name: str, description: str = "") -> dict:
    cid = str(uuid.uuid4())[:8]
    camp = {"id": cid, "name": name, "created_at": _now(), "description": description}
    state["campaigns"][cid] = camp
    save_state(state)
    return camp


def get_campaign(state: dict, campaign_id: str) -> dict:
    return state.get("campaigns", {}).get(campaign_id, {})


def leads_for_campaign(state: dict, campaign_id: str) -> list:
    return [l for l in state["leads"].values() if l.get("campaign_id") == campaign_id]


# ── Leads ─────────────────────────────────────────────────────────────────────

def get_lead(state: dict, linkedin_url: str) -> dict:
    return state["leads"].get(linkedin_url, {})


def upsert_lead(state: dict, lead: dict, campaign_id: str = "default"):
    url = lead["linkedin_url"]
    if url not in state["leads"]:
        state["leads"][url] = {
            "linkedin_url":     url,
            "name":             lead.get("name", ""),
            "title":            lead.get("title", ""),
            "company":          lead.get("company", ""),
            "sector":           lead.get("sector", ""),
            "email":            lead.get("email", ""),
            "status":           STATUS_PENDING,
            "campaign_id":      campaign_id,
            "request_sent_at":  None,
            "connected_at":     None,
            "first_message_at": None,
            "last_activity_at": None,
            "messages":         [],
            "notes":            "",
            "icp_score":        None,
            "manual_mode":      False,   # True = user has taken over, AI stops replying
            "warm":             False,   # True = showing real buying interest
        }
    for k, v in lead.items():
        if k in state["leads"][url] and v is not None:
            state["leads"][url][k] = v
    if not state["leads"][url].get("campaign_id"):
        state["leads"][url]["campaign_id"] = campaign_id
    return state["leads"][url]


def set_status(state: dict, linkedin_url: str, new_status: str, note: str = ""):
    rec = state["leads"].get(linkedin_url)
    if rec:
        rec["status"] = new_status
        rec["last_activity_at"] = _now()
        if note:
            rec["notes"] += f"\n[{_now()}] {note}"
        ts_map = {
            STATUS_REQUESTED: "request_sent_at",
            STATUS_CONNECTED: "connected_at",
            STATUS_MESSAGED:  "first_message_at",
        }
        if new_status in ts_map:
            rec[ts_map[new_status]] = _now()
        save_state(state)


def add_message(state: dict, linkedin_url: str, role: str, content: str, msg_type: str = ""):
    """
    msg_type values:
      "outreach"  — first message sent to a newly connected lead (counts against daily limit)
      "follow_up" — follow-up to a non-responder (counts against daily limit)
      "reply"     — AI reply to a prospect who already responded (does NOT count against limit)
      ""          — legacy / unclassified (counted conservatively)
    """
    rec = state["leads"].get(linkedin_url)
    if rec:
        rec["messages"].append({"role": role, "content": content, "ts": _now(), "msg_type": msg_type})
        rec["last_activity_at"] = _now()
        save_state(state)


def get_conversation(state: dict, linkedin_url: str) -> list:
    return state["leads"].get(linkedin_url, {}).get("messages", [])


def leads_by_status(state: dict, status: str) -> list:
    leads = [r for r in state["leads"].values() if r["status"] == status]
    # Sort by when they entered this status (oldest first) so the queue is fair
    # and new bulk-adds don't always crowd out earlier connections.
    leads.sort(key=lambda r: r.get("connected_at") or r.get("request_sent_at") or r.get("last_activity_at") or "")
    return leads


# ── Comments ──────────────────────────────────────────────────────────────────

def add_pending_comment(state: dict, post_url: str, post_text: str,
                        poster_url: str, poster_name: str, suggested_comment: str,
                        relevance_score: int = 5, low_relevance: bool = False,
                        tier: str = "", tier_reason: str = ""):
    entry = {
        "id":                str(uuid.uuid4())[:8],
        "post_url":          post_url,
        "post_text":         post_text[:500],
        "poster_url":        poster_url,
        "poster_name":       poster_name,
        "suggested_comment": suggested_comment,
        "created_at":        _now(),
        "status":            "pending",
        "relevance_score":   relevance_score,
        "low_relevance":     low_relevance,
        "tier":              tier,
        "tier_reason":       tier_reason,
    }
    state["pending_comments"].append(entry)
    save_state(state)
    return entry


def mark_comment(state: dict, comment_id: str, status: str, final_text: str = ""):
    for c in state["pending_comments"]:
        if c["id"] == comment_id:
            c["status"] = status
            if final_text:
                c["final_text"] = final_text
            if status == "posted":
                c["posted_at"] = _now()
                # Remove from pending FIRST, then add to posted — so a crash
                # between the two operations can't create a duplicate entry.
                state["pending_comments"] = [
                    p for p in state["pending_comments"] if p["id"] != comment_id
                ]
                state["posted_comments"].append(dict(c))
            save_state(state)
            return c
    return None


def print_summary(state: dict):
    leads = state["leads"].values()
    counts = {}
    for r in leads:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n─── Lead Status Summary ───────────────────────────────")
    for s in [STATUS_PENDING, STATUS_REQUESTED, STATUS_CONNECTED,
              STATUS_MESSAGED, STATUS_REPLIED, STATUS_MEETING, STATUS_DISQUALIFIED]:
        print(f"  {s:<20} {'█' * counts.get(s,0)} {counts.get(s,0)}")
    print("────────────────────────────────────────────────────────\n")
