# ─────────────────────────────────────────────────────────────────────────────
# message_ai.py  —  Claude-powered message generation (Kakiyo framework)
# ─────────────────────────────────────────────────────────────────────────────
import anthropic
from config import (
    ANTHROPIC_API_KEY,
    YOUR_NAME,
    YOUR_COMPANY,
    YOUR_GOAL,
    YOUR_GOAL_LINK,
    YOUR_OFFERING,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL   = "claude-sonnet-4-5"   # best performance/cost (update every few months)


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PROMPT  (governs ALL replies after the first message)
# Based on Kakiyo's Context Prompt template
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_PROMPT = f"""# Role
You are {YOUR_NAME}, a representative of {YOUR_COMPANY}. You are reaching out personally
to prospects on LinkedIn and holding natural, human-like conversations.

# Mission
Your mission is to engage in personalized conversations that lead to one of two outcomes:
- If interest is detected, guide them to {YOUR_GOAL} using this link: {YOUR_GOAL_LINK}
- If no interest is expressed, maintain professionalism, provide value, and exit gracefully without pushing.

# Our Offering
{YOUR_OFFERING}

# Instructions

## Output
1. Always only return the message as the output and nothing else
2. Always keep your messages under 30 words

## Style
1. Do not ever start your sentence with a verb — this feels abrupt or commanding
2. Always include an explicit subject pronoun
3. Write as if speaking orally
4. Use pragmatic, straight-to-the-point language
5. Never appear robotic or formal
6. Write in English
7. Do not skip lines in your messages
8. Do not ever use the em dash (—) or the dash (-). Use commas or periods instead.

## Conversation Flow
1. Maintain a moderate number of questions throughout the conversation
2. Do not ask more than 2 questions during the entire conversation
3. Show genuine interest without being scripted
4. Don't send any link too quickly, but don't wait too long if the prospect is interested
5. Do not repeat the prospect's name in every message

## Goal Rules
1. When the prospect shows real interest in the product, propose {YOUR_GOAL}
2. Once they say they would like to {YOUR_GOAL}, share the link: {YOUR_GOAL_LINK}

# Special Cases
1. If unrelated requests: politely decline and redirect to the relevant topic
2. If asked about a free trial: there is no free trial for this product
3. For company names in CAPS: capitalize the first letter only
"""


# ─────────────────────────────────────────────────────────────────────────────
# FIRST MESSAGE PROMPT  (generates the opening icebreaker after connection)
# Based on Kakiyo's First Message Prompt template
# ─────────────────────────────────────────────────────────────────────────────
def build_first_message_prompt(prospect: dict, profile_data: dict, posts: list) -> str:
    """
    Build the full first-message prompt with prospect data injected.

    prospect: dict from state_manager (name, title, company, sector, etc.)
    profile_data: raw LinkedIn profile dict from linkedin_client.get_profile()
    posts: list of recent posts from linkedin_client.get_profile_posts()
    """
    name      = prospect.get("name", "")
    headline  = profile_data.get("headline", prospect.get("title", ""))
    location  = profile_data.get("locationName", "Australia")

    # Summarise posts
    post_summaries = []
    for p in posts[:3]:
        text = (p.get("commentary", {}) or {}).get("text", {})
        if isinstance(text, dict):
            text = text.get("text", "")
        if text:
            post_summaries.append(text[:200])
    posts_text = "\n".join(post_summaries) if post_summaries else "No recent posts found."

    # Experience
    exp = profile_data.get("experience", [])
    current_exp = ""
    past_exps   = []
    for e in exp:
        title   = e.get("title", "")
        company = (e.get("companyName") or e.get("company", {}).get("name", ""))
        start   = (e.get("timePeriod", {}) or {}).get("startDate", {})
        end     = (e.get("timePeriod", {}) or {}).get("endDate", None)
        desc    = f"{title} at {company}"
        if not end:
            current_exp = desc
        else:
            past_exps.append(desc)

    # Skills
    skills = profile_data.get("skills", [])
    skills_text = ", ".join([s.get("name", "") for s in skills[:10]]) or "N/A"

    # Education
    edu = profile_data.get("education", [])
    edu_text = "; ".join([
        f"{e.get('degreeName','')} at {e.get('schoolName','')}".strip(" at")
        for e in edu[:3]
    ]) or "N/A"

    return f"""# Task
Generate a short, ultra-personalized LinkedIn icebreaker for {name}.
- Point out one specific fact that smoothly opens the conversation.
- Focus on the person, not the company, without exaggeration.
- End with one short, bold, meaningful open question linked to what you're selling,
  answerable in very few words.

# Instructions

## Style
1. Always greet the prospect in the first message only
2. Do not use empty words: "impressed", "inspiring", "admire", "love", "fascinating", "noticed"
3. Keep the message concise and natural, avoid fluff
4. Write in a tone that feels oral, pragmatic, and straight to the point
5. Never appear robotic or overly formal
6. Do not ever use em dash or regular dash. Use commas or periods instead.
7. Keep it under 50 words total

## Personalization
1. Show you've done real research: mention a specific detail, not just their title
2. Prove you know them better than the average prospector

## Conversation Rules
1. Offer value upfront; don't ask generic favors
2. NEVER ask for a meeting in the first DM
3. Ask one bold, hard-hitting question that makes them pause

# Our Product/Service Description
{YOUR_OFFERING}

# Prospect Information

## Basic Profile
- Full name: {name}
- Headline: {headline}
- Location: {location}
- Industry/Sector: {prospect.get('sector', '')}

## Recent Posts (highest priority for personalisation)
{posts_text}

## Experience
- Current: {current_exp or prospect.get('title','') + ' at ' + prospect.get('company','')}
- Past: {'; '.join(past_exps[:3]) or 'N/A'}

## Skills
{skills_text}

## Education
{edu_text}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_first_message(prospect: dict, profile_data: dict, posts: list) -> str:
    """
    Generate the personalised opening message for a newly connected lead.
    Returns the message text.
    """
    prompt = build_first_message_prompt(prospect, profile_data, posts)
    response = _client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def generate_reply(prospect: dict, conversation_history: list) -> str:
    """
    Generate a contextual reply continuing an active conversation.

    conversation_history: list of {"role": "ai"|"prospect", "content": "..."}
    Returns the AI's next message.
    """
    # Convert our internal history format to Anthropic messages format
    messages = []
    for msg in conversation_history:
        role = "assistant" if msg["role"] == "ai" else "user"
        messages.append({"role": role, "content": msg["content"]})

    # Add context about who we're talking to
    system = CONTEXT_PROMPT + f"""

# Current Prospect Context
- Name: {prospect.get('name', '')}
- Title: {prospect.get('title', '')}
- Company: {prospect.get('company', '')}
- Sector: {prospect.get('sector', '')}
"""

    response = _client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=system,
        messages=messages,
    )
    return response.content[0].text.strip()


def classify_conversation_status(prospect: dict, conversation_history: list) -> str:
    """
    Ask Claude to classify where the conversation stands.
    Returns: "interested" | "not_interested" | "meeting_booked" | "ongoing"
    """
    history_text = "\n".join([
        f"{'AI' if m['role']=='ai' else 'PROSPECT'}: {m['content']}"
        for m in conversation_history
    ])

    prompt = f"""Given this LinkedIn conversation, classify its current status.
Reply with ONLY one of these words: interested / not_interested / meeting_booked / ongoing

Conversation:
{history_text}

Status:"""

    response = _client.messages.create(
        model=MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip().lower()

    valid = {"interested", "not_interested", "meeting_booked", "ongoing"}
    return result if result in valid else "ongoing"
