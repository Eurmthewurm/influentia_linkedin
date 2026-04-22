# Influentia — Beta Tester Quickstart

Thanks for testing. This should take about 10 minutes end-to-end.

## What you need before you start

- A computer (macOS or Windows).
- A LinkedIn account you actively use.
- Two free API keys — you'll grab these during setup.
- A license key — start your 14-day free trial at **https://influentia.io**. Your license key will appear on the success page; keep it handy.

## Step 1 — Install (one time)

**macOS**
1. Unzip the folder somewhere you'll find again (Desktop is fine).
2. Double-click `Install.command`.
3. The Terminal window will show progress. When it says "Setup complete", you can close it.

_If macOS blocks the file with "can't be opened because it is from an unidentified developer", right-click → Open → Open. That's a one-time prompt._

**Windows**
1. Unzip the folder somewhere you'll find again (Desktop is fine).
2. Double-click `Install.bat`.
3. If Python isn't installed, the script will open the download page. Install Python 3.11, check "Add Python to PATH" during install, then re-run `Install.bat`.
4. When it says "Setup complete", close the window.

## Step 2 — Launch

- **macOS:** double-click `start.command`
- **Windows:** double-click `Start.bat`

Your browser opens at `http://localhost:5555`. On first launch you'll be asked to paste your license key — this is shown on the success page right after checkout, and also in your Stripe receipt email. After that, a setup wizard will appear.

## Step 3 — The wizard (first run)

The wizard has 6 short steps:

1. **Welcome** — read the heads-up about LinkedIn's terms of service.
2. **API keys** — paste two keys:
   - **Claude** — get it at https://console.anthropic.com (API Keys → Create Key). Starts with `sk-ant-`.
   - **Brave Search** — free at https://api.search.brave.com. No credit card.
3. **You** — your name, company, booking link (Calendly etc.), and what you want prospects to do ("book a quick call" is fine).
4. **What you sell** — a short paragraph about your offering. Be specific. Generic input = generic AI messages.
5. **Your story** — two short paragraphs: why you started, and how you talk. This shapes the AI's tone on every message.
6. **Connect LinkedIn** — click the button, a Chrome window opens, log into LinkedIn once. The session is saved locally so you never have to log in again.

You can edit everything later in Settings.

## Step 4 — Your first real run

On the dashboard:

1. Go to **Find Leads** and review the default Ideal Client Profile. Edit the job titles/industries/locations to match who you want to reach.
2. Click **Find leads now**. Give it 5–10 minutes — it searches and scrapes profiles with human-like pauses.
3. Go to the **Dashboard** tab. You'll see new leads in the pipeline.
4. Click **Connect** to send connection requests (max 10/day on your first week — you can raise it later).
5. Check back tomorrow. Accepted requests show up automatically; the AI drafts first messages for you to review.

## Things to know

- **Start slow.** Send 5–10 connection requests per day for the first week. Ramp up only if you see zero LinkedIn warnings.
- **Don't browse LinkedIn in another tab while automation is running.** LinkedIn gets suspicious when the same account does two things at once.
- **If the dashboard shows a red banner** ("LinkedIn security challenge detected"), automation auto-pauses for 24 hours. Open LinkedIn in your regular browser, resolve the challenge (usually a CAPTCHA), then click Resume in the dashboard.
- **Your data stays on your computer.** Leads, messages, and your LinkedIn session are stored in local files. Prospect profile data is sent to Claude to generate messages (this is disclosed in the wizard).

## When something breaks

Click the **💬 Feedback** button (bottom-right of the dashboard). It packages your recent logs + your note so you can send it to me in one click. This is the single most helpful thing you can do as a beta tester.

If the whole app won't start:
- Make sure you ran `Install.command` / `Install.bat` first.
- Delete the `venv/` folder and run install again — it'll do a clean setup.

## Known limits of this beta

- English-language LinkedIn only (works worldwide, but prompts are in English).
- One LinkedIn account per install.
- No CRM integrations yet.
- macOS and Windows; Linux works via `install.sh` but less tested.

## Billing notes

- Your 14-day trial starts when you enter your card on the landing page. After 14 days your card is charged $29/month. Cancel anytime from Settings → "Manage subscription" (opens the Stripe customer portal), or email support before day 14 and I'll cancel for you.
- If the trial expires, the dashboard still loads — your leads, messages, and LinkedIn session stay intact — but the Connect/Send/Find Leads buttons are disabled until you upgrade.

Questions, bugs, weird LinkedIn behavior — the Feedback button is your friend.

Thanks again.
