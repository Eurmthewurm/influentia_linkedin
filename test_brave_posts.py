#!/usr/bin/env python3
"""
Quick diagnostic: test whether Brave Search API returns LinkedIn posts.
Run from your linkedin_outreach folder:

    python test_brave_posts.py

This does NOT need LinkedIn login. It just tests the Brave API.
"""
import sys
import urllib.request, urllib.parse, json, gzip

# ── load key from config ───────────────────────────────────────────
try:
    from config import BRAVE_SEARCH_API_KEY
except ImportError:
    print("ERROR: could not import config.py — run this from the linkedin_outreach folder.")
    sys.exit(1)

if not BRAVE_SEARCH_API_KEY:
    print("ERROR: BRAVE_SEARCH_API_KEY is empty in config.py")
    sys.exit(1)

print(f"API key: {BRAVE_SEARCH_API_KEY[:8]}…")

# ── test query ────────────────────────────────────────────────────
kw = sys.argv[1] if len(sys.argv) > 1 else "b2b founder video content"
query = f"site:linkedin.com/posts {kw}"
url = (
    "https://api.search.brave.com/res/v1/web/search"
    f"?q={urllib.parse.quote(query)}&count=10"
)

print(f"\nQuery: {query!r}")
print(f"URL:   {url}\n")

try:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    })
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        data = json.loads(raw)

except Exception as e:
    print(f"ERROR calling Brave API: {e}")
    sys.exit(1)

# ── show results ─────────────────────────────────────────────────
results = data.get("web", {}).get("results", [])
print(f"Raw results returned: {len(results)}")

if not results:
    print("\nNo results. Possible causes:")
    print("  - API key expired or over monthly limit (2,000 searches/month on free tier)")
    print("  - site: operator not supported on your plan")
    print("\nFull response:")
    print(json.dumps(data, indent=2)[:2000])
    sys.exit(0)

posts_found = 0
for i, r in enumerate(results):
    url_r = r.get("url", "")
    title = r.get("title", "")
    desc  = r.get("description", "")[:120]
    is_post = any(p in url_r for p in ("linkedin.com/posts/", "linkedin.com/pulse/", "linkedin.com/feed/update/"))
    marker = "✓ POST" if is_post else "  page"
    if is_post:
        posts_found += 1
    print(f"{marker} [{i+1}] {title[:50]}")
    print(f"         {url_r[:80]}")
    if desc:
        print(f"         snippet: {desc}")
    print()

print(f"─────────────────────────────────────────────")
print(f"Post results: {posts_found} / {len(results)}")
if posts_found == 0:
    print("\n⚠  Brave returned results but none are linkedin.com/posts/ URLs.")
    print("   This usually means the 'site:linkedin.com/posts' operator is")
    print("   not respected on the free Brave API tier.")
    print("   → Try searching without 'site:' to see if general LinkedIn results appear.")
else:
    print("\n✓ Brave API is working and returning LinkedIn post URLs!")
    print("  The scan_posts command should work. Make sure to restart server.py.")
