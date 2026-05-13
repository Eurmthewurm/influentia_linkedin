# ─────────────────────────────────────────────────────────────────────────────
# reddit_client.py  —  Reddit API client (read + write)
#
# Reading/scanning uses Reddit's public JSON API — no credentials needed.
# Posting comments requires OAuth credentials set in .env:
#   REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
#
# Register a free "script" app at: https://www.reddit.com/prefs/apps
# ─────────────────────────────────────────────────────────────────────────────
import os
import json
import time
import logging
import urllib.request
import urllib.parse
import urllib.error
import base64
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_PUBLIC_API  = "https://www.reddit.com"
_OAUTH_API   = "https://oauth.reddit.com"
_TOKEN_URL   = "https://www.reddit.com/api/v1/access_token"
# Reddit requires a descriptive User-Agent; generic/bot-like ones get 429/blocked.
# Using a browser UA ensures the public JSON API responds.
_USER_AGENT  = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


# ── Public read-only client (no credentials needed) ───────────────────────────

def search_posts(query: str, subreddits: list = None, limit: int = 25,
                 time_filter: str = "week") -> list:
    """
    Search Reddit for posts matching query. No credentials required.
    Batches all subreddits into a single request using Reddit's multi-sub syntax
    (r/sub1+sub2+sub3) — much faster than one request per subreddit.
    """
    results = []
    seen_ids = set()

    try:
        if subreddits:
            # Batch all subreddits into one URL: /r/sub1+sub2+sub3/search.json
            sub_path = "+".join(subreddits)
            url = f"{_PUBLIC_API}/r/{sub_path}/search.json"
            restrict = 1
        else:
            url = f"{_PUBLIC_API}/search.json"
            restrict = 0

        params = urllib.parse.urlencode({
            "q":           query,
            "sort":        "new",
            "t":           time_filter,
            "limit":       min(limit, 25),
            "restrict_sr": restrict,
        })
        req = urllib.request.Request(
            f"{url}?{params}",
            headers={
                "User-Agent": _USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        children = data.get("data", {}).get("children", [])
        log.info(f"Reddit API → {len(children)} results for {url.split('/r/')[-1].split('/')[0]!r} q={query!r}")
        for child in children:
            pd = child.get("data", {})
            pid = pd.get("id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                results.append(_format_post(pd))

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        log.warning(f"Reddit HTTP {e.code} for q={query!r}: {body}")
    except Exception as e:
        log.warning(f"Reddit search failed (q={query!r}): {type(e).__name__}: {e}")

    return results


def _format_post(pd: dict) -> dict:
    return {
        "post_id":    pd.get("id", ""),
        "fullname":   pd.get("name", ""),          # t3_xxxx
        "title":      pd.get("title", ""),
        "text":       pd.get("selftext", "")[:1200],
        "url":        f"https://reddit.com{pd.get('permalink', '')}",
        "subreddit":  pd.get("subreddit", ""),
        "author":     pd.get("author", ""),
        "score":      pd.get("score", 0),
        "num_comments": pd.get("num_comments", 0),
        "created_utc": pd.get("created_utc", 0),
        "is_self":    pd.get("is_self", True),
    }


# ── Authenticated client (required for posting) ───────────────────────────────

class RedditClient:
    """OAuth client for posting comments and monitoring replies."""

    def __init__(self):
        self.client_id     = os.environ.get("REDDIT_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        self.username      = os.environ.get("REDDIT_USERNAME", "").strip()
        self.password      = os.environ.get("REDDIT_PASSWORD", "").strip()

        if not all([self.client_id, self.client_secret, self.username, self.password]):
            raise RuntimeError(
                "Reddit credentials missing. Add REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
                "REDDIT_USERNAME, REDDIT_PASSWORD to your .env file. "
                "Register a free 'script' app at https://www.reddit.com/prefs/apps"
            )

        self._token         = None
        self._token_expires = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        data  = urllib.parse.urlencode({
            "grant_type": "password",
            "username":   self.username,
            "password":   self.password,
            "scope":      "submit privatemessages read",
        }).encode()

        req = urllib.request.Request(
            _TOKEN_URL, data=data,
            headers={
                "Authorization":  f"Basic {creds}",
                "User-Agent":     _USER_AGENT,
                "Content-Type":   "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())

        self._token         = result["access_token"]
        self._token_expires = time.time() + result.get("expires_in", 3600)
        log.info("Reddit OAuth token refreshed.")
        return self._token

    def _req(self, path: str, method: str = "GET", data: dict = None) -> dict:
        token = self._get_token()
        body  = urllib.parse.urlencode(data).encode() if data else None
        req   = urllib.request.Request(
            f"{_OAUTH_API}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent":    _USER_AGENT,
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            log.error(f"Reddit API {e.code}: {body_text[:200]}")
            raise RuntimeError(f"Reddit API {e.code}: {body_text[:200]}") from e

    # ── Public methods ────────────────────────────────────────────────────────

    def post_comment(self, post_fullname: str, text: str) -> str:
        """
        Post a top-level comment on a Reddit post.
        post_fullname is the t3_xxxx ID.
        Returns the comment fullname (t1_xxxx) or raises on error.
        """
        result = self._req("/api/comment", method="POST", data={
            "api_type": "json",
            "thing_id": post_fullname,
            "text":     text,
        })
        errors = result.get("json", {}).get("errors", [])
        if errors:
            raise RuntimeError(f"Reddit comment errors: {errors}")
        things = result.get("json", {}).get("data", {}).get("things", [])
        comment_fullname = things[0].get("data", {}).get("name", "") if things else ""
        log.info(f"Reddit comment posted: {comment_fullname}")
        return comment_fullname

    def reply_to_comment(self, comment_fullname: str, text: str) -> str:
        """Reply to an existing comment (t1_xxxx). Same API as post_comment."""
        return self.post_comment(comment_fullname, text)

    def get_inbox_replies(self) -> list:
        """Fetch recent replies to our comments from inbox."""
        try:
            result = self._req("/message/selfreply?limit=25&mark=false")
            children = result.get("data", {}).get("children", [])
            return [self._format_message(c.get("data", {})) for c in children]
        except Exception as e:
            log.warning(f"Could not fetch Reddit inbox: {e}")
            return []

    def mark_read(self, fullname: str):
        """Mark a message as read."""
        try:
            self._req("/api/read_message", method="POST", data={"id": fullname})
        except Exception as e:
            log.warning(f"Could not mark {fullname} as read: {e}")

    def _format_message(self, md: dict) -> dict:
        return {
            "id":          md.get("name", ""),
            "author":      md.get("author", ""),
            "body":        md.get("body", ""),
            "subject":     md.get("subject", ""),
            "context_url": f"https://reddit.com{md.get('context', '')}",
            "created_utc": md.get("created_utc", 0),
            "parent_id":   md.get("parent_id", ""),
        }

    def close(self):
        pass  # no persistent connection


# ── Browser-based fallback (no API app needed) ─────────────────────────────

_REDDIT_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "reddit_profile")

# Anti-detection JavaScript — injected before Reddit pages load.
# Reddit's risk engine checks many of the same signals as LinkedIn.
_ANTI_DETECT_JS = """
// 1. navigator.webdriver — Playwright sets this to true by default.
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. window.chrome — headless may be missing chrome.runtime.
if (!window.chrome) {
    window.chrome = { runtime: { onConnect: {addListener:()=>{}}, onMessage: {addListener:()=>{}} } };
}

// 3. navigator.plugins — headless has 0; real browsers have several.
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer'},
            {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
            {name:'Native Client',     filename:'internal-nacl-plugin'},
        ];
        arr.length = arr.length;
        return arr;
    }
});

// 4. navigator.languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-AU', 'en-GB', 'en'] });

// 5. WebGL vendor strings — headless uses SwiftShader/Mesa
try {
    const _getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris Pro OpenGL Engine';
        return _getParam.call(this, p);
    };
} catch(e) {}

// 6. Hide automation-tainted props
const _origHasOwnProp = Object.prototype.hasOwnProperty;
Object.prototype.hasOwnProperty = function(prop) {
    if (prop === 'webdriver') return false;
    return _origHasOwnProp.call(this, prop);
};
"""


class SessionRedditClient:
    """
    Posts Reddit comments via the web API using saved browser session cookies.
    No Playwright or asyncio needed — works anywhere, no subprocess required.

    Requires a valid Playwright session file (from BrowserRedditClient._ensure_browser).
    Falls back gracefully if the session is expired.
    """

    def __init__(self, state_file: str):
        self.state_file = state_file
        self._cookie_str = ""
        self._modhash = ""
        self._load_session()

    def _load_session(self):
        with open(self.state_file) as f:
            session = json.load(f)
        cookies = {
            c["name"]: c["value"]
            for c in session.get("cookies", [])
            if "reddit.com" in c.get("domain", "")
        }
        self._cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        # Fetch modhash (required for write API calls)
        req = urllib.request.Request(
            "https://www.reddit.com/api/me.json",
            headers={"User-Agent": _USER_AGENT, "Cookie": self._cookie_str},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        me = data.get("data", {})
        self._modhash = me.get("modhash", "")
        self._username = me.get("name", "")
        if not self._modhash:
            raise RuntimeError("Could not get Reddit modhash — session may be expired.")
        log.info(f"SessionRedditClient ready for u/{self._username}")

    def post_comment(self, post_fullname: str, text: str) -> str:
        """Post a top-level comment. Returns the new comment's fullname (t1_xxx)."""
        data = urllib.parse.urlencode({
            "api_type": "json",
            "thing_id": post_fullname,
            "text": text,
        }).encode()
        req = urllib.request.Request(
            "https://www.reddit.com/api/comment.json",
            data=data,
            headers={
                "User-Agent": _USER_AGENT,
                "Cookie": self._cookie_str,
                "X-Modhash": self._modhash,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.reddit.com/",
                "Origin": "https://www.reddit.com",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Reddit API error {exc.code}: {exc.read()[:200].decode()}") from exc

        errors = result.get("json", {}).get("errors", [])
        if errors:
            raise RuntimeError(f"Reddit rejected the comment: {errors}")

        things = result.get("json", {}).get("data", {}).get("things", [])
        if things:
            fullname = things[0].get("data", {}).get("name", "")
            if fullname:
                log.info(f"Comment posted: {fullname}")
                return fullname

        raise RuntimeError(f"Unexpected Reddit response: {str(result)[:200]}")

    def close(self):
        pass  # no resources to clean up


class BrowserRedditClient:
    """
    Playwright-based Reddit client for posting comments and checking inbox.
    Uses a real Chromium browser with anti-detection patches and human-like
    delays — behaviourally indistinguishable from a normal user session.

    Requires only REDDIT_USERNAME and REDDIT_PASSWORD in .env.
    On first run, a browser window opens for you to complete login
    (usually just the 2FA prompt if you have it). Subsequent runs use
    the saved session and run headless automatically.
    """

    # Safety limits per account
    MAX_DAILY_POSTS = 5              # hard ceiling across all subreddits
    MIN_DELAY_BETWEEN_POSTS = 45     # seconds (randomised up to 2x)
    MAX_DELAY_BETWEEN_POSTS = 150

    def __init__(self):
        self.username = os.environ.get("REDDIT_USERNAME", "").strip()
        self.password = os.environ.get("REDDIT_PASSWORD", "").strip()

        if not self.username or not self.password:
            raise RuntimeError(
                "Reddit credentials missing. Add REDDIT_USERNAME and "
                "REDDIT_PASSWORD to your .env file."
            )

        self._pw        = None
        self._browser   = None
        self._context   = None
        self._page      = None
        self._post_count_today = 0

    def _human_delay(self, min_s: float = 0.8, max_s: float = 3.0):
        """Wait a random human-like duration with natural jitter."""
        import random as _r
        delay = _r.uniform(min_s, max_s)
        if self._page:
            # Small random mouse movement during the delay
            try:
                self._page.mouse.move(
                    _r.randint(100, 800), _r.randint(100, 600),
                    steps=_r.randint(3, 8),
                )
            except Exception:
                pass
        time.sleep(delay)

    def _ensure_browser(self):
        """Lazy-init Playwright with a persistent Reddit profile."""
        from playwright.sync_api import sync_playwright
        import random as _r

        if self._page is not None:
            return

        log.info("Starting Reddit browser session…")
        self._pw = sync_playwright().start()

        profile_dir = os.path.join(_REDDIT_PROFILE_DIR, self.username.replace("@", "_at_"))
        state_file  = os.path.join(profile_dir, "state.json")
        os.makedirs(profile_dir, exist_ok=True)

        # Reddit now blocks headless Chrome with Cloudflare — always use visible
        # browser for posting. It only runs 1-3 times/day so the window popup is
        # not a nuisance.
        has_session = os.path.exists(state_file)
        self._browser = self._pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )

        ctx_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/"
                + _r.choice(["124", "125", "126", "127"])
                + ".0.0.0 Safari/537.36"
            ),
            "viewport": {"width": _r.choice([1280, 1366, 1440, 1536]),
                         "height": _r.choice([720, 768, 800, 900])},
            "locale": _r.choice(["en-US", "en-GB", "en-AU", "en-CA"]),
            "timezone_id": _r.choice([
                "America/New_York", "Europe/London", "Australia/Sydney",
                "America/Chicago", "Europe/Berlin",
            ]),
            "device_scale_factor": _r.choice([1, 1.25, 1.5, 2]),
        }

        if has_session:
            ctx_kwargs["storage_state"] = state_file

        self._context = self._browser.new_context(**ctx_kwargs)
        self._context.add_init_script(_ANTI_DETECT_JS)
        self._page = self._context.new_page()
        self._page.set_default_timeout(15000)

        self._page.goto("https://www.reddit.com", wait_until="domcontentloaded")
        self._human_delay(1.0, 2.0)

        def _is_logged_in() -> bool:
            """Return True if we can see a logged-in indicator."""
            content = self._page.content()
            # new Reddit shows username in a faceplate element; check for logout link
            return (
                'data-user' in content
                or 'href="/logout"' in content
                or f'href="/user/{self.username.split("@")[0]}' in content.lower()
                or self._page.query_selector('a[href*="/user/"]') is not None
            )

        def _do_login():
            """Navigate to the login page and fill credentials."""
            self._page.goto("https://www.reddit.com/login", wait_until="domcontentloaded")
            self._human_delay(1.5, 2.5)
            # Dismiss cookie banner
            try:
                for label in ["Accept All", "Accept all"]:
                    btn = self._page.query_selector(f'button:has-text("{label}")')
                    if btn and btn.is_visible():
                        btn.click()
                        self._human_delay(0.5, 1.0)
                        break
            except Exception:
                pass
            try:
                self._page.wait_for_selector('input[name="username"]', timeout=10000)
                self._page.fill('input[name="username"]', self.username)
                self._human_delay(0.4, 0.8)
                self._page.fill('input[name="password"]', self.password)
                self._human_delay(0.4, 0.8)
                # Reddit's login button is type="button" with text "Log In"
                login_btn = self._page.wait_for_selector(
                    'button:has-text("Log In"), button[type="submit"]', timeout=5000
                )
                if login_btn:
                    login_btn.click()
            except Exception as ex:
                log.warning(f"Auto-fill login failed: {ex} — complete manually if needed.")
            log.info("Waiting for Reddit login (complete 2FA in the browser if prompted)…")
            try:
                self._page.wait_for_url(
                    lambda url: "reddit.com" in url and "/login" not in url,
                    timeout=120000,
                )
            except Exception:
                pass
            self._human_delay(1.5, 2.5)

        if not has_session:
            log.info("No saved Reddit session — logging in automatically.")
            _do_login()
        else:
            # Verify session is still valid
            if not _is_logged_in():
                log.warning("Reddit session stale — re-logging in.")
                _do_login()

        if not _is_logged_in():
            self.close()
            raise RuntimeError(
                "Could not log into Reddit. Check your REDDIT_USERNAME and "
                "REDDIT_PASSWORD in .env, or complete login manually."
            )

        self._context.storage_state(path=state_file)
        log.info("Reddit session active and saved.")

    def _simulate_reading(self):
        """Scroll the page and wait to mimic reading a post."""
        import random as _r
        if not self._page:
            return
        try:
            for _ in range(_r.randint(1, 3)):
                self._page.mouse.wheel(0, _r.randint(200, 600))
                time.sleep(_r.uniform(0.5, 2.0))
        except Exception:
            pass

    # ── Public methods ────────────────────────────────────────────────────

    def post_comment(self, post_fullname: str, text: str) -> str:
        """
        Post a top-level comment using old.reddit.com (simple HTML form — no React).
        post_fullname is the t3_xxxx ID. Returns the Reddit comment fullname (t1_xxx).
        """
        import random as _r

        if self._post_count_today >= self.MAX_DAILY_POSTS:
            raise RuntimeError(
                f"Daily Reddit post limit reached ({self.MAX_DAILY_POSTS}). "
                "Wait until tomorrow or reduce caps in Settings."
            )

        self._ensure_browser()
        post_id = post_fullname.replace("t3_", "")
        url = f"https://www.reddit.com/comments/{post_id}/"
        self._page.goto(url, wait_until="domcontentloaded")
        self._simulate_reading()
        self._human_delay(1.0, 2.0)

        # Dismiss cookie banner if it appears
        try:
            for label in ["Accept All", "Accept all"]:
                btn = self._page.query_selector(f'button:has-text("{label}")')
                if btn and btn.is_visible():
                    btn.click()
                    self._human_delay(0.5, 1.0)
                    break
        except Exception:
            pass

        # Find the comment textarea — use Playwright's fill() which triggers React events
        textarea = None
        for sel in [
            'textarea[placeholder*="Join the conversation"]',
            'textarea[placeholder*="What are your thoughts"]',
            'textarea[placeholder*="Comment"]',
            'textarea[placeholder*="Add a comment"]',
        ]:
            try:
                el = self._page.wait_for_selector(sel, timeout=5000)
                if el and el.is_visible():
                    textarea = el
                    break
            except Exception:
                continue

        if textarea is None:
            raise RuntimeError(
                "Could not find the Reddit comment box. "
                "The post may be locked, deleted, or Reddit's UI changed."
            )

        # Click to activate, then use fill() which properly triggers React synthetic events
        textarea.click()
        self._human_delay(0.3, 0.8)
        textarea.fill(text)
        self._human_delay(0.8, 1.5)

        # Submit — look for a visible enabled button near the textarea
        submitted = False
        for sel in [
            'button[type="submit"]:has-text("Comment")',
            'button[type="submit"]:has-text("Post")',
            'button[type="submit"]',
        ]:
            try:
                btn = self._page.wait_for_selector(sel, timeout=4000)
                if btn and btn.is_visible() and btn.is_enabled():
                    self._human_delay(0.2, 0.6)
                    btn.click()
                    submitted = True
                    break
            except Exception:
                continue

        if not submitted:
            raise RuntimeError(
                "Found the comment box but couldn't click the submit button. "
                "Reddit may have changed their UI."
            )

        # Wait for submission to process
        self._human_delay(2.0, 4.0)
        self._post_count_today += 1

        log.info(f"Reddit comment posted on {url} (post #{self._post_count_today} today)")
        return f"t1_browser_{post_id}_{int(time.time())}"

    def get_inbox_replies(self) -> list:
        """Fetch recent inbox replies via the web UI."""
        self._ensure_browser()
        self._page.goto(
            "https://www.reddit.com/message/inbox/.json", wait_until="domcontentloaded"
        )

        # Extract from the JSON response
        raw = self._page.evaluate("document.body.innerText")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Could not parse Reddit inbox JSON")
            return []

        results = []
        for child in data.get("data", {}).get("children", []):
            md = child.get("data", {})
            if md.get("subtype") == "post_reply" or md.get("was_comment"):
                results.append({
                    "id":          md.get("name", ""),
                    "author":      md.get("author", ""),
                    "body":        md.get("body", ""),
                    "subject":     md.get("subject", ""),
                    "context_url": f"https://reddit.com{md.get('context', '')}",
                    "created_utc": md.get("created_utc", 0),
                    "parent_id":   md.get("parent_id", ""),
                })
        return results

    def close(self):
        """Clean up browser resources."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None


# ── Factory ────────────────────────────────────────────────────────────────

_REDDIT_PROFILE_DIR_ALIAS = _REDDIT_PROFILE_DIR  # used below


def get_reddit_client(require_browser: bool = False):
    """
    Return the best available Reddit client (fastest / most reliable first):
    1. OAuth RedditClient — if REDDIT_CLIENT_ID + SECRET are set
    2. SessionRedditClient — if a saved Playwright session exists (no Playwright needed)
    3. BrowserRedditClient — opens a browser to log in and save a new session
    """
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    username      = os.environ.get("REDDIT_USERNAME", "").strip()
    password      = os.environ.get("REDDIT_PASSWORD", "").strip()

    if not require_browser and client_id and client_secret and username and password:
        try:
            return RedditClient()
        except Exception as exc:
            log.warning(f"OAuth RedditClient failed: {exc}")

    # Try the saved-session client first (no Playwright, no asyncio conflict)
    if username and not require_browser:
        state_file = os.path.join(
            _REDDIT_PROFILE_DIR_ALIAS,
            username.replace("@", "_at_"),
            "state.json",
        )
        if os.path.exists(state_file):
            try:
                return SessionRedditClient(state_file)
            except Exception as exc:
                log.warning(f"SessionRedditClient failed (session likely expired): {exc}")

    # Fall back to Playwright browser (will open a browser window to log in)
    if username and password:
        return BrowserRedditClient()

    raise RuntimeError(
        "Reddit credentials missing. "
        "Add REDDIT_USERNAME and REDDIT_PASSWORD to your .env file."
    )
