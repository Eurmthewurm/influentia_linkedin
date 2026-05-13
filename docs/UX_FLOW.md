# Influentia — Onboarding & UX Flow Map
_Every screen, every decision, every confusion point — from "first sees ad" to "first booked call." Use this when changing any user-facing path._

---

## The promise

A B2B founder who's never seen Influentia should go from **landing page → first qualified lead** in **under 10 minutes.** Anything that breaks that promise is the next thing to fix.

---

## The full journey (one map)

```
   ① DISCOVER ─────► ② DECIDE ────► ③ BUY ────► ④ INSTALL ─────► ⑤ ACTIVATE ────► ⑥ ENGAGE ─────► ⑦ RETAIN
   (LinkedIn ad,    (landing,      (Stripe   (download,         (paste license,   (first replies, (weekly value,
    referral,        comparison,    checkout, run installer,     connect          first booked     summary email,
    SEO blog)        FAQ, pricing)  email)    open dashboard)    LinkedIn,        meeting)         expansion)
                                                                  first scan)
```

Each box below is one stage. Each stage has: **goal, screen, what users see, what can go wrong, recovery.**

---

## ① DISCOVER

### Goal
Land a qualified visitor on `influentia.io`.

### Channels
- LinkedIn ads to "B2B founder, agency owner, consultant" audience (meta + on-brand).
- Referral / affiliate (Sprint 4 priority).
- SEO comparison pages (`/vs-expandi`, `/vs-phantombuster`, `/vs-dux-soup`) — already built.
- Ermo's own LinkedIn content (Authentik Studio).

### Confusion to remove
- Two URLs (`outreachpilot.app` + future `influentia.io`) → consolidate to one with 301 redirects.
- Brand schizophrenia (Outreach Pilot vs Influentia in copy) → finish the rename.

---

## ② DECIDE

### Goal
Convince a visitor in <90 seconds that Influentia is for them and worth $97.

### Screen — `landing/index.html`

```
┌─────────────────────────────────────────────────────────────┐
│ NAV  Influentia                  Pricing  FAQ  [Start free] │
├─────────────────────────────────────────────────────────────┤
│  ● Live on your machine                                     │
│                                                             │
│  LinkedIn outreach on autopilot.                            │
│  On YOUR machine. In YOUR voice.                            │
│                                                             │
│  Influentia finds your ideal clients, reads what they post  │
│  about, and writes personalised messages. Follows up        │
│  automatically. Runs from your computer, on your IP.        │
│                                                             │
│  [ Start free 7-day trial → ]    [ Watch 60-sec demo ]      │
│                                                             │
│  · No cloud. Your data stays on your machine.               │
│  · No team seats. Built for solo founders.                  │
│  · $97/month. Cancel anytime.                               │
├─────────────────────────────────────────────────────────────┤
│  [Animated product screenshot: dashboard with leads ticking]│
└─────────────────────────────────────────────────────────────┘
```

### What works
- ✅ Strong differentiator (local-first) above the fold.
- ✅ Comparison pages exist for SEO + bottom-funnel.
- ✅ One pricing tier — no decision fatigue.

### Confusion to remove
- ❌ Hero copy still references "Outreach Pilot" in places.
- ❌ "Demo" video doesn't exist yet — placeholder kills credibility.
- ❌ FAQ doesn't address "will I get banned?" head-on. It must.
- ❌ No social proof (logos, testimonials). Even one founder quote helps; until then, hide the empty section, don't show "Trusted by [empty]."

### Fixes (Sprint 1)
1. Find/replace brand strings.
2. Record a 60-second Loom of Ermo using it. Embed.
3. Add an "Account safety" FAQ with conservative, honest answer.
4. Add one founder quote (yours or first beta user) with photo + LinkedIn link.

---

## ③ BUY

### Goal
Visitor → paying customer with a license key in their email.

### Screens
1. CTA click → `/start.html` (collect email)
2. → Stripe Checkout (hosted)
3. → `/success.html?session_id=cs_…`

### What happens technically
```
Browser  POST /api/checkout {email}  ─►  Worker creates Stripe Checkout Session
                                          → returns redirect URL
Browser  redirects to checkout.stripe.com
Customer pays
Stripe   POST /api/stripe/webhook (checkout.session.completed)
Worker   creates license row, generates key, emails customer (Stripe receipt + license)
Browser  redirected to /success.html?session_id=…
success.html  GET /api/license/by-session?session_id=…  ─►  shows license key + download button
```

### What works
- ✅ Webhook → license issuance → success page lookup is wired and tested.
- ✅ 7-day trial in Stripe gives confidence.

### Confusion to remove
- ❌ Two emails arrive (Stripe receipt + license email). Customers miss the license one. Solution: send a **single** combined email from Stripe with the license key in the receipt description, OR a single license email with the receipt PDF attached.
- ❌ Success page shows the key but doesn't say "we also emailed it." Add that line.
- ❌ Download button on `/success.html` says "Download" with no idea what they're getting. Show file size + OS-specific button: "Download for Mac (84 MB)" with a small "Windows" / "Linux" link beneath.

### Fixes (Sprint 1–2)
1. Combined email — license key in Stripe receipt description.
2. OS detection on success page (User-Agent sniff is fine here).
3. Trial reminder emails: day 5, day 7 ("Trial ending — keep going for $97/mo"). Note: 14-day refund window starts at first charge, not at trial start.

---

## ④ INSTALL

### Goal
Customer goes from "I have a license key" to "the dashboard is open in my browser" without a single confusing step.

### Current path (painful)
1. Download `outreach-pilot.zip` (~80 MB)
2. Unzip somewhere
3. Open Terminal (already lost 30% of users)
4. `cd ~/Downloads/outreach-pilot/`
5. `bash install.sh` (Mac/Linux) or run `Install.bat` (Win)
6. Wait for Python + venv + playwright install (~3 min)
7. Edit `.env` with their API keys
8. `python server.py`
9. Open `http://localhost:5555`
10. Paste license key

### Future path (Sprint 2 target)
1. Download `Influentia-1.0.0.dmg` (Mac) / `.msi` (Windows)
2. Drag to Applications / run installer
3. Open Influentia from Launchpad
4. App opens browser to `http://localhost:5555` automatically
5. First-run wizard catches the license key from clipboard or asks for it
6. Done

### Confusion to remove
- ❌ Step 7 (edit `.env`) — non-technical users panic. Must move into in-app onboarding.
- ❌ Anthropic API key requirement at install time — kills conversion. Influentia should ship with **a free trial of message generation through Authentik's API key**, with an option to add their own key later for cost control. (Margin tradeoff = customer cost; covered by the $97.)
- ❌ Brave Search API key requirement — same. Make it optional / handled by your key.
- ❌ LinkedIn cookie capture — currently F12 → Application → Cookies → copy `li_at`. Ridiculous. Replace with a "Connect LinkedIn" button that opens a Playwright window where the user just logs in normally. Cookie captured automatically.

### Fixes (Sprint 2)
1. Build `.dmg` for macOS (use `py2app` or `briefcase`). Code-sign with your Apple Developer cert.
2. Build `.msi` for Windows (use `briefcase` or `pyinstaller` + `wix`).
3. Auto-open browser on launch.
4. Bundle Authentik's API key proxy so users don't need their own Anthropic key in v1.
5. "Connect LinkedIn" Playwright login flow — replaces manual cookie copying.

---

## ⑤ ACTIVATE

### Goal
First scan completes, first lead appears, customer thinks "OK, this works."

### Screens — first-run wizard (5 screens, total <2 minutes)

```
SCREEN 1   Welcome / paste license
┌───────────────────────────────────────┐
│  Welcome to Influentia.                │
│  Paste your license key below.         │
│                                       │
│  [_______________________________]    │
│                                       │
│  [ Activate → ]                        │
│  Don't have one? Start a free trial → │
└───────────────────────────────────────┘

SCREEN 2   Tell us about you (the personalisation primer)
┌───────────────────────────────────────┐
│  In one sentence — what do you sell?  │
│  [textarea — example: "I help B2B... │
│                                       │
│  Who's your ideal customer?           │
│  [textarea — example: "Founders..."]  │
│                                       │
│  We'll use this to personalise every  │
│  message. You can change it later.    │
│                                       │
│  [ Continue → ]                        │
└───────────────────────────────────────┘

SCREEN 3   Connect LinkedIn
┌───────────────────────────────────────┐
│  Connect your LinkedIn                 │
│  We'll open a browser so you can log  │
│  in normally. Your password never      │
│  reaches us — only your session stays │
│  on this machine.                      │
│                                       │
│  [ Open LinkedIn → ]                   │
└───────────────────────────────────────┘

SCREEN 4   Connect Reddit (optional)
┌───────────────────────────────────────┐
│  Want to scan Reddit for buyer signal?│
│  We'll find founders posting about    │
│  pain that matches what you sell.     │
│  No login needed — Reddit is public.  │
│                                       │
│  [ Yes, scan Reddit → ]   [ Skip ]    │
└───────────────────────────────────────┘

SCREEN 5   First scan running
┌───────────────────────────────────────┐
│  Running your first scan…             │
│  ▓▓▓▓▓▓▓▓░░░░░░░░░░░  42%             │
│                                       │
│  Found 7 buyer-intent signals so far. │
│  This takes about a minute.           │
│                                       │
│  [tick list of subreddits being       │
│   scanned, real-time]                 │
└───────────────────────────────────────┘

→ lands on dashboard with leads visible
```

### Confusion to remove
- ❌ Currently no first-run wizard exists at parity. `.onboarding.json` is partial.
- ❌ Knowledge Base setup is buried in a Settings tab — most customers never fill it. Consequence: messages sound generic, customers churn. Solution: force the personalisation primer in Screen 2.
- ❌ The Reddit scan kicks off without ever telling the user it's happening. Fix: progress UI in Screen 5 (already partly built).

### Fixes (Sprint 2)
1. Build the 5-screen wizard. Show only on first run; gated by `state.json.first_run_complete`.
2. Auto-trigger first scan at end of wizard.
3. Land the user on the Dashboard tab with a banner: "Your first 7 leads are ready — review them in Reddit Signal →"

---

## ⑥ ENGAGE

### Goal
Customer reviews leads, approves messages, gets first reply, then first booked call.

### The daily loop (the actual product)

```
9:00 AM     Influentia scans LinkedIn + Reddit (auto)
            Customer opens dashboard, sees:
              · "X new buyer signals on Reddit"
              · "Y new prospects matching ICP on LinkedIn"
              · "Z LinkedIn replies waiting"

9:05 AM     Customer reviews Reddit signals (3 min)
              · clicks "Generate reply" on top 3
              · approves drafts → "Copy & open Reddit"

9:10 AM     Customer reviews LinkedIn replies (5 min)
              · skims AI-suggested follow-ups
              · approves or edits, sends

9:15 AM     Customer closes the tab. Influentia keeps running.

3:00 PM     Influentia checks for new replies (auto)
6:00 PM     Same. Sends a daily summary at 6:30 PM.
```

### What works
- ✅ Reddit Signal cards (score, subreddit, excerpt, tags) are clear.
- ✅ Approve-before-post is the safety story.

### Confusion to remove
- ❌ No "what should I do next?" surface. Users land on the dashboard and don't know whether to look at Reddit, LinkedIn, or settings. Solution: a single **"Today's queue"** card at top of Dashboard, listing the 5 highest-priority actions.
- ❌ "Hot lead" vs "warm lead" labels exist but rules aren't explained. Solution: hover tooltip + a one-line rule card in the empty state of the Insights tab.
- ❌ Messages are loaded from `prompts/*.txt` files. Customers can edit but most don't know they exist. Solution: "Tune AI" tab needs a clear "this is your message style — edit, then preview" UI.

### Fixes (Sprint 3)
1. "Today's queue" card on Dashboard.
2. Tooltip system for ambiguous labels.
3. Tune AI: side-by-side "your prompt" / "preview message" with sample lead.

---

## ⑦ RETAIN

### Goal
Customer renews, refers, expands.

### Triggers built-in
- **Daily summary email** (6:30 PM) — opens with one number ("3 replies today") and a 1-click link back to the dashboard. Sprint 3.
- **Weekly insights** — pattern report (best-performing message, busiest day, top topic).
- **Pain trend report** — Reddit feature; what topics are heating up. This is content marketing material the customer can re-share.
- **Trial ending** email day 6.
- **Inactive 7 days** email — "Want to pause for a week?" (better than churn).

### Expansion paths
- **Authentik DFY upsell** — for customers who say "I just don't have time." That's a $3k–$10k/mo done-for-you deal.
- **Affiliate** — 10% recurring for 12 months (Sprint 4).

### Confusion to remove
- ❌ No retention emails currently. Sprint 3 priority.
- ❌ No way to pause for vacation. Customers cancel instead. Solution: "Pause" button in Settings → Billing that holds Stripe charges + freezes runs.

---

## Confusion audit — top 10 fixes ranked

| # | Confusion | Severity | Sprint |
|---|---|---|---|
| 1 | Two product names (Outreach Pilot / Influentia) | 🔴 High | 1 |
| 2 | Two colour palettes (teal vs purple) | 🔴 High | 1 |
| 3 | Install requires Terminal + .env editing | 🔴 High | 2 |
| 4 | LinkedIn cookie capture is manual F12 | 🔴 High | 2 |
| 5 | First-run wizard incomplete | 🔴 High | 2 |
| 6 | Anthropic API key required to use | 🟠 Med | 2 |
| 7 | License + receipt arrive as 2 separate emails | 🟠 Med | 1 |
| 8 | Knowledge Base buried in Settings | 🟠 Med | 2 |
| 9 | No "Today's queue" surface on Dashboard | 🟠 Med | 3 |
| 10 | No retention emails | 🟡 Low | 3 |

---

## Empty-state and error-state catalogue

Every empty state and error state in the app should follow these patterns. Add new ones here as they arise.

| Surface | Condition | Pattern |
|---|---|---|
| Dashboard, day 1 | No leads yet | "Your first scan is queued. Hang on — we'll have leads in about a minute." + spinner |
| Reddit Signal | No signals scored ≥ 4 | "No buyer-intent posts found this scan. We'll try again at 6 PM." + [Run scan now] |
| Engage | No conversations active | "Quiet here. Try sending 3 connection requests — replies arrive in 24–48h." + [Find leads] |
| Tune AI | No prompts edited | "Your messages use the default style. Edit `first_message` to make them sound like you." + preview |
| Settings | License invalid | Friendly card: "We couldn't validate your license. Check that the subscription is active in [Account]" |
| Any tab | Server unreachable | Top banner: "Lost connection to Influentia. Retrying… [Restart]" |
| LinkedIn | Cookie expired | Top banner: "Your LinkedIn session expired. [Reconnect]" — block scan/connect actions until fixed |

---

## The success metric

A customer at day 30 should be able to say:

> "I open Influentia for 10 minutes a day. It tells me who to talk to and what to say. I've booked X calls."

If they can say that, retention is locked. If they can't, the next bug is in the journey above.

---

_Onboarding is the product. Every minute of friction here costs you 5% of conversion. Spend the engineering time._
