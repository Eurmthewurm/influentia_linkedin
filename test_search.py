"""Quick test — run this in Terminal to diagnose lead search."""
import logging, sys
logging.basicConfig(level=logging.INFO, format='%(message)s')

from lead_finder import search_leads

print("Testing DuckDuckGo search...")
results = search_leads("Founder", "B2B services", "Australia", "LinkedIn", 5)
print(f"\nRESULT: {len(results)} leads found")
for r in results[:5]:
    print(f"  - {r['name']} | {r['linkedin_url']}")

if not results:
    print("\nNo results — checking raw DDG response...")
    import urllib.request, urllib.parse
    q = urllib.parse.quote_plus("site:linkedin.com/in Founder Australia B2B services LinkedIn")
    url = f"https://html.duckduckgo.com/html/?q={q}&kl=au-en"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        print(f"DDG response: {len(html)} bytes")
        import re
        li_count = len(re.findall(r'linkedin\.com/in/', html, re.I))
        print(f"linkedin.com/in/ occurrences in HTML: {li_count}")
        if li_count == 0:
            # show a snippet to diagnose
            print("\nFirst 800 chars of DDG response:")
            print(html[:800])
    except Exception as e:
        print(f"DDG fetch error: {e}")
