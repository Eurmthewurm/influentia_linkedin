# Influentia — UI Design System
_One brand, one palette, one product. Anything visual ships against this doc._

---

## 0. The decision: Purple wins

Two palettes are live today:

| Surface | Current | Decision |
|---|---|---|
| `landing/*.html` | Purple `#7c6aff` on near-black `#0c0c0e` | ✅ Keep |
| `dashboard.html` | Teal `#2dd4bf` on near-black `#07090f` | ❌ Migrate to purple |

**Why purple, not teal:**
- Teal is the default for AI/dev tools (Cursor, GitHub Copilot, Stripe). It signals "generic SaaS."
- Purple/violet positions Influentia closer to Linear, Notion AI, Vercel — premium, opinionated, B2B-considered.
- The landing page already invests in purple. Re-doing the customer-facing site is harder than re-tokenising one HTML file.

**Migration cost:** find/replace `#2dd4bf` → `#7c6aff`, `#5eead4` → `#a78bfa`, `rgba(45,212,191,*)` → `rgba(124,106,255,*)` in `dashboard.html`. ~15 minutes.

---

## 1. Brand tokens (paste these into every file)

```css
:root {
  /* Surfaces — darkest to lightest */
  --bg:           #0c0c0e;   /* page background */
  --s1:           #141417;   /* card resting */
  --s2:           #1c1c21;   /* card raised / input */
  --s3:           #242428;   /* hover / selected */

  /* Borders */
  --border:       rgba(255,255,255,0.07);
  --border-strong:rgba(255,255,255,0.12);

  /* Text */
  --text:         #f1f0ff;   /* primary */
  --text-dim:     #b3b1c8;   /* secondary */
  --muted:        #8b8a9e;   /* tertiary / hints */

  /* Brand */
  --accent:       #7c6aff;   /* primary action */
  --accent-hover: #6b58f0;   /* hover */
  --accent-soft:  rgba(124,106,255,0.12);  /* tints, glows */
  --accent2:      #a78bfa;   /* gradients, highlights */

  /* Semantic */
  --success:      #34d399;
  --warning:      #fbbf24;
  --danger:       #f87171;
  --info:         #60a5fa;

  /* Radii */
  --r-sm: 6px;
  --r-md: 10px;
  --r-lg: 14px;
  --r-pill: 999px;

  /* Motion */
  --t-fast: 0.12s ease;
  --t-base: 0.2s ease;
  --t-slow: 0.4s ease;

  /* Shadows */
  --shadow-card: 0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.35);
  --shadow-pop:  0 12px 32px rgba(124,106,255,0.25);
}
```

Use the variables. Never hard-code hex in components. Future palette changes happen in one place.

---

## 2. Typography

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

Inter is already loaded via Google Fonts on the landing. Keep it. Add the same `<link>` to `dashboard.html` if not already present.

| Role | Size | Weight | Letter-spacing | Use |
|---|---|---|---|---|
| Display | 56px / 64px line | 800 | -1.5px | Hero headline only |
| H1 | 32px / 40px | 700 | -0.6px | Page title |
| H2 | 22px / 30px | 700 | -0.4px | Section title |
| H3 | 16px / 24px | 600 | -0.2px | Card title |
| Body L | 16px / 26px | 400 | 0 | Long-form copy |
| Body | 14px / 22px | 400 | 0 | Default |
| Caption | 12px / 18px | 500 | 0 | Stat labels, badges |
| Eyebrow | 11px / 16px | 700 | 0.8px UPPERCASE | Section eyebrows |
| Code | 13px | 500 | 0 | `JetBrains Mono` or fallback `monospace` |

**Numbers in stats:** use `font-feature-settings: "tnum"` so they don't jitter when changing.

---

## 3. Spacing scale (8-point)

`4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 56 · 72 · 96`

Don't pick spacings outside this scale. If 18px feels right, you actually want 16 or 20.

---

## 4. Components (canonical)

### 4.1 Button

```html
<button class="btn btn-primary">Start free trial</button>
<button class="btn btn-secondary">Learn more</button>
<button class="btn btn-ghost">Cancel</button>
<button class="btn btn-danger">Disconnect LinkedIn</button>
```

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  height: 40px; padding: 0 18px;
  border-radius: var(--r-md); border: 1px solid transparent;
  font-size: 14px; font-weight: 600; letter-spacing: -0.2px;
  cursor: pointer; transition: all var(--t-base);
  white-space: nowrap;
}
.btn-primary   { background: var(--accent); color: #fff; }
.btn-primary:hover   { background: var(--accent-hover); transform: translateY(-1px); box-shadow: var(--shadow-pop); }
.btn-secondary { background: var(--s2); color: var(--text); border-color: var(--border-strong); }
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
.btn-ghost     { background: transparent; color: var(--text-dim); }
.btn-ghost:hover     { background: var(--s2); color: var(--text); }
.btn-danger    { background: transparent; color: var(--danger); border-color: rgba(248,113,113,0.4); }
.btn-danger:hover    { background: rgba(248,113,113,0.1); }
.btn[disabled] { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
.btn-sm        { height: 32px; padding: 0 12px; font-size: 13px; }
.btn-lg        { height: 48px; padding: 0 24px; font-size: 15px; }
```

**Rules.** One primary button per screen at most. Loading state replaces label with spinner, not "Loading…".

### 4.2 Card

```css
.card {
  background: var(--s1);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 20px;
  box-shadow: var(--shadow-card);
  transition: border-color var(--t-base), transform var(--t-base);
}
.card:hover { border-color: var(--border-strong); }
.card-accent { position: relative; overflow: hidden; }
.card-accent::before {
  content: ''; position: absolute; inset: 0 0 auto 0; height: 1px;
  background: linear-gradient(90deg, var(--accent), transparent);
}
```

### 4.3 Input

```css
.input, .textarea, .select {
  width: 100%; background: var(--s2);
  border: 1px solid var(--border); border-radius: var(--r-md);
  padding: 11px 14px;
  color: var(--text); font-size: 14px;
  transition: border-color var(--t-base), box-shadow var(--t-base);
}
.input:focus, .textarea:focus, .select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.input::placeholder { color: var(--muted); }
```

Labels above inputs, never inside (floating labels look like a 2018 redesign that never finished).

### 4.4 Badge / Pill

```css
.badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: var(--r-pill);
  font-size: 11px; font-weight: 600; letter-spacing: 0.02em;
  background: var(--s2); color: var(--text-dim);
}
.badge-accent  { background: var(--accent-soft); color: var(--accent2); }
.badge-success { background: rgba(52,211,153,0.12); color: var(--success); }
.badge-warning { background: rgba(251,191,36,0.12); color: var(--warning); }
.badge-danger  { background: rgba(248,113,113,0.12); color: var(--danger); }
.badge-dot::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; box-shadow: 0 0 8px currentColor;
}
```

### 4.5 Stat card (dashboard hero metric)

```css
.stat {
  background: var(--s1); border: 1px solid var(--border); border-radius: var(--r-lg);
  padding: 18px 20px; position: relative; overflow: hidden;
}
.stat::after {
  content: ''; position: absolute; inset: -50% -50% auto auto; width: 180px; height: 180px;
  background: radial-gradient(closest-side, var(--accent-soft), transparent);
  pointer-events: none;
}
.stat-label { /* eyebrow style */ }
.stat-value { font-size: 32px; font-weight: 700; color: var(--text); font-feature-settings: "tnum"; }
.stat-delta { font-size: 12px; color: var(--success); }
.stat-delta.neg { color: var(--danger); }
```

### 4.6 Empty state

Empty states are signage, not apologies. Always: icon, single sentence, one action.

```html
<div class="empty">
  <svg class="empty-icon">…</svg>
  <p class="empty-text">No leads yet — run your first scan.</p>
  <button class="btn btn-primary">Find leads now</button>
</div>
```

```css
.empty { text-align: center; padding: 56px 24px; color: var(--muted); }
.empty-icon { width: 32px; height: 32px; margin: 0 auto 12px; opacity: 0.5; }
.empty-text { font-size: 14px; margin-bottom: 16px; }
```

### 4.7 Toast / inline alert

Errors are **never** raw exceptions. They are sentences in a card with a recovery action.

```html
<div class="alert alert-warning">
  <strong>LinkedIn session expired.</strong>
  <span>Reconnect to keep messaging running.</span>
  <button class="btn btn-sm btn-secondary">Reconnect</button>
</div>
```

```css
.alert {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-radius: var(--r-md);
  border: 1px solid; font-size: 13px;
}
.alert-warning { background: rgba(251,191,36,0.06); border-color: rgba(251,191,36,0.3); color: var(--warning); }
.alert-danger  { background: rgba(248,113,113,0.06); border-color: rgba(248,113,113,0.3); color: var(--danger); }
.alert-success { background: rgba(52,211,153,0.06); border-color: rgba(52,211,153,0.3); color: var(--success); }
.alert-info    { background: var(--accent-soft);    border-color: rgba(124,106,255,0.3); color: var(--accent2); }
```

### 4.8 Pipeline / progress bar

```css
.bar { height: 8px; background: var(--s2); border-radius: var(--r-pill); overflow: hidden; }
.bar > span { display:block; height:100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width var(--t-slow); }
```

---

## 5. Page anatomy

### 5.1 Landing page (kept structure)

```
[ nav (fixed, blurred bg) ]
[ hero (split: copy left, product visual right) ]
[ social proof strip ]
[ how it works (3 steps with screenshots) ]
[ comparison table ]
[ pricing (one tier, $97/mo or $970/yr, 14-day money-back) ]
[ FAQ ]
[ CTA repeat ]
[ footer ]
```

### 5.2 Dashboard (refactor target)

```
┌─────────────────────────────────────────────────┐
│ TOP BAR: logo · campaign select · status pill · settings │
├──────────────┬──────────────────────────────────┤
│ SIDE NAV     │ MAIN VIEW                        │
│  Dashboard   │                                  │
│  Find Leads  │  [page title]                    │
│  Engage      │  [primary action / context]      │
│  Reddit      │                                  │
│  My Posts    │  [content cards / table]         │
│  Insights    │                                  │
│  Tune AI     │                                  │
│  Settings    │                                  │
├──────────────┴──────────────────────────────────┤
│ ACTIVITY STRIP (collapsed by default)            │
└─────────────────────────────────────────────────┘
```

Side nav (not the current top tabs) gives more horizontal room and signals "real product." Status pill in the top bar shows live state at a glance ("✅ Connected · 12 actions today").

---

## 6. Iconography

**Library:** [Lucide](https://lucide.dev) (free, open source, consistent, has React + plain SVG).

**Sizes:** 16, 20, 24. Stroke `1.5`. Match `currentColor` (so they tint to text/accent automatically).

**Don't use emoji as UI icons.** Emoji renders differently across OSes; brand collapses.

---

## 7. Motion

| Where | Effect | Duration |
|---|---|---|
| Buttons hover | `translateY(-1px)` + shadow | `--t-base` (0.2s) |
| Cards hover | border colour change | `--t-base` |
| Tab change | fade-in 6px translate | `--t-slow` (0.4s) |
| Loading spinner | 1s linear rotate | infinite |
| Number tick (stats) | count-up 0.6s ease-out | one-shot |

**Never animate opacity-only.** Movement (`transform`) reads as deliberate; opacity-only reads as buggy.

**Reduce motion:** respect `prefers-reduced-motion: reduce` — disable transforms, keep colour transitions.

---

## 8. Voice & tone (UI copy)

| Do | Don't |
|---|---|
| "We're scanning LinkedIn — about 30 seconds." | "Loading…" |
| "Your LinkedIn session expired. Reconnect →" | "Error 401: Unauthorized" |
| "No replies yet. Try a softer follow-up?" | "0 replies." |
| "Ready to send 3 messages today." | "Actions/day: 3" |
| "Pause for the weekend?" | "Disable scheduler" |
| "Saved." | "Save successful." |

**Sentences not labels.** Influentia talks like a thoughtful operator, not a control panel. The dashboard is a co-pilot, not an admin tool.

---

## 9. Brand decisions reference

| | |
|---|---|
| Logo wordmark | "Influentia" 800 weight, gradient `linear-gradient(135deg,#fff 20%,var(--accent2))` |
| Logo mark | Stylised `i` — to be commissioned, placeholder = single accent square `border-radius: 6px` with white "i" |
| Favicon | Same mark, 32×32 |
| Email signature | "— The Influentia team" (no parent attribution; brand stands alone — see [`POSITIONING.md`](./POSITIONING.md)) |
| Stripe receipt name | "Influentia Pro" |
| OG image | `landing/og.png` — wordmark on dark bg, accent glow lower-right |

---

## 10. Migration checklist (dashboard.html → this system)

- [ ] Add Inter `<link>` if missing.
- [ ] Replace `:root` block with the canonical block in §1.
- [ ] Find/replace `#2dd4bf` → `var(--accent)`; `#5eead4` → `var(--accent-hover)`; `rgba(45,212,191,*)` → matching `rgba(124,106,255,*)`.
- [ ] Replace ad-hoc `font-size: 11px / 12px / 13px` with the typography scale.
- [ ] Verify all buttons resolve to `.btn` variants.
- [ ] Replace any `<div>` empty states with the canonical `.empty` component.
- [ ] Replace any raw error text with the `.alert` component.
- [ ] Remove `Authentik Studio` lavender purples or other off-palette accents.

When done, the dashboard and landing page should screenshot side-by-side and look like one product.

---

_Design system is the cheapest brand investment. Every hour spent here saves a week of "this looks weird" debt later._
