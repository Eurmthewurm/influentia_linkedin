# Influentia — Legal & Compliance Checklist (cost-minimised)
_DIY-first. No lawyer for v1. Specific edits to existing files. Total incremental cost: ~$0 to launch, ~$0–25/mo to scale._

**Status:** active pre-launch checklist.
**Read this before:** publishing the new landing, taking the first $97 charge.
**Do not pay a lawyer.** Until you're at $10k MRR + 200 customers, the right move is well-written DIY documents reviewed once with an LLM. A $500 lawyer review for v1 is cargo-cult expensive.

---

## 1. The honest risk picture

### What can actually happen, ranked

| Risk | Likelihood | Real consequence | Mitigation already in place |
|---|---|---|---|
| Customer's LinkedIn account gets restricted/banned | Real (especially heavy users) | They blame you, ask for refund, possibly post negative reviews | Conservative caps + Terms §2 disclaimer (already present) + 14-day refund |
| Customer claims they were misled and chargebacks | Low–medium | $97 + Stripe chargeback fee ~$15 + dispute time | Clear marketing copy + visible refund policy + offer refund first, dispute second |
| EU customer asks for DPA | Medium (agency owners will) | Need to provide one within 30 days or lose the deal | Free template (see §6) ready to send |
| GDPR data subject request | Low at <500 customers | 30-day SLA to export/delete | Already simple — `state.json` is local; only email + Stripe ID on your servers |
| LinkedIn legal action against you personally | **Very low** | Cease & desist, possibly takedown demand | hiQ Labs v. LinkedIn (9th Cir. 2022) established scraping ≠ CFAA violation; selling automation tools has never been criminalised |
| Patent troll | Low for a $58k ARR product | Nuisance settlement demand $5–15k | Defer until it happens. Never first-strike legal. |

**The one risk that will actually bite you:** customer #1 gets their LinkedIn restricted, blames you, and posts about it. Your defence is the Terms (already strong), conservative caps (already shipped), and a fast, friendly refund. Not a lawyer.

### What does NOT bite you (resist anxiety here)
- Selling software that automates LinkedIn is legal in every jurisdiction we'd sell into.
- Local-first architecture means you're not the data processor for customer prospect data — that's a major GDPR de-risker.
- $97/mo SaaS to global customers is the most well-trodden legal path on the internet. Standard templates cover 95% of it.

---

## 2. Cost-minimised stack (what to actually use)

| Need | Pick | Cost | Why |
|---|---|---|---|
| Terms of Service | DIY edits to existing `landing/terms.html` (see §3) | **$0** | Already 90% there. |
| Privacy Policy | DIY edits to existing `landing/privacy.html` (see §4) | **$0** | Already 80% there. |
| DPA template | [GDPR.eu free DPA](https://gdpr.eu/wp-content/uploads/2019/01/Data-Processing-Agreement-Template.pdf) | **$0** | Industry-standard EU template. Customise email/address. |
| Refund policy | One paragraph in Terms (see §3) | **$0** | Standalone refund page is over-engineering. |
| Cookie banner | **Not needed** if landing has zero tracking cookies (see §5) | **$0** | Confirm with browser DevTools; if true, skip the banner entirely. |
| Support email | `support@influentia.io` via Cloudflare Email Routing → your Gmail | **$0** | Cloudflare Email Routing is free for any domain on Cloudflare. |
| Email-based contracts (DPA signing) | Free signature on PDF + email reply, or HelloSign free tier | **$0** | E-signature laws (eIDAS/ESIGN) recognise this. |
| Trademark check on "Influentia" | [USPTO TESS](https://www.uspto.gov/trademarks/search) + [EUIPO TMview](https://www.tmdn.org/tmview/) free searches | **$0** | Do this BEFORE printing logo merch. Costs nothing to check. |
| Trademark filing | Defer to Q3 (after $5k MRR) | $250–450 (1 class, 1 jurisdiction) | Not v1-critical. Hold cash. |
| Privacy/Terms generator (if you outgrow DIY) | [Termly](https://termly.io) free tier | $0 / $19+/mo when you scale | Only when you have 200+ customers and changes per quarter. |
| Lawyer review | Defer to $10k MRR | $500–2,000 one-time | At scale, not at launch. |

**Total launch cost for legal: $0.** The Apple Developer cert and Windows EV cert are infrastructure, not legal.

---

## 3. Edits to `landing/terms.html` (specific lines)

The file is mostly correct. Make these changes before launch.

### 3.1 Update the pricing line
**Current (line 108):** `After the trial ends, we charge $29/month on a recurring basis.` (Placeholder from pre-launch setup. No live customers were ever charged at this price.)
**Change to:**
```
After the trial ends, we charge $97/month on a recurring basis (or $970/year if you choose annual).
```

### 3.2 Update the refund clause
**Current (line 111):** `We do not offer refunds for partial months.`
**Change to:**
```
We offer a 14-day "first booked call or full refund" guarantee on your first paid month. If Influentia hasn't helped you book a qualified call within 14 days of your first charge, email support@influentia.io and we'll refund every cent. After the 14-day window, we don't refund partial months — you can cancel anytime and your subscription ends at the next billing date.
```

### 3.3 Strengthen the indemnification section
**Add as new §3a, after §3 "No liability":**
```html
<h2>3a. Your responsibility for your LinkedIn account</h2>
<p>You acknowledge that LinkedIn's Terms of Service prohibit automated activity. By using Influentia, you accept full responsibility for any actions LinkedIn takes against your account, including but not limited to warnings, restrictions, suspensions, or permanent bans. You agree to defend, indemnify, and hold Influentia, its operator, and any affiliated parties harmless from any claim, demand, or damages arising out of or related to your use of this software with your LinkedIn account.</p>
<p>Influentia ships with conservative usage limits designed to minimise — not eliminate — this risk. We do not promise that your account will remain in good standing.</p>
```

### 3.4 Replace the placeholder governing law clause
**Current (line 130):** `These terms are governed by the laws of your jurisdiction. Any disputes will be resolved in the courts of that jurisdiction.`
**Change to (assuming you operate from the Netherlands):**
```
These terms are governed by the laws of the Netherlands. Any disputes will be resolved exclusively in the courts of Amsterdam, the Netherlands. The United Nations Convention on Contracts for the International Sale of Goods does not apply.
```

(If you're not NL-based, swap in your actual jurisdiction. Pick *one* — saying "your jurisdiction" creates ambiguity that hurts you.)

### 3.5 Add data export and deletion rights (GDPR)
**Add as new §10:**
```html
<h2>10. Your data rights</h2>
<p>You have the right to access, export, or delete the personal data we hold about you (your email, license key, and Stripe subscription metadata). To exercise these rights, email support@influentia.io and we will respond within 30 days. Your local data — leads, messages, conversations — lives on your computer; only you control that data.</p>
```

### 3.6 Fix the support email domain
The file uses `support@influentia.io` (line 133). Confirm this matches all other customer-facing surfaces (`influentia.io` is your canonical domain). If you find any `support@influentia.app` remnants, replace them.

---

## 4. Edits to `landing/privacy.html` (specific lines)

Even shorter list. The file is already well-aligned with the local-first story.

### 4.1 Confirm the support email domain
Line 119 should read `support@influentia.io` (matches your canonical domain). If you find any `support@influentia.app` remnants in privacy.html, replace them with `support@influentia.io`.

### 4.2 Add the controller information (GDPR Article 13)
**Add as new §1 at the top, before "Overview":**
```html
<h2>Who we are</h2>
<p>Influentia is operated by Ermo Egberts (acting as data controller), [Your Address Here], Netherlands. Contact: <a href="mailto:support@influentia.io">support@influentia.io</a>.</p>
```

You need a real address. A coworking space mailing address or virtual office (KVK registration) suffices. Cost: typically €50–150/year for a business address.

### 4.3 Add explicit GDPR rights enumeration
**Add as new §"Your rights" before "Cancellation":**
```html
<h2>Your rights</h2>
<p>Under GDPR and similar privacy laws, you have the right to:</p>
<ul>
  <li><strong>Access</strong> — request a copy of the data we hold about you.</li>
  <li><strong>Rectification</strong> — correct inaccurate data.</li>
  <li><strong>Erasure</strong> — delete your account and our records of you.</li>
  <li><strong>Portability</strong> — receive your data in a machine-readable format.</li>
  <li><strong>Object</strong> — opt out of any processing you disagree with.</li>
  <li><strong>Lodge a complaint</strong> — with your local data protection authority (in the Netherlands: the Autoriteit Persoonsgegevens).</li>
</ul>
<p>To exercise any of these, email <a href="mailto:support@influentia.io">support@influentia.io</a>. We respond within 30 days.</p>
```

### 4.4 Add cookie disclosure
**Add as new section before "Changes":**
```html
<h2>Cookies and tracking</h2>
<p>This website uses no third-party tracking cookies. We do not run analytics that identify you personally. If you accept payment, Stripe sets its own cookies on the checkout page — see <a href="https://stripe.com/cookie-settings">Stripe's cookie policy</a>.</p>
<p>The Influentia desktop app stores your license key and LinkedIn session locally on your computer (in your operating system's keychain). These are not cookies; they are local credentials and do not leave your machine.</p>
```

This is the section that turns "no cookies" from a footnote into a *selling point*. Tell the privacy story.

### 4.5 Reflect the local-first AI flow precisely
**Update the "Data sent to Anthropic" section:**
```html
<h2>Data sent to Anthropic (Claude API)</h2>
<p>When Influentia generates or refines a message, the prospect's public profile data (name, headline, recent posts, company) is sent to Anthropic's Claude API to produce the personalised draft. The full prospect record never leaves your machine — only the data needed for that single message generation is sent. Anthropic does not train on API data by default; see <a href="https://www.anthropic.com/legal/aup">Anthropic's terms</a> for full detail.</p>
```

---

## 5. Cookie banner — probably skip

Run this audit before launch (cost: 5 minutes):

1. Open `influentia.io` in an incognito Chrome window.
2. DevTools → Application → Cookies.
3. If the cookie list is empty (or contains only Cloudflare's `__cf_bm` security cookie, which is exempt under GDPR Article 6(1)(f) "legitimate interests"), **you do not need a cookie banner**.
4. The Stripe checkout flow opens on Stripe's domain — their banner, not yours.

If you ever add Plausible, PostHog, or any tracker, revisit this. Until then, no banner = no friction = better conversion.

---

## 6. Data Processing Agreement (DPA) — for B2B customers who ask

A few agency owners will request a DPA. Have one ready in 30 minutes:

1. Download the [GDPR.eu free DPA template](https://gdpr.eu/wp-content/uploads/2019/01/Data-Processing-Agreement-Template.pdf).
2. Fill in: your details (controller — though for Influentia you're mostly *not* the processor of customer data), customer placeholder, signed PDF.
3. Save as `docs/templates/DPA-template.docx` so any new customer can be served same-day.
4. Note in your signed reply: "Influentia is local-first; the customer is the controller and processor of their own LinkedIn / prospect data. We hold only your account email, license key, and Stripe subscription metadata as a sub-processor of payment information (sub-processor: Stripe Inc.)."

That sentence does most of the work. EU agency clients want to see it; they file it; the deal closes.

---

## 7. Refund mechanics (the operational detail)

Stripe handles the money. You handle the license. Wire it once:

1. **Stripe webhook** `customer.subscription.deleted` → Worker sets `tier = 'cancelled'` in D1. License starts failing validation within minutes.
2. **For the 14-day guarantee**, customer emails `support@influentia.io`. You issue refund in Stripe Dashboard (one click). Webhook fires. License revokes automatically. No code changes — already wired.
3. **Optional refinement (Sprint 3):** add a "Self-serve refund within 14 days" button on `/account` that calls a Worker endpoint, refunds via Stripe API, revokes license. Cost: 2 hours of code. Saves your inbox forever.

**Refund-after-heavy-use abuse:** if a customer runs maximum LinkedIn caps + AI generation for 13 days then refunds, your Anthropic cost is ~$8–12 sunk against $0 revenue. At 50 customers and a refund rate <8%, that's <$50/month total. Don't engineer against it. Eat the cost.

---

## 8. Tax and business structure (defer, mostly)

You don't need a Dutch BV (besloten vennootschap) at launch. Here's the staircase:

| Stage | Structure | Why |
|---|---|---|
| 0 → €5k MRR (~50 customers) | Personal eenmanszaak (sole trader) registered with KVK | Already exists; adequate for early sales. |
| €5k → €15k MRR | Add Stripe Tax ($25/mo) for auto VAT | EU customers must be charged VAT in their country; Stripe Tax handles the math. Otherwise you owe it from your margin. |
| €15k+ MRR or first US/UK enterprise customer | Form Influentia BV (NL) or comparable entity | Liability separation, tax efficiency, professional impression. ~€500 setup + €100/mo accountant. |
| Any year > €20k revenue | Hire a part-time accountant | They save you more than they cost. |

**Don't form a BV at zero MRR.** It's premature optimisation that costs €1,000+/year for no benefit until you have revenue and risk to ringfence.

**EU VAT rule (the one you must know):** if you sell digital services to consumers (B2C) in the EU, you owe VAT in *their* country, not yours, the moment you cross €10k/year of cross-border B2C sales. For B2B sales (most of Influentia's market), the customer reverse-charges VAT — you don't collect it, you just need their VAT number. Stripe Tax automates both. €25/mo when you cross €5k MRR is the right time to enable it.

---

## 9. Trademarks — quick check, then move on

Before printing any merchandise or deeply embedding the wordmark:

1. **USPTO search:** https://www.uspto.gov/trademarks/search — search "Influentia." Cost: $0.
2. **EUIPO search:** https://www.tmdn.org/tmview/ — search "Influentia." Cost: $0.
3. **Quick Google + "[Influentia]" in your industry classes (35 advertising/marketing, 42 SaaS):** make sure no one's actively using.

If results are clear, defer the actual filing until $5k MRR. Filing fees:
- USPTO: ~$250–350/class
- EUIPO: ~€850 base for first class
- Single class (35 or 42) covers a SaaS marketing tool.

Total deferred: ~€500–€1,000 once you have revenue to justify it.

---

## 10. The annual review (calendar reminder)

Set a calendar reminder for one date per year (your launch anniversary works) to:

- ☑️ Re-read your own Terms and Privacy. Anything stale? Anything you do that they don't cover?
- ☑️ Update "Last updated" date (only if you actually changed something).
- ☑️ Email customers if there's a material change (GDPR Article 13(3)).
- ☑️ Confirm Stripe Tax is still set up correctly.
- ☑️ If MRR > €5k, talk to an accountant about VAT compliance.
- ☑️ If MRR > €15k, talk to a lawyer about entity formation.

That annual hour replaces six months of paranoia.

---

## 11. The "never do these" list

- ❌ Promise specific results in marketing ("Get 100 leads in 30 days!"). Massive consumer-protection liability across jurisdictions.
- ❌ Mention competitor brands negatively beyond fair-use comparison ("Phantombuster will get you banned" — no; "tools that run on shared cloud IPs face higher detection rates" — yes).
- ❌ Use customer logos or names without written permission.
- ❌ Auto-renew silently after a "free" trial without clear disclosure (EU consumer law violation; Stripe's checkout flow handles this if configured correctly — verify).
- ❌ Process refund requests slowly. Within 24h, every time. The reputation cost of a slow refund dwarfs the dollar cost of the refund.
- ❌ Reply to a legal threat (cease & desist, demand letter) without thinking. Sleep on it. Most threats evaporate when ignored 48 hours; the rest deserve a $200 lawyer hour.

---

## 12. What this doc isn't

- ❌ A substitute for legal advice when you're sued.
- ❌ Comprehensive — there are hundreds of edge cases (US state-by-state privacy laws, China data residency, Russia OFAC, etc.). Add as you encounter them.
- ❌ Static. Re-read once a year. See §10.

---

## 13. Companion docs

| Doc | Use when |
|---|---|
| [`PRE_LAUNCH.md`](./PRE_LAUNCH.md) | Where these legal items land in the 14-day execution checklist. |
| [`POSITIONING.md`](./POSITIONING.md) | Voice/tone for refund replies, support emails, and ToS prose. |
| [`UI.md`](./UI.md) | Visual treatment of the legal pages. |
| [`HANDOFF.md`](./HANDOFF.md) | Where things stand right now. |

---

_Premium SaaS doesn't ship with cheap legal documents. It ships with **honest** legal documents that match the product. Influentia's privacy story is your moat — your privacy policy should be the proudest page on your site, not the most boring._
