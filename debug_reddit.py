#!/usr/bin/env python3
"""
Debug script — tests the EXACT same code path the server scan uses.
Run: cd ~/Desktop/linkedin_outreach && python debug_reddit.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import urllib.request, urllib.parse, json, time

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

SUBREDDITS = ["marketing","content_marketing","b2bmarketing","smallbusiness",
              "entrepreneur","consulting","agencylife","linkedin","videomarketing"]

TEST_QUERIES = ["not getting clients", "B2B lead generation", "how to get more clients"]

def raw_fetch(url, params):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
            data = json.loads(body)
            children = data.get("data", {}).get("children", [])
            return len(children), None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        return 0, f"HTTP {e.code}: {body}"
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"

print("=" * 70)
print("Debug: testing exact server code path")
print("=" * 70)

# Test 1: Does the combined subreddit URL work at all?
print("\n1. Testing batched subreddit URL with first query...")
sub_path = "+".join(SUBREDDITS)
url = f"https://www.reddit.com/r/{sub_path}/search.json"
count, err = raw_fetch(url, {"q": "not getting clients", "sort": "new", "t": "month", "limit": 10, "restrict_sr": 1})
if err:
    print(f"   FAILED: {err}")
else:
    print(f"   OK: {count} posts")

# Test 2: Test each subreddit individually to find the bad one
print("\n2. Testing each subreddit individually (finding broken ones)...")
for sub in SUBREDDITS:
    url = f"https://www.reddit.com/r/{sub}/search.json"
    count, err = raw_fetch(url, {"q": "getting clients", "sort": "new", "t": "month", "limit": 5, "restrict_sr": 1})
    status = f"✅ {count} posts" if not err else f"❌ {err[:60]}"
    print(f"   r/{sub}: {status}")
    time.sleep(0.8)

# Test 3: Global search for each query
print("\n3. Global search for main queries...")
for q in TEST_QUERIES:
    count, err = raw_fetch("https://www.reddit.com/search.json", {"q": q, "sort": "new", "t": "month", "limit": 10})
    status = f"✅ {count} posts" if not err else f"❌ {err[:80]}"
    print(f"   {q!r}: {status}")
    time.sleep(1)

print("\n" + "=" * 70)
print("If individual subs work but combined URL fails → remove broken subs")
print("If global search works but subreddit search fails → use global only")
print("=" * 70)
