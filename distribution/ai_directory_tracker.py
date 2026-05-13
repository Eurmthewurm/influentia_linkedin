#!/usr/bin/env python3
"""Track and manage AI directory submissions for Influentia."""
import os
import json
from datetime import date

DIST_DIR = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
TRACK_FILE = os.path.join(DIST_DIR, "ai_directories.json")
os.makedirs(DIST_DIR, exist_ok=True)

DIRS = [
    {
        "name": "Theres An AI For That",
        "url": "https://theresanaiforthat.com/submit",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "Futurepedia", 
        "url": "https://www.futurepedia.io/submit-tool",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "Toolify.ai",
        "url": "https://www.toolify.ai/submit-tool",
        "type": "AI Directory", 
        "status": "pending",
    },
    {
        "name": "TopAI.tools",
        "url": "https://topai.tools/submit",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "Opentools.ai", 
        "url": "https://opentools.ai/submit",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "100AI.tools",
        "url": "https://100ai.tools/submit",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "AI Scout",
        "url": "https://aiscout.net/submit",
        "type": "AI Directory",
        "status": "pending",
    },
    {
        "name": "Product Hunt",
        "url": "https://www.producthunt.com/posts/new",
        "type": "Launch Platform",
        "status": "pending",
    },
    {
        "name": "AlternativeTo",
        "url": "https://alternativeto.net/about/addsoftware.aspx",
        "type": "Alternative Directory",
        "status": "pending",
        "note": "Submit as alternative to Expandi, Lemlist, Apollo.io"
    },
    {
        "name": "aicrawler.com",
        "url": "https://aicrawler.com",
        "type": "AI Directory",
        "status": "pending",
        "note": "Focus on intent monitoring niche"
    },
]

# Load existing state
if os.path.exists(TRACK_FILE):
    with open(TRACK_FILE) as f:
        existing = json.load(f)
    # Update with new dirs, keep existing status
    existing_urls = {d["url"] for d in existing}
    for d in DIRS:
        if d["url"] not in existing_urls:
            existing.append(d)
    dirs = existing
else:
    dirs = DIRS

# Save
with open(TRACK_FILE, "w") as f:
    json.dump(dirs, f, indent=2)

# Print status
pending = [d for d in dirs if d.get("status") == "pending"]
submitted = [d for d in dirs if d.get("status") == "submitted"]

print(f"AI Directory Tracker — {date.today().isoformat()}")
print(f"Total: {len(dirs)} | Submitted: {len(submitted)} | Pending: {len(pending)}")
print()

if pending:
    print(f"Next {min(2, len(pending))} to submit:")
    for i, d in enumerate(pending[:2]):
        print(f"  {i+1}. {d['name']} -> {d['url']}")
        if "note" in d:
            print(f"     Note: {d['note']}")
        print(f"     Status: Mark as 'submitted' after submitting via browser")
        print()
else:
    print("All directories submitted! 🎉")
    print("Next step: Monitor listings and update URLs when they go live")
