#!/usr/bin/env python3
"""
Quick Reddit API diagnostic — run this directly in Terminal:
  cd ~/Desktop/linkedin_outreach && python test_reddit.py
"""
import urllib.request, urllib.parse, json, time

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

QUERIES = [
    "B2B lead generation",
    "how to get more clients",
    "LinkedIn not working",
    "founder personal brand",
]

def search(query, subreddits=None, global_fallback=False):
    if subreddits:
        sub_path = "+".join(subreddits)
        url = f"https://www.reddit.com/r/{sub_path}/search.json"
        restrict = 1
    else:
        url = "https://www.reddit.com/search.json"
        restrict = 0

    params = urllib.parse.urlencode({
        "q": query, "sort": "new", "t": "month",
        "limit": 10, "restrict_sr": restrict,
    })
    req = urllib.request.Request(
        f"{url}?{params}",
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        children = data.get("data", {}).get("children", [])
        return children, None
    except Exception as e:
        return [], str(e)

def main():
    print("=" * 60)
    print("Reddit API Diagnostic")
    print("=" * 60)

    SUBREDDITS = ["marketing", "entrepreneur", "smallbusiness", "consulting", "linkedin"]

    total = 0
    for q in QUERIES:
        print(f"\nQuery: {q!r}")

        # Try subreddit-scoped first
        posts, err = search(q, subreddits=SUBREDDITS)
        if err:
            print(f"  [subreddit search] ERROR: {err}")
        else:
            print(f"  [subreddit search] {len(posts)} posts")
            for p in posts[:2]:
                pd = p["data"]
                print(f"    • r/{pd['subreddit']}: {pd['title'][:60]}")

        if not posts:
            # Try global
            posts2, err2 = search(q, subreddits=None)
            if err2:
                print(f"  [global search]    ERROR: {err2}")
            else:
                print(f"  [global search]    {len(posts2)} posts")
                for p in posts2[:2]:
                    pd = p["data"]
                    print(f"    • r/{pd['subreddit']}: {pd['title'][:60]}")
            total += len(posts2)
        else:
            total += len(posts)

        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"TOTAL posts found: {total}")
    if total == 0:
        print("❌ Reddit is returning 0 results — likely blocking or rate-limiting this IP.")
        print("   Try again in 5–10 minutes, or check if you're on a VPN.")
    else:
        print("✅ Reddit API is working. The issue is in the running server's code.")
        print("   Run: curl -s http://localhost:5555/api/reload")
        print("   If that returns 404, the server has stale/old code.")
    print("=" * 60)

if __name__ == "__main__":
    main()
