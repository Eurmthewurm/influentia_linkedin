# LinkedIn Outreach Automation — Complete Usage Guide

## Quick Start (30-second version)

```bash
cd ~/Desktop/linkedin_outreach
python main.py status     # see your dashboard
python main.py preview    # dry run — see what WOULD happen
python main.py scan       # message already-accepted connections
```

---

## Setup Checklist

Before running anything, confirm:

1. **Python packages installed:**
   ```bash
   pip install linkedin-api anthropic openpyxl
   ```

2. **config.py filled in:**
   - `ANTHROPIC_API_KEY` — your Claude API key
   - `LINKEDIN_LI_AT_COOKIE` — your LinkedIn session cookie (see below)
   - `YOUR_NAME`, `YOUR_COMPANY`, `YOUR_GOAL`, `YOUR_GOAL_LINK`
   - `YOUR_OFFERING` — detailed description of what you sell

3. **Leads file ready:**
   - `AU_Mining_Staffing_Leads.xlsx` in the same folder
   - Must have LinkedIn URLs in column H

### How to get your LinkedIn session cookie

1. Open LinkedIn in Chrome
2. Press F12 → Application tab → Cookies → linkedin.com
3. Find the cookie named `li_at`
4. Copy its value into `config.py`

**Important:** This cookie expires every ~3 months. If the script stops working, refresh the cookie.

---

## All Commands

Open Terminal, then:

```bash
cd ~/Desktop/linkedin_outreach
```

### `python main.py status`
**What it does:** Shows your dashboard — how many leads are in each state, active conversations, meetings booked.
**When to use:** Anytime you want to check progress. Safe to run as often as you like, makes no changes.

### `python main.py preview`
**What it does:** Dry run. Shows exactly what messages would be sent, to whom, without actually sending anything.
**When to use:** Before your first real run, or after editing prompts to see how messages look.

### `python main.py scan`
**What it does:** Goes through your leads, finds ones already connected to you, and sends them a personalized first message.
**When to use:** The very first time you run the system, to message people who already accepted your connection requests.

### `python main.py connect`
**What it does:** Sends connection requests to leads that haven't been contacted yet. Respects the daily limit (15/day by default).
**When to use:** Daily, to grow your connection pipeline.

### `python main.py check`
**What it does:** Checks which connection requests were accepted, then auto-sends personalized first messages to new connections.
**When to use:** A few hours after sending connection requests, or let `loop` handle it.

### `python main.py reply`
**What it does:** Checks your LinkedIn inbox for replies from prospects, generates AI responses, classifies conversation status (interested, not interested, meeting booked, ongoing).
**When to use:** Multiple times a day, or let `loop` handle it.

### `python main.py followup`
**What it does:** Sends a follow-up message to prospects who were messaged but haven't replied after X days (default: 3 days).
**When to use:** Daily, or let `loop` handle it.

### `python main.py add <linkedin-url>`
**What it does:** Adds a single new lead by LinkedIn profile URL. Fetches their profile data automatically.
**When to use:** When you find a new prospect you want to add to your pipeline.

Example:
```bash
python main.py add https://www.linkedin.com/in/john-doe-12345/
```

### `python main.py loop`
**What it does:** Runs `check` + `reply` + `followup` automatically every 4 hours (configurable). Keeps running until you stop it.
**When to use:** When you want hands-off automation.

---

## Typical Daily Workflow

### Morning
```bash
python main.py status          # check the dashboard
python main.py connect         # send new connection requests
```

### Afternoon
```bash
python main.py check           # find new acceptances, send first messages
python main.py reply           # respond to any replies
python main.py followup        # nudge non-responders
```

### Or just set it and forget it
```bash
python main.py connect         # morning: send connection requests
python main.py loop            # then let it run — it handles check/reply/followup
```

---

## How to Stop

- **Single command (scan, connect, check, reply, followup):** It finishes on its own after processing all leads.
- **Loop mode:** Press `Ctrl+C` in Terminal. It stops immediately and safely.
- **Any command:** `Ctrl+C` always works as an emergency stop. No data is lost — state is saved after each action.

---

## Editing Messages (Prompt Files)

The AI-generated messages are controlled by text files in the `prompts/` folder. Edit these anytime with any text editor.

### `prompts/first_message.txt`
Controls the opening icebreaker sent after a connection is accepted. This is where you define tone, style, and personalization rules.

### `prompts/follow_up.txt`
Controls the follow-up message for prospects who haven't replied. Keep it short and non-pushy.

### `prompts/context.txt`
Controls the AI's behavior during ongoing conversations (replies, objection handling, meeting booking). This is the "personality" of your AI sales agent.

### Tips for editing prompts
- Use `{prospect_name}`, `{prospect_company}`, `{prospect_headline}`, etc. — these get auto-filled
- Use `{offering}` to inject your product description
- Run `python main.py preview` after editing to see how your changes look
- You don't need to restart anything — prompts are loaded fresh each time

### Available variables in first_message.txt
```
{prospect_name}              — Full name
{prospect_headline}          — LinkedIn headline
{prospect_location}          — Location
{prospect_sector}            — Industry/sector
{prospect_company}           — Company name
{prospect_posts}             — Their 3 most recent LinkedIn posts
{prospect_current_experience} — Current role
{prospect_past_experiences}  — Previous roles
{prospect_volunteer}         — Volunteer work
{prospect_skills}            — Top skills
{prospect_languages}         — Languages spoken
{prospect_education}         — Education history
{prospect_certifications}    — Certifications
{prospect_accomplishments}   — Honors/awards
{prospect_recommendations}   — Recommendation excerpts
{prospect_additional}        — Profile summary
```

---

## Adding New Leads

### Option 1: Add one at a time
```bash
python main.py add https://www.linkedin.com/in/someone/
```

### Option 2: Add to the Excel file
1. Open `AU_Mining_Staffing_Leads.xlsx`
2. Add a new row with at minimum: Name (column B), Title (C), Company (D), LinkedIn URL (H)
3. Save the file
4. The next time you run `connect`, new leads will be picked up automatically

---

## Safety Settings (config.py)

These are already set conservatively. **Do not increase them.**

| Setting | Default | What it does |
|---------|---------|-------------|
| `MAX_CONNECTION_REQUESTS_PER_DAY` | 15 | Hard cap on daily connection requests |
| `MAX_MESSAGES_PER_DAY` | 20 | Hard cap on daily messages (all types) |
| `DELAY_BETWEEN_REQUESTS_SECONDS` | 90 | Minimum seconds between any LinkedIn action |
| `POLL_INTERVAL_HOURS` | 4 | How often `loop` checks for updates |
| `FOLLOW_UP_AFTER_DAYS` | 3 | Days before sending a follow-up |
| `MAX_FOLLOW_UPS` | 1 | Max follow-ups per lead (0 = disabled) |

### Built-in safety features (automatic, no config needed)
- Random delay jitter (±30%) so timing looks human
- Session cooldowns: pauses 3-8 minutes every 5 actions
- 1-in-8 chance of a random 30-90 second "scroll pause"
- Human-like browser headers
- Daily counters that reset at midnight
- State saved after every action (crash-safe)

---

## File Structure

```
linkedin_outreach/
├── config.py              ← Your credentials and settings
├── main.py                ← Main script (all commands)
├── linkedin_client.py     ← LinkedIn API wrapper (safety-hardened)
├── message_ai.py          ← Claude AI message generation
├── leads_loader.py        ← Excel file reader
├── state_manager.py       ← Tracks lead lifecycle (JSON)
├── prompts/
│   ├── context.txt        ← AI conversation behavior
│   ├── first_message.txt  ← Icebreaker prompt
│   └── follow_up.txt      ← Follow-up prompt
├── AU_Mining_Staffing_Leads.xlsx  ← Your leads
├── state.json             ← Auto-generated state (don't edit)
├── outreach_log.txt       ← Activity log
├── requirements.txt       ← Python dependencies
├── .gitignore             ← Keeps secrets out of git
└── GUIDE.md               ← This file
```

---

## Troubleshooting

### "CHALLENGE" or authentication error
Your LinkedIn session cookie has expired. Get a fresh `li_at` cookie from your browser and update `config.py`.

### "Too many requests" or rate limit error
You've hit LinkedIn's limits. Stop the script, wait 24 hours, then resume. The script tracks where it left off.

### Messages not sending
Run `python main.py status` to see the state of each lead. Common causes:
- Daily message limit reached (resets at midnight)
- Lead is in `requested` state (waiting for acceptance)
- Lead already messaged (check state.json)

### Script crashes mid-run
No problem. State is saved after each action. Just run the same command again — it picks up where it left off.

### Want to reset everything
Delete `state.json` and `outreach_log.txt`. The script starts fresh on next run.

---

## Important Warnings

1. **Never run multiple instances at the same time.** One Terminal window, one command.
2. **Don't increase the safety limits.** LinkedIn bans are permanent.
3. **Refresh your session cookie** if the script suddenly stops working (every ~3 months).
4. **Review messages with `preview`** before your first real run.
5. **Back up `state.json`** occasionally — it tracks your entire pipeline.
