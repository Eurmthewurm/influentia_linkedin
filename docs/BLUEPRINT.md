# Influentia — Strategic Blueprint
_North-star document. One product, one brand, one story._
_Last updated: 2026-04-29 · Version: 0.9.1-beta_

---

## 1. The product in one sentence

> **Influentia is a local-first LinkedIn + Reddit outreach autopilot for B2B founders. It runs on your machine, on your IP, with your data — and does the prospecting, messaging, and follow-up you'd never have time to do yourself.**

If a customer can't repeat that sentence back, the marketing isn't working.

---

## 2. Brand architecture (locked — revised)

**Influentia stands alone. Authentik Studio is a separate business with a private operational link.** They reinforce each other through Ermo and through content, *not* through merged identity.

| | Decision |
|---|---|
| Product name | **Influentia** (no "by X" suffix) |
| Domain | `influentia.io` |
| Tagline | "LinkedIn outreach on autopilot. On your machine. In your voice." |
| Stripe product display | `Influentia` (not "Influentia by Authentik Studio") |
| Logo wordmark | "Influentia" — no parent attribution in the mark |
| GitHub repo | `Eurmthewurm/influentia` |
| Authentik mention on Influentia | Once on the About page only: "Built by the team behind Authentik Studio." Nowhere else. |
| Influentia mention on Authentik | Case study format: "We built Influentia and use it daily for clients." Adds credibility *to Authentik*, not the other way around. |
| Old names to retire | `Outreach Pilot`, `LinkedIn Outreach Autopilot`, `outreach-pilot.zip` |

### Why separate, not merged

1. **"By X" only works when X has stranger-recognised equity.** Basecamp earned the right to say "by 37signals" after years of *Getting Real*. Authentik isn't there yet. Slapping "by Authentik Studio" on Influentia reads as "agency side project" to a cold visitor — which destroys the premium $97 positioning.
2. **The buying motions are incompatible.** Authentik sells $3.5–10k/mo engagements over weeks. Influentia sells $97 SaaS in five minutes. Merging the funnels creates two failure modes: Influentia customers expect agency-grade help; Authentik prospects question the agency's premium status when they see it selling cheap software.
3. **Exit math.** SaaS trades at 5–10× ARR. Agency revenue trades at 2–3× EBITDA. Merged identity drags Influentia toward agency multiples — bad for any future option.
4. **Operator focus.** Solo-founder running both is already hard. Splitting brand attention compounds the cost.

### The flywheel still works — through Ermo, not through merger

Ermo is the human bridge. He posts on LinkedIn citing Pain Trend data sourced from Influentia. Authentik publishes case studies that mention they use Influentia. Influentia's dashboard has a small, separate-feeling "Need it done for you?" upsell card linking to Authentik's Calendly. Each brand builds its own equity; the flywheel runs in the background.

---

## 3. Positioning — why Influentia wins

### The market
Expandi, Phantombuster, Dux-Soup, Lemlist all run from cloud IPs that LinkedIn now actively detects. Bans are climbing. Privacy concerns are real (your LinkedIn cookie sitting on someone's server).

### The wedge
**Local-first.** Three words competitors can't say without rebuilding from scratch.

| What we say | What it means | What it costs us |
|---|---|---|
| "Runs on your machine" | No shared cloud IPs. LinkedIn sees a real human session. | Higher install friction (we fix this with one-click) |
| "Your cookie never leaves your computer" | Privacy as a moat. Real GDPR/SOC2 talking point. | Slightly slower iteration (we're on R2 auto-update) |
| "Your AI, in your voice" | Knowledge base personalises every message. | Customers must spend 15 min on Knowledge Base setup |
| "Built for solo founders, not sales teams" | Sharpens against Outreach.io / Salesloft / Apollo. Reinforces the operator psychograph. | Forces feature discipline — no team-seat sprawl in v1. |

### Who it's for (ICP) — locked
Three sharp personas (full detail in [`POSITIONING.md`](./POSITIONING.md) §2):
1. **Bootstrapped B2B SaaS Founder** — $1k–$10k MRR, hates being their own SDR.
2. **B2B Agency Owner** — 10–50 employees, scaling, hates being the rainmaker.
3. **B2B Consultant / Fractional Exec** — $5k–$50k engagements, no time to prospect.

Unifying psychograph: *founder-as-operator, allergic to corporate sales tooling, values privacy, willing to pay for premium that saves their time.*

### Who it's NOT for (anti-ICP — locked)
- ❌ Coaches / course creators (wrong channel, wrong deal size, brand-association risk).
- ❌ E-commerce / D2C (LinkedIn isn't where their buyers live).
- ❌ Enterprise SDR teams (they have Outreach.io / Salesloft).
- ❌ Recruiters (different motion, double LinkedIn-ban risk).
- ❌ Anyone wanting "1,000 messages a day" (decline politely).

If a prospect is in any of those segments, **decline.** Bad-fit customers cost more than they pay. See [`POSITIONING.md`](./POSITIONING.md) §3.

---

## 3a. Pricing (locked)

| Tier | Price | Target | Status |
|---|---|---|---|
| **Influentia** | **$97/mo** or **$970/yr** (save $194) | All three ICP personas | Ships at 1.0 relaunch |
| **Influentia Pro** | $197/mo or $1,970/yr | Agency owners with VAs / consultants with assistants | Q3 2026 |
| **Authentik DFY** | $3,500–$10,000/mo (custom) | Customers who say "I don't have time" | Active today |

**Why $97 (locked from day one):** $97 sits at the premium end of the LinkedIn outreach category (cheaper than Expandi $99, Lemlist $99; pricier than Phantombuster $69, Dux-Soup $55), leaves margin for proxied Anthropic costs, and anchors the DFY upsell at 50× rather than 170× — mentally walkable, not absurd. We deliberately chose not to anchor low; "the cheap option" is a positioning weakness in B2B that's hard to walk back later. Full reasoning in [`POSITIONING.md`](./POSITIONING.md) §7.

**Refund / guarantee:** "Book your first qualified call within 14 days, or we refund every cent. Then keep using Influentia anyway — we just want you to win."

**No prior pricing to migrate from.** Influentia 1.0 is the first paid release. There are no existing customers at a different price. Clean slate.

---

## 4. The product model — Local + License (defended)

User's question was "what's best?" Here's the critical answer.

### Three options, ranked

**🥇 Local + License (current) — KEEP THIS.**
- ✅ Runs on user's IP → LinkedIn doesn't ban → tool keeps working → customers keep paying
- ✅ Zero infra cost → $97/mo is mostly margin → we can run profitably with 15 customers
- ✅ Privacy is a real, defensible moat → "your cookie never leaves your machine" beats any cloud tool's marketing
- ✅ Solo-founder feasible → one Cloudflare Worker for licenses, that's it
- ❌ Install friction → **fix with one-click installer + auto-update + better errors**

**🥈 Hybrid (cloud dashboard + local agent)**
- Possible v2 in 2027. Not now.
- Doubles the engineering surface (auth, sync, websocket reliability) for a benefit that one-click install solves cheaper.

**🥉 Hosted SaaS**
- Reject. This is what kills competitors. LinkedIn detects cloud IPs, accounts get banned, refunds explode, you're now a support desk for ToS-violating customer accounts. Don't.

### The unlock for Local + License

Local is correct *only if* it feels like SaaS. That means:

1. **One-click installer** — `.dmg` for macOS, `.msi` for Windows, no Python knowledge required.
2. **Auto-update on launch** — checks R2 for newer version, downloads in background.
3. **Errors are sentences, not stack traces** — "Your LinkedIn session expired. Reconnect →" not `playwright._impl._errors.TimeoutError`.
4. **License is invisible** — paste once, never see it again.
5. **Dashboard is the experience** — landing page, dashboard, and emails all share one design system.

That's the real engineering investment for the next 90 days. Not new features. Polish the install-to-first-lead path until it's irresistible.

---

## 5. Architecture (as it exists, simplified)

```
┌─────────────────────────────────────────────────────────────┐
│  Customer's machine (macOS / Linux / Win-WSL)               │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ dashboard    │◄──►│ server.py    │◄──►│ state.json   │   │
│  │ .html        │    │ :5555        │    │ (local DB)   │   │
│  │ (browser)    │    │              │    │              │   │
│  └──────────────┘    └──────┬───────┘    └──────────────┘   │
│                             │                               │
│                    ┌────────┼────────┐                      │
│                    ▼        ▼        ▼                      │
│              LinkedIn   Reddit   Claude API                 │
│              (Playwright)  (JSON)  (anthropic)              │
└─────────────────────────────────────────────────────────────┘
                             │
                             │ license validate (every 24h)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloudflare (managed by Ermo)                               │
│                                                             │
│  influentia.io          api.influentia.io                 │
│  (Pages — landing)       (Worker — Stripe + licenses)       │
│         │                       │                           │
│         ▼                       ▼                           │
│   downloads.influentia.io   D1 database                    │
│   (R2 — installers, zip)     (license records)              │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                          Stripe
```

**Three planes, three responsibilities:**
- **Customer machine** → does the work (scan, message, follow-up). Source of truth: `state.json`.
- **Cloudflare Worker** → issues + validates licenses, receives Stripe webhooks. Source of truth: D1 `licenses` table.
- **Stripe** → money + subscription state. Source of truth for billing.

State never crosses planes inappropriately. Customer data never leaves their machine.

---

## 6. The kill list — what to remove this week

These exist and create confusion. Delete or consolidate.

| Item | Action | Why |
|---|---|---|
| `Outreach Pilot` brand everywhere | Replace with `Influentia` | Two names = no name |
| `outreach-pilot.zip` | Rename to `influentia.zip` | Same |
| `outreachpilot.app` | Redirect to `influentia.io` | Same |
| `IMPROVEMENTS.md` | Archive to `docs/archive/` | Past-tense, no longer current |
| `GUIDE.md` | Archive — content moves into HANDOFF + in-app help | One source per topic |
| `linkedin_outreach/SETUP.md` (nested) | Delete | Duplicate of root SETUP.md |
| Old `*.plist` files in root | Move to `disabled_plists/` (some already done) | One LaunchAgent in production |
| 8 daily run reports in root | Move to `logs/runs/` | They clutter the repo root |
| `Authentik_Studio_Playbook.docx` | Move to `docs/` if needed, else archive | Not part of product |
| `LinkedIn_Outreach_Autopilot_Guide.docx` | Archive | Old name + replaced by HANDOFF |
| Two README.md files (root + nested) | Keep root only | Same |
| Mixed colour palettes (teal vs purple) | Lock one (purple — see UI.md) | One product, one look |
| `Install.bat` / `Start.bat` | Replace with proper Windows installer in v1.0 | Batch files signal hobby project |

**Rule going forward:** if a doc isn't HANDOFF.md, BLUEPRINT.md, UI.md, UX_FLOW.md, or README.md — it lives in `docs/archive/` until it earns its way back.

---

## 7. 90-day priorities (ranked, do them in order)

### Sprint 1 — Brand consolidation (week 1)
1. Rename everywhere: code, landing copy, Stripe product, zip filename, Cloudflare DNS.
2. Pick the colour palette (UI.md says purple). Update dashboard.html tokens to match landing.
3. Archive the kill-list docs.
4. Replace HANDOFF + README + GUIDE + IMPROVEMENTS with the four canonical docs (this set).

**Done = anyone landing on your site, downloading the app, and opening the dashboard sees one consistent product.**

### Sprint 2 — Onboarding polish (weeks 2–3)
5. One-click installer (`.dmg` first, `.msi` second).
6. Auto-update from R2 on launch.
7. First-run wizard inside the dashboard — 5 screens max, ends with first scan triggered automatically.
8. Replace every Python traceback with a friendly error card.
9. License flow polish — paste once, store in OS keychain, never ask again.

**Done = a non-technical founder goes from Stripe checkout → first qualified Reddit lead in under 10 minutes.**

### Sprint 3 — Trust & retention (weeks 4–6)
10. Daily summary email (sent from a Cloudflare Worker that reads anonymised metrics the user opts into).
11. "Pain trend report" — Reddit feature already in HANDOFF idea list. Powerful for content marketing.
12. Activity log polish (timeline view, not raw text).
13. Privacy page + simple Terms (already drafted, polish them).
14. SOC2-light disclosure: "We never see your data" with a one-page proof.

**Done = customers tell other customers about Influentia.**

### Sprint 4 — Growth surface (weeks 7–12)
15. Landing page comparison pages (`/vs-expandi`, `/vs-phantombuster`, `/vs-dux-soup`) — already exist, polish them.
16. Affiliate / referral system (10% recurring for 12 months).
17. Case study #1 — your own usage, transparently.
18. One paid acquisition channel test (LinkedIn ads to LinkedIn-content founders — meta and on-brand).

**Done = you have a repeatable acquisition channel and the first 50 customers.**

---

## 8. Anti-goals (things we won't do)

These will tempt you. Resist.

- ❌ **No team / multi-seat in v1.** Solo founders are the wedge. Teams come later.
- ❌ **No CRM integration in v1.** Notion/Airtable export is enough. Native HubSpot/Salesforce = scope explosion.
- ❌ **No mobile app.** Outreach is a desk activity. Mobile = vanity.
- ❌ **No "AI does everything" voice.** Customers buy *control*. The AI drafts; the human approves. That's the safety net AND the marketing differentiator.
- ❌ **No more channels yet (X, IG, email).** LinkedIn + Reddit is enough. Depth > breadth.
- ❌ **No web app version.** See section 4. Hosted SaaS is the failure mode of every competitor.
- ❌ **No founder-mode rebuilds.** The current Python+SimpleHTTPServer stack is "ugly but works." Don't rewrite in Next.js until $10k MRR.

---

## 9. Success metrics

Track these. Nothing else matters yet.

| Metric | Target by day 90 | Why |
|---|---|---|
| Landing → checkout conversion | 3%+ | Below this, the page or the offer is wrong. |
| Checkout → first run | 90%+ | Below this, install is too painful. |
| First run → first scan | 95%+ | First scan is automatic; below 95% = a bug. |
| 30-day retention | 75%+ | Tool that doesn't book calls won't retain. |
| MRR | $5,000 (~50 paying at $97) | Wedge proven. |
| Refund rate | <8% | Industry-standard SaaS benchmark. |
| Customer-reported bans | 0 | If this goes above zero, stop selling and fix. |
| Inbound to Authentik DFY | 1+ qualified call/week from Influentia customers by day 60 | Flywheel working. |

---

## 10. The one-line tests

Whenever a decision is murky, run it through these:

1. **Brand test:** does this read as Influentia speaking for itself, with no parent-brand attribution? If not, simplify. (Authentik mention belongs *only* on the About page.)
2. **Local-first test:** does this make the customer's data leave their machine unnecessarily? If yes, don't ship it.
3. **One-screen test:** can the user finish the task on one screen without scrolling or hunting? If not, redesign.
4. **First-time test:** would a customer who's never seen this understand what to do in 5 seconds? If not, simplify.
5. **Confusion test:** is there a name, label, or doc that contradicts another? If yes, that's the next bug to fix.

---

## 11. Companion docs

| Doc | Purpose | When to read |
|---|---|---|
| `BLUEPRINT.md` (this file) | Strategy, brand, priorities, anti-goals, pricing. | When making a decision bigger than a feature. |
| `POSITIONING.md` | ICP / messaging / objection-handlers / ecosystem flywheel / public content engine. | When writing landing copy, naming a feature, replying to a sales lead. |
| `PRE_LAUNCH.md` | Critical-path 14-day checklist. Soft + public launch criteria. | Daily during the run-up to relaunch. |
| `LEGAL.md` | Terms / Privacy / DPA / refund / tax / trademarks. DIY-first, ~$0 cost. | Before publishing any legal page or taking the first $97. |
| `LAUNCH_KIT.md` | 10-customer target sheet + 8-post LinkedIn calendar + Pain Trend Report draft. | Days 11–30 of the launch arc. |
| `HANDOFF.md` | Current state, last session, next action. Paste into a new chat to resume. | Every new session. |
| `UI.md` | Design tokens, components, page anatomy. | When designing or coding any visual change. |
| `UX_FLOW.md` | Customer journey map, every screen, every confusion point. | When changing onboarding, error states, user-facing copy. |
| `INSTALLER.md` | Free path (one-line bash) + signed path (.dmg/.msi). | When building or shipping a release. |

Nine canonical docs. Anything outside that lives in `docs/archive/`.

---

_Strategy is choosing what not to do. Influentia wins by being the only local-first option in a market that has forgotten privacy and quality. Build for the next 50 customers, not the next 5,000._
