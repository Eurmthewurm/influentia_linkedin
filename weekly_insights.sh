#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# weekly_insights.sh — Weekly pattern analysis & lead scoring update
#
# Runs on Sundays via com.authentik.linkedin-weeklyinsights.plist
# Reads state.json and outreach_log.txt and prints a summary.
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR="$(dirname "$0")"
LOG_FILE="$BASE_DIR/autopilot_run.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "═══════════════════════════════════════════════"
log "Weekly LinkedIn Outreach Insights"
log "═══════════════════════════════════════════════"

# ── Check server and run analytics if available ───────────────────────────────
BASE_URL="http://localhost:5555"
STATUS=$(curl -s --connect-timeout 5 "$BASE_URL/api/status")

if [ $? -eq 0 ] && [ -n "$STATUS" ]; then
    log "Server is up — pulling lead status summary..."
    SUMMARY=$(curl -s "$BASE_URL/api/status")
    echo "$SUMMARY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
leads = data.get('leads', {})
print('  Lead pipeline:')
for k, v in leads.items():
    print(f'    {k:<20} {v}')
" 2>/dev/null | tee -a "$LOG_FILE"
else
    log "Server is offline — reading state.json directly..."
fi

# ── Parse state.json for weekly stats ────────────────────────────────────────
python3 - "$BASE_DIR" "$LOG_FILE" << 'EOF'
import sys, json, os
from datetime import datetime, timedelta
from collections import Counter

base_dir = sys.argv[1]
log_file = sys.argv[2]
state_file = os.path.join(base_dir, "state.json")

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(log_file, "a") as f:
        f.write(line + "\n")

try:
    with open(state_file) as f:
        state = json.load(f)
    leads = state.get("leads", [])
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()

    status_counts = Counter(l.get("status") for l in leads)
    recent = [l for l in leads if l.get("added_at", "") >= week_ago]
    recent_connected = [l for l in recent if l.get("status") == "connected"]
    recent_replied = [l for l in recent if l.get("status") == "replied"]
    recent_booked = [l for l in recent if l.get("status") == "meeting_booked"]

    log(f"Weekly summary (last 7 days):")
    log(f"  New leads added:        {len(recent)}")
    log(f"  Connected:              {len(recent_connected)}")
    log(f"  Replied:                {len(recent_replied)}")
    log(f"  Meetings booked:        {len(recent_booked)}")
    log(f"Total pipeline:")
    for status, count in status_counts.most_common():
        log(f"  {status:<22} {count}")
except Exception as e:
    log(f"  Could not parse state.json: {e}")
EOF

log "═══════════════════════════════════════════════"
log "Weekly insights complete."
