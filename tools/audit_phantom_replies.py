#!/usr/bin/env python3
"""
audit_phantom_replies.py — scan state.json for likely-phantom prospect messages.

Background: until today, cmd_reply() in main.py used an EXACT string match
to detect when LinkedIn's scraper had mis-classified our own outbound bubble
as a "prospect reply". When the scraper returned the same text with a
different ellipsis or smart quote, the guard failed and the AI generated an
"answer" — producing the doubled-message bug.

The fix is live for new conversations. This script audits *existing* state
for entries that the new fuzzy guard would have caught, so you can clean
them up before launch.

Usage:
    python3 tools/audit_phantom_replies.py
    python3 tools/audit_phantom_replies.py --threshold 0.75   (more sensitive)
    python3 tools/audit_phantom_replies.py --json             (machine-readable)

Read-only — does NOT modify state.json. Just reports what it finds.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

DEFAULT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "state.json",
)


def normalise(s: str) -> str:
    """Same normalisation as main.py cmd_reply guard."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = (
        s.replace("‘", "'").replace("’", "'")
         .replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-")
         .replace("…", "...")
    )
    s = re.sub(r"\s+", " ", s.lower()).strip()
    return s


def looks_like_ours(prospect_text: str, our_texts: list[str], threshold: float) -> tuple[bool, float, str]:
    """Returns (is_phantom, similarity, matched_our_text) — same logic as the live guard."""
    pn = normalise(prospect_text)
    if not pn:
        return False, 0.0, ""
    best_ratio = 0.0
    best_match = ""
    for ours in our_texts:
        on = normalise(ours)
        if not on:
            continue
        if pn == on or pn in on or on in pn:
            return True, 1.0, ours
        r = SequenceMatcher(None, pn, on).ratio()
        if r > best_ratio:
            best_ratio = r
            best_match = ours
    return (best_ratio >= threshold), best_ratio, best_match


def parse_ts(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def audit(state_path: str, threshold: float = 0.85) -> list[dict]:
    with open(state_path) as f:
        state = json.load(f)
    suspicious = []
    leads = state.get("leads", {})
    if isinstance(leads, list):
        leads = {l.get("linkedin_url", f"_{i}"): l for i, l in enumerate(leads)}

    for url, lead in leads.items():
        msgs = lead.get("messages", []) or []
        if not msgs:
            continue
        our_texts = [m.get("content", "") for m in msgs if m.get("role") == "ai"]
        if not our_texts:
            continue

        for i, msg in enumerate(msgs):
            if msg.get("role") != "prospect":
                continue
            text = msg.get("content", "")
            ts   = msg.get("ts", "")
            is_phantom, sim, matched = looks_like_ours(text, our_texts, threshold)
            if not is_phantom:
                continue

            # Time-since-our-last guard check
            prior_ai = [m for m in msgs[:i] if m.get("role") == "ai"]
            mins_after = None
            if prior_ai:
                their_dt = parse_ts(ts)
                ours_dt  = parse_ts(prior_ai[-1].get("ts", ""))
                if their_dt and ours_dt:
                    mins_after = (their_dt - ours_dt).total_seconds() / 60.0

            suspicious.append({
                "lead_name":       lead.get("name", "(unknown)"),
                "linkedin_url":    url,
                "lead_status":     lead.get("status", ""),
                "phantom_text":    text,
                "matched_our_text": matched,
                "similarity":      round(sim, 4),
                "timestamp":       ts,
                "mins_after_our_last": (None if mins_after is None else round(mins_after, 1)),
                "msg_index":       i,
            })

    return suspicious


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", default=DEFAULT_STATE_PATH)
    p.add_argument("--threshold", type=float, default=0.85,
                   help="Similarity threshold (0–1). Lower = more sensitive. Default 0.85.")
    p.add_argument("--json", action="store_true",
                   help="Output machine-readable JSON.")
    args = p.parse_args()

    if not os.path.exists(args.state):
        print(f"state.json not found at {args.state}", file=sys.stderr)
        sys.exit(2)

    rows = audit(args.state, threshold=args.threshold)

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print(f"OK — no phantom prospect messages detected at threshold {args.threshold}.")
        return

    print(f"Found {len(rows)} suspicious prospect-attributed message(s) "
          f"(threshold {args.threshold}):\n")
    for r in rows:
        print(f"  {r['lead_name']}  (status: {r['lead_status']})")
        print(f"    URL:                 {r['linkedin_url']}")
        print(f"    Similarity:          {r['similarity']}")
        if r['mins_after_our_last'] is not None:
            print(f"    Arrived after ours:  {r['mins_after_our_last']} min")
        print(f"    Phantom 'reply':     {r['phantom_text'][:140]}")
        print(f"    Looks like our:      {r['matched_our_text'][:140]}")
        print()

    print("Recommended action:")
    print("  1. For each row above, open the conversation in the dashboard.")
    print("  2. If the 'phantom' line was indeed our own message mis-classified,")
    print("     toggle the lead to manual_mode = true to silence the AI on it.")
    print("  3. Optionally remove the phantom message from state.json by hand")
    print("     (back up state.json first), or just leave it — manual_mode is enough.")


if __name__ == "__main__":
    main()
