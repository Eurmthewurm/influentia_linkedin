#!/usr/bin/env python3
"""Generate daily social media drafts for Influentia."""
import os
import json
import random
from datetime import date

DIST_DIR = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
TODAY = date.today().isoformat()
os.makedirs(DIST_DIR, exist_ok=True)

# Rotation tracker
TRACK = os.path.join(DIST_DIR, "social_progress.json")
if os.path.exists(TRACK):
    with open(TRACK) as f:
        progress = json.load(f)
else:
    progress = {"day_count": 0, "last_format": None}

progress["day_count"] += 1

# Content pool: 30 varied angles
ANGELS = [
    {"type": "reddit", "title": "Why I killed our outreach tool budget",
     "content": """I run a small B2B agency. Last quarter we had:
- Expandi ($99/mo)
- Lemlist ($60/mo) 
- Apollo ($50/user/mo)
- 20 hours/week on manual LinkedIn DMs

Total cost: $280/mo + 80 hours.
Results from 3 months: 847 connection requests. 3 replies. 0 calls booked.

So we killed everything and built something different. Instead of blasting random people with templates, we started monitoring Reddit and LinkedIn for people actively complaining about the exact problems we solve.

First signal caught:
"Looking for alternatives to HubSpot — budget $800/mo, they're raising prices again and the UI is getting worse"

We responded with context about their specific pain point, not a pitch. Result: 15 minute call. Now a $800/mo client.

Second signal:
"Our current outreach tool costs $400/mo and sends spam. 2% reply rate. How do you scale without going bankrupt?"

Again — real response to a real problem. That one became a 3-month engagement worth $1,200.

The insight: buyers are already talking about their problems. They're just hard to hear above the noise. When someone says "I need X" and you reply "Here's X" — that's fundamentally different from sending 50 cold DMs hoping one lands.

So we built Influentia to do this automatically. Still in beta. 10 spots. $97/mo.

If you're spending $200+/mo on outreach tools that don't work — happy to share what we learned.

(Not trying to sell you. Just sharing what worked.)"""},
    {"type": "linkedin", "title": "The best outreach I ever did had zero templates",
     "content": """I spent 3 months running cold outreach with templates.

847 connection requests.
3 replies.
0 calls booked.

Then I changed my entire approach.

I stopped sending first.

Instead, I started listening.

I monitored LinkedIn and Reddit for people complaining about problems our product solves.

Someone posted: "I hate our current tool. It's expensive and sends spam."

I didn't send a template. I didn't pitch. I read their actual post and responded to their specific situation.

15 minutes later: we were on a call.

That's when I realized: the problem isn't that people don't need our product. The problem is we were reaching them at the wrong time with the wrong message.

Intent-based outreach is simple:
1. Find people already talking about your problem
2. Respond with context, not templates
3. Build relationships with people who need you

It's slower at first. You can't blast 500 people a day.

But the quality is so much higher that it doesn't matter.

34% reply rate vs 0.8% from cold templates.

I'd rather have 10 real conversations than 500 ignored messages.

This is what we're building at Influentia. Find buyers who are already looking. Respond with context, not templates.

If you're doing cold outreach right now — what's your reply rate?"""},
    {"type": "twitter", "title": "Thread: Why 99% of cold outreach fails",
     "content": [
         "🧵 Why 99% of cold outreach fails (and what to do instead):\n\n1/ The problem isn't your template. It's your timing.",
         "2/ Most cold outreach goes to people who don't care at that exact moment. They're busy. They're not thinking about your solution. They don't want to 'hop on a quick call'.",
         "3/ But here's the thing: your buyers are already talking about their problems. On Reddit. In LinkedIn posts. In Slack communities.",
         "4/ They're saying: 'I hate this tool' / 'Looking for alternatives' / 'How do I solve X?' / 'Budget $800/mo for something better'",
         "5/ That's intent. That's signal. That's the difference between someone who's interested and someone who's not.",
         "6/ When someone says 'I need X' and you reply 'Here's X' — you're solving a stated problem. Not interrupting their day.",
         "7/ The math: 0.8% reply rate for cold templates vs 34% for intent-based outreach.",
         "8/ So instead of sending 500 messages hoping 4 land, catch the 10 people who are already looking and respond with context.",
         "9/ This is what we built at Influentia. Not a template tool. An intent detection system. It monitors public conversations for buyer signals and drafts contextual responses.",
         "10/ If you're doing outreach right now:\n- Stop sending templates\n- Start listening\n- Respond with context\n- Build relationships with people who need you",
     ]},
    # More varied content for future days:
    {"type": "reddit", "title": "How we found 14 buyers in 30 days (without ads)",
     "content": """We tracked 14 qualified leads last month by doing one thing differently.

Instead of buying leads or sending cold DMs, we monitored Reddit and LinkedIn for buyer intent signals.

Example of what we look for:
"Looking for [X solution] — our current tool [complaint]"
"Budget $[amount]/mo — what do you recommend for [specific use case]?"
"Anyone else frustrated with [competitor]?"

We scored each signal by:
- Buying language (looking for, alternatives, budget)
- Urgency (right now, this week, evaluating)
- Budget specificity ($ amounts mentioned)
- Problem severity (emotional language)
- Competitor mentions (naming specific tools)

Highest scoring signal last month:
"Need to replace Apollo before Q2. $400/mo for 2% reply rate is insane. 6-person team spending 20+ hours on manual LinkedIn."

Scored 9.4/10. Resulted in a $1200/mo deal.

The system works because buyers are already talking. They're just hard to hear. We're just listening.

Built a tool called Influentia to automate this. Still in beta. Happy to demo if anyone wants to see how signals work.

Not pitching. Just sharing what worked for us."""},
    {"type": "linkedin", "title": "The math that killed our cold outreach",
     "content": """50 cold DMs per day.
350 per week.
1,400 per month.

14 replies.
3 conversations.
1 call booked.

1 call for 1,400 messages.

That's 0.07% booking rate from cold outreach.

We stopped.

Now we catch ~40 intent signals per week:
- 12 are high quality (8+)
- 6 get genuine responses
- 3 become conversations
- 1-2 become calls

1-2 calls from 40 signals vs 1 call from 1,400 cold DMs.

The ratio is 35x better.

It's not about volume. It's about timing and context.

When someone says they need your exact solution and you respond — that's not outreach. That's solving a problem.

We built this into Influentia. Find buyers. Respond with context. No templates.

If you're still doing volume outreach in 2026 — you're just wasting time and money."""},
    {"type": "twitter", "title": "Thread: Cold outreach is dead",
     "content": [
         "🧵 Cold outreach is dead. Here's what replaced it:\n\n1/ I used to send 50 cold LinkedIn DMs per day. Got 3 replies from 350 messages that week.",
         "2/ Then I realized: the buyers who need me are already talking about their problems. I just couldn't hear them.",
         "3/ So I started monitoring Reddit and LinkedIn for buyer intent signals.",
         "4/ The signals are obvious once you look:\n- 'Looking for alternatives'\n- 'Budget $X/mo'\n- 'Current tool sends spam'\n- 'Anyone else frustrated with…'",
         "5/ These aren't cold leads. These are warm buyers actively shopping.",
         "6/ When you catch one of these and respond with context — not a template — the reply rate is 34%.",
         "7/ 34% vs 0.8% for cold outreach. That's 42x better.",
         "8/ The difference: timing. Cold = interrupting someone. Intent = responding to their stated problem.",
         "9/ This is what I built at Influentia. It monitors conversations, scores signals, drafts contextual responses.",
         "10/ Stop sending cold outbound. Start listening for intent. The buyers who need you are already talking.",
     ]},
]

# Pick different format each day
formats = ["reddit", "linkedin", "twitter", "reddit", "linkedin"]
format = formats[(progress["day_count"] - 1) % len(formats)]
if progress.get("last_format") == format:
    format = formats[(progress["day_count"]) % len(formats)]

# Get content for this format
content_pool = [c for c in ANGELS if c["type"] == format]
if not content_pool:
    content_pool = ANGELS  # fallback to everything

idx = (progress["day_count"] - 1) % len(content_pool)
content = content_pool[idx]

# Save draft
if format == "twitter":
    draft_path = os.path.join(DIST_DIR, f"{TODAY}-twitter-thread.md")
    with open(draft_path, "w") as f:
        f.write(f"# Twitter/X Thread - {TODAY}\n\n")
        for i, tweet in enumerate(content["content"], 1):
            f.write(f"## Tweet {i}\n{tweet}\n\n")
    print(f"Saved: {draft_path}")
else:
    draft_path = os.path.join(DIST_DIR, f"{TODAY}-{format}-post.md")
    with open(draft_path, "w") as f:
        f.write(f"# {format.upper()} Post - {TODAY}\n\n## {content['title']}\n\n{content['content']}")
    print(f"Saved: {draft_path}")

# Save progress
progress["last_format"] = format
with open(TRACK, "w") as f:
    json.dump(progress, f, indent=2)

print(f"Format: {format} (Day {progress['day_count']})")
