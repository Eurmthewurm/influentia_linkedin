# ─────────────────────────────────────────────────────────────────────────────
# reddit_signal.py  —  Reddit Signal (social listening) + Engage (commenting)
#
# Two separate pipelines, completely independent of LinkedIn:
#
#   Signal  — scan subreddits for ICP pain-point posts → surface in dashboard
#   Engage  — AI drafts a helpful, non-promotional comment → user approves → post
#
# No credentials required for Signal.
# Engage requires Reddit OAuth credentials in .env (see reddit_client.py).
# ─────────────────────────────────────────────────────────────────────────────
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# ── ICP presets ──────────────────────────────────────────────────────────────
# Each preset bundles the three things that define an ICP scan:
#   1. subreddits — where to look
#   2. queries    — what pain phrases to search for
#   3. scoring    — the prompt body Claude uses to rate post relevance
#
# Switch the active preset via state['reddit_settings']['active_icp'] (one of:
# 'authentik', 'influentia', 'custom'). UI does this with a one-click switcher
# at the top of the Reddit tab. If 'custom', the user's own subreddits/queries
# from state['reddit_settings'] are used and scoring falls back to 'authentik'
# unless the user supplied a custom_scoring_criteria string.

ICP_PRESETS = {
    # ── Authentik Studio: find LinkedIn personal-brand clients ─────────────
    "authentik": {
        "label":       "Authentik Studio",
        "description": "B2B founders, consultants, agency owners who need LinkedIn visibility, content strategy, or inbound leads. Customers buy Authentik's done-for-you LinkedIn content + brand documentary work.",
        "subreddits": [
            "b2bmarketing", "marketing", "consulting", "entrepreneur",
            "smallbusiness", "startups", "linkedin", "content_marketing",
            "freelance", "agency", "Entrepreneur", "SaaS",
        ],
        "queries": [
            # LinkedIn-specific pain (hottest buying signals)
            "LinkedIn content not working",
            "how to grow on LinkedIn",
            "LinkedIn no engagement",
            "LinkedIn personal brand",
            "thought leadership LinkedIn",
            "LinkedIn ghostwriter",
            # Lead generation / client acquisition
            "not getting clients",
            "how to get more clients",
            "struggling to get leads",
            "B2B lead generation help",
            "need more consulting clients",
            # Content creation pain
            "content creation too time consuming",
            "no time to create content",
            "content strategy B2B",
        ],
        "scoring_criteria": """ICP (Ideal Customer Profile):
- B2B founders, consultants, coaches, or agency owners
- Struggle with: LinkedIn visibility, content creation, getting inbound leads, building authority
- Actively looking for solutions, asking for advice, or expressing frustration

Rate this post's buying signal strength on a scale of 1-10:

10: Person IS the ICP and explicitly expresses a pain we solve (LinkedIn content, personal brand, lead gen, thought leadership)
8-9: Strong ICP signal — founder/consultant struggling with visibility, clients, or content strategy
6-7: Adjacent pain — growing a B2B business, needing clients, marketing their services
4-5: General business pain but not clearly content/LinkedIn related
1-3: Wrong audience, irrelevant topic, or already solved""",
        "context_label": "Authentik Studio — a B2B content agency that helps founders, consultants, and agency owners build a LinkedIn personal brand and generate inbound leads through thought leadership content.",
    },

    # ── Influentia: find outreach-tool buyers ─────────────────────────────
    "influentia": {
        "label":       "Influentia",
        "description": "B2B founders / agency owners / consultants tired of being their own SDR, frustrated with cloud-IP tools (Expandi/Phantombuster/Lemlist), or looking for a privacy-first LinkedIn outreach tool. Customers buy Influentia ($97/mo, local-first).",
        "subreddits": [
            # B2B founders + sales operators
            "SaaS", "Entrepreneur", "smallbusiness", "startups",
            "sales", "B2BSaaS", "Outbound", "salesops",
            # Adjacent: agency / consulting / freelance who do their own outreach
            "agency", "consulting", "freelance",
            # Pain-specific subs
            "linkedin", "marketing",
        ],
        "queries": [
            # Direct competitor / category complaints (hottest buying signals)
            "Expandi alternative",
            "Phantombuster alternative",
            "Lemlist alternative",
            "Apollo alternative",
            "Dux-Soup alternative",
            "linkedin automation banned",
            "linkedin account restricted automation",
            "outreach tool got me banned",
            # Founder-as-SDR pain
            "founder doing own sales",
            "hate cold email",
            "hate cold outreach",
            "cant afford SDR",
            "founder hates prospecting",
            "outbound feels spammy",
            # Tooling search
            "linkedin outreach tool recommendations",
            "best B2B prospecting tool",
            "linkedin DM automation",
            "AI outreach tool",
            "linkedin lead gen tool",
            # Privacy / data concerns
            "linkedin cookie automation",
            "outreach tool privacy",
        ],
        "scoring_criteria": """ICP (Ideal Customer Profile):
- B2B founder, agency owner, or consultant doing their OWN outreach (not a sales team)
- Sells to other businesses (services or B2B SaaS), $5k-$50k deal size
- Active on LinkedIn (or wants to be), allergic to template-based tools
- Frustrated with cloud-IP tools (Expandi, Phantombuster, Lemlist, Dux-Soup, Apollo) OR has been banned by one
- Cares about privacy / data security / running tools on their own machine
- Cannot justify a full-time SDR yet ($30k+ MRR is the typical breakpoint)

Rate this post's buying signal strength on a scale of 1-10:

10: Person IS the ICP and explicitly looking for a different LinkedIn outreach tool, or just got banned/restricted by a cloud-IP automation tool, or is openly trying alternatives to Expandi/Lemlist/Phantombuster
8-9: Strong ICP signal — solo founder/consultant fed up with their current outreach tool, asking for recommendations, or describing the exact pain Influentia solves (e.g. "doing my own sales, can't afford SDR", "outreach feels spammy")
6-7: Adjacent pain — B2B founder talking about pipeline/prospecting struggles in general, or asking about LinkedIn growth without naming a tool
4-5: General sales/marketing frustration but unclear if outreach tool fits
1-3: Wrong audience (consumer/e-commerce, recruiters, enterprise SDR teams), or asking for sales-team-grade tools (Outreach.io / Salesloft), or content-creator territory (coaches, course creators)""",
        "context_label": "Influentia — a local-first LinkedIn + Reddit outreach autopilot for B2B founders. Runs on the customer's machine ($97/mo). Privacy-first alternative to cloud tools like Expandi, Phantombuster, Lemlist, Dux-Soup, Apollo.",
    },
}


def get_active_icp(settings: dict) -> dict:
    """Resolve the active ICP preset from settings, with sensible defaults."""
    name = (settings or {}).get("active_icp", "authentik")
    if name in ICP_PRESETS:
        return ICP_PRESETS[name]
    # Custom: build a shim that uses the user's subreddits/queries but falls
    # back to authentik scoring unless explicit custom_scoring_criteria given.
    base = dict(ICP_PRESETS["authentik"])
    if settings.get("subreddits"):
        base["subreddits"] = settings["subreddits"]
    if settings.get("queries"):
        base["queries"] = settings["queries"]
    if settings.get("custom_scoring_criteria"):
        base["scoring_criteria"] = settings["custom_scoring_criteria"]
    if settings.get("custom_context_label"):
        base["context_label"] = settings["custom_context_label"]
    base["label"] = "Custom"
    return base


# ── Backwards-compat exports (older callers may import these directly) ──
DEFAULT_SUBREDDITS = ICP_PRESETS["authentik"]["subreddits"]
DEFAULT_QUERIES    = ICP_PRESETS["authentik"]["queries"] + ["Influentia", "linkedin outreach tool"]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _hours_ago(n: int) -> float:
    """Return Unix timestamp for N hours ago."""
    return (datetime.now(timezone.utc) - timedelta(hours=n)).timestamp()


# ── Signal scanning ───────────────────────────────────────────────────────────

_MAX_POST_AGE_DAYS = 14   # never surface posts older than this


def scan_signals(state: dict, max_results: int = 20,
                 time_filter: str = "week") -> list:
    """
    Search configured subreddits for ICP pain-point posts.
    AI-scores each post (1-10). Saves to state['reddit_signals'].
    Returns list of new signals added this run.

    Does NOT require Reddit credentials — uses public JSON API.
    """
    from reddit_client import search_posts
    from ai_proxy import call_ai as _ai
    from state_manager import save_state

    settings = state.get("reddit_settings", {})
    icp      = get_active_icp(settings)
    # Custom subreddits/queries from settings override the preset's defaults.
    subreddits = settings.get("subreddits") or icp["subreddits"]
    queries    = settings.get("queries")    or icp["queries"]

    # Hard age cutoff — reject posts older than _MAX_POST_AGE_DAYS regardless
    # of what Reddit's API returns (it can resurface old posts via relevance).
    age_cutoff = (datetime.now(timezone.utc) - timedelta(days=_MAX_POST_AGE_DAYS)).timestamp()

    # Build seen-set from existing signals
    existing_ids = {s["post_id"] for s in state.get("reddit_signals", [])}

    # Never draft a reply to our own posts
    import os as _os
    _my_reddit_username = _os.environ.get("REDDIT_USERNAME", "").strip().lower()

    raw_posts = []
    seen_ids  = set(existing_ids)

    # query_map: post_id → list of matching queries (for keyword tags in UI)
    query_map: dict = {}

    for query in queries[:10]:   # cap queries to avoid hammering Reddit
        # Try subreddit-scoped search first; fall back to global if empty
        posts = search_posts(query, subreddits=subreddits,
                             limit=25, time_filter=time_filter)
        if not posts:
            posts = search_posts(query, subreddits=None,
                                 limit=10, time_filter=time_filter)
            log.info(f"Reddit Signal: query {query!r} → 0 in subreddits, {len(posts)} global")
        else:
            log.info(f"Reddit Signal: query {query!r} → {len(posts)} posts")
        for p in posts:
            pid = p["post_id"]
            # Drop posts older than the age cutoff
            if p.get("created_utc", 0) < age_cutoff:
                continue
            # Never reply to our own posts
            if _my_reddit_username and p.get("author", "").lower() == _my_reddit_username:
                log.info(f"Reddit Signal: skipping own post '{p['title'][:60]}…'")
                continue
            # Track which queries matched this post (for UI tags)
            query_map.setdefault(pid, [])
            if query not in query_map[pid]:
                query_map[pid].append(query)
            if pid not in seen_ids:
                seen_ids.add(pid)
                raw_posts.append(p)
        time.sleep(1)   # polite pause between queries
        if len(raw_posts) >= 80:
            break

    log.info(f"Reddit Signal: {len(raw_posts)} unique raw posts collected")
    # Store raw count for the API response to surface in the UI
    state["_reddit_last_raw"] = len(raw_posts)

    if not raw_posts:
        log.warning("Reddit Signal: zero posts from all queries — Reddit may be blocking or returning empty results.")
        return []

    log.info(f"Reddit Signal: {len(raw_posts)} posts collected — AI scoring now…")

    # ── AI scoring ────────────────────────────────────────────────────────────
    from config import YOUR_OFFERING
    offering_snippet = YOUR_OFFERING[:400].split("\n")[0].strip().lstrip("#").strip()

    scored_signals = []
    for post in raw_posts[:40]:   # score up to 40 new posts
        score, reason = _score_post(post, offering_snippet, _ai, icp)
        if score < 4:
            continue   # not relevant enough to surface
        lead_score = score * 10   # 1-10 → 10-100, mirrors Pulse-style scoring
        signal = {
            "id":           str(uuid.uuid4())[:8],
            "post_id":      post["post_id"],
            "post_fullname": post.get("fullname", ""),
            "title":        post["title"],
            "text":         post["text"][:600],
            "url":          post["url"],
            "subreddit":    post["subreddit"],
            "author":       post["author"],
            "score":        post["score"],
            "num_comments": post["num_comments"],
            "created_utc":  post["created_utc"],
            "relevance":    score,
            "lead_score":   lead_score,
            "matched_queries": query_map.get(post["post_id"], []),
            "relevance_reason": reason,
            "scanned_at":   _now_iso(),
            "is_new":       True,       # cleared by UI after first view
            "status":       "new",      # new | comment_drafted | commented | dismissed
            "reddit_comment_id": None,  # set after comment is posted
        }
        scored_signals.append(signal)
        time.sleep(0.1)   # tiny pause between AI calls

    # Sort best first
    scored_signals.sort(key=lambda x: x["relevance"], reverse=True)

    # Prepend new signals (most recent scan at top)
    state.setdefault("reddit_signals", [])
    state["reddit_signals"] = scored_signals + state["reddit_signals"]

    # Expire signals whose Reddit post is older than 45 days
    expire_cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).timestamp()
    state["reddit_signals"] = [
        s for s in state["reddit_signals"]
        if s.get("created_utc", 0) >= expire_cutoff or s.get("status") == "commented"
    ]

    # Keep only the 200 most recent signals
    state["reddit_signals"] = state["reddit_signals"][:200]

    # Record when this scan ran (used by UI to highlight "from this scan")
    state["reddit_last_scan_at"] = _now_iso()

    save_state(state)
    log.info(f"Reddit Signal: saved {len(scored_signals)} new signals.")
    return scored_signals


def _score_post(post: dict, offering_snippet: str, ai_fn, icp: dict = None) -> tuple:
    """
    Ask Claude to rate how relevant this post is for the active ICP.
    Returns (score: int 1-10, reason: str).
    Falls back to (5, "scoring unavailable") on error.

    `icp` is one of the ICP_PRESETS values (or a custom dict). When None,
    defaults to Authentik for backwards-compat with older callers.
    """
    if icp is None:
        icp = ICP_PRESETS["authentik"]

    context_label    = icp.get("context_label",    ICP_PRESETS["authentik"]["context_label"])
    scoring_criteria = icp.get("scoring_criteria", ICP_PRESETS["authentik"]["scoring_criteria"])

    prompt = f"""You evaluate Reddit posts for {context_label}

{scoring_criteria}

Post title: {post['title'][:200]}
Subreddit: r/{post['subreddit']}
Post text: {post['text'][:500]}

Reply with exactly two lines:
SCORE: <number 1-10>
REASON: <one specific sentence identifying the pain point and why it fits or doesn't>"""

    try:
        resp = ai_fn(
            messages=[{"role": "user", "content": prompt}],
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
        )
        lines = [l.strip() for l in resp.strip().splitlines() if l.strip()]
        score  = 5
        reason = ""
        for line in lines:
            if line.upper().startswith("SCORE:"):
                try:
                    score = int(line.split(":", 1)[1].strip())
                    score = max(1, min(10, score))
                except ValueError:
                    pass
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()
        return score, reason
    except Exception as e:
        log.warning(f"Reddit signal scoring failed: {e}")
        return 5, "scoring unavailable"


# ── Comment generation ────────────────────────────────────────────────────────

def generate_reddit_comment(signal: dict, state: dict) -> str:
    """
    Draft a helpful, non-promotional comment for a Reddit post.
    Rule: NEVER mention your company or services. Add genuine value.
    Returns the draft text.
    """
    from ai_proxy import call_ai as _ai
    from config import YOUR_OFFERING, YOUR_NAME

    offering_snippet = YOUR_OFFERING[:400].split("\n")[0].strip().lstrip("#").strip()

    prompt = f"""You are {YOUR_NAME}, a person on Reddit who helps with topics related to: {offering_snippet}.

Write a Reddit comment on this post. It MUST sound like a real human wrote it — not a consultant, not a copywriter, not a marketer.

CRITICAL — NEVER fabricate personal stories or numbers:
- Do NOT invent specific revenue figures, MRR numbers, client counts, or timelines you don't actually know
- Do NOT write "I was at $35K MRR" or "I had 50 clients" or "this happened to me 18 months ago" — these are made-up
- Do NOT claim personal experiences with specific outcomes that can't be verified
- If you have no real personal experience to share, offer a genuine observation or ask a useful question instead
- Authenticity > relatability — a vague honest comment beats a specific fabricated one

What to AVOID entirely:
- "Great question!" ❌
- "One thing I've found helpful is..." ❌
- "It really comes down to understanding your..." ❌
- "From my experience, the key is to..." ❌
- "I'd recommend looking into..." ❌
- rhetorical questions like "Have you tried..." ❌

Good examples of what WORKS on Reddit:
- "Yeah this is super common. Usually it's less about the channel and more about whether you've actually nailed who you're targeting."
- "Honestly it depends on your niche. For B2B services, being direct about what you do works way better than the polished corporate stuff."
- "Most tools overcomplicate this. Simpler approach usually wins — what does your current process actually look like?"
- "What kind of content are you putting out? That usually tells you whether it's a strategy problem or a consistency problem."

Rules:
- NEVER mention your company, service, product, or any promotional content
- NEVER invent specific numbers, milestones, or personal anecdotes — only say what is genuinely true
- Write like you're having a beer with a friend, not like you're giving a TED talk
- Use contractions (don't, can't, it's, I've, you're)
- Be slightly informal — this is Reddit
- 2-4 sentences. Short. Punchy.
- NO em dashes (—), NO bullet lists, NO headers, NO bold/italic
- NO emojis, NO "!", NO "?" unless it's a genuine question to the OP
- No sign-offs, no "hope this helps", no preamble
- Write like you typed it in 10 seconds, not like you spent 10 minutes polishing it

Post title: {signal['title'][:200]}
Subreddit: r/{signal['subreddit']}
Post text: {signal['text'][:600]}

Write ONLY the comment text. Nothing else."""

    try:
        comment = _ai(
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-6",
            max_tokens=200,
            temperature=0.9,
        )
        return comment.strip()
    except Exception as e:
        log.error(f"Reddit comment generation failed: {e}")
        raise


# ── Comment state helpers ─────────────────────────────────────────────────────

def add_reddit_pending_comment(state: dict, signal: dict,
                               draft_text: str) -> dict:
    """Queue a drafted Reddit comment for user approval."""
    from state_manager import save_state
    entry = {
        "id":           str(uuid.uuid4())[:8],
        "signal_id":    signal["id"],
        "post_id":      signal["post_id"],
        "post_fullname": signal.get("post_fullname", ""),
        "post_title":   signal["title"],
        "post_text":    signal["text"][:500],
        "post_url":     signal["url"],
        "subreddit":    signal["subreddit"],
        "author":       signal["author"],
        "draft_text":   draft_text,
        "final_text":   "",
        "created_at":   _now_iso(),
        "status":       "pending",   # pending | approved | posted | skipped
        "posted_at":    None,
        "comment_fullname": None,    # Reddit t1_xxxx after posting
    }
    state.setdefault("reddit_pending_comments", [])
    state["reddit_pending_comments"].append(entry)

    # Mark the source signal as drafted
    for s in state.get("reddit_signals", []):
        if s["id"] == signal["id"]:
            s["status"] = "comment_drafted"
            break

    save_state(state)
    return entry


def mark_reddit_comment(state: dict, comment_id: str,
                        new_status: str, final_text: str = "") -> dict | None:
    """Approve / skip / post a Reddit comment draft."""
    from state_manager import save_state
    for c in state.get("reddit_pending_comments", []):
        if c["id"] == comment_id:
            c["status"] = new_status
            if final_text:
                c["final_text"] = final_text
            if new_status == "posted":
                c["posted_at"] = _now_iso()
                # Move to posted list
                state.setdefault("reddit_posted_comments", [])
                state["reddit_posted_comments"].append(dict(c))
                state["reddit_pending_comments"] = [
                    p for p in state["reddit_pending_comments"]
                    if p["id"] != comment_id
                ]
                # Update the source signal
                for s in state.get("reddit_signals", []):
                    if s["post_id"] == c["post_id"]:
                        s["status"] = "commented"
                        s["reddit_comment_id"] = c.get("comment_fullname", "")
                        break
            save_state(state)
            return c
    return None


# ── Reply monitoring ──────────────────────────────────────────────────────────

def check_reddit_replies(state: dict) -> list:
    """
    Fetch replies to our posted Reddit comments from the inbox.
    Requires OAuth credentials. Saves new replies to state['reddit_reply_queue'].
    Returns list of new replies found.
    """
    try:
        from reddit_client import RedditClient
    except Exception as e:
        log.warning(f"Reddit credentials not set — cannot check replies: {e}")
        return []

    from state_manager import save_state

    try:
        client = RedditClient()
    except RuntimeError as e:
        log.warning(f"Reddit client init failed: {e}")
        return []

    try:
        messages = client.get_inbox_replies()
    except Exception as e:
        log.warning(f"Reddit inbox check failed: {e}")
        return []

    # Build set of already-seen reply IDs
    seen = {r["reply_id"] for r in state.get("reddit_reply_queue", [])}

    # Build set of our posted comment fullnames so we only track replies TO our comments
    our_comments = {
        c.get("comment_fullname", "")
        for c in state.get("reddit_posted_comments", [])
        if c.get("comment_fullname")
    }

    new_replies = []
    for msg in messages:
        if msg["id"] in seen:
            continue
        # Only track if it's a reply to one of our comments
        parent = msg.get("parent_id", "")
        if our_comments and parent not in our_comments:
            continue

        reply = {
            "id":            str(uuid.uuid4())[:8],
            "reply_id":      msg["id"],
            "author":        msg["author"],
            "body":          msg["body"],
            "context_url":   msg.get("context_url", ""),
            "parent_id":     parent,
            "created_utc":   msg.get("created_utc", 0),
            "received_at":   _now_iso(),
            "status":        "pending",   # pending | replied | dismissed
            "ai_draft":      "",
        }
        new_replies.append(reply)

        # Mark read in Reddit inbox
        try:
            client.mark_read(msg["id"])
        except Exception:
            pass

    if new_replies:
        state.setdefault("reddit_reply_queue", [])
        state["reddit_reply_queue"].extend(new_replies)
        save_state(state)
        log.info(f"Reddit: {len(new_replies)} new replies in inbox.")

    return new_replies


def generate_reddit_reply(reply: dict, state: dict) -> str:
    """Draft a helpful reply to someone who responded to our Reddit comment."""
    from ai_proxy import call_ai as _ai
    from config import YOUR_NAME

    # Find context — the original comment we posted
    our_comment_text = ""
    parent_id = reply.get("parent_id", "")
    for c in state.get("reddit_posted_comments", []):
        if c.get("comment_fullname") == parent_id:
            our_comment_text = c.get("final_text") or c.get("draft_text", "")
            break

    prompt = f"""You are {YOUR_NAME}, responding on Reddit to someone who replied to your comment.

Your original comment:
"{our_comment_text[:300]}"

Their reply:
"{reply['body'][:500]}"

Write a natural, helpful follow-up reply. Rules:
- Be genuine and conversational — this is Reddit, not LinkedIn
- NEVER be promotional or mention your services unless directly asked
- Keep it short: 2-4 sentences max
- Answer their question or build on their point
- NO em dashes, NO bullet lists, NO emojis unless they used them

Write ONLY the reply text."""

    try:
        draft = _ai(
            messages=[{"role": "user", "content": prompt}],
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
        )
        return draft.strip()
    except Exception as e:
        log.error(f"Reddit reply generation failed: {e}")
        raise
