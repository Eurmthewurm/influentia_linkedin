# ─────────────────────────────────────────────────────────────────────────────
# lead_finder.py  —  Find LinkedIn leads via Google search + AI ICP generation
#
# SAFE by design: searches Google only, never touches LinkedIn during discovery.
# LinkedIn cannot see this activity at all.
# ─────────────────────────────────────────────────────────────────────────────
import time
import random
import re
import json
import logging
import urllib.request
import urllib.parse
import html as html_module

log = logging.getLogger(__name__)


def _parse_linkedin_title(raw: str) -> dict:
    """
    Parse a LinkedIn profile title from a Google search snippet.
    Common formats:
      "First Last - Job Title - Company | LinkedIn"
      "First Last | LinkedIn"
      "First Last - Job Title | LinkedIn"
    """
    # Strip trailing "| LinkedIn" and anything after
    clean = re.sub(r'\s*\|.*$', '', raw).strip()
    parts = [p.strip() for p in clean.split(' - ')]
    return {
        "name":    parts[0] if len(parts) > 0 else "",
        "title":   parts[1] if len(parts) > 1 else "",
        "company": parts[2] if len(parts) > 2 else "",
    }


def _http_get(url: str, extra_headers: dict = None) -> str:
    """Fetch a URL and return the HTML text. Raises on failure."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        charset = "utf-8"
        ct = resp.headers.get_content_charset()
        if ct:
            charset = ct
        return resp.read().decode(charset, errors="replace")


def _extract_from_html(raw_html: str, sector: str) -> list:
    """
    Pull linkedin.com/in/ URLs + title text from raw HTML.
    Works for both DuckDuckGo and Bing result pages.
    """
    results = []
    seen = set()

    # Find all hrefs that contain linkedin.com/in/
    for m in re.finditer(
        r'href=["\']([^"\']*linkedin\.com/in/([A-Za-z0-9_%-]{2,})[^"\']*)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        full_href = m.group(1)
        username   = m.group(2)

        # Skip generic LinkedIn pages
        if username.lower() in ("login", "feed", "in", "pub", "jobs", "company", "home"):
            continue

        # Normalise URL
        url_clean = f"https://www.linkedin.com/in/{username}/"
        if url_clean in seen:
            continue
        seen.add(url_clean)

        # Try to grab nearby title text: look for the result heading in a window
        # around the match (up to 800 chars ahead)
        window = raw_html[max(0, m.start() - 200): m.end() + 600]
        # h2/h3 tag content
        title_m = re.search(r"<h[23][^>]*>(.*?)</h[23]>", window, re.DOTALL | re.IGNORECASE)
        if title_m:
            title_raw = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        else:
            # Fall back to the link text itself
            link_text_m = re.search(r"<a[^>]*>[^<]{3,}</a>", window, re.DOTALL | re.IGNORECASE)
            title_raw = re.sub(r"<[^>]+>", "", link_text_m.group(0)).strip() if link_text_m else ""

        title_clean = html_module.unescape(title_raw).strip()
        parsed = _parse_linkedin_title(title_clean)
        results.append({
            "linkedin_url": url_clean,
            "name":         parsed["name"],
            "title":        parsed["title"],
            "company":      parsed["company"],
            "sector":       sector,
        })

    return results


def search_leads(
    job_title: str,
    industry: str,
    location: str,
    keywords: str = "",
    count: int = 20,
) -> list:
    """
    Search for LinkedIn profiles matching your ICP.
    Strategy 1: Brave Search API (free tier, 2000/month — fast and reliable).
    Strategy 2: SearXNG public meta-search instances (fallback, no key needed).
    Uses plain HTTP — no browser/Playwright needed, so much harder to block.

    Returns a list of lead dicts:
      { linkedin_url, name, title, company, sector }

    ONLY touches search engines — LinkedIn is never contacted during this step.
    """

    # ── Build query ──────────────────────────────────────────────────────────
    parts = ["site:linkedin.com/in"]
    if job_title:
        parts.append(job_title)
    if location:
        parts.append(location)
    if industry:
        parts.append(industry)
    if keywords:
        parts.append(keywords)
    query = " ".join(parts)
    log.info(f"Lead search query: {query}")

    leads     = []
    seen_urls = set()

    def _add_lead(url_raw: str, title_text: str):
        """Normalise URL, parse title, append to leads if new."""
        m = re.search(r'linkedin\.com/in/([A-Za-z0-9_%-]{2,})', url_raw, re.I)
        if not m:
            return
        username = m.group(1)
        if username.lower() in ("login", "feed", "in", "pub", "jobs", "company", "home"):
            return
        # Skip if title looks like a generic LinkedIn page (no real person)
        title_lower = (title_text or "").lower()
        if "log in" in title_lower or "sign up" in title_lower or "sign in" in title_lower:
            return
        url_clean = f"https://www.linkedin.com/in/{username}/"
        if url_clean in seen_urls or len(leads) >= count:
            return
        seen_urls.add(url_clean)
        parsed = _parse_linkedin_title(html_module.unescape(title_text or ""))
        leads.append({
            "linkedin_url": url_clean,
            "name":         parsed["name"],
            "title":        parsed["title"],
            "company":      parsed["company"],
            "sector":       industry or "",
        })

    # ── Strategy 1: Brave Search API (free, 2000/month) ──────────────────────
    try:
        from config import BRAVE_SEARCH_API_KEY
        brave_key = (BRAVE_SEARCH_API_KEY or "").strip()
    except ImportError:
        brave_key = ""

    if brave_key:
        log.info("Using Brave Search API…")
        try:
            per_page = min(20, count)
            for page_num in range(max(1, (count // per_page) + 1)):
                if len(leads) >= count:
                    break
                offset  = page_num * per_page
                encoded = urllib.parse.quote_plus(query)
                brave_url = (
                    f"https://api.search.brave.com/res/v1/web/search"
                    f"?q={encoded}&count={per_page}&offset={offset}&search_lang=en&country=AU"
                )
                brave_html = _http_get(brave_url, extra_headers={
                    "Accept":               "application/json",
                    "Accept-Encoding":      "identity",
                    "X-Subscription-Token": brave_key,
                })
                data = json.loads(brave_html)
                results = data.get("web", {}).get("results", [])
                added = 0
                for r in results:
                    url = r.get("url", "")
                    title = r.get("title", "") or r.get("description", "")
                    if "linkedin.com/in/" in url.lower():
                        before = len(leads)
                        _add_lead(url, title)
                        if len(leads) > before:
                            added += 1
                log.info(f"Brave page {page_num+1}: +{added} profiles (total: {len(leads)})")
                if not results:
                    break
                time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            log.error(f"Brave API error: {e}")

    # ── Strategy 2: SearXNG public instances (no key needed) ─────────────────
    if not leads:
        SEARX_INSTANCES = [
            "https://searx.be/search",
            "https://search.mdosch.de/search",
            "https://searx.tiekoetter.com/search",
            "https://searx.fmac.xyz/search",
        ]
        encoded = urllib.parse.quote_plus(query)
        for instance in SEARX_INSTANCES:
            if leads:
                break
            try:
                searx_url = (
                    f"{instance}?q={encoded}&format=json"
                    f"&engines=google,bing,brave&language=en-AU"
                )
                log.info(f"Trying SearXNG: {instance}…")
                resp_text = _http_get(searx_url, extra_headers={"Accept": "application/json"})
                data = json.loads(resp_text)
                results = data.get("results", [])
                added = 0
                for r in results:
                    url   = r.get("url", "")
                    title = r.get("title", "")
                    if "linkedin.com/in/" in url.lower():
                        before = len(leads)
                        _add_lead(url, title)
                        if len(leads) > before:
                            added += 1
                log.info(f"SearXNG {instance}: +{added} profiles")
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                log.warning(f"SearXNG instance {instance} failed: {e}")
                continue

    if not leads and not brave_key:
        log.warning(
            "No leads found. Add a free Brave Search API key to config.py for reliable results.\n"
            "Sign up at: https://api.search.brave.com"
        )

    log.info(f"Lead search complete — {len(leads)} profiles found.")
    return leads[:count]


def score_leads_quality(leads: list, icp_description: str, min_score: int = 5) -> list:
    """
    Use Claude to score leads 1-10 for ICP fit and filter out poor matches.
    Sends all leads in one API call to keep costs low.
    Returns leads with score >= min_score, sorted best first.
    """
    if not leads:
        return []

    import anthropic
    from config import ANTHROPIC_API_KEY

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    leads_txt = "\n".join(
        f"{i+1}. {l.get('name','?')} | {l.get('title','?')} | {l.get('company','?')}"
        for i, l in enumerate(leads)
    )

    prompt = f"""You are a B2B lead qualification expert.

ICP (Ideal Customer Profile): {icp_description}

Rate each lead 1-10 for ICP fit. Score 8-10 = great match, 5-7 = OK, 1-4 = poor fit or too big/irrelevant.

Leads:
{leads_txt}

Respond with ONLY a JSON array of numbers matching the leads in order.
Example: [8, 3, 7, 9, 2, ...]"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",   # cheap + fast for scoring
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        scores = json.loads(raw)
        if not isinstance(scores, list):
            raise ValueError("Expected list")

        # Attach scores and filter
        scored = []
        for i, lead in enumerate(leads):
            score = scores[i] if i < len(scores) else 5
            if score >= min_score:
                lead["icp_score"] = score
                scored.append(lead)

        # Sort best first
        scored.sort(key=lambda l: l.get("icp_score", 0), reverse=True)
        log.info(f"Quality filter: kept {len(scored)}/{len(leads)} leads (min score {min_score})")
        return scored

    except Exception as e:
        log.warning(f"Quality scoring failed ({e}) — returning all leads unfiltered")
        return leads


def generate_icp_from_description(description: str, offering: str = "") -> dict:
    """
    Use Claude to turn a natural-language ICP description into structured
    Google search parameters.

    Returns:
      {
        job_titles:  ["Founder", "Agency Owner"],   # primary roles to search
        industries:  ["B2B Consulting", "Marketing Agency"],
        locations:   ["Australia"],
        keywords:    ["LinkedIn", "video content"],
        signals:     ["active_on_linkedin", "recently_posted"],
        explanation: "I'll search for..."
      }
    """
    import anthropic
    from config import ANTHROPIC_API_KEY, YOUR_OFFERING

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    offering_text = offering or YOUR_OFFERING

    prompt = f"""You are a B2B lead generation expert. A user wants to find LinkedIn leads.

Their offering:
{offering_text[:800]}

Their ICP description:
{description}

Generate structured Google search parameters to find matching LinkedIn profiles.
Respond with ONLY valid JSON (no markdown, no explanation outside JSON):

{{
  "job_titles": ["list of 2-4 specific job titles to search for"],
  "industries": ["list of 1-3 industry/niche terms"],
  "locations": ["list of 1-2 locations, or empty if not specified"],
  "keywords": ["list of 0-3 extra keywords that help find active/relevant people"],
  "signals": ["active_on_linkedin" if they should post on LinkedIn, "decision_maker" if senior roles],
  "explanation": "One sentence explaining who you'll find and why they match"
}}

Rules:
- job_titles should be specific (e.g. "Founder" not "Person")
- keywords should help find active LinkedIn users (e.g. "LinkedIn" if they post there)
- Keep it tight — 2-4 job titles max, not a long list
- Location should match what the user said, or leave empty for global
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
        log.info(f"ICP generated: {result.get('explanation','')}")
        return result
    except Exception as e:
        log.error(f"ICP generation failed: {e}")
        return {
            "job_titles": [],
            "industries": [],
            "locations": [],
            "keywords": [],
            "signals": [],
            "explanation": "Could not generate ICP — please fill in the fields manually.",
        }
