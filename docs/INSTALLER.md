# Influentia — Installer Build Spec
_How to ship Influentia as a clean install on macOS and Windows. **Two paths are documented: free (one-line bash) and signed (.dmg + .msi).** Pick the free path for soft launch; revisit the signed path if and only if data justifies the spend._

**Status:** spec — not yet executed.
**Owner:** Ermo.
**Estimated effort:** ~half a day for the free path; +1 focused day each for `.dmg` and `.msi` if you upgrade later.

---

## Path comparison (read this first)

| | Free path (recommended for soft launch) | Signed path (defer until justified) |
|---|---|---|
| **What customer does** | Opens Terminal, pastes one line: `curl -fsSL https://get.influentia.io/install.sh \| bash` | Double-clicks `.dmg`, drags to Applications |
| **Customer first impression** | "Devtool-style install" — familiar to anyone who's used Homebrew, rustup, Vercel CLI, Stripe CLI | "Premium polished SaaS" |
| **Gatekeeper warnings** | None (nothing to scan — it's bash + Python) | None (signed + notarised) |
| **Cost to ship** | **$0** | $99/yr Apple + $300–600/yr Windows EV |
| **Cost to maintain** | $0 | Yearly cert renewals |
| **Time to first build** | ~2 hours (script + R2 upload + test) | ~2 days (Briefcase setup + signing + notarising) |
| **Best for** | Technical B2B founders / agency owners / consultants — your actual ICP | Non-technical buyers (which you're not targeting at v1) |
| **When to upgrade** | If install completion rate < 70% in soft launch | Day 30+ after data shows the bash path under-converts |

**My recommendation:** ship the free path for soft launch. Watch install completion. Pay for signing only if data demands it.

The rest of this doc covers both paths. §A is the free path. §B is the original signed path (preserved for when you scale).

---

---

# §A — FREE PATH (one-line bash install, no signing)

This is the launch path. Total cost: $0. Total time: ~2 hours from spec to working install.

## A.1 The customer experience

```
1. Customer clicks "Download for Mac" on the success page.
2. Page shows a single curl command in a copy-button styled code block:

     curl -fsSL https://get.influentia.io/install.sh | bash

3. Customer pastes into Terminal, presses Enter.
4. Script runs (60–90 seconds), shows progress with friendly emojis/text.
5. At the end, it auto-opens the dashboard at http://localhost:5555/wizard
6. Wizard takes over. Customer never thinks about Terminal again.
```

Windows version: `irm https://get.influentia.io/install.ps1 | iex` (PowerShell one-liner). Identical UX.

## A.2 What the install script does

```bash
#!/usr/bin/env bash
# get.influentia.io/install.sh
set -e

INFLUENTIA_DIR="$HOME/.influentia"
INFLUENTIA_VERSION="1.0.0"

echo "→ Installing Influentia $INFLUENTIA_VERSION…"

# 1. Detect OS, install Python 3.11+ if missing
if ! command -v python3 &> /dev/null; then
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &> /dev/null; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install python@3.11
  else
    sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv
  fi
fi

# 2. Create install dir
mkdir -p "$INFLUENTIA_DIR"
cd "$INFLUENTIA_DIR"

# 3. Download Influentia source bundle from R2
curl -fsSL https://downloads.influentia.io/Influentia-$INFLUENTIA_VERSION.tar.gz | tar xz

# 4. Create venv + install deps
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet anthropic playwright requests python-dotenv pytz keyring
python -m playwright install chromium --with-deps

# 5. Register a launchd agent (macOS) so the server starts on login
cat > ~/Library/LaunchAgents/io.influentia.server.plist <<EOF
<?xml version="1.0"?>
<plist version="1.0">
<dict>
  <key>Label</key><string>io.influentia.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>$INFLUENTIA_DIR/venv/bin/python</string>
    <string>$INFLUENTIA_DIR/server.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$INFLUENTIA_DIR/logs/server_stdout.log</string>
  <key>StandardErrorPath</key><string>$INFLUENTIA_DIR/logs/server_stderr.log</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/io.influentia.server.plist

# 6. Open the wizard in browser
sleep 2
open http://localhost:5555/wizard

echo "✓ Influentia is running at http://localhost:5555"
```

Windows PowerShell version is structurally identical: detect Python (install via winget if missing), download source, create venv, install deps, register a Scheduled Task or Startup shortcut for the server, open browser. About 80 lines. Defender may show a one-time SmartScreen prompt — workable.

## A.3 Hosting `get.influentia.io`

Free, on Cloudflare Pages.

1. Create a new Cloudflare Pages project pointed at a small repo containing only `install.sh`, `install.ps1`, and an `index.html` that auto-detects OS and shows the right command.
2. Set custom domain `get.influentia.io` (free with Cloudflare DNS).
3. The source bundle (`Influentia-1.0.0.tar.gz`) lives in R2 at `downloads.influentia.io`. Free tier covers it.

## A.4 Updating the source bundle

When you ship a new version:
1. `tar -czf Influentia-1.1.0.tar.gz` of the relevant Python files.
2. Upload to R2 with `wrangler r2 object put downloads.influentia.io/Influentia-1.1.0.tar.gz --file=...`.
3. Bump `INFLUENTIA_VERSION` in `install.sh`.
4. Existing customers see an "update available" banner in the dashboard (per the auto-update spec in §B.10) and re-run the same one-liner — script detects the install dir and updates in place.

## A.5 What this path doesn't do

- ❌ No code-signing → if you ever ship binaries (compiled Python, etc.), Gatekeeper will warn. Solution: don't ship binaries. Stay interpreted.
- ❌ No Mac App Store or Microsoft Store distribution. (Both reject automation tools anyway.)
- ❌ No "drag to Applications" UX. The app lives at `~/.influentia`, accessed via the dashboard URL.

For the soft launch, none of these matter. If they ever start to, upgrade to §B.

## A.6 When to revisit (upgrade triggers)

Pay the $99 + build the `.dmg` only if:
- 🚨 **Soft launch install completion < 70%** — friction is killing conversion.
- 🚨 **3+ founders ask "is there a regular installer?"** — perception gap is real.
- 🚨 **You start selling to less-technical segments** (which would also mean revisiting POSITIONING.md).

If none of those is true at day 30, the $99/yr is pure overhead. Keep it.

---

# §B — SIGNED PATH (.dmg + .msi, deferred)

_Only execute this section if the upgrade triggers in A.6 fire. Until then, treat it as future reference._

## 0. Why this matters

Per `docs/UX_FLOW.md` §④, the current install path loses ~70% of customers between checkout and first run. Replacing the `bash install.sh` / `Install.bat` ritual with a signed `.dmg` and `.msi` is the single highest-leverage UX improvement available — bigger than any feature.

---

## 1. Tooling decision

**Use [BeeWare Briefcase](https://briefcase.readthedocs.io).**

Why Briefcase over PyInstaller / py2app / Wix Toolset:
- One config (`pyproject.toml`) builds for macOS, Windows, and Linux.
- Handles `.dmg` packaging on macOS and `.msi` on Windows out of the box.
- Bundles Python + dependencies into a self-contained app.
- Active maintenance, sane docs, MIT licence.
- Plays nicely with `playwright` (its bundled Chromium handled separately — see §6).

Trade-off: Briefcase apps are slightly larger than PyInstaller ones (~30 MB overhead). Worth it for the cross-platform ergonomics.

---

## 2. Prerequisites (obtain before building)

### macOS path
- [ ] **Apple Developer Program** enrolment — $99/year. Apply at https://developer.apple.com/programs/enroll/. Approval takes 24–48h.
- [ ] **Developer ID Application** certificate — generated in Xcode → Settings → Accounts → Manage Certificates → "+ Developer ID Application".
- [ ] **App-specific password** for notarisation — https://appleid.apple.com → Sign in → App-Specific Passwords.
- [ ] Xcode + command-line tools installed.

### Windows path
- [ ] **Windows code-signing certificate** — EV (Extended Validation) recommended for instant SmartScreen reputation. Sources: SSL.com, Sectigo, DigiCert. Cost $300–600/year. EV ships on a USB token.
- [ ] **Wix Toolset v3.11+** (Briefcase uses it under the hood for `.msi`).
- [ ] **Windows VM** or actual Windows machine — cross-compiling from macOS to a signed `.msi` is not supported. Either a Windows laptop, a Parallels VM, or a GitHub Actions Windows runner.

### Both paths
- [ ] Briefcase: `pip install briefcase` (in a fresh venv, not the runtime venv).
- [ ] An R2 bucket reachable at `downloads.influentia.io` (already exists as `outreach-pilot-downloads` — rename during the migration day).

---

## 3. Project layout (target)

Briefcase wants a specific structure. Refactor the repo once, then iterate.

```
linkedin_outreach/
├── pyproject.toml                ← Briefcase config (NEW)
├── src/
│   └── influentia/               ← Python package (move .py files here)
│       ├── __init__.py
│       ├── __main__.py           ← entry point: starts server, opens browser
│       ├── server.py
│       ├── main.py
│       ├── linkedin_client.py
│       ├── reddit_client.py
│       ├── reddit_signal.py
│       ├── message_ai.py
│       ├── state_manager.py
│       ├── ai_proxy.py
│       ├── config.py
│       └── resources/            ← bundled assets
│           ├── dashboard.html
│           ├── wizard.html
│           ├── icon.icns         ← macOS icon (1024×1024 .icns)
│           ├── icon.ico          ← Windows icon (256×256 .ico)
│           └── prompts/          ← copies of prompts/*.txt
└── tests/
```

**Migration plan (one-shot, an afternoon):**
1. `git checkout -b briefcase-migration`
2. `mkdir -p src/influentia`, `git mv` the .py files in.
3. Replace top-level imports (`from message_ai import …`) with relative (`from .message_ai import …`).
4. Update `server.py` to read `dashboard.html` from `importlib.resources` instead of the cwd.
5. Verify `python -m influentia` starts the server.
6. Commit.

---

## 4. `pyproject.toml`

```toml
[tool.briefcase]
project_name = "Influentia"
bundle = "studio.authentik"
version = "1.0.0"
url = "https://influentia.io"
license = "MIT"
author = "Authentik Studio"
author_email = "info@ermoegberts.com"

[tool.briefcase.app.influentia]
formal_name = "Influentia"
description = "LinkedIn + Reddit outreach autopilot. Local-first."
long_description = "Influentia finds your ideal clients on LinkedIn, reads what they post about, and writes personalised messages — runs entirely on your machine."
sources = ["src/influentia"]
test_sources = ["tests"]

requires = [
    "anthropic",
    "playwright",
    "requests",
    "python-dotenv",
    "pytz",
    "keyring",          # for license + cookie storage
]
test_requires = ["pytest"]

[tool.briefcase.app.influentia.macOS]
universal_build = true     # arm64 + x86_64
icon = "src/influentia/resources/icon"   # .icns auto-resolved
requires = ["std-nslog"]

[tool.briefcase.app.influentia.windows]
icon = "src/influentia/resources/icon"   # .ico auto-resolved

[tool.briefcase.app.influentia.linux]
# Optional. Skip until v1.1.
```

---

## 5. Entry point — `src/influentia/__main__.py`

The bundled app needs to start the server *and* open the user's default browser. macOS apps don't get a Terminal window; Windows users won't tolerate a stray cmd.exe.

```python
import threading
import webbrowser
import time
from .server import start_server
from .state_manager import load_state

PORT = 5555
URL  = f"http://localhost:{PORT}"

def open_browser():
    # Wait for server to bind, then route to wizard or dashboard
    time.sleep(0.8)
    state = load_state()
    target = "/wizard" if not state.get("onboarding", {}).get("completed_at") else "/"
    webbrowser.open(URL + target)

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    start_server(host="127.0.0.1", port=PORT)
```

---

## 6. Playwright Chromium — the gotcha

Playwright downloads ~150 MB of Chromium at first run by default. We can't ship that in the .dmg (size + signing nightmare). Two options:

### Option A — bundle Chromium (recommended)
Use Briefcase's `pre-build` hook or a custom step:

```bash
PLAYWRIGHT_BROWSERS_PATH=./build/chromium python -m playwright install chromium
```

Then point `linkedin_client.py` at the bundled path:

```python
import os, sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Running from packaged app
    base = Path(sys.executable).parent / "resources" / "chromium"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(base)
```

App size grows to ~250 MB but install is single-step.

### Option B — first-run download (not recommended)
On first launch, run `playwright install chromium` and show a "Setting up browser…" screen.

Trade-off: users see a 90-second blank screen on day one. Bad first impression. Avoid unless §A becomes intractable.

---

## 7. Code-signing — macOS

```bash
# Build the app
briefcase create macOS
briefcase build macOS

# Identify your signing identity
security find-identity -v -p codesigning
# Find: "Developer ID Application: Authentik Studio (TEAM_ID)"

# Sign and notarise
briefcase package macOS --identity "Developer ID Application: Authentik Studio (XXXXXXXXXX)"

# This produces: Influentia-1.0.0.dmg (signed + notarised)
```

Briefcase handles `xcrun notarytool` under the hood. First notarisation can take 5–15 minutes. Watch the console.

**If notarisation fails**, the most common cause is an unsigned binary inside the bundle. Run:
```bash
codesign --verify --verbose=4 build/influentia/macos/app/Influentia.app
spctl --assess --verbose=4 build/influentia/macos/app/Influentia.app
```

---

## 8. Code-signing — Windows

```powershell
# Build on Windows machine / VM
briefcase create windows
briefcase build windows

# Sign with EV cert (USB token must be plugged in)
briefcase package windows --identity "<thumbprint of cert>"

# Output: Influentia-1.0.0.msi
```

EV certs sign instantly with full SmartScreen reputation. OV certs need ~30 days of "reputation building" before SmartScreen stops warning users.

---

## 9. Distribution — upload to R2

```bash
# After successful build
cd ~/Desktop/linkedin_outreach
VERSION=$(cat VERSION)

# Upload macOS dmg
wrangler r2 object put outreach-pilot-downloads/Influentia-${VERSION}.dmg \
  --file=build/influentia/macos/Influentia-${VERSION}.dmg

# Upload Windows msi (from Windows machine)
wrangler r2 object put outreach-pilot-downloads/Influentia-${VERSION}.msi \
  --file=build/influentia/windows/Influentia-${VERSION}.msi

# Update "latest" pointers
wrangler r2 object put outreach-pilot-downloads/Influentia-latest.dmg \
  --file=build/influentia/macos/Influentia-${VERSION}.dmg
wrangler r2 object put outreach-pilot-downloads/Influentia-latest.msi \
  --file=build/influentia/windows/Influentia-${VERSION}.msi
```

Update `landing/success.html` to detect OS via User-Agent and serve the right link:

```js
const ua = navigator.userAgent;
const dl = /Win/.test(ua) ? 'Influentia-latest.msi'
        : /Mac/.test(ua) ? 'Influentia-latest.dmg'
        : 'Influentia-latest.dmg';   // default
document.getElementById('download').href =
  `https://downloads.influentia.io/${dl}`;
```

---

## 10. Auto-update — version handshake

The simplest possible mechanism (no Sparkle, no MSIX delta updates, no Squirrel — they're all overkill for our scale).

### On every server startup
```python
# src/influentia/updater.py
import requests
from . import __version__

LATEST_URL = "https://api.influentia.io/api/version/latest"

def check_for_update():
    try:
        r = requests.get(LATEST_URL, timeout=4)
        latest = r.json().get("version")
        if latest and latest != __version__:
            return latest
    except Exception:
        pass
    return None
```

### Worker endpoint (add to `worker/src/index.ts`)
```ts
app.get('/api/version/latest', c => c.json({
  version: '1.0.0',
  download_mac: 'https://downloads.influentia.io/Influentia-latest.dmg',
  download_win: 'https://downloads.influentia.io/Influentia-latest.msi',
  notes_url:    'https://influentia.io/changelog'
}));
```

### Dashboard banner (in `dashboard.html`)
If `check_for_update()` returns a version, show a non-intrusive banner:
```
A new version is available (1.1.0). [Download →]
```
Don't auto-download. Don't auto-install. Trust comes from the user being in control.

---

## 11. Keychain integration (license + LinkedIn cookie)

Replace `.env` and `.license.json` for sensitive material:

```python
import keyring

KEYRING_SERVICE = "influentia"

def store_license(key: str):
    keyring.set_password(KEYRING_SERVICE, "license_key", key)

def load_license() -> str | None:
    return keyring.get_password(KEYRING_SERVICE, "license_key")

def store_linkedin_cookie(li_at: str):
    keyring.set_password(KEYRING_SERVICE, "linkedin_li_at", li_at)
```

`keyring` uses macOS Keychain and Windows Credential Manager natively. No prompts, no friction — but the cookie sits encrypted at rest, which we can advertise as a privacy feature.

---

## 12. Smoke-test checklist

After every build, before uploading to R2:

- [ ] App launches on a clean VM (no dev environment).
- [ ] First run opens browser to `/wizard`.
- [ ] Wizard advances through all 5 screens.
- [ ] LinkedIn connect opens a real Playwright window.
- [ ] First Reddit scan completes and shows ≥ 1 signal.
- [ ] Dashboard loads.
- [ ] Closing the app cleanly stops the server (`launchctl` / Windows service exit).
- [ ] Re-launching shows the dashboard, not the wizard.
- [ ] `Activity Monitor` / `Task Manager` shows one Python process, not multiple.
- [ ] No Python tracebacks visible at any point.

---

## 13. Order of operations (one-day plan)

A focused person can ship the macOS path in a single working day if Apple Developer enrolment is already complete.

| Hour | Task |
|---|---|
| 0–1 | Refactor repo to `src/influentia/` layout. Verify `python -m influentia` runs. |
| 1–2 | Author `pyproject.toml`. `briefcase create macOS` succeeds. |
| 2–3 | Wire `__main__.py`, browser auto-open. Local debug build runs. |
| 3–4 | Bundle Playwright Chromium per §6A. App launches on a clean VM. |
| 4–5 | Code-sign + notarise. Verify with `spctl`. |
| 5–6 | Upload to R2. Update `landing/success.html` download link. |
| 6–7 | End-to-end smoke test from incognito → checkout → email → download → install → wizard → first lead. Fix anything that breaks. |
| 7–8 | Document anything new in `docs/HANDOFF.md`. Tag release. |

Windows path is a separate day (need EV cert + Windows VM).

---

## 14. What this spec doesn't cover

- **Linux** — `.deb` and `.AppImage` are easy via Briefcase but defer to v1.1. B2B founders are 95% on macOS/Windows.
- **Mac App Store / Microsoft Store** — both reject apps that automate other apps. Not our path.
- **Squirrel-style background updates** — over-engineering for our scale. Manual update banner is enough until 500+ paying customers.
- **Crash reporting** — add Sentry only if support load justifies it. For now, `logs/server_stderr.log` is enough.

---

_Once §1–13 are done, install conversion should jump from ~30% to ~85%. That's the target. If first-run telemetry shows we're below 85%, the flow has a hidden friction we missed — find it before adding any new features._
