#!/usr/bin/env bash
#
# stop_harvest.sh -- stop running harvests and monitors safely.
#
# Doing this inline is a trap: `pgrep -f harvest.py` also matches the shell running
# the command, because the pattern appears in that shell's own command line. That has
# killed this session's shell twice mid-edit. Keeping the patterns inside a script
# file means they never appear in the caller's argv.
set -uo pipefail
SELF=$$
killed=0
for pat in 'harvest\.py' 'gendba/monitor\.sh' 'queue_tpch\.sh' 'queue_dsb\.sh'; do
  for p in $(pgrep -f "$pat" 2>/dev/null || true); do
    [ "$p" = "$SELF" ] && continue
    [ "$p" = "$PPID" ] && continue
    if kill "$p" 2>/dev/null; then
      echo "stopped $p ($pat)"
      killed=$((killed+1))
    fi
  done
done
sleep 2
echo "stopped $killed process(es)"
for pat in 'harvest\.py' 'gendba/monitor\.sh'; do
  pgrep -f "$pat" >/dev/null 2>&1 && echo "WARNING still alive: $pat"
done
exit 0
