# Influentia 1.0 — Pre-Launch Critical Path
_The 14-day plan from "almost ready" to "soft launch." Every blocker, ranked, with severity, owner, and estimate. Read top-to-bottom. Don't skip the no-go criteria._

**Status:** active critical path.
**Target soft-launch date:** day 14 from kickoff.
**Target public-launch date:** day 30 (after 14-day soft-launch validation).

---

## 0. Go / no-go decision (read first)

**Current state:** product works locally, brand consolidation done in code, wizard built but not wired, install path still developer-grade, DNS still on old name.

**Decision:** **NO-GO for public launch right now.** Soft-launch in 14 days, public launch in 30, only if the no-go criteria below clear.

### No-go criteria — any of these triggers a delay
- Installer requires Terminal commands or `.env` editing.
- Customer must supply their own Anthropic API key.
- DNS still mixes `outreachpilot.app` and `influentia.io`.
- License + receipt arrive as separate emails.
- A fresh install on a clean Mac VM does not reach "first lead" in under 10 minutes.
- Any unhandled Python traceback can surface in the dashboard UI.

If any of those is true on day 13, push the soft launch by a week. **Do not soft-launch a half-baked product.**

---

## 1. Severity legend

| | Meaning |
|---|---|
| 🔴 BLOCKER | Soft launch cannot happen with this open. |
| 🟠 HIGH | Soft launch can happen with this open, but public launch cannot. |
| 🟡 MEDIUM | Public launch can happen with this open. Fix in week 1 of post-launch. |
| 🟢 LOW | Polish. Fix as time allows. |

---

## 2. The 14-day critical path

### Days 1–3 — Brand finalisation + install flow

| # | Task | Severity | Est | Cost | Notes |
|---|---|---|---|---|---|
| 2.1 | **Apple Developer Program — DEFERRED.** Soft launch ships the free one-line install path per [`INSTALLER.md`](./INSTALLER.md) §A. Order the $99/yr cert only if A.6 upgrade triggers fire after day 30. | 🟢 | 0 | **$0 (deferred)** | The free path is fine for technical B2B founders. Saves $99/yr possibly forever. Re-evaluate at day 30. |
| 2.2 | **Windows EV cert — DEFERRED.** Same logic — `Install.bat` works without signing for the soft-launch audience. | 🟢 | 0 | **$0 (deferred)** | Save $300–600/yr until data demands it. |
| 2.3 | DNS migration — `outreachpilot.app` → `influentia.io` | 🔴 | 2 h | $0 | Single coordinated operation. Add new domain in Cloudflare, point Pages + Worker routes, set 301 redirect from old. |
| 2.4 | Rename Cloudflare Worker service `outreach-pilot-api` → `influentia-api` | 🔴 | 1 h | $0 | Deploy new worker, update all client URLs, retire old. Test webhook before retiring. |
| 2.5 | Rename D1 database binding | 🟠 | 30 min | $0 | Keep existing DB; just rename the binding label in `wrangler.toml`. Data integrity > cosmetic name. |
| 2.6 | Rename R2 bucket items — upload new keys (`Influentia-1.0.0.dmg`, etc.); leave old `outreach-pilot.zip` in place for 30-day grace period. | 🟠 | 1 h | $0 | Old links keep working during transition. |
| 2.7 | Stripe — create the live "Influentia" product at $97/mo + $970/yr. Archive any test-mode products. | 🔴 | 1 h | $0 | New price IDs. Update worker `STRIPE_PRICE_ID` env. (No prior live customers to migrate — clean launch.) |
| 2.8 | Stripe webhook — verify `checkout.session.completed` includes the new price ID. | 🔴 | 30 min | $97 (refunded) | Test with a real $97 charge on a card you own. Refund immediately after. |
| 2.9 | Combined license + receipt email | 🔴 | 3 h | $0 | Use Resend free tier (3,000 emails/mo) triggered from the worker. Stripe receipt customisation is uglier. |
| 2.10 | **Set up `support@influentia.io` via Cloudflare Email Routing** → forward to your Gmail. Add the address to Terms, Privacy, dashboard, footer. | 🔴 | 30 min | $0 | Free with any domain on Cloudflare. Five-minute setup. Zero ongoing cost. |
| 2.11 | **Legal page edits per `docs/LEGAL.md` §3 + §4** — update pricing, refund clause, indemnification, GDPR rights, cookie disclosure, controller info, support email TLD fix (`.io` → `.app`). | 🔴 | 2 h | $0 | Existing files are 80% there. Targeted edits only. No lawyer needed. |
| 2.12 | **Trademark check** — search "Influentia" on USPTO TESS + EUIPO TMview. Document findings in a one-liner. | 🟠 | 30 min | $0 | If clear, defer filing to Q3 ($250–€850 then). If a conflict appears, decide brand response now, before more sunk cost. |

### Days 4–7 — Wizard + install path

| # | Task | Severity | Est | Notes |
|---|---|---|---|---|
| 4.1 | Wire `wizard.html` into `server.py` per integration notes at top of the file. | 🔴 | 3 h | $0 | Add `/wizard` route, gate dashboard load on `state.onboarding.completed_at`, expose the four mocked APIs. |
| 4.2 | LinkedIn connect — replace manual `li_at` cookie capture with Playwright login flow. User clicks "Connect," browser opens, they log in normally, cookie is captured to OS keychain. | 🔴 | 6 h | $0 | Highest-leverage UX fix in the codebase. Test on three different LinkedIn account types. |
| 4.3 | Anthropic key — proxy through worker. Add `/api/claude/messages` endpoint that authenticates the customer's license, then forwards to Claude with your Anthropic key. **Enforce per-license usage cap (1M tokens/day soft, 3M/month hard).** | 🔴 | 6 h | ~$10–25/customer/mo Anthropic usage (already in margin) | Removes the single biggest install friction. Caps prevent abuse. Show "fair-use limit" friendly message at threshold. |
| 4.4 | **`state.json` backup mechanism** — add an "Export pipeline" button in dashboard Settings → downloads a portable JSON. Add an "Import" counterpart on first run. Document the 30-second nightly auto-export-to-Downloads option. | 🟠 | 3 h | $0 | Customer-controlled backup. No cloud storage paid by you. Saves the refund event when their laptop dies. |
| 4.5 | First-run end-to-end test on a clean Mac VM. From `curl ... \| bash` to dashboard with first leads visible — must be < 10 minutes (including install + wizard). | 🔴 | 2 h | $0 (built-in macOS VM or Parallels trial) | If it takes longer, fix the slowest step. Iterate until under 10. |
| 4.6 | **Build the free install pipeline per `INSTALLER.md` §A.** Write `install.sh` + `install.ps1`, host `get.influentia.io` on Cloudflare Pages, upload tar.gz source bundle to R2. | 🔴 | 4 h | $0 | Replaces the deferred `.dmg` path. Ships everything customers need. |
| 4.7 | Update `landing/success.html` and download CTAs to show the one-line `curl` (Mac) or `irm` (Windows) command in a copy-button code block. | 🔴 | 1 h | $0 | Visual: pretend it's a polished SaaS install command, not a dev terminal. Use a styled code block with one-click copy. |
| 4.8 | Test install completion on at least 3 different fresh machines (Mac Intel + Apple Silicon + Windows). Time each one. Fix anything > 90 sec. | 🔴 | 3 h | $0 | The "is bash install OK for our ICP?" data point starts here. |
| 4.9 | Friendly error sweep — grep `dashboard.html` and `server.py` for raw error rendering. Replace with `.alert` component per `docs/UI.md` §4.7. | 🟠 | 4 h | $0 | Five most common errors first: license invalid, LinkedIn cookie expired, Reddit scan failed, Claude rate-limit, network down. |
| 4.10 | **Anonymous opt-in metrics via PostHog free tier** (1M events/mo). Wire 8 events: install, wizard step start/complete, first-scan, first-message, license-validate-fail, error-shown, refund. Default off; enable in wizard with one-tap consent. | 🟠 | 3 h | $0 (PostHog free tier; 1M events covers ~5,000 active customers) | Without this, you fly blind. Privacy-respecting, EU-hosted option available. Anonymous IDs only. |

### Days 8–10 — Landing polish + trust signals

| # | Task | Severity | Est | Cost | Notes |
|---|---|---|---|---|---|
| 8.1 | Demo video — 60-second Loom of Ermo using Influentia. Pin to landing hero. | 🟠 | 3 h | $0 (Loom free tier covers <25 videos at <5 min each) | Don't over-produce. Real screen recording with clear narration. Embed via Loom's iframe. |
| 8.2 | Pricing copy — update landing to $97/mo, add annual option ($970/yr, "save $194"), add money-back guarantee callout. | 🔴 | 2 h | $0 | Use the canonical objection-handlers from `docs/POSITIONING.md` §5.4. |
| 8.3 | Comparison table — Influentia $97 vs Expandi $99 / Phantombuster $69 / Lemlist $99 / Apollo $49. Differentiation rows: "Runs on your machine," "AI personalisation," "Built for solo founders, not sales teams." | 🟠 | 3 h | $0 | Visual table, not bullets. Anchor on differentiation, not feature parity. |
| 8.4 | Social proof — one founder quote with photo + LinkedIn URL. Yours counts for v1 if no other beta has shipped one yet. | 🟠 | 2 h | $0 | One real quote beats ten fabricated ones. |
| 8.5 | OG image + favicon — Influentia wordmark on dark background with accent glow. 1200×630 for OG, 32×32 for favicon. | 🟡 | 2 h | $0 (Figma free or Canva free) | Test in LinkedIn share preview before publishing. |
| 8.6 | DFY upsell card in dashboard — Settings tab, after first scan: "Need it done for you? Authentik Studio (a partner agency) does this as DFY — see if it's a fit." Links to a Calendly. **Brand-separated per `POSITIONING.md` §6.** | 🟡 | 1 h | $0 (Calendly free tier) | The flywheel needs this exit ramp, but it's a *partner referral*, not "Influentia Pro." |
| 8.7 | **Status page** — `status.influentia.io` via cstate (open-source) hosted on Cloudflare Pages. Auto-checks Worker, D1, R2 every 5 min. | 🟢 | 1 h | $0 (Cloudflare Pages free) | Customers will hit Cloudflare/Anthropic outages. Public status page = professional. |

### Days 11–14 — Soft launch validation

| # | Task | Severity | Est | Notes |
|---|---|---|---|---|
| 11.1 | Pick 10 hand-selected B2B founders from your network (one per ICP persona where possible). Send a personal email offering free 30-day Influentia 1.0 access in exchange for honest feedback + a quote. | 🔴 | 2 h | Don't blast. Personal note per founder. |
| 11.2 | Watch every install. Use a screen-share or Loom-walkthrough offer. Note every confusion point. | 🔴 | 4 h | This is the most valuable data of the entire launch — don't skip it. |
| 11.3 | Daily friction log — one Notion / doc / Linear sheet listing every issue from beta installs. Triage daily. | 🔴 | 1 h | Anything 3+ users hit = ship-stop fix. |
| 11.4 | Get 3 quotable testimonials in writing. Get permission to use names + photos. | 🟠 | 3 h | These go on the landing page before public launch. |
| 11.5 | Run the 10 betas through the wizard yourself one last time on day 13. If anything still feels off, push public launch a week. | 🔴 | 2 h | Last quality gate before public. |

---

## 3. Definition of "ready for soft launch"

All true:
- ✅ DNS migrated. `influentia.io` resolves. `outreachpilot.app` 301-redirects.
- ✅ Stripe at $97/mo with new price ID, single combined receipt+license email working (Resend or similar).
- ✅ `support@influentia.io` set up via Cloudflare Email Routing, forwarded and tested.
- ✅ Legal pages updated per `LEGAL.md` (pricing, refund clause, indemnification, GDPR rights, support TLD).
- ✅ Trademark search performed and documented (no blocker found, or response decided).
- ✅ One-line install (`curl … | bash` for Mac, `irm … | iex` for Windows) live at `get.influentia.io`.
- ✅ Install takes < 90 seconds from paste-and-Enter to dashboard browser open.
- ✅ Wizard end-to-end works without manual `.env` editing or Anthropic key entry.
- ✅ LinkedIn Connect works via Playwright login (no F12 cookie copy).
- ✅ Anthropic proxy live with per-license usage cap (1M/day, 3M/month).
- ✅ State.json export/import button in dashboard.
- ✅ Five most common errors render as friendly cards, not tracebacks.
- ✅ Anonymous opt-in metrics wired (PostHog free tier).
- ✅ DFY upsell card visible in dashboard (as partner referral, not as Influentia tier).
- ✅ Status page live at `status.influentia.io`.
- ✅ Demo video embedded on landing.
- ✅ Pricing + comparison table updated on landing.
- ✅ One real founder quote on landing.

If any of these is still red on day 13, **delay**.

---

## 3a. Total cost to reach soft launch (cost-minimised — free path)

| Item | Cost | Recurring? |
|---|---|---|
| Apple Developer Program | **$0 (deferred)** | Re-evaluate at day 30 |
| Windows EV cert | **$0 (deferred)** | Re-evaluate when shipping Windows users at scale |
| Domain `influentia.io` | already paid | ~$15/yr |
| Cloudflare Pages / Workers / D1 / R2 / Email Routing | $0 | Free tier covers everything to ~5,000 customers |
| Resend transactional email (free tier) | $0 | Free under 3,000 emails/mo |
| Loom (free tier) | $0 | Free under 25 videos / 5 min |
| PostHog (free tier) | $0 | Free under 1M events/mo |
| Calendly (free tier) | $0 | Free for 1 event type |
| Figma / Canva (OG image, favicon) | $0 | Free tiers |
| Cstate status page | $0 | Open source, runs on Cloudflare Pages |
| Test charge ($97, refunded) | $0 net | One-shot |
| Legal templates (DPA, Terms, Privacy edits) | $0 | DIY per `LEGAL.md` |
| **Total to reach soft launch (free path)** | **$0 incremental** | |
| **Total to maintain (free path)** | **~$15/yr** (just the domain) | |
| ───────── upgrade triggers ───────── | | |
| Apple Developer (only if §A.6 trigger fires) | $99/yr | Only if install completion < 70% in soft launch |
| Windows EV cert (only when shipping Windows at scale) | $300–600/yr | Defer until you have Windows customers |
| Stripe Tax (when crossing €5k MRR) | $25/mo | Auto VAT/GST |
| **At-scale cost ceiling (everything paid)** | **~$1,500/yr** | Only if all triggers fire |

**You can launch this for the cost of the domain.** Pay nothing more until customer data tells you to.

---

## 4. Definition of "ready for public launch"

All soft-launch criteria still pass, plus:
- ✅ At least 7 of 10 beta installs reached "first booked call" (or first qualified reply).
- ✅ At least 3 written testimonials with names + photos.
- ✅ No customer-reported LinkedIn warnings or restrictions.
- ✅ < 10% beta refund / cancellation rate.
- ✅ Friction log shows zero 3-user-or-more open issues.
- ✅ Windows `.msi` shipped (or explicit "macOS only for now" disclaimer on landing).
- ✅ "Pain Trend Report" public archive page live (even if only one report).

---

## 5. Soft launch plan

**Day 14:** invite 10 hand-picked B2B founders. Personal email from Ermo.

**Days 14–28:** active monitoring. Twice-daily `wrangler tail`. Daily check of:
- New license activations
- Wizard completion rate (target: 90%+)
- First-scan completion rate (target: 95%+)
- LinkedIn Connect success rate (target: 95%+)
- Errors in `server_stderr.log`
- Stripe events

**Communication:**
- Email each beta on day 3 ("How's it going? Any friction?").
- Email each beta on day 7 ("Got a minute for a 15-min screen-share?").
- Email each beta on day 14 ("If you've gotten value, can we quote you?").

---

## 6. Public launch plan (day 30)

**Day 30 morning:**
- Switch landing CTA from "Join the beta" to "Start free trial."
- Publish first "Pain Trend Report" weekly.
- Ermo posts on LinkedIn: launch announcement + behind-the-scenes story (Authentik built it for clients, opening it to everyone).
- Newsletter to existing Authentik audience.

**Day 30 afternoon:**
- Post to relevant subreddits where it's appropriate (r/SaaS, r/B2BMarketing, r/Entrepreneur — read each sub's self-promo rules).
- Consider Product Hunt launch on day 35 (after polish week).

**Days 30–60:**
- One LinkedIn post from Ermo per week, anchored on a Pain Trend insight.
- Weekly newsletter.
- Watch acquisition channels: which one converts? Double down.
- Collect more testimonials.
- Ship Windows `.msi` if not already.

---

## 7. Rollback / kill-switch criteria

If any of these happens within 14 days of public launch, **pull the launch and triage:**

- 3+ customers report LinkedIn account warnings or restrictions.
- Stripe refund rate exceeds 20%.
- Wizard completion rate drops below 70%.
- A security issue surfaces (license bypass, key leak, etc.).
- A major Anthropic / Cloudflare outage prevents validation for > 2 hours.

**How to pull a launch:**
- Switch landing CTA back to "Join the waitlist."
- Pause Stripe price (don't archive — pause).
- Email all active customers: honest status update.
- Fix. Re-launch with explicit retrospective post.

A pulled launch with honesty restores trust faster than limping along with a broken product.

---

## 8. First-30-day metrics to watch

| Metric | Target | Why |
|---|---|---|
| Landing → checkout conversion | 3%+ | Below this: copy/offer wrong. |
| Checkout → install | 90%+ | Below this: install path still has friction. |
| Install → first scan | 95%+ | Below this: wizard or LinkedIn connect broken. |
| First scan → first reply | 60%+ in 14 days | Below this: ICP messaging or AI quality off. |
| 14-day refund rate | < 8% | Above this: positioning vs delivery mismatch. |
| 30-day retention | 75%+ | Below this: product stickiness issue. |
| Customer-reported bans | 0 | Above 0: stop selling, fix immediately. |
| MRR | $1,000 by day 30 (~10 paying) | Modest, real. |
| MRR | $5,000 by day 90 (~50 paying) | Wedge proven. |
| Inbound to Authentik DFY | 1+ qualified call/week from Influentia customers by day 60 | Flywheel working. |

---

## 9. What we're explicitly not doing in the 1.0 launch

(Listed here to resist scope creep mid-sprint.)

- ❌ Team / multi-seat (Pro tier ships Q3).
- ❌ Mobile app.
- ❌ HubSpot / Salesforce integration.
- ❌ Email outreach channel.
- ❌ Twitter / X scanning.
- ❌ Linux installer (defer to v1.1).
- ❌ Localisation (English only at launch).
- ❌ White-label / reseller program.
- ❌ Public Slack / Discord community.
- ❌ Anything not in this checklist.

If you find yourself working on something not in this checklist, **stop.** Add it to a post-launch backlog and return to the list.

---

## 10. Companion docs

| Doc | Use when |
|---|---|
| [`BLUEPRINT.md`](./BLUEPRINT.md) | Strategic context. |
| [`POSITIONING.md`](./POSITIONING.md) | Messaging + ICP + pricing rationale. |
| **`PRE_LAUNCH.md`** (this file) | Day-by-day execution. |
| [`LEGAL.md`](./LEGAL.md) | Terms / Privacy / DPA / refund / tax / trademarks — cost-minimised checklist. |
| [`UX_FLOW.md`](./UX_FLOW.md) | Customer journey detail. |
| [`UI.md`](./UI.md) | Visual implementation. |
| [`INSTALLER.md`](./INSTALLER.md) | Build pipeline detail. |
| [`HANDOFF.md`](./HANDOFF.md) | Where things stand right now. |

---

_The hardest part of launch isn't the work. It's resisting the urge to launch before the no-go criteria clear. A two-week delay costs you almost nothing. A bad launch costs you the brand._
