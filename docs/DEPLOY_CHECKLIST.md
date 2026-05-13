# Influentia 1.0 — Deploy Checklist
_The single page that gets you from "everything is committed" to "the first customer can buy." Every item is something you have to do — the sandbox can't do them for you. Tick them in order; they have dependencies._

**Estimated total time:** ~6–8 focused hours, spread across 3–5 days.
**Cost:** ~$15 (the domain you already pay for) + $97 (test charge, refunded immediately).
**Skills needed:** copy-paste DNS records, click around Cloudflare/Stripe dashboards, run `wrangler` once.

---

## ✅ A — GitHub backup (5 min, do this first)

The sandbox can't commit for you. Run this once on your terminal so all session work is safely on GitHub before you touch anything live.

```bash
cd ~/Desktop/linkedin_outreach
git add -A
git status                                    # sanity check — only edits, no .env or state.json
git commit -m "Influentia 1.0 prep: wizard wired, worker caps, $0 launch path, $29 → $97 sweep, .app → .io sweep"
git push
```

If `git status` shows `.env`, `state.json`, or `.license.json` as staged, **stop** — your `.gitignore` isn't catching them. Investigate before pushing.

---

## ✅ B — Domain & DNS (Cloudflare, ~30 min)

Goal: `influentia.io` resolves to your landing page, `api.influentia.io` resolves to the worker, `downloads.influentia.io` resolves to the R2 bucket.

| Step | Where | What |
|---|---|---|
| B.1 | Cloudflare → Domains | Confirm `influentia.io` is in your account and nameservers point to Cloudflare. |
| B.2 | Cloudflare → DNS | Add CNAME `influentia.io` → your Pages project (proxied). |
| B.3 | Cloudflare → DNS | Add CNAME `www.influentia.io` → your Pages project (proxied). |
| B.4 | Cloudflare → DNS | Add CNAME `api.influentia.io` → `influentia-api.workers.dev` (proxied). |
| B.5 | Cloudflare → DNS | Add CNAME `downloads.influentia.io` → R2 bucket public hostname (proxied). |
| B.6 | Cloudflare → DNS | Add CNAME `get.influentia.io` → your install-script Pages project (created in F below). |
| B.7 | Cloudflare → DNS | Keep `outreachpilot.app` zone active for now; add a 301 redirect rule at the zone level: `https://outreachpilot.app/*` → `https://influentia.io/$1`. |
| B.8 | Cloudflare → SSL/TLS | Set mode to "Full (strict)" on `influentia.io`. |

Verify with `curl -I https://influentia.io` — should return 200 once Pages is wired in step C.

---

## ✅ C — Cloudflare Pages (landing site, ~15 min)

| Step | What |
|---|---|
| C.1 | Cloudflare → Pages → Create project → "Connect to Git" → select the `Eurmthewurm/influentia` repo, branch `main`. |
| C.2 | Build settings: framework `None`, build command empty, output directory `landing`. |
| C.3 | Save and Deploy. First build takes ~1 minute. |
| C.4 | Pages → Project → Custom domains → Add `influentia.io` and `www.influentia.io`. |
| C.5 | Visit `https://influentia.io` in incognito — landing page should load. |

---

## ✅ D — Stripe (~30 min)

You don't have any live customers, so this is a clean setup.

| Step | Where | What |
|---|---|---|
| D.1 | Stripe Dashboard → switch to **Live mode** (top right). | |
| D.2 | Products → + Add product → Name: `Influentia`. Description: `LinkedIn + Reddit outreach autopilot for B2B founders. Local-first.` | |
| D.3 | Pricing — add two prices: **monthly** $97 USD recurring, **annual** $970 USD recurring. Save the price IDs (start with `price_…`). | |
| D.4 | Settings → Billing → Customer portal → Activate. Return URL: `https://influentia.io/account`. Allow customers to update payment method and cancel subscriptions. | |
| D.5 | Developers → API keys → Reveal live `sk_live_…` secret key. Save for step E.3. | |
| D.6 | If a `Outreach Pilot Pro` test or live product exists, archive it. (Don't delete — Stripe keeps history for accounting.) | |

---

## ✅ E — Cloudflare Worker (~30 min)

This deploys the new code with usage caps + device caps + new D1 migration.

```bash
cd ~/Desktop/linkedin_outreach/worker

# E.1 — Apply the new migration to D1 (adds license_usage + license_devices tables)
wrangler d1 execute outreach-pilot-db --remote --file=./migrations/0002_usage_and_devices.sql

# E.2 — Verify the tables exist
wrangler d1 execute outreach-pilot-db --remote \
  --command="SELECT name FROM sqlite_master WHERE type='table';"
# Should show: licenses, license_usage, license_devices

# E.3 — Set the new STRIPE_PRICE_ID
# Edit wrangler.toml, find [env.production].vars, set STRIPE_PRICE_ID = "price_..."
# Then save the live Stripe secret as a worker secret:
wrangler secret put STRIPE_SECRET_KEY --env production
# (paste sk_live_... from Stripe step D.5)

# E.4 — Deploy
wrangler deploy --env production

# E.5 — Smoke test
curl https://api.influentia.io/
# Expected: {"service":"...","ok":true}
```

| Step | What |
|---|---|
| E.6 | Cloudflare → Workers → outreach-pilot-api → Triggers → Add custom route `api.influentia.io/*`. |

---

## ✅ F — Install pipeline at `get.influentia.io` (~3 hours)

This is the biggest piece of remaining work. Per `INSTALLER.md` §A.2 + §A.3.

| Step | What |
|---|---|
| F.1 | Create a tiny new GitHub repo `Eurmthewurm/influentia-installer` with three files: `install.sh`, `install.ps1`, `index.html`. |
| F.2 | Copy `install.sh` from `INSTALLER.md` §A.2 (already drafted). Edit the Windows version into `install.ps1` similarly. |
| F.3 | `index.html` — a one-page landing that auto-detects OS via User-Agent and shows the right one-line install command in a copy-button code block. Use the same purple palette as `landing/index.html`. |
| F.4 | Cloudflare Pages → Create project → connect to `influentia-installer` repo → Save & Deploy. |
| F.5 | Pages → Project → Custom domains → Add `get.influentia.io`. |
| F.6 | Build the source tar.gz: `tar -czf Influentia-1.0.0.tar.gz server.py dashboard.html wizard.html main.py linkedin_client.py message_ai.py reddit_client.py reddit_signal.py state_manager.py ai_proxy.py config.py prompts/ knowledge_base.json requirements.txt VERSION` |
| F.7 | Upload to R2: `wrangler r2 object put outreach-pilot-downloads/Influentia-1.0.0.tar.gz --file=Influentia-1.0.0.tar.gz`. Also upload as `Influentia-latest.tar.gz`. |
| F.8 | Test on a clean VM or borrowed Mac: `curl -fsSL https://get.influentia.io/install.sh | bash`. Expect dashboard to open in browser within 90 seconds. |

---

## ✅ G — Email infrastructure (~30 min)

Goal: `support@influentia.io` works, transactional emails don't end up in spam.

| Step | What |
|---|---|
| G.1 | Cloudflare → Email Routing → Get started → set up `influentia.io`. Add destination: your personal Gmail. Add custom address `support@influentia.io` → forwards to your Gmail. |
| G.2 | Send a test email to `support@influentia.io` from another address. Confirm delivery. |
| G.3 | Sign up for Resend at resend.com. Free tier: 3,000 emails/mo. |
| G.4 | Resend → Domains → Add `influentia.io`. Resend gives you 4 DNS records (SPF, DKIM, DMARC, return-path). |
| G.5 | Cloudflare → DNS → add all 4 records exactly as Resend specifies. |
| G.6 | Wait 5–15 min, click "Verify" in Resend. Should turn green. |
| G.7 | In `worker/src/index.ts`, find the existing license-issuance code (in `/api/stripe/webhook` handler, after the D1 insert). Add a Resend API call to send a single combined "Welcome to Influentia + your license key + download link" email. (Code skeleton in `LEGAL.md` §7 + Resend's API docs.) |
| G.8 | Redeploy worker: `wrangler deploy --env production`. |
| G.9 | Test: charge yourself $97 (will refund in step H), confirm the email arrives in your inbox, not spam. |

---

## ✅ H — End-to-end smoke test (~30 min)

In an incognito browser, top-to-bottom:

1. Visit `https://influentia.io`. Landing loads.
2. Click "Start free trial." Fill in your email.
3. Stripe Checkout opens. Pay with a real card you own. Use $97 monthly.
4. Redirected to `/success.html?session_id=cs_…`. Page shows your license key.
5. Email arrives in your inbox within 30 seconds. Single email, contains license key prominently.
6. Click the install link. Lands on `get.influentia.io`. Shows the one-line `curl` command for your detected OS.
7. Open Terminal. Paste the command. Press Enter.
8. Watch the install (60–90 sec). Browser auto-opens to `localhost:5555/wizard`.
9. Paste your license key. Activate.
10. Fill in the personalisation primer. Continue.
11. Click "Connect LinkedIn." (Stub records click — real Playwright login happens on first scan.)
12. Reddit opt-in: yes.
13. First-scan animation runs. "Open dashboard" appears.
14. Click. Dashboard loads with your real Authentik scan results.
15. Refund the $97 charge in Stripe Dashboard. Confirm webhook fires and your license tier flips to `cancelled`.
16. Refresh `localhost:5555` — license invalid screen.

If all 16 steps pass, you're soft-launch ready.

---

## ✅ I — Marketing prep (~3–4 hours, parallel to A–H)

These don't need any of the above to be live. Do them while DNS propagates.

| Step | What |
|---|---|
| I.1 | Fill in the 10-customer target sheet from `LAUNCH_KIT.md` §1. Don't skip — without 10 named humans, day 14 has nothing to launch *to*. |
| I.2 | Edit the 8 LinkedIn posts in `LAUNCH_KIT.md` §2 to your voice. Schedule them in your scheduler of choice (Buffer, Typefully, or just calendar reminders). |
| I.3 | Run a real Influentia scan over the past 7 days on your machine. Replace the placeholder data in `LAUNCH_KIT.md` §3.2 with actual numbers. Save as `pain_trend_2026-W18.md`. |
| I.4 | Record a 60-second Loom of yourself using Influentia. Don't over-produce. Embed on `landing/index.html` (replaces the `[Watch 60-sec demo]` placeholder). |
| I.5 | Trademark search: 5 minutes on USPTO TESS (uspto.gov/trademarks/search) and EUIPO TMview (tmdn.org/tmview/). Document findings in a one-line note in HANDOFF. |

---

## ✅ J — Pre-launch landing polish (~2 hours)

Open `landing/index.html` and `landing/terms.html` and `landing/privacy.html` in your editor. Apply the line-by-line edits in `LEGAL.md` §3 + §4. The most important ones:

- Replace `$29/month` → `$97/month` (already done in code; verify nothing missed).
- Add the indemnification clause from `LEGAL.md` §3.3.
- Add the GDPR rights enumeration from `LEGAL.md` §4.3.
- Add the cookie disclosure from `LEGAL.md` §4.4.
- Add a real address for the data-controller line (a virtual office at €50–150/year is fine; KVK Netherlands offers cheap business addresses).
- Add the comparison table from `PRE_LAUNCH.md` §8.3 (Influentia $97 vs Expandi $99 etc.).
- Add the founder quote (yours for v1) per `PRE_LAUNCH.md` §8.4.

---

## ✅ K — Final go/no-go (day 13)

Re-read `PRE_LAUNCH.md` §0 (the no-go criteria). For each line, ask: is this true today?

- ☑️ Installer requires Terminal commands? **No (one curl line is fine).**
- ☑️ Customer must supply Anthropic API key? **No (proxied via worker).**
- ☑️ DNS still mixes `outreachpilot.app` and `influentia.io`? **No (B + redirects done).**
- ☑️ License + receipt arrive as separate emails? **No (G.7 combined them).**
- ☑️ Fresh install on clean Mac VM doesn't reach "first lead" in <10 min? **Test in step H.**
- ☑️ Any Python traceback can surface in the dashboard? **No (showToast covers it).**

If all checks pass, send the 10 personal beta-invite emails (staggered 2/day for 5 days per `LAUNCH_KIT.md` §1.4).

If any fails, push the soft launch by a week.

---

## What this checklist explicitly doesn't include

- ❌ Apple Developer cert ($99/yr) — deferred per `INSTALLER.md` §A.6. Reconsider at day 30 if install completion < 70%.
- ❌ Windows EV cert ($300–600/yr) — deferred. Same logic.
- ❌ Forming a Dutch BV / business entity — defer to €5k MRR per `LEGAL.md` §8.
- ❌ Stripe Tax — defer to €5k MRR per `LEGAL.md` §8.
- ❌ Status page at `status.influentia.io` — nice-to-have, do post-launch.
- ❌ PostHog metrics wiring — `PRE_LAUNCH.md` §4.10. Do in week 1 post-launch if launching blind worries you. Otherwise defer to week 2 when you have a real signal to compare.

---

## Order of operations (suggested calendar)

| Day | Block | Items |
|---|---|---|
| Mon | morning (1h) | A (GitHub) + I.5 (trademark) + D (Stripe) |
| Mon | afternoon (2h) | B (DNS) + C (Pages) |
| Tue | morning (2h) | E (Worker deploy) + G (email setup) |
| Tue | afternoon (3h) | F (install pipeline) |
| Wed | morning (2h) | J (landing polish) |
| Wed | afternoon (3h) | I.1–I.4 (target sheet, posts, Loom, Pain Trend) |
| Thu | (1h) | H (full smoke test) |
| Fri | (off / overflow) | Whatever spilled. |
| Sat–Sun | (off) | Schedule LinkedIn Post #1 to drop Tuesday. |
| Mon (next) | (1h) | K (final go/no-go) + send first 2 beta invites |
| Tue–Fri | staggered | Send remaining 8 beta invites, 2/day |

By the end of week two you have 10 founders trying Influentia, real install-completion data, and real testimonials forming. Public launch on day 30 is then a function of soft-launch data, not anxiety.

---

## Companion docs

| Doc | Use when |
|---|---|
| **`DEPLOY_CHECKLIST.md`** (this file) | Daily during the deploy week. |
| [`PRE_LAUNCH.md`](./PRE_LAUNCH.md) | Strategic context for *why* each step exists. |
| [`INSTALLER.md`](./INSTALLER.md) | Detail on F (install pipeline). |
| [`LEGAL.md`](./LEGAL.md) | Detail on J (landing polish — terms, privacy, refund). |
| [`LAUNCH_KIT.md`](./LAUNCH_KIT.md) | Detail on I (marketing prep). |
| [`HANDOFF.md`](./HANDOFF.md) | If something breaks and you need orientation. |

---

_The shortest path from "code is ready" to "customer #1 paid" is this checklist, in order, without skipping. Skip B and you can't run E. Skip E and H fails. Don't optimise the order; just do the next item._
