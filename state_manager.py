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

    # Reply approval migration
    if "pending_replies" not in state:
        state["pending_replies"] = []

    # Settings migration — default auto_reply OFF so new installs require approval
    if "settings" not in state:
        state["settings"] = {}
    if "auto_reply_enabled" not in state["settings"]:
        state["settings"]["auto_reply_enabled"] = False

    # ── Reddit Signal + Engage migrations ──────────────────────────────────────
    if "reddit_signals" not in state:
        state["reddit_signals"] = []
    if "reddit_pending_comments" not in state:
        state["reddit_pending_comments"] = []
    if "reddit_posted_comments" not in state:
        state["reddit_posted_comments"] = []
    if "reddit_reply_queue" not in state:
        state["reddit_reply_queue"] = []
    if "reddit_settings" not in state:
        state["reddit_settings"] = {
            "subreddits": [],   # empty = use defaults from reddit_signal.py
            "queries":    [],   # empty = use defaults from reddit_signal.py
            "auto_post":  False,
        }
    rs = state["reddit_settings"]
    rs.setdefault("auto_reply_replies", False)
    rs.setdefault("auto_reply_daily_cap", 3)

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


def _normalise_msg(s: str) -> str:
    """Collapse whitespace and lowercase for duplicate detection."""
    import re, unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-")
          .replace("…", "..."))
    return re.sub(r"\s+", " ", s.lower()).strip()


def add_message(state: dict, linkedin_url: str, role: str, content: str, msg_type: str = ""):
    """
    msg_type values:
      "outreach"  — first message sent to a newly connected lead (counts against daily limit)
      "follow_up" — follow-up to a non-responder (counts against daily limit)
      "reply"     — AI reply to a prospect who already responded (does NOT count against limit)
      ""          — legacy / unclassified (counted conservatively)
    """
    rec = state["leads"].get(linkedin_url)
    if not rec:
        return
    # Deduplication: never store the same message twice in a row.
    # Protects against crash-and-restart double-writes and scraper re-reads.
    if rec["messages"]:
        last = rec["messages"][-1]
        if (last.get("role") == role and
                _normalise_msg(last.get("content", "")) == _normalise_msg(content)):
            return
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
                        tier: str = "", tier_reason: str = "", post_age: str = ""):
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
        "post_age":          post_age,
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


# ── Pending Replies ───────────────────────────────────────────────────────────

def add_pending_reply(state: dict, linkedin_url: str, lead_name: str,
                      prospect_msg: str, ai_draft: str) -> dict:
    """Queue an AI-generated reply for human approval before sending."""
    entry = {
        "id":           str(uuid.uuid4())[:8],
        "linkedin_url": linkedin_url,
        "lead_name":    lead_name,
        "prospect_msg": prospect_msg[:500],
        "ai_draft":     ai_draft,
        "created_at":   _now(),
        "status":       "pending",   # pending | approved | skipped | sent
    }
    state["pending_replies"].append(entry)
    save_state(state)
    return entry


def mark_reply(state: dict, reply_id: str, status: str, edited_text: str = "") -> dict:
    """Update the status of a pending reply. Returns the entry or None."""
    for r in state["pending_replies"]:
        if r["id"] == reply_id:
            r["status"] = status
            if edited_text:
                r["ai_draft"] = edited_text
            if status in ("sent", "skipped"):
                r["resolved_at"] = _now()
            save_state(state)
            return r
    return None


def purge_stale_pending_comments(state: dict, max_age_days: int = 14) -> int:
    """Remove pending/skipped comments older than max_age_days. Returns count removed."""
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.utcnow() - _td(days=max_age_days)).strftime("%Y-%m-%dT%H:%M")
    before = len(state.get("pending_comments", []))
    state["pending_comments"] = [
        c for c in state.get("pending_comments", [])
        if c.get("status") not in ("pending", "skipped")
           or (c.get("created_at") or "") >= cutoff
    ]
    removed = before - len(state["pending_comments"])
    if removed:
        save_state(state)
    return removed


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
