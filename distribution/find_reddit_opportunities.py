#!/usr/bin/env python3
"""Find Reddit opportunities and draft helpful responses."""
import os
import json
import webbrowser
from datetime import date

DIST_DIR = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
os.makedirs(DIST_DIR, exist_ok=True)

TODAY = date.today().isoformat()
outfile = os.path.join(DIST_DIR, f"{TODAY}-reddit-opportunities.md")

# In a real implementation, this would search Reddit via API/web
# For now, we generate search URLs and draft response templates
subreddits = ["SaaS", "entrepreneur", "startups", "agency", "B2Bmarketing", "sales", "consulting"]
search_queries = [
    "outreach tool",
    "lead generation", 
    "cold email",
    "linkedin dm",
    "sales automation",
    "crm alternatives",
    "finding leads"
]

print("Finding Reddit opportunities...")
print(f"Today's target subreddits: {', '.join(subreddits)}")
print(f"Search terms: {', '.join(search_queries)}")

# Generate search URLs
print("\nSearch URLs to check manually:")
for sub in subreddits[:3]:  # Top 3 most relevant
    for q in search_queries[:2]:  # Top 2 queries
        url = f"https://www.reddit.com/r/{sub}/search/?q={q.replace(' ', '+')}&sort=new&t=week"
        print(f"  {url}")

# Draft sample response
draft = f"""# Reddit Opportunities — {TODAY}

## High-Value Threads to Check (manual search needed)

Check these Reddit searches daily:

1. **r/SaaS — "outreach tool"** → https://www.reddit.com/r/SaaS/search/?q=outreach+tool&sort=new&t=week
2. **r/entrepreneur — "lead generation"** → https://www.reddit.com/r/entrepreneur/search/?q=lead+generation&sort=new&t=week  
3. **r/startups — "cold email"** → https://www.reddit.com/r/startups/search/?q=cold+email&sort=new&t=week

## Response Framework

When you find a relevant post, use this framework:

### For "Looking for tool" posts:
> "We ran into this exact issue. Spent months testing Expandi, Lemlist, Apollo. Found the problem wasn't the tools — it was that we were interrupting people who didn't care.
> 
> Started monitoring conversations for buyer signals instead. 34% reply rate vs 0.8% with cold outreach. Built Influentia to automate this. Happy to share what we learned if helpful."

### For "Tool not working" posts:
> "Same thing happened to us. $99/mo for Expandi, 50 DMs/day, got 1 reply per week. The tools aren't bad — they're designed for volume when you need timing.
> 
> Now we monitor Reddit/LinkedIn for people actively complaining about problems we solve. When someone says 'I need X' and you reply with context — it works way better than templates."

### For "How do you scale outreach?" posts:
> "We found that scaling isn't about sending more — it's about being more relevant to fewer people. 
> 
> Instead of 500 cold messages (0.8% reply), we catch ~40 intent signals per week (34% reply). The buyers who need you are already talking. They're just hard to hear.
> 
> If you're interested in the signal-based approach, I can share the framework we use."

## When NOT to mention Influentia

- If the post is about a completely different topic
- If it's a "how to make money online" type post
- If it's already got 500+ comments (our response will be buried)
- If the user seems hostile to any product recommendations

Focus on being helpful, not promotional. The goal is to add value, not sell.
"""

with open(outfile, "w") as f:
    f.write(draft)

print(f"\nSaved opportunities: {outfile}")
print("Review this daily and respond to 1-2 relevant threads")
