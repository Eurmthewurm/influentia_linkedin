#!/usr/bin/env python3
"""Generate programmatic SEO landing pages for Influentia."""
import os
import json

SEO_DIR = "/Users/ermoegberts/Desktop/linkedin_outreach/landing/seo"
TRACK_FILE = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution/seo_progress.json"
os.makedirs(SEO_DIR, exist_ok=True)

if os.path.exists(TRACK_FILE):
    with open(TRACK_FILE) as f:
        progress = json.load(f)
else:
    progress = {"completed": []}

KEYWORDS = [
    {"slug": "saas-buyer-intent-detection", "title": "SaaS Buyer Intent Detection: Find Buyers Before They Churn", "focus": "buyer intent monitoring", "stats": ["0.8% cold reply rate", "34% intent-based rate", "42x improvement"]},
    {"slug": "linkedin-outreach-without-banned", "title": "LinkedIn Outreach Without Getting Banned: Signal-Based Approach", "focus": "safe LinkedIn outreach", "stats": ["847 requests sent", "3 replies received", "0 risk with intent"]},
    {"slug": "expandi-alternative", "title": "Expandi Alternative: Intent Intelligence Beats Volume", "focus": "Expandi comparison", "stats": ["$99 Expandi/mo", "2% reply rate", "$97 Influentia"]},
    {"slug": "lemlist-alternative", "title": "Lemlist Alternative: Email Sequences Don't Work in 2026", "focus": "cold email critique", "stats": ["15% open rate", "0.5% reply rate", "8.8/10 signal score"]},
    {"slug": "find-buyers-on-reddit", "title": "How to Find Buyers on Reddit Without Being Spammy", "focus": "Reddit lead generation", "stats": ["44M daily visitors", "2.1K signals/day", "34% reply rate"]},
    {"slug": "b2b-lead-intelligence", "title": "B2B Lead Intelligence: Beyond CRM and Cold Outreach", "focus": "B2B intelligence framework", "stats": ["$99 wasted tools", "20 hrs/week manual", "14 calls from signals"]},
    {"slug": "reddit-intent-monitoring", "title": "Reddit Intent Monitoring for SaaS: Catch Active Buyers", "focus": "Reddit monitoring guide", "stats": ["500+ subreddits", "12 buying signals/hr", "$800 avg budget"]},
    {"slug": "ai-outreach-personalization", "title": "AI Outreach Personalization: Context Over Templates", "focus": "AI personalization guide", "stats": ["0.8% template rate", "34% contextual rate", "42x improvement"]},
    {"slug": "agency-client-acquisition", "title": "Agency Client Acquisition: Signal-Based Lead Generation", "focus": "agency acquisition strategy", "stats": ["847 cold requests", "3 replies", "0 booked calls"]},
    {"slug": "b2b-saas-lead-discovery", "title": "B2B SaaS Lead Discovery: Intent Intelligence Platform", "focus": "SaaS lead monitoring", "stats": ["$400 wasted/mo", "2% reply rate", "14 real calls"]},
]

generate_today = [k for k in KEYWORDS if k["slug"] not in progress["completed"]][:3]

if not generate_today:
    print("All SEO pages already generated!")
    exit(0)

for kw in generate_today:
    slug = kw["slug"]
    title = kw["title"]
    focus = kw["focus"]
    stats = kw["stats"]

    html_template = open("/Users/ermoegberts/Desktop/linkedin_outreach/distribution/seo_template.html").read()
    
    # Replace template variables
    html = html_template.replace("{{TITLE}}", title)
    html = html.replace("{{FOCUS}}", focus)
    html = html.replace("{{SLUG}}", slug)
    html = html.replace("{{STAT1}}", stats[0])
    html = html.replace("{{STAT2}}", stats[1])
    html = html.replace("{{STAT3}}", stats[2])
    
    filepath = os.path.join(SEO_DIR, f"{slug}.html")
    with open(filepath, "w") as f:
        f.write(html)
    progress["completed"].append(slug)
    print(f"Generated: {title} -> {filepath}")

with open(TRACK_FILE, "w") as f:
    json.dump(progress, f, indent=2)
print(f"Progress: {len(progress['completed'])}/{len(KEYWORDS)} SEO pages done")
