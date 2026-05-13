# Influentia

LinkedIn + Reddit outreach autopilot for B2B founders. Local-first — runs on your machine, on your IP, with your data.

> **Customer?** Visit **[influentia.io](https://influentia.io)** to start a free trial.
> **Operator / contributor?** Read **[`docs/HANDOFF.md`](./docs/HANDOFF.md)** first — that's the canonical brief.

---

## Quick start (operator)

```bash
# 1. Activate the venv
source venv/bin/activate

# 2. Start the dashboard
python server.py
# → opens at http://localhost:5555

# 3. Hot-reload code without restarting
curl -X POST http://localhost:5555/api/reload
```

---

## Documentation map

The four canonical docs live in [`docs/`](./docs). Anything else is archived.

| Doc | Read when |
|---|---|
| [`docs/BLUEPRINT.md`](./docs/BLUEPRINT.md) | Making a strategic decision (brand, pricing, model, priorities). |
| [`docs/HANDOFF.md`](./docs/HANDOFF.md) | Resuming work in a new session. State of the system, last changes, next action. |
| [`docs/UI.md`](./docs/UI.md) | Touching anything visual (landing, dashboard, emails). Tokens + components. |
| [`docs/UX_FLOW.md`](./docs/UX_FLOW.md) | Changing onboarding, error states, or any user-facing copy. |
| [`DEPLOY.md`](./DEPLOY.md) | Deploying the Cloudflare Worker / D1 / Pages / R2 layer. |

Older content (the previous five overlapping docs) is preserved in [`docs/archive/`](./docs/archive) for historical reference but is no longer current.

---

## Repo layout

```
docs/                  Canonical docs (BLUEPRINT, HANDOFF, UI, UX_FLOW)
docs/archive/          Old README/IMPROVEMENTS/GUIDE/SETUP/HANDOFF
landing/               Marketing site (deployed to influentia.io via Cloudflare Pages)
worker/                Cloudflare Worker — Stripe webhooks + license API
prompts/               Editable AI message templates (hot-reloaded)
logs/                  Server logs and historical run reports
linkedin_outreach/     (legacy nested folder — to be consolidated)
server.py              Local dashboard server (localhost:5555)
dashboard.html         Single-file frontend
main.py                LinkedIn automation orchestrator
linkedin_client.py     Playwright wrapper
reddit_client.py       Reddit JSON + OAuth
reddit_signal.py       Reddit scan + AI scoring
message_ai.py          Claude calls for message generation
state_manager.py       Reads/writes state.json
ai_proxy.py            Claude API proxy
config.py              Reads .env
state.json             Local data (NOT in git)
.env                   Secrets (NOT in git)
VERSION                Current version
```

---

## License

MIT. Provided as-is. © 2026 Ermo Egberts.

---

_If you're an AI agent continuing this work, start with [`docs/HANDOFF.md`](./docs/HANDOFF.md). Don't re-read everything — those four docs are the canon._
