# ─────────────────────────────────────────────────────────────────────────────
# ai_proxy.py  —  Thin HTTP client for Influentia's hosted AI + Search proxy.
#
# All Claude and Brave Search calls are routed through the Influentia Worker,
# which validates the license on every request and holds the API keys securely.
# Users never need their own API keys — they just subscribe.
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import time
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

WORKER_URL = "https://outreach-pilot-api-production.plain-king-ead0.workers.dev"

_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
_LICENSE_FILE = os.path.join(_BASE_DIR, ".license.json")


def _load_license_key() -> str:
    """Read the cached license key from .license.json."""
    try:
        with open(_LICENSE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("key", "")
    except Exception:
        return ""


def call_ai(
    messages: list,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 256,
    system: str = None,
) -> str:
    """
    Call Claude through the Influentia proxy worker.
    License is validated server-side on every request.

    Args:
        messages:   list of {"role": "user"|"assistant", "content": "..."}
        model:      Claude model string
        max_tokens: max tokens to generate
        system:     optional system prompt

    Returns:
        The text content of Claude's response.

    Raises:
        RuntimeError if the license is missing/revoked or the proxy call fails.
    """
    key = _load_license_key()
    if not key:
        raise RuntimeError(
            "No license key found. Please enter your license key in the dashboard."
        )

    payload: dict = {
        "license_key": key,
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{WORKER_URL}/api/proxy/message",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
            # Anthropic response shape: {content: [{type:"text", text:"..."}], ...}
            return result["content"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            log.error("AI proxy HTTP %s: %s", e.code, body)
            if e.code == 403:
                # License invalid — surface a clean error
                try:
                    detail = json.loads(body).get("reason", "invalid")
                except Exception:
                    detail = "invalid"
                raise RuntimeError(
                    f"License {detail}. Please renew your subscription at influentia.io/account."
                ) from e
            if e.code in (429, 529) and attempt < 2:
                wait = 15 * (attempt + 1)
                log.warning("Rate limit hit — retrying in %ss", wait)
                time.sleep(wait)
                continue
            raise RuntimeError(f"AI proxy error {e.code}: {body[:200]}") from e
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
                continue
            raise RuntimeError(f"AI proxy failed: {e}") from e

    raise RuntimeError("AI proxy failed after 3 attempts.")


def call_ai_fast(messages: list, max_tokens: int = 150, system: str = None) -> str:
    """Convenience wrapper using the fast/cheap Haiku model."""
    return call_ai(
        messages,
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
    )


def search_web(query: str, count: int = 20, offset: int = 0) -> dict:
    """
    Search the web via the Influentia proxy (Brave Search behind the scenes).
    License is validated server-side.

    Returns:
        The raw Brave Search API JSON dict, e.g. {"web": {"results": [...]}}

    Raises:
        RuntimeError on failure.
    """
    key = _load_license_key()
    if not key:
        raise RuntimeError(
            "No license key found. Please enter your license key in the dashboard."
        )

    payload = json.dumps({
        "license_key": key,
        "query": query,
        "count": min(20, count),
        "offset": offset,
    }).encode()

    req = urllib.request.Request(
        f"{WORKER_URL}/api/proxy/search",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            log.error("Search proxy HTTP %s: %s", e.code, body)
            if e.code == 403:
                try:
                    detail = json.loads(body).get("reason", "invalid")
                except Exception:
                    detail = "invalid"
                raise RuntimeError(
                    f"License {detail}. Please renew your subscription at influentia.io/account."
                ) from e
            if e.code == 429 and attempt < 2:
                time.sleep(10)
                continue
            raise RuntimeError(f"Search proxy error {e.code}: {body[:200]}") from e
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            raise RuntimeError(f"Search proxy failed: {e}") from e

    raise RuntimeError("Search proxy failed after 3 attempts.")
