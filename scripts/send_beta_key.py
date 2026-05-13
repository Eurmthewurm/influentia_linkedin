#!/usr/bin/env python3
"""
Influentia — Beta Key Distributor
Send a beta license key to a Reddit user via DM.

Usage:
  python send_beta_key.py <reddit_username>
  python send_beta_key.py <reddit_username> --key CUSTOM-KEY-HERE

Requirements:
  pip install praw
  Set env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
            REDDIT_USERNAME, REDDIT_PASSWORD
"""

import argparse
import os
import sys
import json
from pathlib import Path

KEYS_FILE = Path(__file__).parent.parent / "beta_keys.json"


def load_keys() -> list[dict]:
    if KEYS_FILE.exists():
        return json.loads(KEYS_FILE.read_text())
    return []


def save_keys(keys: list[dict]):
    KEYS_FILE.write_text(json.dumps(keys, indent=2))


def get_next_key(keys: list[dict]) -> str | None:
    for k in keys:
        if not k.get("sent_to"):
            return k["key"]
    return None


def mark_sent(keys: list[dict], key: str, username: str):
    for k in keys:
        if k["key"] == key:
            k["sent_to"] = username
            k["sent_at"] = __import__("datetime").datetime.now().isoformat()
            break
    save_keys(keys)


def send_dm(username: str, subject: str, body: str):
    import praw
    
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "influentia-bot/1.0"),
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
    )
    
    reddit.redditor(username).message(subject=subject, message=body)
    print(f"DM sent to u/{username}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="Reddit username (without u/)")
    parser.add_argument("--key", help="Specific key to send (auto-assigns next available)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    keys = load_keys()
    key = args.key or get_next_key(keys)
    
    if not key:
        print("ERROR: No available beta keys. Generate more with generate_beta_keys.py")
        sys.exit(1)
    
    subject = "Your Influentia beta key 🎉"
    body = f"""Hey! You commented on the Influentia beta post. Here's your key:

**{key}**

**To get started (takes ~10 min):**
1. Go to https://influentia.io/start.html
2. Download the app for your OS
3. Paste your license key when prompted
4. Follow the setup guide

**What you get:**
- 2 weeks free, no credit card
- 50K tokens/day (enough for real testing)
- Direct line to me for feedback

If you hit any issues, reply here or email info@influentia.io.

— Ermo

P.S. If this doesn't work for you, no hard feelings. Just let me know what didn't click — that feedback is worth more than the beta."""
    
    print(f"Sending key {key} to u/{args.username}...")
    
    if args.dry_run:
        print(f"[DRY RUN] Would send:\n{body}")
    else:
        send_dm(args.username, subject, body)
        mark_sent(keys, key, args.username)
        print(f"Key {key} marked as sent to u/{args.username}")


if __name__ == "__main__":
    main()
