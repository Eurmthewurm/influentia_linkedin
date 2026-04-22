# ─────────────────────────────────────────────────────────────────────────────
# message_ai.py  —  Claude-powered message generation
# Loads prompts from prompts/ folder — edit those files to change behaviour
# ─────────────────────────────────────────────────────────────────────────────
import os
import time
import logging
import anthropic
from config import (
    ANTHROPIC_API_KEY,
    YOUR_NAME,
    YOUR_COMPANY,
    YOUR_GOAL,
    YOUR_GOAL_LINK,
    YOUR_OFFERING,
)
try:
    from config import YOUR_WEBSITE
except ImportError:
    YOUR_WEBSITE = ""

log = logging.getLogger(__name__)


class MissingAPIKey(Exception):
    """Raised when the Claude API key is not configured."""
    pass


# Lazy client — avoids crashing on import when the user hasn't set a key yet.
_client = None

def _get_client():
    """Return a cached Anthropic client. Re-reads the key each time so that
    saving a new key via the dashboard takes effect without a server restart."""
    global _client
    # Re-read the key from the live config module (may have been updated)
    try:
        import importlib, config as _cfg
        # Cheap re-import — only actually reloads if something changed
        key = _cfg.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    except Exception:
        key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise MissingAPIKey(
            "No Claude API key set. Open the dashboard → Settings → Account "
            "and paste your key from https://console.anthropic.com."
        )
    if _client is None or getattr(_client, "_configured_key", None) != key:
        _client = anthropic.Anthropic(api_key=key)
        _client._configured_key = key
    return _client


def _create_message(**kwargs):
    """Wrapper around messages.create with retries for transient errors."""
    last_err = None
    for attempt in range(3):
        try:
            return _get_client().messages.create(**kwargs)
        except MissingAPIKey:
            raise
        except anthropic.RateLimitError as e:
            wait = (attempt + 1) * 20
            log.warning(f"Claude rate limit hit, backing off {wait}s (attempt {attempt+1}/3)")
            time.sleep(wait)
            last_err = e
        except anthropic.APIConnectionError as e:
            wait = (attempt + 1) * 5
            log.warning(f"Claude connection error ({e}). Retrying in {wait}s...")
            time.sleep(wait)
            last_err = e
        except anthropic.APIStatusError as e:
            # 5xx server errors are worth retrying; 4xx are not
            status = getattr(e, "status_code", 0)
            if 500 <= status < 600 and attempt < 2:
                wait = (attempt + 1) * 5
                log.warning(f"Claude server error {status}. Retrying in {wait}s...")
                time.sleep(wait)
                last_err = e
                continue
            raise
    # If we fell out of the loop, raise the last error
    if last_err:
        raise last_err

# Models — configurable via config.py, falls back to defaults
try:
    from config import CLAUDE_MODEL_CHEAP
except ImportError:
    CLAUDE_MODEL_CHEAP = None
try:
    from config import CLAUDE_MODEL_SMART
except ImportError:
    CLAUDE_MODEL_SMART = None

MODEL_CHEAP = CLAUDE_MODEL_CHEAP or "claude-haiku-4-5-20251001"   # first msg, follow-up, goodbye, classify
MODEL_SMART = CLAUDE_MODEL_SMART or "claude-sonnet-4-6"            # contextual replies only

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt loader
# ─────────────────────────────────────────────────────────────────────────────
def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts/ folder."""
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _fill_config_vars(template: str) -> str:
    """Replace config-level variables in a prompt template."""
    return template.replace("{agent_name}", YOUR_NAME) \
                   .replace("{company}", YOUR_COMPANY) \
                   .replace("{goal}", YOUR_GOAL) \
                   .replace("{goal_link}", YOUR_GOAL_LINK) \
                   .replace("{website}", YOUR_WEBSITE) \
                   .replace("{offering}", YOUR_OFFERING)


# ─────────────────────────────────────────────────────────────────────────────
# Profile data extraction (comprehensive — matches all Kakiyo fields)
# ─────────────────────────────────────────────────────────────────────────────
def _extract_prospect_data(prospect: dict, profile_data: dict, posts: list) -> dict:
    """
    Extract all available data from a LinkedIn profile into template variables.
    """
    pd = profile_data or {}

    # Posts (highest priority for personalisation)
    post_summaries = []
    for p in (posts or [])[:3]:
        text = (p.get("commentary", {}) or {}).get("text", {})
        if isinstance(text, dict):
            text = text.get("text", "")
        if isinstance(text, str) and text:
            post_summaries.append(text[:200])
    posts_text = "\n".join(post_summaries) if post_summaries else "No recent posts found."

    # Experience
    exp = pd.get("experience", []) or []
    current_exp = ""
    past_exps = []
    for e in exp:
        title = e.get("title", "")
        company = e.get("companyName") or (e.get("company", {}) or {}).get("name", "")
        desc = f"{title} at {company}" if company else title
        end = (e.get("timePeriod", {}) or {}).get("endDate", None)
        if not end:
            current_exp = desc
        else:
            past_exps.append(desc)

    # Skills
    skills = pd.get("skills", []) or []
    skills_text = ", ".join([s.get("name", "") for s in skills[:10]]) or "N/A"

    # Languages
    languages = pd.get("languages", []) or []
    langs_text = ", ".join([
        l.get("name", "") for l in languages
    ]) if languages else "N/A"

    # Education
    edu = pd.get("education", []) or []
    edu_text = "; ".join([
        f"{e.get('degreeName', '')} at {e.get('schoolName', '')}".strip(" at")
        for e in edu[:3]
    ]) or "N/A"

    # Certifications
    certs = pd.get("certifications", []) or []
    certs_text = "; ".join([
        c.get("name", "") for c in certs[:5]
    ]) if certs else "N/A"

    # Volunteer
    volunteer = pd.get("volunteer", []) or []
    volunteer_text = "; ".join([
        f"{v.get('role', '')} at {v.get('companyName', '')}".strip(" at")
        for v in volunteer[:3]
    ]) if volunteer else "N/A"

    # Recommendations
    recs = pd.get("recommendations", []) or []
    recs_text = " | ".join([
        r.get("recommendationText", "")[:100] for r in recs[:2]
    ]) if recs else "N/A"

    # Accomplishments / honors
    honors = pd.get("honors", []) or []
    honors_text = "; ".join([
        h.get("title", "") for h in honors[:3]
    ]) if honors else "N/A"

    # Summary as additional info
    summary = pd.get("summary", "") or ""

    return {
        "prospect_name":               prospect.get("name", ""),
        "prospect_headline":           pd.get("headline", prospect.get("title", "")),
        "prospect_location":           pd.get("locationName", "Australia"),
        "prospect_sector":             prospect.get("sector", ""),
        "prospect_company":            prospect.get("company", ""),
        "prospect_posts":              posts_text,
        "prospect_current_experience": current_exp or f"{prospect.get('title', '')} at {prospect.get('company', '')}",
        "prospect_past_experiences":   "; ".join(past_exps[:3]) or "N/A",
        "prospect_volunteer":          volunteer_text,
        "prospect_skills":             skills_text,
        "prospect_languages":          langs_text,
        "prospect_education":          edu_text,
        "prospect_certifications":     certs_text,
        "prospect_accomplishments":    honors_text,
        "prospect_recommendations":    recs_text,
        "prospect_additional":         summary[:300] if summary else "N/A",
    }


def _fill_prospect_vars(template: str, data: dict) -> str:
    """Replace prospect-level variables in a prompt template."""
    result = template
    for key, value in data.items():
        result = result.replace("{" + key + "}", str(value))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_NO_AI_PHRASES_RULE = """
# Non-negotiable rules — these patterns instantly reveal AI authorship:
- NO em dashes (—). Never. This is the single biggest AI tell. Use a comma, a period, or rewrite the sentence.
- NO emojis of any kind
- NO "Absolutely", "Certainly", "Great question", "That's a great point", "Great insight"
- NO "This resonates", "Couldn't agree more", "Love this", "So true"
- NO "I hope this finds you well", "Feel free to reach out", "Don't hesitate to"
- NO "particularly compelling", "genuinely rare", "incredibly important", "truly fascinating"
- NO "what makes this X is", "the tension between X and Y", "the reality is"
- NO hashtags
- NO buzzwords: leveraging, synergy, game-changer, revolutionize, streamline, utilize, impactful, actionable
- NO "It's worth noting", "It goes without saying", "At the end of the day", "In today's landscape"
- NO long complex sentences with multiple clauses — keep sentences short and punchy
- NO exclamation marks used just to seem enthusiastic
Write like a real human — plain words, short sentences, direct. Like texting a smart peer."""


def _clean_ai_text(text: str) -> str:
    """Post-processing safety net: strip em dashes and other AI tells that slip through."""
    import re
    # Em dashes are the #1 AI tell — replace with comma or period
    text = text.replace(" — ", ", ").replace("— ", ", ").replace(" —", ",")
    text = text.replace("\u2014", ",")  # unicode em dash
    text = text.replace("\u2013", "-")  # en dash to regular hyphen
    # Strip any emojis that slipped through
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Strip hashtags that slipped through
    text = re.sub(r'#\w+', '', text).strip()
    # Strip exclamation marks (AI loves them)
    text = text.replace("!", ".")
    # Fix double periods/commas from replacements
    text = re.sub(r'\.\.+', '.', text)
    text = re.sub(r',,+', ',', text)
    text = re.sub(r',\.', '.', text)
    # Strip common AI opener phrases that slip through
    _ai_openers = [
        "Absolutely", "Certainly", "Great question", "That's a great point",
        "Great insight", "This resonates", "Couldn't agree more", "Love this",
        "I hope this finds you well", "It's worth noting",
    ]
    for phrase in _ai_openers:
        if text.startswith(phrase):
            text = text[len(phrase):].lstrip(" ,.-:").strip()
    return text.strip()


def validate_message(text: str) -> tuple[bool, str]:
    """
    Validate a message before sending. Returns (is_valid, reason).
    Catches issues that could get the account flagged or look obviously automated.
    """
    if not text or len(text.strip()) < 10:
        return False, "Message too short (under 10 characters)"
    if len(text) > 500:
        return False, f"Message too long ({len(text)} chars, max 500)"
    if "\u2014" in text:
        return False, "Contains em dash (AI tell)"
    if any(text.lower().startswith(p.lower()) for p in [
        "I hope this", "I noticed", "I came across", "I was impressed",
        "Dear ", "Hello!", "Hi there!", "Hope you"
    ]):
        return False, "Opens with a flagged AI/template phrase"
    import re
    if re.search(r'#\w+', text):
        return False, "Contains hashtag"
    if text.count("!") > 1:
        return False, "Too many exclamation marks"
    if "http" in text.lower() or "calendly" in text.lower() or ".com" in text.lower():
        # Links in first messages look like spam
        return False, "Contains a link (not allowed in first messages)"
    return True, "OK"


def generate_first_message(prospect: dict, profile_data: dict, posts: list) -> str:
    """Generate the personalised opening message for a newly connected lead."""
    template = _load_prompt("first_message.txt")
    template = _fill_config_vars(template)
    data     = _extract_prospect_data(prospect, profile_data, posts)
    prompt   = _fill_prospect_vars(template, data)
    # Append anti-AI rules so the first message never sounds robotic
    prompt  += "\n" + _NO_AI_PHRASES_RULE

    response = _create_message(
        model=MODEL_CHEAP,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return _clean_ai_text(response.content[0].text.strip())


def generate_follow_up(prospect: dict, days_since: int, first_msg_text: str) -> str:
    """Generate a follow-up message for a prospect who hasn't replied."""
    template = _load_prompt("follow_up.txt")
    template = _fill_config_vars(template)
    template = template.replace("{prospect_name}", prospect.get("name", ""))
    template = template.replace("{prospect_headline}", prospect.get("title", ""))
    template = template.replace("{prospect_company}", prospect.get("company", ""))
    template = template.replace("{prospect_sector}", prospect.get("sector", ""))
    template = template.replace("{days_since_first_message}", str(days_since))
    template = template.replace("{first_message_text}", first_msg_text)
    template += "\n" + _NO_AI_PHRASES_RULE

    response = _create_message(
        model=MODEL_CHEAP,
        max_tokens=128,
        messages=[{"role": "user", "content": template}],
    )
    return _clean_ai_text(response.content[0].text.strip())


def generate_reply(prospect: dict, conversation_history: list) -> str:
    """Generate a contextual reply continuing an active conversation."""
    context_template = _load_prompt("context.txt")
    system = _fill_config_vars(context_template)

    # Append optional DM tone instructions if saved
    try:
        dm_tone = _load_prompt("dm_tone.txt").strip()
    except Exception:
        dm_tone = ""
    if dm_tone:
        system += f"\n\n# Tone & Style Instructions\n{dm_tone}\n"

    system += _NO_AI_PHRASES_RULE

    # Count exchanges so the AI knows where in the funnel we are
    ai_messages = [m for m in conversation_history if m["role"] == "ai"]
    exchange_count = len(ai_messages)

    if exchange_count >= 3:
        funnel_note = "You have been chatting for a while. If they seem genuinely engaged, it is time to naturally steer toward a call or share the booking link. Do not force it — only if it fits the flow."
    elif exchange_count == 2:
        funnel_note = "You have exchanged a couple of messages. If they are warm and curious, start moving toward next steps. You can mention the website if they want to know more."
    else:
        funnel_note = "This is an early exchange. Focus on building rapport. Do not pitch or share links yet."

    system += f"""

# Current Prospect Context
- Name: {prospect.get('name', '')}
- Title: {prospect.get('title', '')}
- Company: {prospect.get('company', '')}
- Sector: {prospect.get('sector', '')}
- Exchange number: {exchange_count + 1} (this will be your {exchange_count + 1}{"st" if exchange_count == 0 else "nd" if exchange_count == 1 else "rd" if exchange_count == 2 else "th"} reply)

# Funnel Guidance
{funnel_note}
"""

    messages = []
    for msg in conversation_history:
        role = "assistant" if msg["role"] == "ai" else "user"
        messages.append({"role": role, "content": msg["content"]})

    response = _create_message(
        model=MODEL_SMART,
        max_tokens=256,
        system=system,
        messages=messages,
    )
    return _clean_ai_text(response.content[0].text.strip())


def generate_goodbye(prospect: dict) -> str:
    """Generate a short, warm closing message for a prospect who isn't interested."""
    name = prospect.get("name", "").split()[0]  # first name only
    prompt = f"""Write a single short closing message (1-2 sentences max) to send on LinkedIn to {name}, who has just indicated they are not interested in what you offered.

Rules:
- Warm and genuine, not fake cheerful
- Leave the door open without being desperate or grovelling
- Sound like a real person, not a corporate script
- No emojis, no em dashes, no exclamation marks
- Under 20 words

Good examples:
"No worries at all, makes sense. If that ever changes you know where to find me."
"Totally fair, appreciate you taking the time either way."
"Understood, good luck with everything."

Reply with ONLY the closing message. Nothing else."""

    response = _create_message(
        model="claude-haiku-4-5-20251001",  # cheap, simple task
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def classify_conversation_status(prospect: dict, conversation_history: list) -> str:
    """Classify conversation: interested / not_interested / meeting_booked / ongoing"""
    history_text = "\n".join([
        f"{'AI' if m['role']=='ai' else 'PROSPECT'}: {m['content']}"
        for m in conversation_history
    ])

    name    = prospect.get("name", "the prospect")
    title   = prospect.get("title", "")
    company = prospect.get("company", "")
    context = f"{name}"
    if title or company:
        context += f" ({title}{' @ ' + company if company else ''})"

    prompt = f"""Classify the current status of this LinkedIn outreach conversation with {context}.
Reply with ONLY one of: interested / not_interested / meeting_booked / ongoing

not_interested = prospect clearly said no, not now, we're good, handle in-house, not relevant, stop messaging me, or anything that ends the conversation
meeting_booked = prospect confirmed a call, meeting, or clicked a booking link and said they booked
interested = prospect is engaged, asking follow-up questions, wants to know more, mentioned pricing, timelines, or next steps
ongoing = they replied but no clear signal yet — polite but non-committal

Conversation:
{history_text}

Status:"""

    response = _create_message(
        model="claude-haiku-4-5-20251001",  # cheap classification task
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip().lower()
    valid = {"interested", "not_interested", "meeting_booked", "ongoing"}
    return result if result in valid else "ongoing"
