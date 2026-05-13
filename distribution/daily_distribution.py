#!/usr/bin/env python3
"""Master daily distribution script for Influentia."""
import os, subprocess, sys
from datetime import date

DIST = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
os.chdir("/Users/ermoegberts/Desktop/linkedin_outreach")
TODAY = date.today().isoformat()

for name, script in [
    ("SEO Pages", "generate_seo_pages.py"),
    ("Blog Post", "generate_blog_post.py"),
    ("Social Drafts", "generate_social_drafts.py"),
    ("Reddit Opps", "find_reddit_opportunities.py"),
    ("AI Dirs", "ai_directory_tracker.py"),
]:
    print(f"\n--- {name} ---")
    r = subprocess.run([sys.executable, os.path.join(DIST, script)],
                       capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print(f"ERR: {r.stderr}")

# Deploy + git
print("\n--- Deploy + Git ---")
subprocess.run(["wrangler", "pages", "deploy", "landing",
                "--project-name=influentia", "--commit-dirty=true"],
               capture_output=True, text=True)
subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
subprocess.run(["git", "commit", "-m", f"daily distribution batch - {TODAY}"],
               capture_output=True, text=True)
subprocess.run(["git", "push"], capture_output=True, text=True)
print("Deployed + pushed.")
