#!/usr/bin/env python3
"""
Influentia — Personal Outreach Scanner
Scans Reddit for buyer-intent posts matching Influentia's ICP.
Sends a daily digest email with the best prospects to reply to.

Usage:
  python outreach_scanner.py --dry-run    # print results, don't email
  python outreach_scanner.py              # send digest via Resend

Requirements:
  pip install praw requests
  Set env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
          RESEND_API_KEY
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Reddit scanning ──────────────────────────────────────────────────────────

SUBREDDITS = [
    "SaaS", "startups", "indiehackers", "Entrepreneur", "smallbusiness",
    "B2B", "sales", "marketing", "ProductHunt", "nocode",
    "webdev", "sideproject", "launch", "alpha", "beta",
]

# Pain signals that indicate someone is struggling with outreach / getting customers
PAIN_KEYWORDS = [
    "how do i get customers",
    "how to get first customers",
    "outreach not working",
    "linkedin outreach",
    "cold email",
    "getting no replies",
    "no one is responding",
    "lead generation",
    "pipeline is empty",
    "need more leads",
    "struggling to get clients",
    "how do you get clients",
    "first 10 customers",
    "getting traction",
    "no sales",
    "outreach tool",
    "expandi",
    "lemlist",
    "phantombuster",
    "apollo",
    "sales navigator",
    "b2b sales",
    "booking calls",
    "discovery calls",
    "revenue is flat",
    "growth has stalled",
]

# Negative keywords — skip these
SKIP_KEYWORDS = [
    "job", "hiring", "career", "resume", "interview",
    "fired", "laid off", "unemployed",
]


def score_post(title: str, body: str) -> tuple[int, str]:
    """Score a post for ICP fit. Returns (score, reason)."""
    text = (title + " " + body).lower()
    
    # Skip check
    for kw in SKIP_KEYWORDS:
        if kw in text:
            return 0, "skip"
    
    score = 0
    reasons = []
    
    for kw in PAIN_KEYWORDS:
        if kw in text:
            score += 2
            reasons.append(kw)
    
    # Bonus for question posts (higher intent)
    if "?" in title:
        score += 1
        reasons.append("question")
    
    # Bonus for recent posts with engagement
    # (handled by sorting)
    
    return score, ", ".join(reasons[:3])


def scan_reddit(limit_per_sub: int = 10) -> list[dict]:
    """Scan subreddit for relevant posts."""
    try:
        import praw
    except ImportError:
        print("ERROR: pip install praw")
        sys.exit(1)
    
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "influentia-scanner/1.0"),
    )
    
    seen = set()
    results = []
    
    for sub_name in SUBREDDITS:
        try:
            sub = reddit.subreddit(sub_name)
            for post in sub.hot(limit=limit_per_sub):
                if post.id in seen:
                    continue
                seen.add(post.id)
                
                # Skip stickied, very old, or low engagement
                if post.stickied:
                    continue
                if post.score < 2:
                    continue
                
                score, reason = score_post(post.title, post.selftext or "")
                if score >= 3:
                    results.append({
                        "id": post.id,
                        "subreddit": sub_name,
                        "title": post.title,
                        "url": f"https://reddit.com{post.permalink}",
                        "score": post.score,
                        "comments": post.num_comments,
                        "created": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                        "fit_score": score,
                        "reason": reason,
                        "snippet": (post.selftext or "")[:200],
                    })
        except Exception as e:
            print(f"  Warning: r/{sub_name} error: {e}")
            continue
    
    # Sort by fit score, then by engagement
    results.sort(key=lambda x: (x["fit_score"], x["score"] + x["comments"]), reverse=True)
    return results[:20]  # top 20


# ── Email digest ─────────────────────────────────────────────────────────────

DIGEST_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0c0c0e;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#f4f3ff">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
      <tr><td style="font-size:20px;font-weight:800;padding-bottom:8px">🔍 Influentia Outreach Scanner</td></tr>
      <tr><td style="font-size:13px;color:#8b8a9e;padding-bottom:24px">{date} · {count} prospects found</td></tr>
      {posts}
      <tr><td style="padding-top:24px;border-top:1px solid rgba(255,255,255,0.06);font-size:12px;color:#555">
        This scan covers r/SaaS, r/startups, r/indiehackers, r/Entrepreneur, r/sales, and 10 more. 
        <a href="https://influentia.io" style="color:#a78bfa">influentia.io</a>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

POST_HTML_TEMPLATE = """<tr><td style="padding:16px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
    <a href="{url}" style="color:#f4f3ff;font-size:15px;font-weight:600;text-decoration:none;line-height:1.4">{title}</a>
    <span style="background:rgba(124,106,255,0.15);color:#a78bfa;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;flex-shrink:0;margin-left:12px">score {score}</span>
  </div>
  <div style="font-size:12px;color:#8b8a9e;margin-bottom:6px">r/{subreddit} · {upvotes} upvotes · {comments} comments · {reason}</div>
  {snippet}
  <div style="margin-top:8px">
    <a href="{url}" style="color:#7c6aff;font-size:12px;font-weight:600;text-decoration:none">Reply on Reddit →</a>
  </div>
</td></tr>"""


def build_digest(posts: list[dict]) -> str:
    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    posts_html = ""
    for p in posts[:10]:  # top 10 in email
        snippet_html = ""
        if p["snippet"]:
            snippet_html = f'<div style="font-size:13px;color:#a3a1b8;line-height:1.5;margin-top:4px">{p["snippet"][:150]}...</div>'
        
        posts_html += POST_HTML_TEMPLATE.format(
            url=p["url"],
            title=p["title"][:100],
            score=p["fit_score"],
            subreddit=p["subreddit"],
            upvotes=p["score"],
            comments=p["comments"],
            reason=p["reason"],
            snippet=snippet_html,
        )
    
    return DIGEST_HTML_TEMPLATE.format(
        date=date_str,
        count=len(posts),
        posts=posts_html,
    )


def send_digest(html: str, to_email: str = "info@ermoegberts.com"):
    """Send the digest via Resend."""
    import requests
    
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("ERROR: RESEND_API_KEY not set")
        return False
    
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "Influentia Scanner <scanner@influentia.io>",
            "to": [to_email],
            "subject": f"🔍 {datetime.now().strftime('%b %d')} — Outreach prospects",
            "html": html,
        },
    )
    
    if resp.status_code == 200:
        print(f"Digest sent to {to_email}")
        return True
    else:
        print(f"Send failed: {resp.status_code} {resp.text}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Influentia Outreach Scanner")
    parser.add_argument("--dry-run", action="store_true", help="Print results without sending email")
    parser.add_argument("--limit", type=int, default=10, help="Posts per subreddit")
    parser.add_argument("--email", default="info@ermoegberts.com", help="Digest recipient")
    args = parser.parse_args()
    
    print(f"Scanning {len(SUBREDDITS)} subreddits...")
    posts = scan_reddit(limit_per_sub=args.limit)
    print(f"Found {len(posts)} relevant posts")
    
    if args.dry_run:
        for p in posts[:10]:
            print(f"  [{p['fit_score']}] r/{p['subreddit']}: {p['title'][:80]}")
            print(f"       {p['url']}")
            print(f"       reason: {p['reason']}")
            print()
    else:
        html = build_digest(posts)
        send_digest(html, args.email)


if __name__ == "__main__":
    main()
