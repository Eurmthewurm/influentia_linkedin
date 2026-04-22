# ─────────────────────────────────────────────────────────────────────────────
# linkedin_client.py  —  LinkedIn automation via session cookie
#
# Uses the unofficial 'linkedin-api' Python library.
# Install: pip install linkedin-api
# Docs:    https://github.com/tomquirk/linkedin-api
# ─────────────────────────────────────────────────────────────────────────────
import time
import random
import logging
from typing import Optional
from linkedin_api import Linkedin
from config import (
    LINKEDIN_LI_AT_COOKIE,
    DELAY_BETWEEN_REQUESTS_SECONDS,
    LOG_FILE_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def _safe_delay():
    """Random delay between actions to mimic human behaviour."""
    base  = DELAY_BETWEEN_REQUESTS_SECONDS
    jitter = random.randint(15, 45)
    total  = base + jitter
    log.info(f"Waiting {total}s before next action…")
    time.sleep(total)


class LinkedInClient:
    """
    Thin wrapper around linkedin-api that adds rate-limiting and logging.

    Usage:
        client = LinkedInClient()
        profile = client.get_profile("https://www.linkedin.com/in/someuser")
        client.send_connection_request(profile["urn"], message="Hi!")
    """

    def __init__(self):
        # linkedin-api can authenticate via cookie.
        # We pass the li_at cookie value directly.
        self.api = Linkedin("", "", authenticate=False)
        self.api.client.session.cookies.set("li_at", LINKEDIN_LI_AT_COOKIE)
        log.info("LinkedIn client initialised with session cookie.")

    # ── Profile ───────────────────────────────────────────────────────────────

    def get_profile(self, linkedin_url: str) -> Optional[dict]:
        """
        Fetch a full LinkedIn profile from a profile URL.
        Returns None if the profile cannot be fetched.
        """
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            log.warning(f"Could not extract public ID from: {linkedin_url}")
            return None
        try:
            profile = self.api.get_profile(public_id)
            log.info(f"Fetched profile: {public_id}")
            return profile
        except Exception as e:
            log.error(f"Failed to fetch profile {public_id}: {e}")
            return None

    def get_profile_posts(self, linkedin_url: str, count: int = 5) -> list:
        """Fetch recent posts for a profile (used to personalise message)."""
        public_id = self._extract_public_id(linkedin_url)
        try:
            posts = self.api.get_profile_posts(public_id, post_count=count)
            return posts or []
        except Exception as e:
            log.warning(f"Could not fetch posts for {public_id}: {e}")
            return []

    # ── Connections ───────────────────────────────────────────────────────────

    def send_connection_request(self, linkedin_url: str, message: str = "") -> bool:
        """
        Send a connection request to a profile URL.
        Returns True on success.

        NOTE: LinkedIn limits connection requests to ~20-25/day.
        The config.MAX_CONNECTION_REQUESTS_PER_DAY enforces this in main.py.
        """
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            return False
        try:
            # Get the profile URN first (needed by linkedin-api)
            profile = self.api.get_profile(public_id)
            urn_id  = profile.get("profile_id") or profile.get("entityUrn", "").split(":")[-1]

            self.api.add_connection(urn_id, message=message)
            log.info(f"Connection request sent to {public_id}")
            _safe_delay()
            return True
        except Exception as e:
            log.error(f"Connection request failed for {public_id}: {e}")
            return False

    def get_pending_connections(self) -> list:
        """
        Return a list of profiles who accepted our connection requests.
        linkedin-api returns these as 'new connections' in the network feed.
        """
        try:
            return self.api.get_new_connections() or []
        except Exception as e:
            log.error(f"Failed to fetch new connections: {e}")
            return []

    # ── Messaging ─────────────────────────────────────────────────────────────

    def send_message(self, linkedin_url: str, message_text: str) -> bool:
        """
        Send a direct message to a 1st-degree connection.
        Returns True on success.
        """
        public_id = self._extract_public_id(linkedin_url)
        if not public_id:
            return False
        try:
            profile = self.api.get_profile(public_id)
            urn_id  = profile.get("profile_id") or profile.get("entityUrn", "").split(":")[-1]

            self.api.send_message(message_body=message_text, recipients=[urn_id])
            log.info(f"Message sent to {public_id}: {message_text[:60]}…")
            _safe_delay()
            return True
        except Exception as e:
            log.error(f"Failed to send message to {public_id}: {e}")
            return False

    def get_conversation(self, linkedin_url: str) -> list:
        """
        Fetch the full message thread with a connection.
        Returns a list of {"sender": "me"|"them", "text": "...", "timestamp": ...}
        """
        public_id = self._extract_public_id(linkedin_url)
        try:
            profile = self.api.get_profile(public_id)
            urn_id  = profile.get("profile_id") or profile.get("entityUrn", "").split(":")[-1]
            messages = self.api.get_conversation(urn_id)

            result = []
            for m in (messages or []):
                body   = m.get("body", {}).get("text", "")
                sender = m.get("from", {}).get("com.linkedin.voyager.messaging.MessagingMember", {})
                is_me  = sender.get("miniProfile", {}).get("publicIdentifier") == self._my_public_id()
                result.append({
                    "sender": "me" if is_me else "them",
                    "text": body,
                    "timestamp": m.get("createdAt", ""),
                })
            return result
        except Exception as e:
            log.error(f"Failed to fetch conversation with {public_id}: {e}")
            return []

    def get_all_conversations_with_replies(self, tracked_urls: list) -> dict:
        """
        For a list of LinkedIn URLs we're tracking, check if any have
        new messages from the prospect. Returns {url: [messages]} for
        any threads that have an unread reply.
        """
        updates = {}
        for url in tracked_urls:
            convo = self.get_conversation(url)
            # Check if last message is from them (i.e., they replied)
            if convo and convo[-1]["sender"] == "them":
                updates[url] = convo
            _safe_delay()
        return updates

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_public_id(url: str) -> Optional[str]:
        """Extract the public ID from a LinkedIn profile URL."""
        import re
        match = re.search(r"linkedin\.com/in/([^/?#]+)", url)
        return match.group(1).rstrip("/") if match else None

    def _my_public_id(self) -> str:
        """Return the authenticated user's public ID (cached)."""
        if not hasattr(self, "_me_id"):
            try:
                me = self.api.get_user_profile()
                self._me_id = me.get("miniProfile", {}).get("publicIdentifier", "")
            except Exception:
                self._me_id = ""
        return self._me_id
