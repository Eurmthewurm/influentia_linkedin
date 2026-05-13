#!/usr/bin/env python3
"""Generate Medium republish drafts from blog posts"""
import os
import json
from datetime import date

DIST = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
TODAY = date.today().isoformat()

TRACK = os.path.join(DIST, "medium_posts_progress.json")
if os.path.exists(TRACK):
    with open(TRACK) as f:
        progress = json.load(f)
else:
    progress = {"day": 0}

progress["day"] += 1

posts = [
    {
        "title": "Why Cold Outreach Fails: The Math Behind 0.8% Reply Rates",
        "subtitle": "We sent 1,400 cold messages. Got 11 replies. Then changed one thing and saw 42x better results.",
        "tags": ["sales", "marketing", "startups", "saas", "lead-generation"],
        "canonical": "https://influentia.io/blog/why-cold-outreach-fails-framework",
        "content": (
            "I used to send 50 cold LinkedIn DMs per day. That's 350 per week, 1,400 per month.\n\n"
            "Results? 11 replies. 3 conversations. 1 booked call.\n\n"
            "That's a 0.07% booking rate. And we were paying $99/month for it.\n\n"
            "Most people blame their templates. They're wrong.\n\n"
            "The problem isn't the template. It's the timing.\n\n"
            "When you interrupt someone with a cold message, they weren't thinking about your product. "
            "They don't want to hop on a quick call. They don't have time for a demo.\n\n"
            "But what if you could catch buyers when they're already looking?\n\n"
            "We switched from sending first to listening first. We monitored Reddit and LinkedIn for "
            "people complaining about problems we solve. When someone said 'I need X' and we responded "
            "with context — not a template — results changed everything.\n\n"
            "0.8% reply rate (industry average) vs 34% reply rate (intent-based). That's 42x better.\n\n"
            "The framework:\n\n"
            "1. Monitor where buyers hang out (Reddit, LinkedIn, niche forums)\n"
            "2. Track five intent signals: replacement, pain, budget, urgency, peer influence\n"
            "3. Score signals 0-10 on buying language, urgency, budget, severity, competitive mentions\n"
            "4. Score 8+ = respond with context. Score below 6 = skip.\n\n"
            "We built Influentia to automate this framework. It monitors public conversations, scores "
            "signals, and drafts contextual responses (not templates).\n\n"
            "If you're doing volume outreach: try listening for one week instead. You'll see how many "
            "buyers are already talking.\n\n"
            "See it live: https://influentia.io"
        )
    },
    {
        "title": "The Buyer Intent Framework We Use to Find Qualified Leads on Reddit",
        "subtitle": "How we catch 40+ buyer signals per week from Reddit and convert them at 34% reply rates.",
        "tags": ["marketing", "sales", "reddit", "lead-generation", "startups"],
        "canonical": "https://influentia.io/blog/buyer-intent-framework-spotting-signals",
        "content": (
            "Every day, your ideal buyers are telling you exactly what they need.\n\n"
            "They're posting on Reddit about pricing frustrations. Complaining on LinkedIn about tool "
            "limitations. Asking in community forums for recommendations.\n\n"
            "But most companies miss every signal because they're looking in the wrong direction.\n\n"
            "Here's our exact framework:\n\n"
            "THE FIVE SIGNAL TYPES\n\n"
            "1. REPLACEMENT SIGNALS: someone shopping for replacements. 'Looking for alternatives to X'\n\n"
            "2. PAIN SIGNALS: complaining about problems you solve. 'Spending 20 hrs/week on manual work'\n\n"
            "3. BUDGET SIGNALS: mentioning specific amounts. '$400/mo for 2% reply rate is insane'\n\n"
            "4. URGENCY SIGNALS: timeline or deadline. 'Need to replace before Q2'\n\n"
            "5. PEER INFLUENCE: asking for recommendations. 'What do you guys use for X?'\n\n"
            "SCORING SYSTEM (10-point scale)\n\n"
            "- Buying language: 'looking for', 'alternatives', 'budget' (0-2 pts)\n"
            "- Urgency: 'right now', 'this week' (0-2 pts)\n"
            "- Budget specificity: '$800/mo' vs 'reasonable price' (0-2 pts)\n"
            "- Problem severity: emotional language vs mild complaint (0-2 pts)\n"
            "- Competitor mentions: naming tools they hate (0-2 pts)\n\n"
            "REAL EXAMPLE FROM LAST WEEK:\n\n"
            "'Need to replace Apollo before Q2. $400/mo for 2% reply rate is insane. 6-person team "
            "spending 20+ hours/week on manual LinkedIn.'\n\n"
            "Score: 9/10. Result: $1,200/mo deal after one conversation.\n\n"
            "Cold outbound = interrupting people who don't care.\n"
            "Intent-based = responding to people who told you they need help.\n\n"
            "0.8% vs 34%. 42x better.\n\n"
            "The buyers are already talking. They're just hard to hear above the noise.\n\n"
            "https://influentia.io"
        )
    },
    {
        "title": "Expandi vs Lemlist vs Manual: What Actually Works in 2026",
        "subtitle": "We spent 3 months testing every major outreach tool. Honest results included.",
        "tags": ["sales", "marketing", "tools", "saas", "automation"],
        "canonical": "https://influentia.io/blog/expandi-vs-lemlist-vs-manual-honest-comparison",
        "content": (
            "We spent 3 months testing every major outreach tool. Here are the raw numbers:\n\n"
            "EXPANDI ($99/mo):\n"
            "- 1,100 connection requests sent\n"
            "- 180 accepted (16.4%)\n"
            "- 12 replies (1.1% of requests)\n"
            "- 1 call booked, 0 closed deals\n\n"
            "LEMLIST ($60/mo):\n"
            "- 1,500 emails sent\n"
            "- 225 opens (15% — industry average)\n"
            "- 8 replies (0.5%)\n"
            "- 2 calls booked, 0 closed deals\n\n"
            "MANUAL OUTREACH (time only):\n"
            "- 4 hours/day monitoring Reddit and LinkedIn\n"
            "- 40 genuine conversations started\n"
            "- 14 replies (34%)\n"
            "- 6 calls booked, 2 closed deals ($2,000 MRR)\n\n"
            "The winner wasn't a tool. It was timing.\n\n"
            "When someone posts 'Looking for alternatives to your competitor' on Reddit — that's not cold. "
            "That's a warm buyer actively shopping.\n\n"
            "We built Influentia to automate the manual approach. It monitors conversations, scores signals, "
            "and drafts contextual responses.\n\n"
            "$97/month. No per-seat pricing. No credit limits. Not a volume tool — a signal tool.\n\n"
            "Stop paying for tools that send spam. Start building conversations with people who told you "
            "they need you.\n\n"
            "https://influentia.io"
        )
    },
]

idx = (progress["day"] - 1) % len(posts)
post = posts[idx]

filepath = os.path.join(DIST, f"{TODAY}-medium-post.md")
with open(filepath, "w") as f:
    f.write(f"# Medium Republish Post — {TODAY}\n\n")
    f.write(f"**Title:** {post['title']}\n\n")
    f.write(f"**Subtitle:** {post['subtitle']}\n\n")
    f.write(f"**Tags:** {', '.join(post['tags'])}\n\n")
    f.write(f"**Canonical URL:** {post['canonical']}\n\n")
    f.write("---\n\n")
    f.write("**Content:**\n\n")
    f.write(post['content'])
    f.write("\n\n---\n")
    f.write("Publish at: https://medium.com/new-story\n")
    f.write(f"Set canonical link to: {post['canonical']}\n")

with open(TRACK, "w") as f:
    json.dump(progress, f, indent=2)

print(f"Generated: Medium post '{post['title']}'")
print(f"Saved: {filepath}")
print(f"Progress: {progress['day']}/{len(posts)} Medium posts")