#!/usr/bin/env bash
# Deploy one tested commit to the EC2 host. Runs ON the host, piped over SSH
# by .github/workflows/ci-cd.yml:
#
#   ssh host 'bash -s' -- <app_dir> <commit_sha> < deploy/remote_deploy.sh
#
# Order matters: wait for any running scan to finish, snapshot queue+history
# together, fast-forward to the exact tested commit, rebuild, verify.
set -euo pipefail

APP_DIR="${1:?usage: remote_deploy.sh <app_dir> <commit_sha>}"
TARGET_SHA="${2:?usage: remote_deploy.sh <app_dir> <commit_sha>}"
SERVICE="steve_jobs_agent"
BACKUP_DIR="${HOME}/backups"
BACKUPS_TO_KEEP=10
# The producer watchdog is 3600 s; wait slightly longer than one full phase.
BUSY_WAIT_SECONDS=3900
BUSY_POLL_SECONDS=30

log() { printf '[deploy] %s\n' "$*"; }

cd "$APP_DIR"

# 1. Never recreate the container mid-cycle: a killed consumer between a
#    Telegram send and its history write would re-send that alert.
waited=0
while docker compose top "$SERVICE" 2>/dev/null \
        | grep -qE 'scrapers\.orchestrator|notifications\.dispatcher'; do
    if (( waited >= BUSY_WAIT_SECONDS )); then
        log "A scan cycle is still running after ${waited}s; aborting deploy."
        exit 1
    fi
    log "Scan cycle in progress; waiting (${waited}s so far)."
    sleep "$BUSY_POLL_SECONDS"
    waited=$(( waited + BUSY_POLL_SECONDS ))
done

# 2. Snapshot queue and history together (they are only consistent as a pair).
mkdir -p "$BACKUP_DIR"
backup="${BACKUP_DIR}/state-$(date -u +%Y%m%dT%H%M%SZ).tgz"
backup_paths=(data)
[[ -f config/prompts/user_profile.md ]] && backup_paths+=(config/prompts/user_profile.md)
tar czf "$backup" "${backup_paths[@]}"
log "State snapshot: $backup"
ls -1t "$BACKUP_DIR"/state-*.tgz | tail -n +"$(( BACKUPS_TO_KEEP + 1 ))" | xargs -r rm --

# 3. Move to exactly the commit CI tested. --ff-only refuses to clobber any
#    local edits on the host instead of silently merging them.
previous_sha="$(git rev-parse HEAD)"
git fetch --quiet origin main
git merge --ff-only --quiet "$TARGET_SHA"
log "Code: ${previous_sha:0:7} -> $(git rev-parse --short HEAD)"

# 4. Rebuild and restart. The scheduler runs one cycle immediately on start.
docker compose up -d --build
docker image prune -f >/dev/null

# 5. Verify the container stayed up past startup.
sleep 20
if ! docker compose ps --status running --services | grep -qx "$SERVICE"; then
    log "Container is not running after deploy. Recent logs:"
    docker compose logs --tail 50 "$SERVICE" || true
    log "To roll back on the host: git reset --hard ${previous_sha} && docker compose up -d --build"
    exit 1
fi

docker compose logs --tail 15 "$SERVICE"
log "Deploy of $(git rev-parse --short HEAD) succeeded."
