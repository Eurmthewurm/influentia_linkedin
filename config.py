# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  Loads configuration from .env (or environment variables)
# ─────────────────────────────────────────────────────────────────────────────
#
#  You should NOT put API keys or personal details in this file.
#  Everything sensitive lives in the `.env` file next to this one.
#
#  On first run, copy `.env.example` to `.env` and fill it in:
#      cp .env.example .env
#
#  If a key is ever exposed, revoke it immediately:
#    • Claude API:  https://console.anthropic.com  → API Keys
#    • Brave Search: https://api.search.brave.com  → Your Keys
#
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
from pathlib import Path

# ── Tiny .env loader (no extra dependencies) ─────────────────────────────────
def _load_dotenv(path: Path) -> None:
    """Read a .env file and populate os.environ for any keys not already set."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip surrounding quotes if present
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                # Do not overwrite variables already set (with a real value)
                # in the real environment. Empty values are treated as unset.
                existing = os.environ.get(key, "")
                if key and not existing.strip():
                    os.environ[key] = value
    except Exception as exc:
        print(f"[config] Warning: could not read .env file ({exc})", file=sys.stderr)


_BASE_DIR = Path(__file__).resolve().parent
_load_dotenv(_BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    """Read a string from the environment, fall back to default."""
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list) -> list:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ── 1. API keys (loaded from .env) ───────────────────────────────────────────
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
BRAVE_SEARCH_API_KEY = _env("BRAVE_SEARCH_API_KEY")

# ── 2. Your identity (loaded from .env, with sensible defaults) ──────────────
YOUR_NAME      = _env("YOUR_NAME", "")
YOUR_COMPANY   = _env("YOUR_COMPANY", "")
YOUR_GOAL      = _env("YOUR_GOAL", "book a quick call")
YOUR_GOAL_LINK = _env("YOUR_GOAL_LINK", "")
YOUR_WEBSITE   = _env("YOUR_WEBSITE", "")

# ── 3. Your offering (long-form description of what you sell) ────────────────
# Kept here because multi-line values are awkward in .env files.
# Edit freely — this is not a secret and is easy to change from the dashboard.
YOUR_OFFERING = """
# Authentik Studio — Brand Documentary and Video Content for B2B Founders

Authentik Studio is a brand new video production and content studio. We just signed our first client.

The founder, Ermo, was previously Creative Director at J-Griff — an online creator and influencer brand. During that time the channel grew from 2 million to 8 million views over 18 months through a structured weekly content system and anchor documentary work, with no paid promotion.

## The problem we solve

Expert-led B2B founders — consultants, agency owners, niche recruiters, coaches — do exceptional real-world work but their online presence does not reflect it. The credibility gap between what they actually do and what the market can see is costing them deals they never know they are losing. Buyers find their profile, see generic content that does not match the reputation they heard about, and move on quietly.

Most AI clip tools (Descript, Opus) make volume easier but not trust easier. Volume without trust is just more noise.

## What we do

We handle the entire video content system end to end: strategy, storytelling, on-site filming, production, and editing. Every client gets a content framework built around their specific expertise and buyer, weekly talking-head episodes for consistent LinkedIn visibility, and anchor mini-documentaries that go deep on their story or process. Everything mapped for LinkedIn distribution.

## Who we serve

Expert-led B2B service businesses who are already delivering great work but are invisible online. Consultants, agency owners, niche recruiters, coaches. Active on LinkedIn and ready to invest in a content system that actually reflects the quality of their work.

## Our edge

Ermo combines film-grade documentary storytelling with strategic content planning. Unlike editors who only cut footage or strategists who only plan, we do both. The result: content that makes buyers trust you before the first call.

## Honest position

We are early. We have deep expertise and one client in production. We are building this the right way — with real results, not manufactured ones.
"""

# ── 4. Location exclusions ───────────────────────────────────────────────────
#    Leads whose location/country matches any of these strings (case-insensitive)
#    will be skipped during lead-finding and connection-syncing.
#    Override via EXCLUDED_LOCATIONS in .env (comma-separated).
EXCLUDED_LOCATIONS: list = _env_list(
    "EXCLUDED_LOCATIONS",
    ["Netherlands", "Nederland", "Dutch", " NL ", "Holland"],
)

# ── 5. Safety settings (LinkedIn rate limits — do NOT raise these blindly) ───
MAX_CONNECTION_REQUESTS_PER_DAY = _env_int("MAX_CONNECTION_REQUESTS_PER_DAY", 15)
MAX_MESSAGES_PER_DAY            = _env_int("MAX_MESSAGES_PER_DAY", 20)
DELAY_BETWEEN_REQUESTS_SECONDS  = _env_int("DELAY_BETWEEN_REQUESTS_SECONDS", 90)
POLL_INTERVAL_HOURS             = _env_int("POLL_INTERVAL_HOURS", 4)

# ── 6. Follow-up settings ────────────────────────────────────────────────────
FOLLOW_UP_AFTER_DAYS = _env_int("FOLLOW_UP_AFTER_DAYS", 3)
MAX_FOLLOW_UPS       = _env_int("MAX_FOLLOW_UPS", 1)

# ── 7. File paths ────────────────────────────────────────────────────────────
LEADS_EXCEL_PATH = _env("LEADS_EXCEL_PATH", "")
STATE_FILE_PATH  = _env("STATE_FILE_PATH", "state.json")
LOG_FILE_PATH    = _env("LOG_FILE_PATH", "outreach_log.txt")


# ── Startup validation (friendly errors instead of silent failures) ──────────
def validate_config(strict: bool = False) -> list:
    """
    Return a list of human-readable problems with the current config.
    If strict=True and problems exist, prints them and raises SystemExit.
    """
    problems = []

    if not ANTHROPIC_API_KEY:
        problems.append(
            "ANTHROPIC_API_KEY is missing. Get a key at https://console.anthropic.com "
            "and add it to your .env file."
        )
    elif not ANTHROPIC_API_KEY.startswith("sk-ant-"):
        problems.append(
            "ANTHROPIC_API_KEY does not look like a valid Claude key "
            "(expected to start with 'sk-ant-')."
        )

    if not BRAVE_SEARCH_API_KEY:
        problems.append(
            "BRAVE_SEARCH_API_KEY is missing. Free key at https://api.search.brave.com "
            "(no credit card needed). Add it to your .env file."
        )

    if not YOUR_NAME:
        problems.append("YOUR_NAME is empty. Set it in .env so messages can be personalised.")

    if not YOUR_COMPANY:
        problems.append("YOUR_COMPANY is empty. Set it in .env.")

    if strict and problems:
        print("\n⚠️  Configuration problems detected:\n", file=sys.stderr)
        for p in problems:
            print(f"  • {p}", file=sys.stderr)
        print(
            "\nFix these by editing the `.env` file next to config.py, "
            "then try again.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return problems
