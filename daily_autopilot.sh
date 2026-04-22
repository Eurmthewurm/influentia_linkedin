#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# daily_autopilot.sh — LinkedIn Outreach daily automation sequence
#
# Runs directly on your Mac (bypasses any sandbox restrictions).
# Schedule with launchd using com.authentik.linkedin-autopilot.plist
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL="http://localhost:5555"
LOG_FILE="$(dirname "$0")/autopilot_run.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ── Step 1: Check server ──────────────────────────────────────────────────────
log "Checking if LinkedIn Outreach server is running..."
STATUS=$(curl -s --connect-timeout 5 "$BASE_URL/api/status")
if [ $? -ne 0 ] || [ -z "$STATUS" ]; then
    log "ERROR: Server is not running at $BASE_URL. Aborting."
    exit 1
fi
log "Server is up."

# ── Helper: run a task and wait for completion ────────────────────────────────
run_task() {
    local COMMAND="$1"
    local LABEL="$2"
    log "Starting: $LABEL..."

    RESPONSE=$(curl -s "$BASE_URL/api/run/$COMMAND")
    log "  → $RESPONSE"

    # Poll until not running (max 10 minutes)
    for i in $(seq 1 120); do
        sleep 5
        POLL=$(curl -s "$BASE_URL/api/status")
        RUNNING=$(echo "$POLL" | python3 -c "import sys,json; t=json.load(sys.stdin).get('task',{}); print(t.get('running', False))" 2>/dev/null)
        if [ "$RUNNING" = "False" ]; then
            log "  ✓ $LABEL done."
            return 0
        fi
    done

    log "  ⚠ $LABEL timed out after 10 minutes."
    return 1
}

# ── Step 2: Run automation sequence ──────────────────────────────────────────
log "═══════════════════════════════════════════════"
log "Starting daily LinkedIn automation sequence"
log "═══════════════════════════════════════════════"

run_task "find_leads"  "Find new leads"
run_task "withdraw"    "Withdraw old requests"
run_task "scan_posts"  "Smart scan for posts"
run_task "connect"     "Send connection requests"
run_task "scan"        "Check connections"
run_task "send"        "Send messages"
run_task "reply"       "Handle replies"
run_task "followup"    "Send followups"

# ── Step 3: Summary ───────────────────────────────────────────────────────────
log "Fetching summary..."
LOGS=$(curl -s "$BASE_URL/api/logs?since=0")
STATE_FILE="$(dirname "$0")/state.json"
SUMMARY_FILE="$(dirname "$0")/daily_summary.log"
TODAY=$(date '+%Y-%m-%d')

LEADS=$(echo "$LOGS"    | python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('new lead' in m.lower() or 'lead found' in m.lower() for m in msgs))" 2>/dev/null || echo "?")
CONNECTS=$(echo "$LOGS" | python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('connection request sent' in m.lower() for m in msgs))" 2>/dev/null || echo "?")
MESSAGES=$(echo "$LOGS" | python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('message sent' in m.lower() for m in msgs))" 2>/dev/null || echo "?")
COMMENTS=$(echo "$LOGS" | python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('queued' in m.lower() or 'comment' in m.lower() for m in msgs))" 2>/dev/null || echo "?")
WITHDRAWN=$(echo "$LOGS"| python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('withdrew' in m.lower() or 'withdrawn' in m.lower() for m in msgs))" 2>/dev/null || echo "?")
REPLIES=$(echo "$LOGS"  | python3 -c "import sys,json; msgs=[e['msg'] for e in json.load(sys.stdin)]; print(sum('reply sent' in m.lower() or 'auto-reply' in m.lower() for m in msgs))" 2>/dev/null || echo "?")

# Read pipeline totals from state.json
PIPELINE=$(python3 -c "
import json, sys
try:
    with open('$STATE_FILE') as f:
        state = json.load(f)
    leads = state.get('leads', {})
    from collections import Counter
    c = Counter(l.get('status') for l in (leads.values() if isinstance(leads, dict) else leads))
    print(f\"pending={c.get('pending',0)} requested={c.get('requested',0)} connected={c.get('connected',0)} messaged={c.get('messaged',0)} replied={c.get('replied',0)} booked={c.get('meeting_booked',0)} total={sum(c.values())}\")
except Exception as e:
    print(f'error={e}')
" 2>/dev/null || echo "unavailable")

# Write clean daily summary
{
echo "════════════════════════════════════════════════════"
echo "  LinkedIn Autopilot — Daily Report: $TODAY"
echo "════════════════════════════════════════════════════"
echo ""
echo "  TODAY'S ACTIVITY"
echo "  ─────────────────────────────────────────────────"
echo "  New leads found:        $LEADS"
echo "  Connection requests:    $CONNECTS"
echo "  Old requests withdrawn: $WITHDRAWN"
echo "  Messages sent:          $MESSAGES"
echo "  Replies sent:           $REPLIES"
echo "  Comments queued:        $COMMENTS  ← review in Engage tab"
echo ""
echo "  PIPELINE TOTALS"
echo "  ─────────────────────────────────────────────────"
python3 -c "
s='$PIPELINE'
pairs=dict(p.split('=') for p in s.split())
labels=[('pending','Pending (not contacted)'),('requested','Requests sent'),('connected','Connected'),('messaged','Messaged'),('replied','Replied'),('booked','Meetings booked'),('total','TOTAL')]
for k,label in labels:
    v=pairs.get(k,'?')
    print(f'  {label:<28} {v}')
" 2>/dev/null
echo ""
echo "  Run at: $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════"
echo ""
} | tee -a "$SUMMARY_FILE" | tee -a "$LOG_FILE"
