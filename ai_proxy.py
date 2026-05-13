# ─────────────────────────────────────────────────────────────────────────────
# ai_proxy.py  —  Thin HTTP client for Influentia's hosted AI + Search proxy.
#
# All Claude and Brave Search calls are routed through the Influentia Worker,
# which validates the license on every request and holds the API keys securely.
# Users never need their own API keys — they just subscribe.
#
# DEVELOPER BYPASS: When the license key starts with "OWNER-", calls are made
# directly to Anthropic and Brave Search APIs using the keys in .env, skipping
# the proxy entirely. This lets the developer run without a paid license.
# ─────────────────────────────────────────────────────────────────────────────
import hashlib
import json
import os
import platform
import time
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

WORKER_URL = "https://outreach-pilot-api-production.plain-king-ead0.workers.dev"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"

_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
_LICENSE_FILE = os.path.join(_BASE_DIR, ".license.json")


def _machine_id() -> str:
    """Stable fingerprint for this machine — used to enforce per-device license limits."""
    raw = f"{platform.node()}-{platform.machine()}-{platform.system()}-{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _machine_name() -> str:
    """Human-readable name shown in the license portal."""
    return f"{platform.system()} / {platform.node()}"


def _is_owner_key(key: str) -> bool:
    """Returns True if this is a developer/owner key that bypasses the proxy."""
    return key.startswith("OWNER-")


def _get_direct_api_keys() -> tuple:
    """Load Anthropic and Brave keys directly from config (via .env)."""
    try:
        import config
        return config.ANTHROPIC_API_KEY, config.BRAVE_SEARCH_API_KEY
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", ""), os.environ.get("BRAVE_SEARCH_API_KEY", "")


def _call_ai_direct(messages: list, model: str, max_tokens: int,
                     system: str = None, temperature: float = None) -> str:
    """Call Anthropic API directly, bypassing the Influentia proxy."""
    anthropic_key, _ = _get_direct_api_keys()
    if not anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env — required for developer mode.")

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": anthropic_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
            return result["content"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            log.error("Anthropic direct HTTP %s: %s", e.code, body)
            if e.code in (429, 529) and attempt < 2:
                wait = 15 * (attempt + 1)
                log.warning("Rate limit — retrying in %ss", wait)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Anthropic direct error {e.code}: {body[:200]}") from e
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
                continue
            raise RuntimeError(f"Anthropic direct call failed: {e}") from e

    raise RuntimeError("Anthropic direct call failed after 3 attempts.")


def _search_web_direct(query: str, count: int = 20, offset: int = 0, freshness: str = "") -> dict:
    """Call Brave Search API directly, bypassing the Influentia proxy."""
    _, brave_key = _get_direct_api_keys()
    if not brave_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY not set in .env — required for developer mode.")

    params = f"?q={urllib.request.quote(query)}&count={min(20, count)}&offset={offset}&search_lang=en"
    if freshness:
        params += f"&freshness={freshness}"
    req = urllib.request.Request(
        BRAVE_SEARCH_API_URL + params,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": brave_key,
        },
        method="GET",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                import gzip
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            log.error("Brave direct HTTP %s: %s", e.code, body)
            if e.code == 429 and attempt < 2:
                time.sleep(10)
                continue
            raise RuntimeError(f"Brave direct error {e.code}: {body[:200]}") from e
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            raise RuntimeError(f"Brave direct search failed: {e}") from e

    raise RuntimeError("Brave direct search failed after 3 attempts.")


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
    temperature: float = None,
) -> str:
    """
    Call Claude through the Influentia proxy worker.
    License is validated server-side on every request.

    Args:
        messages:   list of {"role": "user"|"assistant", "content": "..."}
        model:      Claude model string
        max_tokens: max tokens to generate
        system:     optional system prompt
        temperature: optional sampling temperature (passed only for direct calls)

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

    # Developer bypass — call Anthropic directly without going through the proxy
    if _is_owner_key(key):
        log.debug("Owner key detected — calling Anthropic API directly.")
        return _call_ai_direct(messages, model, max_tokens, system, temperature)

    payload: dict = {
        "license_key": key,
        "device_id": _machine_id(),
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
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
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


def search_web(query: str, count: int = 20, offset: int = 0, freshness: str = "") -> dict:
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

    # Developer bypass — call Brave Search directly without going through the proxy
    if _is_owner_key(key):
        log.debug("Owner key detected — calling Brave Search API directly.")
        return _search_web_direct(query, count, offset, freshness)

    payload = json.dumps({
        "license_key": key,
        "device_id": _machine_id(),
        "query": query,
        "count": min(20, count),
        "offset": offset,
        "freshness": freshness,
    }).encode()

    req = urllib.request.Request(
        f"{WORKER_URL}/api/proxy/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
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
