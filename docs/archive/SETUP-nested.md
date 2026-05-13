# LinkedIn Outreach Automation — Setup Guide

## What This Does

1. **`python main.py connect`** — Sends connection requests to your 20 leads (max 15/day, rate-limited)
2. **`python main.py check`** — Detects accepted connections and sends each a unique AI-written first message
3. **`python main.py reply`** — Checks for replies and sends AI-generated contextual follow-ups
4. **`python main.py loop`** — Runs check + reply automatically every 4 hours (leave it running)
5. **`python main.py status`** — See a live dashboard of all lead statuses + active conversations

---

## Step 1 — Prerequisites

Make sure you have Python 3.9+ installed. Then install dependencies:

```bash
pip install -r requirements.txt
```

---

## Step 2 — Get Your LinkedIn Session Cookie

1. Open **LinkedIn** in Chrome
2. Press **F12** → go to the **Application** tab
3. Click **Cookies** → **https://www.linkedin.com**
4. Find the cookie named **`li_at`** and copy its value
5. Paste it into `config.py` → `LINKEDIN_LI_AT_COOKIE`

> ⚠️ **Important:** This cookie expires after ~1 year or when you log out. If the script stops working, refresh it.

---

## Step 3 — Fill in config.py

Open `config.py` and fill in every `REPLACE_ME` field:

| Field | What to put |
|-------|-------------|
| `ANTHROPIC_API_KEY` | Your Claude API key from console.anthropic.com |
| `LINKEDIN_LI_AT_COOKIE` | The `li_at` cookie value from Step 2 |
| `YOUR_NAME` | Your first name (appears in messages) |
| `YOUR_COMPANY` | Your company name |
| `YOUR_GOAL` | e.g. `"book a quick 20-minute call"` |
| `YOUR_GOAL_LINK` | Your Calendly / booking link |
| `YOUR_OFFERING` | Describe what you do (see Offering Tips below) |

### Offering Tips (crucial for good messages)
Follow the Kakiyo rule: **be specific, not generic**.

❌ Bad: `"We help businesses grow"`

✅ Good:
```
We help Australian mining and staffing companies generate high-quality B2B leads
using AI-powered LinkedIn outreach. Unlike generic automation tools, our approach
personalises every single message based on real research about the prospect.
We typically see 30-40% reply rates vs the 5-15% industry average.
Clients book 2-5 qualified calls per day on autopilot without writing a single
message themselves. We've helped recruitment founders in Perth, Sydney and Brisbane
reduce their prospecting time from 3 hours/day to zero.
```

---

## Step 4 — Copy the Excel File

Make sure `AU_Mining_Staffing_Leads.xlsx` is in the **same folder** as these scripts.

---

## Step 5 — Run It

### Day 1: Send connection requests
```bash
python main.py connect
```
This sends up to 15 requests. The script automatically rate-limits with ~90s+ gaps between each to mimic human behaviour.

### Every few hours: Check for acceptances + send first messages
```bash
python main.py check
```
Run this manually, or use `loop` mode below.

### Check for replies and respond
```bash
python main.py reply
```

### Hands-free mode (recommended)
```bash
python main.py loop
```
Leave this running in a terminal. It polls LinkedIn every 4 hours, sends messages, handles replies, and logs everything.

### Check progress anytime
```bash
python main.py status
```

---

## Safety Rules (Do NOT change these)

| Setting | Value | Why |
|---------|-------|-----|
| Max connection requests/day | 15 | LinkedIn flags accounts that send 20+ |
| Delay between actions | 90s + random jitter | Mimics human typing speed |
| No connection note | (intentional) | Notes reduce acceptance rate |
| Poll interval | 4 hours | Avoids LinkedIn's bot detection |

---

## What the AI Writes

### First Message (after connection accepted)
The AI reads the prospect's LinkedIn profile, recent posts, job history, and your offering — then writes a **unique** icebreaker for each person. Example output:

> *"Hey Tamara, your work bridging AI and geoscience at Fortescue caught my eye. Most mining teams still prospect manually. Is AI-driven outreach something Fortescue has explored?"*

### Follow-up Replies
The AI continues the conversation naturally, handling:
- Questions about pricing, how it works, integrations
- Objections ("we already have a solution", "not the right time")
- Scheduling — books the meeting when the prospect is ready
- Graceful exits — stops following up if clearly not interested

---

## Files Created

| File | Purpose |
|------|---------|
| `state.json` | Tracks every lead's status and full conversation history |
| `outreach_log.txt` | Full activity log (requests sent, messages, errors) |

---

## Troubleshooting

**"Authentication failed"** → Your `li_at` cookie expired. Repeat Step 2.

**"Rate limit exceeded"** → LinkedIn throttled the account. Wait 24h and lower `MAX_CONNECTION_REQUESTS_PER_DAY` to 10.

**Messages sound generic** → Improve `YOUR_OFFERING` in `config.py`. More specific = better personalisation.

**ImportError: No module named 'linkedin_api'** → Run `pip install -r requirements.txt` again.
