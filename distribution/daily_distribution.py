#!/usr/bin/env python3
"""Master daily distribution runner — executes ALL generation scripts."""
import os, subprocess, sys
from datetime import date

DIST = "/Users/ermoegberts/Desktop/linkedin_outreach/distribution"
LANDING = "/Users/ermoegberts/Desktop/linkedin_outreach/landing"
os.chdir("/Users/ermoegberts/Desktop/linkedin_outreach")

lines = []
TODAY = date.today().isoformat()
lines.append(f"\n{'='*60}")
lines.append(f"DISTRIBUTION DAILY RUN — {TODAY}")
lines.append(f"{'='*60}")

for name, script in [
    ("SEO Pages", "generate_seo_pages.py"),
    ("Blog Post", "generate_blog_post.py"),
    ("Social Drafts", "generate_social_drafts.py"),
    ("Reddit Opps", "find_reddit_opportunities.py"),
]:
    lines.append(f"\n--- {name} ---")
    r = subprocess.run([sys.executable, os.path.join(DIST, script)],
                       capture_output=True, text=True, timeout=60)
    lines.append(r.stdout or "")
    if r.stderr and "Traceback" in r.stderr:
        lines.append(f"ERROR: {r.stderr[:200]}")

lines.append(f"\n--- Deploy ---")
r = subprocess.run(["wrangler", "pages", "deploy", "landing",
                     "--project-name=influentia", "--commit-dirty=true"],
                    capture_output=True, text=True, timeout=120)
if "Deployment complete" in r.stdout:
    url = [l for l in r.stdout.split("\n") if "pages.dev" in l]
    lines.append(f"DEPLOYED: {url[0] if url else 'ok'}")
else:
    lines.append(f"deploy: {r.stdout[-200:]}")

r = subprocess.run(["git", "add", "-A"], capture_output=True)
r = subprocess.run(["git", "commit", "-m", f"distribution batch - {TODAY}"],
                    capture_output=True, text=True)
if "nothing to commit" in r.stdout.lower() or "no changes added" in r.stdout.lower():
    lines.append("git: no changes")
else:
    lines.append(f"git: committed")
    r = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        lines.append("git: pushed")
    else:
        lines.append(f"git push: {r.stderr[:100]}")

print("\n".join(lines))
