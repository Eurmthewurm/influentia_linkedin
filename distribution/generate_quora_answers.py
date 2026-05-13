#!/usr/bin/env python3
"""Generate Quora answers and Medium republish drafts"""
import os, json
from datetime import date

DIST = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
os.makedirs(DIST, exist_ok=True)
TODAY = date.today().isoformat()

TRACK = os.path.join(DIST, "quora_medium_progress.json")
if os.path.exists(TRACK):
    with open(TRACK) as f:
        p = json.load(f)
else:
    p = {"day": 0}

p["day"] += 1

quora_answers = [
    {
        "question": "How do I generate leads without cold calling?",
        "url": "https://www.quora.com/How-do-I-generate-leads-without-cold-calling",
        "answer": """Most people think lead generation is about finding people who need your product. It's not.

It's about finding people who are already looking for your product.

Here's the framework we use:

1. Monitor where buyers talk about their problems (Reddit, LinkedIn, niche forums)
2. Look for intent signals: "looking for alternatives", "budget $X", "current tool sends spam"
3. Score them: buying language, urgency, budget, problem severity, competitor mentions
4. Score 8+ = respond with context, not template

Why this works: When someone says "I need X" and you reply "Here's X" — you're solving a stated problem, not interrupting their day.

Results we saw: 0.8% cold outreach reply rate → 34% with intent-based responses.

We even built a tool to automate this: https://influentia.io

But even manually: one week of listening instead of sending will change your lead generation game."""
    },
    {
        "question": "What's the best cold email strategy for B2B in 2026?",
        "url": "https://www.quora.com/What-is-the-best-cold-email-strategy-for-B2B",
        "answer": """Stop sending cold emails.

Seriously.

The average cold email reply rate in 2026 is 0.5%. That means 995 people out of 1,000 don't care about your email.

Here's what works instead: Intent-based outreach.

1. Find where your buyers hang out (Reddit, LinkedIn, niche communities)
2. Monitor for signals they're actively looking for your solution
3. Respond with context specific to their situation

This isn't theoretical. We tracked 14 calls in 30 days from Reddit alone. Zero ad spend. Zero cold emails.

The math:
- Cold emails: 0.5% reply rate
- Intent responses: 34% reply rate
- 68x better

We built Influentia (influentia.io) to do this automatically, but the principle works even if you monitor manually.

The key insight: Buyers are already talking about their problems. They're just hard to hear above the noise."""
    },
    {
        "question": "What's the best alternative to Lemlist in 2026?",
        "url": "https://www.quora.com/Alternative-to-Lemlist",
        "answer": """I spent 3 months testing every major outreach tool:

Expandi ($99/mo): 1,100 connection requests, 180 accepted, 12 replies, 1 call
Lemlist ($60/mo): 1,500 emails, 225 opens, 8 replies, 2 calls
Manual outreach (4 hrs/day): 40 genuine conversations, 14 replies, 6 calls, 2 closed deals

The winner wasn't a tool. It was timing.

Instead of sending 50 messages per day to people who don't care, we monitored Reddit for people who did care.

Found buyer signals like:
- "Looking for alternatives to [tool]"
- "Budget $X/mo for something better"
- "Our current tool sends spam"

Responded with context. Not templates.

Results: $1,200/mo + $800/mo new clients from 2 real conversations. vs $0 from 225 cold emails.

We built Influentia (influentia.io) to automate this signal monitoring. It's not another email sequencing tool — it's an intent intelligence system.

If you're comparing tools right now: Expandi and Lemlist get you volume. Intent-based outreach gets you buyers. Pick what you need."""
    }
]

# Generate today's content
idx = (p["day"] - 1) % len(quora_answers)
q = quora_answers[idx]

filepath = os.path.join(DIST, f"{TODAY}-quora-answer.md")
with open(filepath, "w") as f:
    f.write(f"# Quora Answer — {TODAY}\n\n")
    f.write(f"**Question:** {q['question']}\n")
    f.write(f"**URL:** {q['url']}\n\n")
    f.write(f"**Answer:**\n{q['answer']}\n\n")
    f.write(f"---\n")
    f.write(f"Post at: {q['url']}\n")

# Save progress
with open(TRACK, "w") as f:
    json.dump(p, f, indent=2)

print(f"Generated: Quora answer for '{q['question']}'")
print(f"Saved: {filepath}")
print(f"Total Quora answers generated: {p['day']}/{len(quora_answers)}")
