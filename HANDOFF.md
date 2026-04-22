# Outreach Pilot — Handoff

Paste this into a new Sonnet chat to pick up the project.

---

## What this is

**Outreach Pilot** — a LinkedIn outreach automation tool that runs locally on the user's computer (Mac/Windows). Claude + Brave Search personalize messages; Playwright drives LinkedIn with human-like pacing and CAPTCHA detection. Commercial model: $29/month with a 7-day free trial, license keys validated by a hosted Cloudflare Worker.

## Where the code lives

All in `/Users/ermoegberts/Desktop/linkedin_outreach/`:

- **Local app (ships to testers):** `server.py` (Python HTTP server, ~2400 lines), `dashboard.html` (single-file UI, ~5500 lines), `linkedin_client.py` (Playwright wrapper with safety layer), `config.py`, plus `prompts/` and launcher scripts (`Install.command`, `start.command`, `Install.bat`, `Start.bat`, `install.sh`).
- **Tester distribution:** `outreach-pilot.zip` (178 KB, v0.9.1-beta) — already built, ready to ship.
- **Hosted license backend:** `worker/` — Cloudflare Worker + D1 + Stripe (TypeScript, Hono).
- **Landing page:** `landing/` — static HTML for outreachpilot.app with Stripe Checkout, success page, account/portal page, privacy, terms.
- **Operator docs:** `DEPLOY.md` (602-line runbook), `TESTER_QUICKSTART.md` (for testers).
- **Version:** `VERSION` → `0.9.1-beta`.

## Current status

**Everything is built and verified.** Worker TypeScript compiles clean. Python compiles clean. Dashboard JS parses clean. License gate returns HTTP 402 on `/api/run/*` when trial is expired or no license is present. Trial countdown banner + read-only expired mode are wired. Tester zip is scrubbed of personal data. DEPLOY.md covers Stripe → Cloudflare → R2 → smoke test → test-to-live.

**What's NOT done:** actual deployment. The whole commercial layer is code-complete but nothing is live yet. Next step is running through `DEPLOY.md`.

## Key decisions already made (don't re-litigate)

- **Distribution:** Local-execution app + hosted license backend (Dux-Soup / Expandi pattern). Rejected fully-hosted SaaS because LinkedIn aggressively bans datacenter IPs.
- **Pricing:** $29/month, 7-day free trial (card required up front — standard Stripe subscription trial).
- **Trial expiry UX:** Read-only mode, not hard paywall. Dashboard still loads, shows all data, action buttons greyed out with "Upgrade to reactivate."
- **Backend stack:** Cloudflare Workers + D1 + Stripe Checkout. Stripe customer portal for subscription management. No email sending from our side — Stripe handles receipts.
- **License keys:** 32-char, format `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX`, Crockford-ish alphabet (no 0/O/1/I/l).

## What you might help with next

- Walking through `DEPLOY.md` step-by-step if Eurm wants to actually go live
- Copy tweaks on the landing page (`landing/index.html`)
- Pricing/trial adjustments (change `STRIPE_PRICE_ID`, trial length in worker)
- Bug fixes if anything shows up in real-world testing
- Building CRM integrations (Hubspot / Salesforce / Notion) — that's the obvious next feature

## How to verify nothing's broken before starting

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/
python3 -c "import py_compile; py_compile.compile('server.py', doraise=True); print('server OK')"
cd worker && npx tsc --noEmit && echo "worker OK"
```

Both should exit 0.

## Ground rules from Eurm

- Non-developer context — explain clearly, avoid jargon dumps.
- Don't re-read every file constantly — be surgical with tool calls.
- TodoList aggressively; use AskUserQuestion for underspecified requests.
- Only save final deliverables to `/Users/ermoegberts/Desktop/linkedin_outreach/`, not to internal temp folders.
