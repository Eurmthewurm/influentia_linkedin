# LinkedIn Outreach Autopilot

Automated LinkedIn prospecting for B2B founders and consultants. Find your ideal clients, connect with them intelligently, and nurture conversations at scale—all powered by Claude AI.

## What It Does

LinkedIn Outreach Autopilot automates your entire outreach workflow: it finds prospects matching your ICP, sends personalized connection requests, follows up with contextual messages, and replies to interested prospects. The dashboard lets you monitor all activity and tweak settings in real time.

## Requirements

- Python 3.8+
- macOS or Linux (Windows via WSL2)
- Claude API key (free trial available)
- Brave Search API key (free tier works)
- 2-3 posts on your LinkedIn profile (optional, but recommended for better results)

## Setup

### 1. Quick Install (Recommended)

```bash
bash install.sh
```

This script will:
- Detect your OS and install Python if needed
- Create a virtual environment
- Install all dependencies (anthropic, playwright, etc.)
- Install the Chromium browser for automation
- Bootstrap your `.env` file

### 2. Manual Setup

```bash
# Create virtualenv
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install anthropic playwright requests python-dotenv pytz

# Install browser
playwright install chromium
```

### 3. Configure API Keys

Copy `.env.example` to `.env` and fill in:

```bash
ANTHROPIC_API_KEY=sk-ant-...         # from https://console.anthropic.com
BRAVE_SEARCH_API_KEY=...              # from https://api.search.brave.com
YOUR_NAME=Your Name                   # for personalization
YOUR_COMPANY=Your Company
YOUR_GOAL=Your goal (booking link)
```

## How to Use

### Start the Dashboard

```bash
source venv/bin/activate              # activate virtualenv if not already
python server.py
```

Then open: **http://localhost:5555**

### The Workflow

1. **Connect LinkedIn** (first time only)
   - Click "Connect" in the dashboard
   - A browser opens—log into your LinkedIn account
   - Session is saved forever; you never log in again

2. **Set Your ICP** (Ideal Customer Profile)
   - Go to "Find Leads" tab
   - Configure: job titles, industries, locations
   - The system will auto-refill your pipeline

3. **Let It Run Automatically**
   - Every 9 AM: Full routine (find leads, connect, check acceptances, send messages)
   - 1 PM & 6 PM: Quick checks for replies
   - Monitor the dashboard for activity and results

4. **Approve & Engage**
   - Conversations appear in real time
   - Approve comments before they post (Engage tab)
   - Mark leads as "warm" if they show buying interest
   - Switch to manual mode if you want to take over a conversation

## Key Features

- **AI-Powered Personalization**: Every message is contextual, pulling from LinkedIn profiles and posts
- **Smart Follow-ups**: Remembers conversation history, knows when to push vs. back off
- **Safety First**: LinkedIn-safe delays, human-looking behavior, no spam patterns
- **Campaign Tracking**: Organize leads into named campaigns
- **Insights & Analytics**: Weekly patterns, funnel stats, "hot" lead identification
- **Post Queue**: Generate and schedule LinkedIn posts to build credibility before outreach
- **Comment Intelligence**: Auto-find high-value posts to comment on, approve before posting

## Daily Limits (Configurable)

- 15 connection requests/day (LinkedIn's soft limit)
- 20 messages/day (start conservative, increase after 1 week)
- 5 comments/day (safety limit)

Adjust in the Settings tab.

## File Structure

```
├── server.py                 # Web dashboard & API
├── main.py                   # Outreach orchestration
├── linkedin_client.py        # Browser automation (Playwright)
├── message_ai.py             # Claude message generation
├── state.json                # Persistent lead database
├── prompts/                  # Editable message templates
├── .env                      # Your API keys & identity
├── install.sh                # One-line setup
└── README.md                 # This file
```

## Common Tasks

### Add a Single Lead by LinkedIn URL

```bash
python main.py add https://www.linkedin.com/in/johndoe/
```

### Preview Messages (Dry Run)

```bash
python main.py preview
```

See what messages would be sent without actually sending them.

### View Logs

```bash
tail -f outreach_log.txt
```

### Manually Trigger a Step

From the dashboard, click any action button (Connect, Check, Send, etc.).

## Troubleshooting

### "Claude API key is missing"
→ Open Settings → Account in the dashboard. Paste your key from https://console.anthropic.com

### "Could not reach Claude"
→ Check your internet connection. If rate-limited, wait a few minutes.

### "No LinkedIn profile found"
→ Make sure the LinkedIn URL is correct and the profile is public. Some profiles are private.

### "Session expired, please reconnect"
→ Click "Connect" in the dashboard again. Takes 30 seconds.

### Can't connect on Linux with headless desktop?
→ Set environment variable: `DISPLAY=:99 python server.py` (or use X11 forwarding)

## Tips for Success

1. **Warm Up First**: Have 2-3 posts live on LinkedIn before you start. Buyers check your profile when you connect.

2. **Start Conservative**: Send 5-10 connection requests your first day. Increase slowly to 15/day after a week.

3. **Read the Knowledge Base**: Fill in your origin story, process, and brand voice. This powers personalization.

4. **Monitor Replies Daily**: Set a time each day to check the Active Conversations tab. Reply manually to early prospects.

5. **Adjust Your ICP**: After 50 connections, review replies and update your ICP based on who's engaging.

6. **Use Manual Mode**: For hot prospects, switch to manual mode so you take over the conversation.

## Support

Issues? Check:
- The Activity Log (bottom of dashboard)
- The outreach_log.txt file
- The onboarding wizard tips (Settings → Setup Status)

## Privacy & Data

**What stays on your machine:**
- `state.json` — lead database, conversation history, all prospect data
- `linkedin_profile/` — your LinkedIn browser session (treat like a password)
- `.env` — API keys and personal details

**What gets sent externally:**
- **Claude API** — prospect profile data (name, title, posts, experience) is sent per message to generate personalized outreach
- **Brave Search** — job title + location search queries (no personal prospect data)

**Nothing else leaves your machine.** No analytics, no telemetry, no cloud sync.

To delete everything: remove `state.json` (leads + conversations) and `linkedin_profile/` (LinkedIn session).

---

## ⚠️ LinkedIn Terms of Service

LinkedIn's Terms of Service prohibit automated activity on their platform. **Using this tool carries risk — including potential account restriction or suspension.**

This tool is designed to minimize that risk:
- Stays well below LinkedIn's daily activity thresholds
- Uses human-like delays between actions (90+ seconds)
- Requires manual approval for comments before posting
- Withdraws stale requests automatically to keep your ratio healthy

**Recommended practices:**
- Start with 5–10 connection requests/day, not the maximum
- Don't run automation while actively browsing LinkedIn yourself
- If you see a CAPTCHA or account warning — stop for 48 hours and lower your limits
- Keep 2–3 posts live on your profile so connections look legitimate

**By using this software, you accept full responsibility for how it interacts with your LinkedIn account.** The authors provide this as-is with no warranty or liability for account actions.

---

## FAQ

**Q: Is my LinkedIn account safe?**
A: Lower risk than most automation tools due to conservative limits and human-like behavior — but no automation is zero-risk. Start slow, monitor, and reduce limits if you see any warnings.

**Q: What happens to my data if I stop using it?**
A: Everything is stored locally. Delete `state.json` and `linkedin_profile/` and nothing persists anywhere.

**Q: Can I run it on a VPS or server?**
A: Yes, but LinkedIn's session is tied to that machine's IP. Switching machines or IPs may trigger a session check.

**Q: The messages sound generic. How do I fix it?**
A: Fill in the Knowledge Base section in Settings — origin story, process, brand voice. The more specific you are, the more specific the messages.

---

## License

MIT License — you can use, modify, and distribute this software freely.

Copyright © 2025 — provided as-is, no warranty expressed or implied.

---

Good luck. Start small, measure everything, iterate on what works.
