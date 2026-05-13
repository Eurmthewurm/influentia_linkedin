#!/usr/bin/env python3
"""Standalone script to post approved Reddit comments via browser (no server)."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from reddit_client import BrowserRedditClient
from state_manager import load_state, save_state

approved = [
    {
        "id": "2a42b31d",
        "post_fullname": "t3_1sk50k7",
        "text": "Per-seat pricing absolutely kills agencies at scale—that math gets brutal fast. The unified inbox thing is real though. Most tools treat multi-account management like an afterthought, so you end up doing manual work that defeats the whole purpose of automation. Have you looked at what happens with response rates when you're bouncing between different dashboards, or did consolidating everything actually move the needle on your metrics."
    },
    {
        "id": "f033abcd",
        "post_fullname": "t3_1sdgn2e",
        "text": "The lead discovery + outreach combo in one place solves a real problem, but the actual bottleneck most teams hit isn't the tools themselves—it's data quality and follow-up consistency. Saw this a lot when we were managing our own outbound: people would spend 30% of their time cleaning data and another 30% figuring out who actually responded. What's your approach to keeping lead lists from going stale, and how does it handle the messy part where conversations drop off and need revival sequences?"
    },
    {
        "id": "6f3bc819",
        "post_fullname": "t3_1t38tf5",
        "text": "The real bottleneck most early teams hit isn't the tool itself—it's that they're trying to use a Swiss Army knife when they should pick one motion and nail it first. Saw this with three different founders who'd bought tier 1 tools but were splitting focus between email, LinkedIn, and phone simultaneously with maybe 2 people. They switched to just running sequences on one channel for 60 days, got their messaging and targeting locked in, then layered the second channel. Conversion rates went up because they actually had time to iterate instead of managing six half-baked campaigns. What's your team's current bottleneck—is it the number of touches you can execute or the quality of responses you're getting."
    },
    {
        "id": "0ceb85dd",
        "post_fullname": "t3_1t30kti",
        "text": "six years is the part people skip over when they share these. they see \"$1M ARR linkedin playbook\" and think it's a 90 day thing. I did outbound on linkedin for about two years for a smaller services business and the grind is real, the algorithm shifts alone will age you."
    }
]

state = load_state()
client = BrowserRedditClient()

posted = 0
failed = 0

for idx, c in enumerate(approved):
    print(f"\n[{idx+1}/{len(approved)}] Posting to r/... (fullname: {c['post_fullname']})")
    try:
        result = client.post_comment(c["post_fullname"], c["text"])
        print(f"  ✓ Posted: {result}")

        # Update state
        from reddit_signal import mark_reddit_comment
        mark_reddit_comment(state, c["id"], "posted", c["text"])
        posted += 1

        if idx < len(approved) - 1:
            pause = 120  # 2 min between posts
            print(f"  Waiting {pause}s before next post...")
            time.sleep(pause)
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        failed += 1

client.close()
print(f"\nDone: {posted} posted, {failed} failed")
