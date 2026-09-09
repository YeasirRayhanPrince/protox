#!/usr/bin/env bash
#
# deadline_guard.sh -- make sure everything of value is on /proj before the node dies.
#
# The CloudLab node is released 2026-09-10 11:59 PM EST = 2026-09-11 04:59 UTC.
# Only /proj/pmoss-PG0 survives. /mnt, /data and /users are all destroyed, which means
# the postgres build, the conda envs, the 46 GB of snapshots, every harvest log, and
# the Claude transcripts + memory files all disappear.
#
# At CUTOFF (default 3h before expiry) this:
#   1. stops harvesting cleanly, so no episode is half-written
#   2. re-gates the whole corpus with the CURRENT validator and restores anything that
#      only failed against an older one
#   3. copies the harvest logs off /mnt (they are provenance and they are small)
#   4. syncs Claude transcripts + memory off the node-local disk
#   5. writes a final report next to the corpus
#
# Run it detached; it sleeps until the cutoff. Safe to run early — it only acts at the
# cutoff, and `--now` forces the finalisation immediately.
set -uo pipefail

REPO=/proj/pmoss-PG0/protox
OUT=$REPO/gendba_records
LOGD=/mnt/protox/logs
CUTOFF_UTC="2026-09-11 01:59:00"
FORCE=0
[ "${1:-}" = "--now" ] && FORCE=1

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $*"; }

if [ $FORCE -eq 0 ]; then
  target=$(date -u -d "$CUTOFF_UTC" +%s)
  now=$(date -u +%s)
  wait_s=$(( target - now ))
  if [ "$wait_s" -gt 0 ]; then
    log "sleeping ${wait_s}s until cutoff $CUTOFF_UTC UTC ($(echo "scale=1; $wait_s/3600" | bc)h)"
    sleep "$wait_s"
  fi
fi

log "=== FINALISING (cutoff reached or forced) ==="

# 1. stop harvesting cleanly -------------------------------------------------
log "stopping harvests..."
"$REPO/scripts/gendba/stop_harvest.sh" || true
for p in $(pgrep -f 'chain_phase2\.sh' 2>/dev/null || true) \
         $(pgrep -f 'run_all\.sh' 2>/dev/null || true) \
         $(pgrep -f 'udo_harvest\.py' 2>/dev/null || true); do
  kill "$p" 2>/dev/null && log "  stopped $p"
done
sleep 5

# 2. re-gate the corpus with the CURRENT validator ---------------------------
# Records quarantined by a long-running harvest hold whatever validator that process
# loaded at start; the gate has gained checks since. Anything that passes now belongs
# in the corpus.
log "re-gating quarantine with the current validator..."
source /mnt/protox/miniconda3/etc/profile.d/conda.sh 2>/dev/null && conda activate ise 2>/dev/null
restored=0
for f in "$OUT"/quarantine/*.json; do
  case "$f" in *failures.json) continue;; esac
  [ -e "$f" ] || continue
  if python3 "$REPO/scripts/gendba/validate.py" "$f" >/dev/null 2>&1; then
    mv "$f" "$OUT/episodes/" && rm -f "$f.failures.json"
    restored=$((restored+1))
  fi
done
log "  restored $restored record(s) from quarantine"

log "re-gating all episodes..."
python3 "$REPO/scripts/gendba/validate.py" "$OUT/episodes" \
  > "$OUT/final_validation.txt" 2>&1 || true
tail -1 "$OUT/final_validation.txt" | sed 's/^/  /'

# 3. harvest logs are provenance and live on /mnt ---------------------------
log "copying harvest logs to /proj..."
mkdir -p "$OUT/logs"
cp -f "$LOGD"/*.log "$LOGD"/*.status "$OUT/logs/" 2>/dev/null || true
log "  $(ls "$OUT/logs" 2>/dev/null | wc -l) log files, $(du -sh "$OUT/logs" 2>/dev/null | cut -f1)"

# 4. Claude transcripts + memory off the node-local disk --------------------
log "syncing Claude session state..."
rsync -a --delete /users/yrayhan/.claude/projects/-proj-pmoss-PG0-protox/ \
      "$REPO/claude_sessions/" 2>/dev/null \
  && log "  $(du -sh "$REPO/claude_sessions" 2>/dev/null | cut -f1)" \
  || log "  SYNC FAILED"

# 5. final report -----------------------------------------------------------
log "writing final report..."
python3 "$REPO/scripts/gendba/report.py" --records "$OUT" \
        --json "$OUT/final_report.json" > "$OUT/final_report.txt" 2>&1 || true
grep -E "CORPUS|episodes|tool_sft|preference|cardinality" "$OUT/final_report.txt" 2>/dev/null \
  | head -8 | sed 's/^/  /'

log "=== DONE — everything of value is under $OUT ==="
log "episodes: $(ls "$OUT/episodes" 2>/dev/null | grep -c '[.]json$')"
log "NOTE: /mnt, /data and /users are lost at 04:59 UTC. Snapshots are NOT copied"
log "      (46 GB); scripts/cloudlab/provision.sh rebuilds a machine in ~3h."
