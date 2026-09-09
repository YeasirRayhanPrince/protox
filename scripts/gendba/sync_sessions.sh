#!/usr/bin/env bash
#
# sync_sessions.sh -- keep Claude transcripts and memory on persistent storage.
#
# /users/<user> on this node is NOT NFS -- it sits on the node-local root filesystem
# (/dev/nvme1n1p3). So the session transcripts AND the memory files that stop us
# repeating past mistakes are destroyed when the experiment ends. /proj/pmoss-PG0 is
# the NFS project directory and survives.
#
# Runs continuously; syncing only at the end is a bet that we get a clean shutdown.
set -uo pipefail
SRC=/users/yrayhan/.claude/projects/-proj-pmoss-PG0-protox/
DEST=/proj/pmoss-PG0/protox/claude_sessions
INTERVAL=${1:-300}

mkdir -p "$DEST"
while true; do
  rsync -a --delete "$SRC" "$DEST/" 2>/dev/null \
    && echo "[$(date +%H:%M:%S)] synced $(du -sh "$DEST" 2>/dev/null | cut -f1)" \
    || echo "[$(date +%H:%M:%S)] sync FAILED"
  sleep "$INTERVAL"
done
