# ─────────────────────────────────────────────────────────────────────────────
# analytics.py  —  Pattern recognition & lead intelligence
#
# Reads historical data from state.json to learn:
#   - Which lead attributes (title, industry, location) convert best
#   - Which message styles get replies
#   - Which engagement tiers drive profile visits
#
# Results saved to learned_patterns.json.
# Used by lead scoring (before connecting) and weekly insights reports.
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_HERE            = os.path.dirname(os.path.abspath(__file__))
_PATTERNS_FILE   = os.path.join(_HERE, "learned_patterns.json")
_STATE_FILE      = os.path.join(_HERE, "state.json")

# ── Statuses ranked by value (higher = better outcome) ───────────────────────
_STATUS_RANK = {
    "pending":      0,
    "requested":    1,
    "connected":    2,
    "messaged":     3,
    "replied":      4,
    "meeting":      5,
    "disqualified": -1,
    "withdrawn":    -1,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(_STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"leads": {}, "posted_comments": [], "pending_comments": []}


def _load_patterns() -> dict:
    try:
        with open(_PATTERNS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_patterns(p: dict):
    tmp = _PATTERNS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(p, f, indent=2)
    os.replace(tmp, _PATTERNS_FILE)


def _normalise_title(title: str) -> str:
    """Collapse job title variants into canonical groups."""
    t = (title or "").lower().strip()
    if any(w in t for w in ("recruit", "talent", "staffing", "headhunt")):
        return "recruiter"
    if any(w in t for w in ("coach", "mentor", "trainer")):
        return "coach"
    if any(w in t for w in ("consultant", "advisor", "adviser")):
        return "consultant"
    if any(w in t for w in ("agency", "studio", "creative")):
        return "agency_owner"
    if any(w in t for w in ("founder", "ceo", "owner", "director", "md ", "managing")):
        return "founder_executive"
    if any(w in t for w in ("marketing", "brand", "growth", "demand")):
        return "marketer"
    return "other"


def _normalise_location(loc: str) -> str:
    l = (loc or "").lower()
    if "australia" in l or " au" in l or "sydney" in l or "melbourne" in l or "brisbane" in l:
        return "australia"
    if "united kingdom" in l or " uk" in l or "london" in l:
        return "uk"
    if "united states" in l or " us" in l or "new york" in l or "california" in l:
        return "usa"
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# Core analysis
# ─────────────────────────────────────────────────────────────────────────────

def get_funnel_stats(state: dict = None) -> dict:
    """
    Return conversion rates at each stage of the funnel.
    All leads that were ever requested are included.
    """
    if state is None:
        state = _load_state()

    leads = list(state.get("leads", {}).values())
    total = len(leads)
    if not total:
        return {"total": 0}

    by_status = defaultdict(int)
    for l in leads:
        by_status[l.get("status", "pending")] += 1

    requested   = sum(by_status[s] for s in ("requested", "connected", "messaged", "replied", "meeting"))
    connected   = sum(by_status[s] for s in ("connected",  "messaged", "replied", "meeting"))
    messaged    = sum(by_status[s] for s in ("messaged",   "replied",  "meeting"))
    replied     = sum(by_status[s] for s in ("replied",    "meeting"))
    meeting     = by_status["meeting"]

    def _pct(n, d):
        return round(100 * n / d, 1) if d else 0

    return {
        "total":            total,
        "by_status":        dict(by_status),
        "requested":        requested,
        "connected":        connected,
        "messaged":         messaged,
        "replied":          replied,
        "meeting":          meeting,
        "acceptance_rate":  _pct(connected, requested),   # connect req → connected
        "reply_rate":       _pct(replied,   messaged),    # messaged   → replied
        "meeting_rate":     _pct(meeting,   replied),     # replied    → meeting
        "overall_rate":     _pct(meeting,   requested),   # req → meeting
    }


def get_attribute_conversion(state: dict = None) -> dict:
    """
    For each normalised title/location group, compute the average outcome rank.
    Higher = leads in that group tend to convert further down the funnel.
    Returns dicts sorted best → worst.
    """
    if state is None:
        state = _load_state()

    leads = [l for l in state.get("leads", {}).values()
             if _STATUS_RANK.get(l.get("status", "pending"), 0) >= 0]

    if len(leads) < 5:
        return {}  # not enough data yet

    title_scores   = defaultdict(list)
    loc_scores     = defaultdict(list)

    for l in leads:
        rank  = _STATUS_RANK.get(l.get("status", "pending"), 0)
        title = _normalise_title(l.get("title", ""))
        loc   = _normalise_location(l.get("location", ""))
        title_scores[title].append(rank)
        loc_scores[loc].append(rank)

    def _summarise(scores_dict):
        out = {}
        for k, scores in scores_dict.items():
            if len(scores) < 2:
                continue
            avg = sum(scores) / len(scores)
            out[k] = {"avg_rank": round(avg, 2), "count": len(scores)}
        return dict(sorted(out.items(), key=lambda x: -x[1]["avg_rank"]))

    return {
        "by_title":    _summarise(title_scores),
        "by_location": _summarise(loc_scores),
    }


def score_lead(lead: dict, patterns: dict = None) -> int:
    """
    Score a new lead 1-10 using learned conversion patterns.
    10 = looks like your best converters. 1 = low historical fit.
    Falls back to 5 (neutral) if patterns are thin.
    """
    if patterns is None:
        patterns = _load_patterns()

    attr = patterns.get("attribute_conversion", {})
    if not attr:
        return 5  # no data yet — neutral

    title_data = attr.get("by_title", {})
    loc_data   = attr.get("by_location", {})

    title = _normalise_title(lead.get("title", ""))
    loc   = _normalise_location(lead.get("location", ""))

    title_rank = title_data.get(title, {}).get("avg_rank", 2.0)
    loc_rank   = loc_data.get(loc,   {}).get("avg_rank", 2.0)

    # Max possible rank is 5 (meeting). Normalise to 1-10.
    # Weight title 60%, location 40%
    combined = title_rank * 0.6 + loc_rank * 0.4
    score    = max(1, min(10, round(combined * 2)))
    return score


def get_comment_insights(state: dict = None) -> dict:
    """Analyse which engagement tiers and relevance scores led to profile views / replies."""
    if state is None:
        state = _load_state()

    posted = state.get("posted_comments", [])
    if not posted:
        return {}

    by_tier = defaultdict(lambda: {"count": 0, "avg_score": 0})
    scores  = []

    for c in posted:
        tier  = c.get("tier", "unknown")
        score = c.get("relevance_score", 5)
        by_tier[tier]["count"] += 1
        by_tier[tier]["avg_score"] += score
        scores.append(score)

    for t in by_tier.values():
        if t["count"]:
            t["avg_score"] = round(t["avg_score"] / t["count"], 1)

    return {
        "total_posted":       len(posted),
        "avg_relevance":      round(sum(scores) / len(scores), 1) if scores else 0,
        "by_tier":            dict(by_tier),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Weekly analysis — called by scheduled task
# ─────────────────────────────────────────────────────────────────────────────

def run_weekly_analysis() -> dict:
    """
    Full analysis pass. Updates learned_patterns.json.
    Returns a summary dict (also passed to Claude for the narrative report).
    """
    state   = _load_state()
    funnel  = get_funnel_stats(state)
    attr    = get_attribute_conversion(state)
    comment = get_comment_insights(state)

    patterns = {
        "updated_at":           datetime.now(timezone.utc).isoformat(),
        "funnel":               funnel,
        "attribute_conversion": attr,
        "comment_insights":     comment,
        # Lead score weights — updated each week as data accumulates
        "data_quality":         "rich" if funnel.get("messaged", 0) >= 10 else
                                "growing" if funnel.get("requested", 0) >= 5 else
                                "early",
    }

    _save_patterns(patterns)
    log.info(f"Patterns saved. Data quality: {patterns['data_quality']}. "
             f"Funnel: {funnel.get('requested',0)} req → {funnel.get('connected',0)} conn "
             f"→ {funnel.get('replied',0)} replied → {funnel.get('meeting',0)} meetings")
    return patterns


def generate_weekly_report(patterns: dict = None) -> str:
    """
    Use Claude to turn the raw pattern data into a plain-English weekly report
    with specific recommendations for next week.
    """
    if patterns is None:
        patterns = _load_patterns()
        if not patterns:
            patterns = run_weekly_analysis()

    try:
        import anthropic
        from config import ANTHROPIC_API_KEY
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        funnel  = patterns.get("funnel", {})
        attr    = patterns.get("attribute_conversion", {})
        comment = patterns.get("comment_insights", {})
        quality = patterns.get("data_quality", "early")

        prompt = f"""You are the growth analyst for Authentik Studio — a brand documentary and video production studio for B2B founders.

Your job: write a SHORT weekly LinkedIn outreach performance report for Ermo, the founder.
Tone: direct, no fluff, like a smart colleague summarising the week. Max 200 words.

Data quality: {quality} (early = < 5 requests, growing = 5-10 messaged, rich = 10+ messaged)

FUNNEL THIS WEEK:
{json.dumps(funnel, indent=2)}

LEAD ATTRIBUTE PATTERNS (avg_rank: 0=pending, 5=meeting):
{json.dumps(attr, indent=2)}

COMMENT ENGAGEMENT:
{json.dumps(comment, indent=2)}

Write:
1. ONE sentence on overall momentum (is it growing, flat, stalled?)
2. The single biggest pattern you see (which title/location converts best — or if data is too early, say so honestly)
3. ONE specific action Ermo should take next week based on the data
4. If data is early (< 5 requests), be honest that it's too early to draw conclusions — just show the raw numbers

No bullet points. Short paragraphs. Plain English."""

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    except Exception as e:
        log.warning(f"Report generation failed: {e}")
        funnel = patterns.get("funnel", {})
        return (
            f"Weekly snapshot: {funnel.get('requested',0)} connection requests sent, "
            f"{funnel.get('connected',0)} accepted ({funnel.get('acceptance_rate',0)}%), "
            f"{funnel.get('replied',0)} replied to messages ({funnel.get('reply_rate',0)}%), "
            f"{funnel.get('meeting',0)} meetings booked."
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (python analytics.py)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    patterns = run_weekly_analysis()
    print("\n── Patterns saved ──")
    print(f"Data quality : {patterns['data_quality']}")
    funnel = patterns.get("funnel", {})
    print(f"Funnel       : {funnel.get('requested',0)} req → {funnel.get('connected',0)} conn "
          f"→ {funnel.get('replied',0)} replied → {funnel.get('meeting',0)} meetings")

    print("\n── Weekly report ──")
    print(generate_weekly_report(patterns))
