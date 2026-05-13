# Influentia — Handoff Brief
_Paste this into a new chat to continue without re-reading everything._

---

## What is this

**Influentia** — a local LinkedIn + Reddit outreach autopilot built for Ermo Egberts / Authentik Studio (B2B content agency helping founders build LinkedIn personal brand + inbound leads).

- Runs at `http://localhost:5555`
- All code lives at `/Users/ermoegberts/Desktop/linkedin_outreach/`
- Backed up at `https://github.com/Eurmthewurm/influentia` (private)
- Server managed by launchd: `~/Library/LaunchAgents/io.influentia.server.plist`
- Uses venv Python: `/Users/ermoegberts/Desktop/linkedin_outreach/venv/bin/python`
- Server logs: `~/Desktop/linkedin_outreach/logs/server_stdout.log` / `server_stderr.log`

---

## Key files

| File | Purpose |
|------|---------|
| `server.py` | Python HTTP server (~3050 lines). All /api/* endpoints. |
| `dashboard.html` | Single-file frontend. All JS inline. Tabs: Dashboard, Find Leads, Engage, Reddit, My Posts, Settings, Tune AI, Insights. |
| `reddit_client.py` | Reddit public JSON API (read) + OAuth (post comments). No credentials needed for scanning. |
| `reddit_signal.py` | Reddit Signal (scan + AI score) + Engage (draft/approve/post comments). |
| `state_manager.py` | Loads/saves state.json — single source of truth for all data. |
| `ai_proxy.py` | Calls Claude API. |
| `config.py` | Reads .env, exposes YOUR_NAME, YOUR_OFFERING etc. |
| `main.py` | LinkedIn automation (scan, connect, message, follow-up). |
| `state.json` | NOT in git. Contains all leads, signals, comments. Persists on disk. |
| `.env` | NOT in git. API keys and personal config. |

---

## Architecture

```
dashboard.html (browser)
    ↕ fetch /api/*
server.py (localhost:5555, SimpleHTTPRequestHandler)
    ├── reads dashboard.html from disk on every GET /
    ├── imports modules at request time
    └── state.json (persisted JSON, never in git)
```

Hot reload (no restart needed):
```bash
curl -s -X POST http://localhost:5555/api/reload
```

---

## Reddit feature (built in last session)

### How it works
1. POST /api/reddit/scan → scan_signals(state) in reddit_signal.py
2. Searches 12 subreddits with 17 ICP queries via Reddit public JSON API
3. Claude Haiku scores each post 1-10. Only scores ≥ 4 kept.
4. Shown as Leadverse-style cards: score badge, subreddit pill, title, excerpt, keyword tags
5. "Generate Reply" drafts helpful non-promotional comment → "Copy Draft & Open Reddit"

### ICP (Authentik Studio)
- Who: B2B founders, consultants, agency owners needing LinkedIn content / thought leadership
- Subreddits: b2bmarketing, marketing, consulting, entrepreneur, smallbusiness, startups, linkedin, content_marketing, freelance, agency, SaaS
- Queries: LinkedIn content pain, personal brand, thought leadership, not getting clients, B2B lead gen, ghostwriter, no time for content

### Critical bug fixed
state.json had reddit_settings: { subreddits: [], queries: [] } — empty arrays silently
overrode defaults (dict.get("key", default) doesn't fall back on [], only on missing key).
Fixed in reddit_signal.py:
```python
subreddits = settings.get("subreddits") or DEFAULT_SUBREDDITS
queries    = settings.get("queries") or DEFAULT_QUERIES
```

### Server LaunchAgent situation
Old com.authentik.linkedin-outreach.plist kept respawning stale code.
Moved to ~/Desktop/linkedin_outreach/disabled_plists/
Now only io.influentia.server.plist manages the server.

Restart cleanly:
```bash
launchctl unload ~/Library/LaunchAgents/io.influentia.server.plist
sleep 2 && launchctl load ~/Library/LaunchAgents/io.influentia.server.plist
```

---

## Git workflow
```bash
cd ~/Desktop/linkedin_outreach
git add -A && git commit -m "message" && git push
```
Gitignored: .env, state.json, venv/, logs/, *.plist, disabled_plists/

---

## What's working
- LinkedIn autopilot (scan, connect, message, follow-up, replies)
- Reddit Signal — scans, AI scores, Leadverse-style cards with score badge
- Reddit Engage — draft comment, copy & open Reddit
- Live scanning animation (subreddits tick off as it scans)
- Stats bar (subreddits monitored, signals stored, last scan)
- All tabs visible (blank tabs bug fixed — unclosed div in settings tab)
- GitHub private backup at github.com/Eurmthewurm/influentia

## Ideas for next session
- "Turn into LinkedIn post" button on Reddit signals — drafts LinkedIn post about that pain point
- Pain trend report — after scan, shows which topics came up most (content intelligence)
- Reddit reply monitoring — inbox checker for replies to our comments
- Scheduled auto-scan — daily Reddit scan without manual click
- Better signal filtering / search

---

## About Ermo
- Email: info@ermoegberts.com
- GitHub: Eurmthewurm
- Service: Authentik Studio — LinkedIn thought leadership + personal brand for B2B founders
- Tool: Influentia (this codebase)
- Goal: Find B2B founders on Reddit expressing pain about LinkedIn / not getting clients → engage helpfully → get leads
