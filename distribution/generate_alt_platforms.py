#!/usr/bin/env python3
"""Add Hacker News, Indie Hackers + other free platform support to daily distribution."""
import os, json, sys
from datetime import date

DIST = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
os.makedirs(DIST, exist_ok=True)
TODAY = date.today().isoformat()

TRACK = os.path.join(DIST, "alt_platforms.json")
if os.path.exists(TRACK):
    with open(TRACK) as f:
        p = json.load(f)
else:
    p = {"day": 0, "last_platform": None}

p["day"] += 1

content = [
    {
        "platform": "Hacker News",
        "format": "Show HN",
        "title": "Show HN: Influentia – intent intelligence for B2B outreach (14 buyers from Reddit, 0 ads)",
        "body": """We built a tool that monitors Reddit and LinkedIn for buyer intent signals and drafts contextual responses. Not templates — messages grounded in what the buyer actually said.

Background: we spent 3 months on cold outreach. 847 requests. 3 replies. 0 calls. $280/mo wasted.

Then we started listening instead of sending. Found someone on r/SaaS: "Looking for alternatives to X, budget $800/mo." Responded to their specific pain point. 15-min call, now $800/mo customer.

System: (1) monitor 12 subreddits + LinkedIn, (2) score signals 0-10 on buying language, urgency, budget, problem severity, competitor mentions, (3) draft contextual responses, (4) founder approves.

Results: 34% reply rate vs 0.8% cold. 42x better.

Live: https://influentia.io

Happy to answer questions about signal scoring or why cold doesn't work.""",
    },
    {
        "platform": "Indie Hackers",
        "format": "Post",
        "title": "Found 14 buyers in 30 days on Reddit — zero ads, zero cold outreach",
        "body": """Sharing our distribution strategy since it might help other IHers.

Instead of ads or cold DMs, we monitor Reddit for buyer intent signals:
"Looking for alternatives to X", "Budget $800/mo", "Our current tool sends spam"

We score signals 0-10 based on: buying language, urgency, budget markers, problem severity, competitor mentions. Score 8+ = genuine response specific to their situation.

Math:
- Cold outreach: 0.8% reply rate
- Intent-based: 34% reply rate
- ~40 signals/week caught → 12 high quality → 6 responses → 3 conversations → 1-2 calls
- 8-10 calls/month from Reddit alone → 2-3 customers (~$2700 MRR)

Cost: $0 ads. ~1 hr/day.

The tool: https://influentia.io ($97/mo, 14-day trial).
But even manually — one week of listening instead of sending changes everything.

Happy to share our signal scoring framework or subreddit list.""",
    },
    {
        "platform": "Dev.to",
        "format": "Article",
        "title": "Why I stopped sending 50 cold DMs per day and started listening instead",
        "body": """I used to send 50 cold LinkedIn DMs per day. From 1,400 messages per month, I got 11 replies. 3 conversations. 1 call. That's a 0.07% booking rate.

The problem isn't the template. It's the timing.

When you send a cold message, you interrupt someone who wasn't thinking about your solution. But the buyers who actually need you? They're already talking about their problem — on Reddit, LinkedIn, community forums.

So I switched to intent monitoring.

Here's the framework:

1. Monitor where buyers hang out (r/SaaS, r/entrepreneur, LinkedIn posts)
2. Look for signals: "looking for alternatives", "budget $X", "current tool sends spam"
3. Score them: buying language (0-2), urgency (0-2), budget (0-2), severity (0-2), competitors (0-2)
4. Score 8+ = respond with context, not template

Results went from 0.8% reply rate to 34%. That's 42x better.

We built Influentia (https://influentia.io) to automate this. It monitors conversations, scores signals, drafts responses. Founder approves, sends.

If you're doing volume outreach: try listening for one week instead. You'll see how many buyers are already talking.""",
    },
    {
        "platform": "Lobsters",
        "format": "Post",
        "title": "How we replaced 1400 cold messages/month with ~40 intent signals (and got 35x better results)",
        "body": """We track buyer intent signals from public conversations — not via scraping personal data, just monitoring public posts where people openly discuss looking for alternatives, sharing budgets, and complaining about tools.

Framework: score each signal 0-10 on buying language, urgency, budget specificity, problem severity, competitor mentions. Score 8+ = respond with context.

Key insight: when someone says "I need X" and you reply "Here's X" — that's solving a stated problem, not cold outreach.

Results: 34% reply rate vs 0.8% cold. The signal quality beats volume every time.

Built a tool at https://influentia.io that automates scoring and response drafting. Open to questions on the approach.""",
    },
]

idx = (p["day"] - 1) % len(content)
sel = content[idx]

filepath = os.path.join(DIST, f"{TODAY}-{sel['platform'].lower().replace(' ', '-')}.md")
with open(filepath, "w") as f:
    f.write(f"# {sel['platform']} — {TODAY}\n\n")
    f.write(f"**Format:** {sel['format']}\n\n")
    f.write(f"**Title/Subject:**\n{sel['title']}\n\n")
    f.write(f"**Body/Content:**\n{sel['body']}\n\n")
    f.write("---\n")
    f.write(f"Submit at: {'https://news.ycombinator.com' if 'Hacker' in sel['platform'] else 'https://indiehackers.com' if 'Indie' in sel['platform'] else 'https://dev.to' if 'Dev' in sel['platform'] else 'https://lobste.rs'}\n")

p["last_platform"] = sel["platform"]
with open(TRACK, "w") as f:
    json.dump(p, f, indent=2)

print(f"Generated: {sel['platform']} ({sel['format']})")
print(f"Saved: {filepath}")
print(f"Total alternate platform days: {p['day']}/{len(content)}")
