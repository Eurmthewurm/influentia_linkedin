# ─────────────────────────────────────────────────────────────────────────────
# linkedin_client.py  —  LinkedIn automation via Playwright (real browser)
#
# Uses a persistent browser profile so LinkedIn never sees a "new" session.
# The first run opens a visible browser — you log in once, and the session
# is saved forever in linkedin_profile/ next to this file.
# ─────────────────────────────────────────────────────────────────────────────
import time
import random
import re
import json
import os
import logging
from typing import Optional
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page, Browser

from config import (
    DELAY_BETWEEN_REQUESTS_SECONDS,
    LOG_FILE_PATH,
)

# Persistent profile folder — lives next to this file
_HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(_HERE, "linkedin_profile")

# ── Stop signal ──────────────────────────────────────────────────────────────
# The server writes this file when the user clicks Stop.
# Every action checks for it and raises StopSignal if found.
STOP_FILE = os.path.join(os.path.dirname(__file__), ".stop_signal")

# ── Pause file ───────────────────────────────────────────────────────────────
# Written when LinkedIn shows a security challenge.
# The server reads this and shows a warning to the user.
PAUSE_FILE = os.path.join(os.path.dirname(__file__), ".linkedin_paused.json")


class StopSignal(Exception):
    """Raised when the user clicks Stop in the dashboard."""
    pass


class LinkedInPaused(RuntimeError):
    """Raised when LinkedIn shows a security challenge and automation is paused."""
    pass


class SessionExpired(RuntimeError):
    """Raised when the LinkedIn session expires mid-run."""
    pass


def _check_stop():
    """Check if a stop has been requested. Raises StopSignal if so."""
    if os.path.exists(STOP_FILE):
        raise StopSignal("Stop requested by user")


def _is_paused() -> bool:
    """Check if LinkedIn is paused due to security challenge. Returns True if paused."""
    if not os.path.exists(PAUSE_FILE):
        return False
    try:
        with open(PAUSE_FILE, "r") as f:
            data = json.load(f)
        until_str = data.get("until", "")
        if until_str:
            until = datetime.fromisoformat(until_str)
            if datetime.now() < until:
                return True
        # Expired — clean it up
        os.remove(PAUSE_FILE)
    except Exception:
        pass
    return False


def _pause_linkedin(reason: str, trigger: str, hours: int = 24):
    """
    Write a pause file and raise LinkedInPaused to stop execution.

    Args:
        reason: Human-readable explanation (e.g. "LinkedIn showed a CAPTCHA challenge.")
        trigger: Machine-readable trigger (captcha|unusual_activity|rate_limit|session_expired)
        hours: Duration of the pause (default 24h)
    """
    now = datetime.now()
    until = now + timedelta(hours=hours)
    pause_data = {
        "reason": reason,
        "until": until.isoformat(),
        "set_at": now.isoformat(),
        "triggered_by": trigger,
    }
    try:
        with open(PAUSE_FILE, "w") as f:
            json.dump(pause_data, f, indent=2)
        log.warning(f"LinkedIn paused for {hours}h: {reason}")
    except Exception as e:
        log.error(f"Failed to write pause file: {e}")

    raise LinkedInPaused(f"linkedin_paused: {reason}")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Anti-detection JavaScript ─────────────────────────────────────────────────
# Injected into every page BEFORE LinkedIn JS runs.
# Patches the most common bot-detection signals used by LinkedIn's risk engine.
_ANTI_DETECT_JS = """
// 1. navigator.webdriver — THE #1 signal. Playwright sets this to true by default.
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. window.chrome — headless Chromium is missing chrome.runtime entirely.
if (!window.chrome) {
    window.chrome = { runtime: { onConnect: {addListener:()=>{}}, onMessage: {addListener:()=>{}} } };
}

// 3. navigator.plugins — headless has 0 plugins; real Chrome has at least 3.
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

// 4. navigator.languages — headless sometimes returns [] or just ['en'].
Object.defineProperty(navigator, 'languages', { get: () => ['en-AU', 'en-GB', 'en'] });

// 5. navigator.permissions — headless returns 'denied' for notifications by default.
const _origPermQuery = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origPermQuery(p);

// 6. WebGL strings — headless returns 'Google SwiftShader' / 'Mesa' which is flagged.
try {
    const _getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris Pro OpenGL Engine';
        return _getParam.call(this, p);
    };
} catch(e) {}

// 7. Hide automation-related object keys from toString checks.
const _origHasOwnProp = Object.prototype.hasOwnProperty;
Object.prototype.hasOwnProperty = function(prop) {
    if (prop === 'webdriver') return false;
    return _origHasOwnProp.call(this, prop);
};
"""


# ── Human-like delay helpers ─────────────────────────────────────────────────

def _human_delay(base: int = None):
    """
    Randomised delay that mimics human behaviour.
    Occasionally adds a longer 'coffee break' pause.
    Checks for stop signal during the wait.
    """
    _check_stop()
    if base is None:
        base = DELAY_BETWEEN_REQUESTS_SECONDS
    jitter = random.uniform(-0.3 * base, 0.6 * base)
    delay = base + jitter

    # 1-in-8 chance of a longer natural pause (reading a profile)
    if random.randint(1, 8) == 1:
        extra = random.uniform(30, 90)
        log.info(f"Natural pause: adding {extra:.0f}s (simulating profile reading)")
        delay += extra

    delay = max(delay, 45)  # never go below 45s between actions
    log.info(f"Waiting {delay:.0f}s…")
    # Sleep in small increments so we can check stop signal
    elapsed = 0
    while elapsed < delay:
        chunk = min(5, delay - elapsed)
        time.sleep(chunk)
        elapsed += chunk
        _check_stop()


def _session_cooldown():
    """
    Longer break between batches of actions (3-8 minutes).
    Extends to 15-30 min if 3+ consecutive errors.
    Pauses automation for 6h if 5+ consecutive errors.
    """
    global _consecutive_failures
    _check_stop()

    # Adaptive cooldown based on consecutive failures
    if _consecutive_failures >= 5:
        # Too many errors — pause for 6 hours
        _pause_linkedin(
            "Too many consecutive LinkedIn errors. Automation paused for 6 hours.",
            "rate_limit",
            hours=6,
        )

    if _consecutive_failures >= 3:
        # 3+ errors — extend cooldown to 15-30 minutes
        pause = random.uniform(900, 1800)
        log.info(f"Multiple errors detected. Extended cooldown: {pause:.0f}s…")
    else:
        # Normal 3-8 minute cooldown
        pause = random.uniform(180, 480)
        log.info(f"Session cooldown: {pause:.0f}s pause…")

    # Sleep in small increments so we can check stop signal
    elapsed = 0
    while elapsed < pause:
        chunk = min(5, pause - elapsed)
        time.sleep(chunk)
        elapsed += chunk
        _check_stop()


def _short_wait():
    """Short wait for page loads (2-5 seconds)."""
    time.sleep(random.uniform(2, 5))


def _simulate_human_browsing(page: Page):
    """Scroll and move around like a human would when reading a profile."""
    # Random scroll down
    scroll_amount = random.randint(200, 600)
    page.mouse.wheel(0, scroll_amount)
    time.sleep(random.uniform(1, 3))
    # Sometimes scroll a bit more
    if random.random() > 0.5:
        page.mouse.wheel(0, random.randint(100, 400))
        time.sleep(random.uniform(0.5, 2))


# ── Adaptive error tracking ──────────────────────────────────────────────────
_consecutive_failures = 0


def _note_linkedin_error():
    """Record a LinkedIn error (timeout, nav failure, etc)."""
    global _consecutive_failures
    _consecutive_failures += 1
    log.debug(f"LinkedIn error recorded (consecutive: {_consecutive_failures})")


def _note_linkedin_success():
    """Record a successful LinkedIn action. Resets error counter."""
    global _consecutive_failures
    if _consecutive_failures > 0:
        log.debug(f"LinkedIn success. Error counter reset from {_consecutive_failures}")
    _consecutive_failures = 0


class LinkedInClient:
    """
    Browser-based LinkedIn automation using Playwright.

    Key safety features:
    - Uses a REAL Chromium browser (not API calls)
    - Randomised delays between every action
    - Simulates human scrolling and reading patterns
    - Session cooldowns every 5 actions
    - Headless by default (invisible browser)
    """

    def __init__(self, headless: bool = True):
        # Check if LinkedIn is paused before opening browser
        if _is_paused():
            raise LinkedInPaused("linkedin_paused: LinkedIn is paused due to a security challenge.")

        state_file = os.path.join(PROFILE_DIR, "state.json")
        first_run = not os.path.exists(state_file)
        if first_run:
            log.info("=" * 60)
            log.info("FIRST-TIME SETUP: No saved LinkedIn session found.")
            log.info("A browser window will open. Log into LinkedIn manually.")
            log.info("Once you see your feed, close the browser window.")
            log.info("Your session will be saved and reused every future run.")
            log.info("=" * 60)
            # Launch visible so user can log in
            self._launch(headless=False)
            self._page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            log.info("Waiting for you to log in… (close the browser when done)")
            try:
                self._page.wait_for_url("**/feed/**", timeout=300000)  # 5 min
            except Exception:
                pass  # user may have navigated elsewhere after login
            log.info("Login detected — saving session. Future runs will be headless.")
            self._context.storage_state(path=os.path.join(PROFILE_DIR, "state.json"))
            self._browser.close()
            self._pw.stop()
            # Re-launch headless with the saved session
            self._launch(headless=headless)
        else:
            self._launch(headless=headless)

        self._action_count = 0
        self._profile_cache = {}
        self._consecutive_auth_redirects = 0  # Track consecutive failed navigation attempts
        self._unusual_activity_check_counter = 0  # Counter for periodic unusual activity checks
        log.info("LinkedIn client initialised.")
        self._verify_session()

    def _launch(self, headless: bool = True):
        """Start Playwright + Chromium with the persistent profile."""
        self._pw = sync_playwright().start()
        os.makedirs(PROFILE_DIR, exist_ok=True)
        state_file = os.path.join(PROFILE_DIR, "state.json")

        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        if os.path.exists(state_file):
            ctx_kwargs["storage_state"] = state_file
        self._context = self._browser.new_context(**ctx_kwargs)
        # Inject anti-detection patches before any page JS runs
        self._context.add_init_script(_ANTI_DETECT_JS)
        self._page = self._context.new_page()
        # Prevent page.evaluate() from hanging forever
        self._page.set_default_timeout(20000)

    def _verify_session(self):
        """
        Navigate to LinkedIn feed as a quick health-check.
        If we land on a login page, delete the stale saved session and
        raise a clear error so the user knows to restart for a fresh login.
        """
        log.info("Verifying LinkedIn session…")
        try:
            self._page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
        except Exception as e:
            if "ERR_TOO_MANY_REDIRECTS" in str(e):
                self._nuke_profile()
                raise SessionExpired(
                    "session expired (redirect loop). "
                    "The saved session has been deleted. "
                    "Restart the server — a browser will open for you to log in again."
                ) from e
            raise

        url = self._page.url
        if any(x in url for x in ("linkedin.com/login", "linkedin.com/checkpoint",
                                   "linkedin.com/authwall", "linkedin.com/uas/")):
            self._nuke_profile()
            raise SessionExpired(
                f"session expired — redirected to: {url}. "
                "The saved session has been deleted. "
                "Restart the server — a browser will open for you to log in again."
            )

        # Session is good — save the refreshed cookies back to disk
        state_file = os.path.join(PROFILE_DIR, "state.json")
        self._context.storage_state(path=state_file)
        log.info("Session OK — LinkedIn feed loaded. Session saved.")

    def _nuke_profile(self):
        """Delete the saved session so next launch triggers a fresh login."""
        import shutil
        state_file = os.path.join(PROFILE_DIR, "state.json")
        if os.path.exists(state_file):
            os.remove(state_file)
            log.warning("Stale session file deleted.")

    def close(self):
        """Clean up browser resources."""
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def __del__(self):
        self.close()

    def _tick(self):
        """
        Increment action counter; trigger cooldown every 5 actions.
        Check for unusual activity every 10 ticks (expensive operation).
        """
        self._action_count += 1
        _note_linkedin_success()  # Reset error counter on successful action

        # Every 10 ticks, check for unusual activity banner
        self._unusual_activity_check_counter += 1
        if self._unusual_activity_check_counter >= 10:
            self._unusual_activity_check_counter = 0
            try:
                has_unusual = self._page.evaluate(
                    "() => document.body && document.body.innerText ? "
                    "document.body.innerText.toLowerCase().includes('unusual activity') : false"
                )
                if has_unusual:
                    _pause_linkedin(
                        "LinkedIn showed 'unusual activity' warning.",
                        "unusual_activity",
                    )
            except Exception:
                # Page may have navigated; skip check
                pass

        if self._action_count % 5 == 0:
            _session_cooldown()
        else:
            _human_delay()

    # ── Profile ──────────────────────────────────────────────────────────────

    def get_profile(self, linkedin_url: str) -> Optional[dict]:
        """
        Visit a LinkedIn profile page and extract key data.
        Returns a dict with headline, experience, skills, etc.
        """
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            log.warning(f"Cannot extract public ID from: {linkedin_url}")
            return None

        # Check cache first
        if public_id in self._profile_cache:
            return self._profile_cache[public_id]

        try:
            url = f"https://www.linkedin.com/in/{public_id}/"
            ok = self._safe_goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self._page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            _short_wait()

            if not ok:
                return None

            _simulate_human_browsing(self._page)

            profile = self._scrape_profile_data()
            profile["public_id"] = public_id
            self._profile_cache[public_id] = profile
            log.info(f"Fetched profile: {public_id}")
            self._tick()
            return profile
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.error(f"Failed to fetch profile {public_id}: {e}")
            return None

    def _scrape_profile_data(self) -> dict:
        """Extract profile data from the current page using JavaScript."""
        data = self._page.evaluate("""() => {
            const getText = (sel) => {
                const el = document.querySelector(sel);
                return el ? el.innerText.trim() : '';
            };
            const getAll = (sel) => {
                return Array.from(document.querySelectorAll(sel))
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0);
            };

            // Name and headline
            const name = getText('h1') || '';
            const headline = getText('.text-body-medium') || '';
            const location = getText('.text-body-small.inline.t-black--light') || '';

            // Summary / About section
            let summary = '';
            const aboutSection = document.querySelector('#about');
            if (aboutSection) {
                const aboutContent = aboutSection.closest('section');
                if (aboutContent) {
                    const spans = aboutContent.querySelectorAll('.inline-show-more-text span[aria-hidden="true"]');
                    if (spans.length > 0) summary = spans[0].innerText.trim();
                }
            }

            // Experience
            let experience = [];
            const expSection = document.querySelector('#experience');
            if (expSection) {
                const expContainer = expSection.closest('section');
                if (expContainer) {
                    const items = expContainer.querySelectorAll('.pvs-list__paged-list-item');
                    items.forEach(item => {
                        const lines = item.innerText.split('\\n').map(l => l.trim()).filter(l => l);
                        if (lines.length >= 2) {
                            experience.push({
                                title: lines[0] || '',
                                companyName: lines[1] || '',
                                dateRange: lines[2] || '',
                            });
                        }
                    });
                }
            }

            // Education
            let education = [];
            const eduSection = document.querySelector('#education');
            if (eduSection) {
                const eduContainer = eduSection.closest('section');
                if (eduContainer) {
                    const items = eduContainer.querySelectorAll('.pvs-list__paged-list-item');
                    items.forEach(item => {
                        const lines = item.innerText.split('\\n').map(l => l.trim()).filter(l => l);
                        if (lines.length >= 1) {
                            education.push({
                                schoolName: lines[0] || '',
                                degreeName: lines[1] || '',
                            });
                        }
                    });
                }
            }

            // Skills
            let skills = [];
            const skillsSection = document.querySelector('#skills');
            if (skillsSection) {
                const skillsContainer = skillsSection.closest('section');
                if (skillsContainer) {
                    const items = skillsContainer.querySelectorAll('.pvs-list__paged-list-item');
                    items.forEach(item => {
                        const name = item.querySelector('.t-bold span[aria-hidden="true"]');
                        if (name) skills.push({ name: name.innerText.trim() });
                    });
                }
            }

            return {
                firstName: name.split(' ')[0] || '',
                lastName: name.split(' ').slice(1).join(' ') || '',
                headline: headline,
                locationName: location,
                summary: summary,
                experience: experience,
                education: education,
                skills: skills,
                languages: [],
                certifications: [],
                volunteer: [],
                honors: [],
                recommendations: [],
            };
        }""")
        return data or {}

    def get_profile_posts(self, linkedin_url: str, count: int = 3) -> list:
        """Visit the profile's recent activity and grab post text."""
        public_id = self._extract_public_id(linkedin_url)
        try:
            url = f"https://www.linkedin.com/in/{public_id}/recent-activity/all/"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _short_wait()
            _simulate_human_browsing(self._page)

            posts = self._page.evaluate(f"""() => {{
                const posts = [];
                const items = document.querySelectorAll('.feed-shared-update-v2');
                for (let i = 0; i < Math.min(items.length, {count}); i++) {{
                    const textEl = items[i].querySelector('.feed-shared-text .break-words');
                    if (textEl) {{
                        posts.push({{
                            commentary: {{ text: textEl.innerText.trim().slice(0, 300) }}
                        }});
                    }}
                }}
                return posts;
            }}""")
            self._tick()
            return posts or []
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"Could not fetch posts for {public_id}: {e}")
            return []

    # ── Connection status ────────────────────────────────────────────────────

    def check_connection_status(self, linkedin_url: str, fast: bool = False) -> str:
        """
        Visit the profile page and check for 'Message' button (= connected)
        vs 'Connect' button (= not connected).

        fast=True skips human simulation — use when bulk-checking many profiles.
        Each fast check takes ~5s instead of ~85s.
        """
        public_id = self._extract_public_id(linkedin_url)
        try:
            url = f"https://www.linkedin.com/in/{public_id}/"
            ok = self._safe_goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            if fast:
                time.sleep(random.uniform(2, 4))
                # Degree badge is JS-rendered and may take a moment to appear.
                # Give it up to 5 extra seconds before falling through.
                try:
                    self._page.wait_for_function(
                        "() => /[\\u00b7\\u2022]\\s*(1st|2nd|3rd)/.test(document.body.innerText || '')",
                        timeout=5000,
                    )
                except Exception:
                    pass  # Badge didn't appear — will return 'unknown' below
            else:
                _short_wait()
                _simulate_human_browsing(self._page)

            if not ok:
                return "unknown"

            status = self._safe_evaluate("""() => {
                // ── Degree badge is the ONLY reliable signal ──────────────────────────
                // LinkedIn shows a "Message" button for ALL users (1st, 2nd, 3rd degree)
                // to upsell InMail — so presence of "Message" alone is NOT trustworthy.
                // The degree badge (· 1st / · 2nd / · 3rd) is ground truth.
                const bodyText = document.body.innerText || '';

                // LinkedIn renders it as "· 1st", "· 2nd", "· 3rd"
                const degreeMatch = bodyText.match(/[\\u00b7\\u2022]\\s*(1st|2nd|3rd)\\b/);
                if (degreeMatch) {
                    if (degreeMatch[1] === '1st') return 'connected';
                    // 2nd or 3rd — not a direct connection; check for pending
                    const pendingMatch = bodyText.match(/\\bpending\\b/i);
                    if (pendingMatch) return 'pending';
                    return 'none';
                }

                // ── Fallback: buttons (only used when badge never rendered) ─────────
                // At this point the page may not have fully loaded.
                // Only trust explicit Connect/Pending buttons — NEVER Message alone.
                const buttons = Array.from(document.querySelectorAll('button'));
                let hasConnect = false;
                let hasPending = false;

                for (const btn of buttons) {
                    const text = (btn.innerText || '').trim().toLowerCase();
                    const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (text === 'connect' || aria.includes('connect with') || aria.includes('invite')) hasConnect = true;
                    if (text === 'pending' || aria.includes('pending') || text === 'withdraw') hasPending = true;
                }

                if (hasPending) return 'pending';
                if (hasConnect) return 'none';

                // No badge + no Connect/Pending button = we can't tell yet.
                // Return 'unknown' so the lead stays in 'requested' and is checked again next run.
                return 'unknown';
            }""")

            if fast:
                time.sleep(random.uniform(2, 5))  # short pause, no cooldown
            else:
                self._tick()
            return status if status is not None else "unknown"
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"Could not check connection status for {public_id}: {e}")
            if not fast:
                self._tick()
            return "unknown"

    def _safe_evaluate(self, script: str):
        """Run page.evaluate, returning None if the page navigated away."""
        try:
            return self._page.evaluate(script)
        except Exception as e:
            msg = str(e)
            if "Execution context was destroyed" in msg or "Target closed" in msg:
                return None
            raise

    def _safe_goto(self, url: str, **kwargs) -> bool:
        """
        Navigate to url. Returns False (and logs) instead of raising if:
          - ERR_TOO_MANY_REDIRECTS  (expired cookie)
          - Page ended up on a login/authwall page
        Raises SessionExpired after 2 consecutive auth redirects (real expiry).
        Returns True on success.
        """
        try:
            self._page.goto(url, **kwargs)
        except Exception as e:
            if "ERR_TOO_MANY_REDIRECTS" in str(e):
                log.error("LinkedIn session expired (ERR_TOO_MANY_REDIRECTS).")
                log.error("Click Reconnect in the dashboard to log in again.")
                self._consecutive_auth_redirects += 1
                if self._consecutive_auth_redirects >= 2:
                    raise SessionExpired("session expired (too many redirects)")
                return False
            raise

        ok = self._assert_on_linkedin()
        if not ok:
            # Auth redirect detected
            self._consecutive_auth_redirects += 1
            if self._consecutive_auth_redirects >= 2:
                raise SessionExpired("session expired (auth redirect)")
        else:
            # Successful nav — reset counter
            self._consecutive_auth_redirects = 0
        return ok

    def _assert_on_linkedin(self) -> bool:
        """
        Return True if we're on a real LinkedIn page (not the login/authwall).
        Detect CAPTCHA/security challenges and pause automation if found.
        """
        url = self._page.url.lower()

        # Check URL for CAPTCHA and security-related patterns
        suspicious_urls = (
            "/checkpoint/challenge",
            "/checkpoint/lg/login-submit",
            "uas/",
            "security-challenge",
            "captcha",
        )
        if any(pattern in url for pattern in suspicious_urls):
            _pause_linkedin(
                "LinkedIn showed a security challenge (CAPTCHA or verification).",
                "captcha",
            )

        # Check URL for standard auth redirects
        bad = ("linkedin.com/login", "linkedin.com/checkpoint",
               "linkedin.com/authwall", "linkedin.com/uas/")
        if any(b in url for b in bad):
            log.warning(f"LinkedIn redirected to gated page: {url}")
            log.warning("Your li_at cookie may have expired. Refresh it from your browser.")
            return False

        # Check page text for unusual activity / security warnings
        try:
            page_text = self._page.evaluate(
                "() => document.body && document.body.innerText ? "
                "document.body.innerText.toLowerCase() : ''"
            ) or ""

            suspicious_phrases = (
                "unusual activity",
                "we noticed some unusual activity",
                "please verify",
                "security check",
                "let's do a quick security check",
                "captcha",
                "prove you're not a robot",
            )
            if any(phrase in page_text for phrase in suspicious_phrases):
                _pause_linkedin(
                    "LinkedIn showed a security challenge (unusual activity warning).",
                    "unusual_activity",
                )
        except Exception:
            # If we can't evaluate the page, just continue
            pass

        return True

    def get_my_connections(self, limit: int = 300) -> set:
        """
        Visit your connections page and collect public profile IDs.
        Uses keyboard End + explicit container scroll to trigger LinkedIn's
        virtual scroll, which mouse.wheel() alone does not reliably do.
        """
        try:
            ok = self._safe_goto(
                "https://www.linkedin.com/mynetwork/invite-connect/connections/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            _short_wait()

            if not ok:
                return set()

            def _collect_ids() -> set:
                ids = self._safe_evaluate("""() => {
                    const links = document.querySelectorAll('a[href*="/in/"]');
                    const ids = new Set();
                    for (const a of links) {
                        const m = a.href.match(/\\/in\\/([^/?#]+)/);
                        if (m && !/^\\d+$/.test(m[1])) ids.add(m[1]);
                    }
                    return Array.from(ids);
                }""")
                return set(ids) if ids else set()

            loaded_ids: set = set()
            stale_scrolls = 0  # consecutive scrolls that added nothing

            for scroll_attempt in range(40):  # up to ~400 connections
                _check_stop()
                if not self._assert_on_linkedin():
                    break

                current = _collect_ids()
                new_ids = current - loaded_ids
                loaded_ids.update(current)

                if len(loaded_ids) >= limit:
                    break

                if len(new_ids) == 0:
                    stale_scrolls += 1
                    if stale_scrolls >= 3:
                        # Three scrolls in a row with no new IDs — we've hit the end
                        break
                else:
                    stale_scrolls = 0

                # Scroll via JS on the page body AND fire keyboard End key —
                # LinkedIn's infinite scroll listens to both.
                self._safe_evaluate("""() => {
                    window.scrollTo(0, document.body.scrollHeight);
                    // Also scroll any overflow container that might hold the list
                    const containers = document.querySelectorAll(
                        'div[class*="scaffold-finite-scroll"], div[class*="connections"]'
                    );
                    for (const c of containers) {
                        c.scrollTop = c.scrollHeight;
                    }
                }""")
                self._page.keyboard.press("End")
                time.sleep(random.uniform(1.8, 3.0))

                # After scrolling, wait briefly for new cards to render
                try:
                    self._page.wait_for_function(
                        f"() => document.querySelectorAll('a[href*=\"/in/\"]').length > {len(loaded_ids)}",
                        timeout=4000,
                    )
                except Exception:
                    pass  # no new cards appeared — stale counter will catch it

            log.info(f"Fetched {len(loaded_ids)} connections from your network.")
            self._tick()
            return loaded_ids
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"Could not fetch connections list: {e}")
            return set()

    def get_new_connections(self) -> list:
        """Return recently accepted connections from the notifications."""
        # With Playwright we use get_recent_connections_rich instead
        return []

    def get_accepted_from_notifications(self) -> list:
        """
        Visit LinkedIn notifications page and find profiles that accepted
        our connection requests ("X accepted your connection request").
        Returns list of dicts: { url, name, slug }

        This is the most direct way to detect acceptances — no CSS selector
        fragility, because we just search for the acceptance phrase in text.
        """
        try:
            ok = self._safe_goto(
                "https://www.linkedin.com/notifications/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                self._page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            time.sleep(random.uniform(2, 3))

            if not ok:
                return []

            # Scroll a few times to load more notifications
            results = []
            seen_slugs: set = set()

            for scroll_attempt in range(5):
                _check_stop()
                if not self._assert_on_linkedin():
                    break

                accepted = self._safe_evaluate("""() => {
                    const out = [];
                    // Walk every element; if it contains "accepted your connection request"
                    // find the nearest /in/ profile link.
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null
                    );
                    const acceptedNodes = [];
                    let node;
                    while ((node = walker.nextNode())) {
                        if (/accepted your (invitation|connection request)/i.test(node.textContent)) {
                            acceptedNodes.push(node.parentElement);
                        }
                    }
                    for (const el of acceptedNodes) {
                        // Walk up to find a container with a profile link
                        let container = el;
                        let link = null;
                        for (let i = 0; i < 10; i++) {
                            if (!container) break;
                            link = container.querySelector('a[href*="/in/"]');
                            if (link) break;
                            container = container.parentElement;
                        }
                        if (!link) continue;
                        const m = link.href.match(/\\/in\\/([^/?#]+)/);
                        if (!m || /^\\d+$/.test(m[1])) continue;
                        const slug = m[1];

                        // Name: first strong/span with text near the link
                        let name = '';
                        const strong = container ? container.querySelector('strong') : null;
                        if (strong) name = strong.innerText.trim();
                        if (!name) {
                            const nameSpan = link.querySelector('span[aria-hidden="true"]') ||
                                             link.querySelector('span');
                            if (nameSpan) name = nameSpan.innerText.trim();
                        }
                        if (!name) name = link.innerText.split('\\n')[0].trim();
                        name = name.replace(/\\s*\\(.*?\\)\\s*$/, '').trim();
                        if (!name || name.length < 2) continue;

                        out.push({ slug, name, url: 'https://www.linkedin.com/in/' + slug + '/' });
                    }
                    return out;
                }""")

                if accepted:
                    for item in accepted:
                        slug = item.get("slug", "")
                        if slug and slug not in seen_slugs:
                            seen_slugs.add(slug)
                            results.append(item)

                # Scroll for older notifications
                self._safe_evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                self._page.keyboard.press("End")
                time.sleep(random.uniform(1.5, 2.5))

            log.info(f"Found {len(results)} accepted connection(s) in notifications.")
            return results

        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"get_accepted_from_notifications failed: {e}")
            return []

    def get_recent_connections_rich(self, days_back: int = 30) -> list:
        """
        Visit the connections page (sorted by most-recent) and return connections
        as a list of dicts: { url, name, title, company, connected_on_str }

        Class-agnostic approach — doesn't rely on LinkedIn CSS class names that
        change frequently.  Walks up from each /in/ link to find card context.
        Returns ALL visible connections (not just last N days) — the caller
        (cmd_sync_connections) skips ones already in state.
        """
        try:
            # Sort by recently added so newest appear first
            ok = self._safe_goto(
                "https://www.linkedin.com/mynetwork/invite-connect/connections/?sort=RECENTLY_ADDED",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            _short_wait()

            if not ok:
                return []

            results = []
            seen_slugs: set = set()

            for scroll_attempt in range(20):
                _check_stop()
                if not self._assert_on_linkedin():
                    break

                # Class-agnostic: find every /in/ link, walk up to card container,
                # extract name + subtitle + any date text from that container.
                cards = self._safe_evaluate("""() => {
                    const out = [];
                    const seenSlugs = new Set();

                    // All profile links on the page
                    const links = Array.from(document.querySelectorAll('a[href*="/in/"]'));
                    for (const link of links) {
                        const m = link.href.match(/\\/in\\/([^/?#]+)/);
                        if (!m) continue;
                        const slug = m[1];
                        if (/^\\d+$/.test(slug)) continue;   // skip numeric company IDs
                        if (seenSlugs.has(slug)) continue;
                        seenSlugs.add(slug);

                        // Walk up to a reasonable card container
                        let container = link.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!container) break;
                            const tag = container.tagName;
                            // Stop at list items or block-level divs with several children
                            if (tag === 'LI' || tag === 'ARTICLE') break;
                            if (tag === 'DIV' && container.children.length >= 3) break;
                            container = container.parentElement;
                        }

                        // Name: prefer span[aria-hidden="true"] inside the link (LinkedIn pattern)
                        let name = '';
                        const hiddenSpan = link.querySelector('span[aria-hidden="true"]');
                        if (hiddenSpan) name = hiddenSpan.innerText.trim();
                        if (!name) name = link.innerText.split('\\n')[0].trim();
                        // Strip trailing " (they/them)" etc.
                        name = name.replace(/\\s*\\(.*?\\)\\s*$/, '').trim();
                        if (!name || name.length < 2) continue;
                        // Skip nav / header links
                        if (/^(linkedin|home|messaging|jobs|notifications)/i.test(name)) continue;

                        // Subtitle (headline / occupation) — first non-name text block in container
                        let occupation = '';
                        if (container) {
                            const spans = Array.from(container.querySelectorAll('span, p'))
                                .filter(el => {
                                    const t = el.innerText.trim();
                                    return t && t.length > 3 && t !== name
                                        && !el.querySelector('a')   // not a link wrapper
                                        && el.children.length === 0; // leaf node
                                });
                            if (spans.length > 0) occupation = spans[0].innerText.trim();
                        }

                        // Date text: look for month names or "connected" keyword anywhere in container
                        let dateText = '';
                        if (container) {
                            const full = container.innerText || '';
                            const dm = full.match(
                                /(?:connected[\\s\\S]{0,20})?(?:january|february|march|april|may|june|july|august|september|october|november|december)\\s+\\d{1,2},?\\s+\\d{4}/i
                            );
                            if (dm) dateText = dm[0].trim();
                        }

                        out.push({ slug, name, occupation, dateText,
                                   url: 'https://www.linkedin.com/in/' + slug + '/' });
                    }
                    return out;
                }""")

                if not cards:
                    # No cards yet — may still be loading; try a couple of times
                    if scroll_attempt < 3:
                        self._page.mouse.wheel(0, 400)
                        time.sleep(random.uniform(1.5, 2.5))
                        continue
                    break

                new_in_scroll = 0
                for card in cards:
                    slug = card.get("slug", "")
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    name = card.get("name", "").strip()
                    if not name or len(name) < 2:
                        continue

                    # Split occupation into title + company
                    occupation = card.get("occupation", "")
                    title, company = "", ""
                    if " at " in occupation:
                        parts = occupation.split(" at ", 1)
                        title, company = parts[0].strip(), parts[1].strip()
                    elif " | " in occupation:
                        parts = occupation.split(" | ", 1)
                        title, company = parts[0].strip(), parts[1].strip()
                    else:
                        title = occupation

                    results.append({
                        "url":              card["url"],
                        "name":             name,
                        "title":            title,
                        "company":          company,
                        "connected_on_str": card.get("dateText", ""),
                    })
                    new_in_scroll += 1

                # Once we're only seeing already-seen slugs we've loaded everything
                if new_in_scroll == 0 and scroll_attempt >= 2:
                    break

                # Scroll down for more
                self._page.mouse.wheel(0, random.randint(600, 900))
                time.sleep(random.uniform(1.5, 2.5))

            log.info(f"Synced {len(results)} connections from network page.")
            self._tick()
            return results

        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"get_recent_connections_rich failed: {e}")
            return []

    def withdraw_old_invitations(self, sent_urls: list, max_withdraw: int = 20) -> list:
        """
        Visit the sent-invitations manager and withdraw requests that are in sent_urls.
        Returns list of public_ids that were successfully withdrawn.
        Only withdraws up to max_withdraw per call to stay safe.
        """
        withdrawn = []
        try:
            ok = self._safe_goto(
                "https://www.linkedin.com/mynetwork/invitation-manager/sent/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if not ok:
                return withdrawn
            try:
                self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            _short_wait()

            # Build set of public_ids to withdraw
            ids_to_withdraw = set()
            for url in sent_urls:
                pid = self._extract_public_id(url)
                if pid:
                    ids_to_withdraw.add(pid.lower())

            scroll_attempts = 0
            while scroll_attempts < 15 and len(withdrawn) < max_withdraw:
                _check_stop()

                # Find all invitation cards on the page
                cards = self._safe_evaluate("""() => {
                    const results = [];
                    const cards = document.querySelectorAll('.invitation-card, [data-view-name="invitation-card"], li.mn-invitation-card');
                    for (const card of cards) {
                        const link = card.querySelector('a[href*="/in/"]');
                        const btn = card.querySelector('button[aria-label*="Withdraw"], button[aria-label*="withdraw"]');
                        if (link && btn) {
                            const match = link.href.match(/\\/in\\/([^/?#]+)/);
                            if (match) results.push({ id: match[1].toLowerCase(), btnText: btn.innerText });
                        }
                    }
                    return results;
                }""") or []

                for card in cards:
                    pid = card.get("id", "")
                    if pid in ids_to_withdraw and pid not in withdrawn:
                        # Click withdraw button for this card
                        withdrew = self._safe_evaluate(f"""() => {{
                            const cards = document.querySelectorAll('.invitation-card, [data-view-name="invitation-card"], li.mn-invitation-card');
                            for (const card of cards) {{
                                const link = card.querySelector('a[href*="/in/{pid}"]');
                                const btn = card.querySelector('button[aria-label*="Withdraw"], button[aria-label*="withdraw"]');
                                if (link && btn) {{ btn.click(); return true; }}
                            }}
                            return false;
                        }}""")
                        if withdrew:
                            withdrawn.append(pid)
                            log.info(f"Withdrew invitation: {pid}")
                            time.sleep(random.uniform(2, 4))
                            # Confirm dialog if it appears
                            try:
                                self._page.wait_for_selector('button[aria-label*="Withdraw"]', timeout=2000)
                                self._safe_evaluate("""() => {
                                    const modal = document.querySelector('[role="dialog"]');
                                    if (modal) {
                                        const btn = modal.querySelector('button[aria-label*="Withdraw"], button[aria-label*="withdraw"]');
                                        if (btn) btn.click();
                                    }
                                }""")
                                time.sleep(random.uniform(1, 2))
                            except Exception:
                                pass
                        if len(withdrawn) >= max_withdraw:
                            break

                # Scroll to load more
                self._page.mouse.wheel(0, random.randint(600, 1000))
                time.sleep(random.uniform(1.5, 3))
                scroll_attempts += 1

            log.info(f"Withdrew {len(withdrawn)} old invitations.")
            self._tick()
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.warning(f"Could not withdraw invitations: {e}")
        return withdrawn

    # ── Connection requests ──────────────────────────────────────────────────

    def send_connection_request(self, linkedin_url: str, message: str = "") -> bool:
        """
        Visit a profile and click the Connect button.
        No note by default — notes lower acceptance rates.
        """
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            return False
        try:
            url = f"https://www.linkedin.com/in/{public_id}/"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _short_wait()
            _simulate_human_browsing(self._page)

            # Find and click the Connect button
            clicked = self._page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.innerText.trim().toLowerCase();
                    const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (text === 'connect' || ariaLabel.includes('connect with') || ariaLabel.includes('invite')) {
                        btn.click();
                        return true;
                    }
                }
                // Check for "More" dropdown that might contain Connect
                for (const btn of buttons) {
                    const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (ariaLabel.includes('more actions')) {
                        btn.click();
                        return 'more_menu';
                    }
                }
                return false;
            }""")

            if clicked == "more_menu":
                time.sleep(1)
                # Look for Connect in the dropdown
                self._page.evaluate("""() => {
                    const items = document.querySelectorAll('[role="menuitem"], .artdeco-dropdown__item');
                    for (const item of items) {
                        if (item.innerText.toLowerCase().includes('connect')) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                time.sleep(1)

            if clicked:
                time.sleep(1.5)
                # Handle the "Add a note" / "Send without a note" modal
                self._page.evaluate("""() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.innerText.trim().toLowerCase();
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('send without a note') || text === 'send' ||
                            ariaLabel.includes('send now') || ariaLabel.includes('send invitation')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                time.sleep(1)
                log.info(f"Connection request sent → {public_id}")
                self._tick()
                return True
            else:
                log.warning(f"Could not find Connect button for {public_id}")
                self._tick()
                return False

        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.error(f"Connection request failed for {public_id}: {e}")
            return False

    # ── Messaging ────────────────────────────────────────────────────────────

    def send_message(self, linkedin_url: str, message_text: str) -> bool:
        """Open messaging with a connection and send a message."""
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            return False
        try:
            # Navigate to the profile page and click the Message button
            profile_url = f"https://www.linkedin.com/in/{public_id}/"
            self._page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            _short_wait()

            # Verify this is actually a 1st-degree connection before trying to message
            degree = self._safe_evaluate("""() => {
                const t = document.body.innerText || '';
                const m = t.match(/[·•]\\s*(1st|2nd|3rd)\\b/);
                return m ? m[1] : 'unknown';
            }""")
            if degree and degree not in ('1st', 'unknown'):
                log.warning(f"Skipping {public_id} — not a 1st-degree connection (shows '{degree}'). Returning not_connected.")
                return "not_connected"

            # Click the Message button
            clicked = self._page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const t = (btn.innerText || '').trim().toLowerCase();
                    const a = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (t === 'message' || a.includes('message')) { btn.click(); return true; }
                }
                return false;
            }""")
            if not clicked:
                log.error(f"No Message button found for {public_id}")
                return False

            # Wait for response — could be overlay, full page nav, or paywall popup
            time.sleep(3)

            # Detect paywall / Sales Nav / Premium modal — means not truly connected
            paywall = self._safe_evaluate("""() => {
                const modals = document.querySelectorAll('[role="dialog"], .artdeco-modal, .premium-upsell-modal');
                for (const m of modals) {
                    const t = (m.innerText || '').toLowerCase();
                    if (t.includes('sales nav') || t.includes('premium') || t.includes('inmail') || t.includes('reactivate')) {
                        // Close the modal
                        const closeBtn = m.querySelector('button[aria-label*="Dismiss"], button[aria-label*="Close"], .artdeco-modal__dismiss');
                        if (closeBtn) closeBtn.click();
                        return true;
                    }
                }
                return false;
            }""")
            if paywall:
                log.warning(f"Skipping {public_id} — not a 1st-degree connection (paywall appeared). Reverting status.")
                return "not_connected"

            # Find the message compose box (overlay or full messaging page)
            msg_box = None
            for sel in [
                'div.msg-form__contenteditable[contenteditable="true"]',
                '.msg-form__msg-content-container div[contenteditable="true"]',
                'div[contenteditable="true"][data-placeholder]',
                '[role="textbox"][contenteditable="true"]',
                'div[contenteditable="true"]',
            ]:
                try:
                    self._page.wait_for_selector(sel, timeout=6000, state="visible")
                    loc = self._page.locator(sel)
                    visible = [l for l in loc.all() if l.is_visible()]
                    if visible:
                        msg_box = visible[0]
                        log.info(f"Found message input via: {sel}")
                        break
                except Exception:
                    continue

            if msg_box is None:
                log.error(f"Could not find message input box for {public_id} — skipping")
                return False

            msg_box.click()
            time.sleep(0.5)

            # Validate message before typing — guard against empty or absurdly long messages
            msg_stripped = message_text.strip()
            if not msg_stripped:
                log.error(f"Message text is empty for {public_id} — skipping")
                return False
            if len(msg_stripped) > 1800:
                log.warning(f"Message too long ({len(msg_stripped)} chars) for {public_id} — truncating to 1800")
                msg_stripped = msg_stripped[:1800]

            # Type the message character by character with small delays (human-like)
            for char in msg_stripped:
                msg_box.type(char, delay=random.randint(20, 80))
                if random.random() < 0.02:  # occasional micro-pause
                    time.sleep(random.uniform(0.3, 0.8))

            time.sleep(random.uniform(1, 2))

            # Click Send — button first (actually submits the form), Enter as fallback
            send_btn = None
            for sel in [
                'button.msg-form__send-button',
                '.msg-form__send-button',
                'button[aria-label="Send"]',
                'button[data-control-name="send"]',
                'button:has-text("Send")',
            ]:
                try:
                    loc = self._page.locator(sel)
                    visible_btns = [b for b in loc.all() if b.is_visible()]
                    if visible_btns:
                        send_btn = visible_btns[-1]
                        break
                except Exception:
                    continue

            if send_btn:
                send_btn.click()
                time.sleep(1.5)
                # Verify: message box should be empty after a successful send
                try:
                    box_text = msg_box.inner_text()
                    if box_text.strip():
                        # Box still has text — button click may not have submitted; try Enter
                        log.warning(f"Send button clicked but box still has text for {public_id} — trying Enter")
                        msg_box.press("Enter")
                        time.sleep(1)
                except Exception:
                    pass
                log.info(f"Message sent via button → {public_id}")
            else:
                # Fallback: Enter key (less reliable but better than nothing)
                msg_box.press("Enter")
                time.sleep(1)
                log.info(f"Message sent via Enter key → {public_id}")

            time.sleep(0.5)
            log.info(f"Message sent → {public_id}: {msg_stripped[:60]}…")

            # No close button needed — we navigated to the full messaging page, not an overlay

            self._tick()
            return True

        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.error(f"Failed to send message to {public_id}: {e}")
            return False

    def get_conversation(self, linkedin_url: str) -> list:
        """Navigate to the messaging thread and extract messages."""
        public_id = self._extract_public_id(linkedin_url)
        try:
            # Go to messaging page
            url = f"https://www.linkedin.com/messaging/thread/new/?recipient={public_id}"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _short_wait()

            # Walk message GROUPS so every bubble in a group inherits the same sender name.
            # LinkedIn only puts the profile-link on the first bubble of each group; individual
            # bubbles don't have it — hence the old code was tagging most messages as 'unknown'.
            messages = self._page.evaluate("""() => {
                const msgs = [];
                // Each group container holds consecutive messages from one sender
                const groups = document.querySelectorAll(
                    '.msg-s-message-group, .msg-s-message-group-container'
                );
                groups.forEach(group => {
                    // The sender name lives on the group-level profile link
                    const senderEl = group.querySelector(
                        '.msg-s-message-group__profile-link, ' +
                        '.msg-s-message-group__name, ' +
                        'a[data-control-name="view_profile"]'
                    );
                    const senderName = senderEl ? senderEl.innerText.trim() : '';
                    // Collect every message bubble inside this group
                    const bubbles = group.querySelectorAll(
                        '.msg-s-event-listitem__body, ' +
                        '.msg-s-event-listitem__message-bubble'
                    );
                    bubbles.forEach(bubble => {
                        const text = bubble.innerText.trim();
                        if (text) {
                            msgs.push({ text, sender_name: senderName });
                        }
                    });
                });
                // Fallback: if groups approach returns nothing try flat list
                if (!msgs.length) {
                    document.querySelectorAll('.msg-s-event-listitem').forEach(item => {
                        const body = item.querySelector('.msg-s-event-listitem__body');
                        const sender = item.querySelector('.msg-s-message-group__profile-link');
                        if (body) {
                            msgs.push({
                                text: body.innerText.trim(),
                                sender_name: sender ? sender.innerText.trim() : '',
                            });
                        }
                    });
                }
                return msgs;
            }""")

            # Classify each message as "me" or "them"
            result = []
            my_name = self._get_my_name().lower()
            for m in (messages or []):
                sn = m.get("sender_name", "").lower().strip()
                # A blank sender_name means we couldn't detect it — treat as "them"
                # to be safe (we'd rather miss a false reply than send a duplicate)
                if not sn:
                    sender = "them"
                elif my_name and my_name in sn:
                    sender = "me"
                else:
                    sender = "them"
                result.append({
                    "sender": sender,
                    "text": m.get("text", ""),
                    "timestamp": "",
                })
            return result
        except StopSignal:
            raise
        except Exception as e:
            _note_linkedin_error()
            log.error(f"Failed to fetch conversation with {public_id}: {e}")
            return []

    def get_all_conversations_with_replies(self, tracked_urls: list) -> dict:
        """Check inbox for new replies from tracked leads."""
        updates = {}
        for url in tracked_urls:
            convo = self.get_conversation(url)
            if convo and convo[-1]["sender"] == "them":
                updates[url] = convo
            self._tick()
        return updates

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_my_name(self) -> str:
        """Get your own name for message attribution."""
        if not hasattr(self, "_me_name") or not self._me_name:
            try:
                self._page.goto(
                    "https://www.linkedin.com/feed/",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                _short_wait()
                self._me_name = self._page.evaluate("""() => {
                    const el = document.querySelector('.feed-identity-module__actor-meta a');
                    return el ? el.innerText.trim() : '';
                }""") or ""
            except Exception:
                self._me_name = ""
        return self._me_name

    @staticmethod
    def _extract_public_id(url: str) -> Optional[str]:
        match = re.search(r"linkedin\.com/in/([^/?#]+)", url)
        return match.group(1).rstrip("/") if match else None
