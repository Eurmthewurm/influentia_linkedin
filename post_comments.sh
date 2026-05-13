#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# post_comments.sh — Post approved LinkedIn comments
#
# Runs 1 hour after daily_autopilot.sh to give time to review comments.
# Scheduled via com.authentik.linkedin-postcomments.plist
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL="http://localhost:5555"
LOG_FILE="$(dirname "$0")/autopilot_run.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ── Check server ──────────────────────────────────────────────────────────────
STATUS=$(curl -s --connect-timeout 5 "$BASE_URL/api/status")
if [ $? -ne 0 ] || [ -z "$STATUS" ]; then
    log "ERROR: Server is not running. Skipping post_comments."
    exit 1
fi

log "Posting approved LinkedIn comments..."

RESPONSE=$(curl -s "$BASE_URL/api/run/post_comments")
log "  → $RESPONSE"

# Poll until done (max 10 minutes)
for i in $(seq 1 120); do
    sleep 5
    POLL=$(curl -s "$BASE_URL/api/status")
    RUNNING=$(echo "$POLL" | python3 -c "import sys,json; t=json.load(sys.stdin).get('task',{}); print(t.get('running', False))" 2>/dev/null)
    if [ "$RUNNING" = "False" ]; then
        log "  ✓ post_comments done."
        break
    fi
done

log "Comment posting complete."
