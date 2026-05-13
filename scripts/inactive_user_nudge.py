"""
Automated daily check for inactive Influentia beta users.
Sends personalized "are you stuck?" emails to users who signed up >48h ago
with zero activity (no scans sent).
"""
import json
import subprocess
import sys

WORKER_URL = "https://outreach-pilot-api-production.plain-king-ead0.workers.dev"
RESEND_API_KEY = ""  # Will be loaded from worker secret
FROM_EMAIL = "hello@influentia.io"

def check_inactive_users():
    """Fetch licenses, find inactive ones, return list to nudge."""
    cmd = f'curl -s "{WORKER_URL}/api/admin/licenses"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if not result.stdout:
        print("[ERROR] Could not reach worker")
        return []
    
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid response: {result.stdout[:200]}")
        return []
    
    licenses = data.get("licenses", [])
    
    # Filter: inactive (signed up 2+ days ago, never seen, not expired)
    inactive = [
        l for l in licenses 
        if l.get("inactive") 
        and l.get("tier") in ("trial", "beta", "active")
        and l.get("email")
        and "@" in l.get("email", "")
    ]
    
    return inactive

def send_nudge_email(email, key_masked, days_since_signup):
    """Send a personalized nudge email to the inactive user."""
    # Check if we already nudged this user today (state file)
    import os
    state_file = "/tmp/influentia_nudge_state.json"
    nudged_today = set()
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                nudged_today = set(json.load(f))
        except:
            pass
    
    # Already nudged this cycle (24h window)
    nudge_key = f"{email}:{days_since_signup}"
    if nudge_key in nudged_today:
        print(f"[SKIP] Already nudged {email}")
        return False
    
    subject = "Need a hand getting started?"
    body = f"""
<html><body>
<p>Hey there,</p>
<p>I'm the founder of Influentia. I noticed you signed up <strong>{days_since_signup} days ago</strong> but haven't run a scan yet.</p>
<p>Usually this means one of two things:</p>
<ol>
<li><strong>Setup got stuck</strong> — the install process confused you, or the app won't open.</li>
<li><strong>ICP is hard to define</strong> — you're not sure what keywords to use.</li>
</ol>
<p><strong>Reply to this email</strong> and tell me which one. I'll personally walk you through the fix in 5 minutes.</p>
<p>You've got <strong>14 days</strong> to try the full product — no credit card required during trial. I want you to see results before that timer runs out.</p>
<p>Your license key (in case you lost it): {key_masked}</p>
<p>Cheers,<br>Erm</p>
</body></html>
"""
    
    # Call Resend API
    resend_cmd = f'''curl -s -X POST "https://api.resend.com/emails" \\
      -H "Authorization: Bearer {RESEND_API_KEY}" \\
      -H "Content-Type: application/json" \\
      -d '{{"from":"Influentia <{FROM_EMAIL}>","to":["{email}"],"subject":"{subject}","html":{json.dumps(body)}}}'
'''
    
    result = subprocess.run(resend_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            resp = json.loads(result.stdout)
            if "id" in resp:
                print(f"[SENT] Nudge email to {email}")
                nudged_today.add(nudge_key)
                with open(state_file, "w") as f:
                    json.dump(list(nudged_today), f)
                return True
        except:
            print(f"[ERROR] Bad response: {result.stdout}")
    
    print(f"[FAILED] Could not send to {email}: {result.stderr}")
    return False

if __name__ == "__main__":
    print("=== INFLUENTIA INACTIVE USER CHECK ===")
    
    inactive = check_inactive_users()
    
    if not inactive:
        print("No inactive users to nudge today.")
        sys.exit(0)
    
    print(f"\nFound {len(inactive)} inactive user(s):")
    sent = 0
    for user in inactive:
        email = user.get("email")
        days = user.get("days_since_signup", "?")
        key = user.get("key_masked", "unknown")
        print(f"\n  - {email} (day {days}, key ends {key[-4:]})")
        
        if send_nudge_email(email, key, days):
            sent += 1
    
    print(f"\n=== SUMMARY: {sent}/{len(inactive)} nudges sent ===")
