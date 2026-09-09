#!/usr/bin/env bash
#
# monitor.sh -- active health monitor for a harvest.
#
# Waiting on process exit detects COMPLETION but is blind to a STALL, which is the
# failure mode that actually happens here: a hung query with no statement_timeout kept
# the TPC-H harvest "running" for 81 minutes while it produced zero episodes. A
# process burning CPU on a hung query looks identical to a healthy one unless you
# watch a progress signal.
#
# Watches four things and writes a status line each poll:
#   1. liveness   -- is the driver process alive at all
#   2. progress   -- is the episode count advancing (the signal that actually matters)
#   3. errors     -- tracebacks / EPISODE ERROR / FAIL in the log
#   4. downstream -- any query running far longer than one unit of work should take
#
# Exit codes: 0 finished · 2 stalled · 3 errors · 4 driver died early
#
# Usage: monitor.sh <log> <episodes-dir> <target-count> [stall-minutes] [label]
set -uo pipefail

LOG=${1:?log path}
EPDIR=${2:?episodes dir}
TARGET=${3:?target episode count}
STALL_MIN=${4:-25}
LABEL=${5:-harvest}
POLL=60
PGBIN=/mnt/protox/pg15/bin
STATUS=/mnt/protox/logs/monitor_${LABEL}.status
export PGUSER=${PGUSER:-admin} PGPASSWORD=${PGPASSWORD:-password}

# grep -c prints its count AND exits 1 when that count is zero, so a `|| echo 0`
# fallback appends a SECOND zero and every arithmetic test downstream blows up.
# Capture the value and default only when it is genuinely empty.
count_eps() { local n; n=$(ls "$EPDIR" 2>/dev/null | grep -c '[.]json$'); echo "${n:-0}"; }
count_err() { local n; n=$(tr '\r' '\n' < "$LOG" 2>/dev/null | grep -acE 'Traceback|EPISODE ERROR|FAIL '); echo "${n:-0}"; }
longest_query() {
  local n
  n=$($PGBIN/psql -h localhost -p 5492 -d benchbase -tAc \
      "SELECT coalesce(max(extract(epoch from now()-query_start))::int,0)
       FROM pg_stat_activity WHERE datname='benchbase' AND state='active'
         AND pid<>pg_backend_pid();" 2>/dev/null | head -1 | tr -d ' ')
  echo "${n:-?}"
}

START=$(date +%s)
BASE=$(count_eps)
LAST=$BASE
LAST_CHANGE=$START
FIRST_SEEN=0

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$STATUS"; }
say "monitor start: label=$LABEL target=$TARGET baseline=$BASE stall_after=${STALL_MIN}m"

while true; do
  sleep "$POLL"
  now=$(date +%s)
  n=$(count_eps); errs=$(count_err); lq=$(longest_query)
  alive=no; pgrep -f 'harvest[.]py' >/dev/null && alive=yes

  if [ "$n" -ne "$LAST" ]; then LAST=$n; LAST_CHANGE=$now; fi
  done_n=$(( n - BASE ))
  idle_min=$(( (now - LAST_CHANGE) / 60 ))
  el_min=$(( (now - START) / 60 ))

  say "$LABEL ${done_n}/${TARGET} eps | alive=$alive | idle=${idle_min}m | longest_query=${lq}s | errors=$errs"

  if [ "$FIRST_SEEN" -eq 0 ] && [ "$done_n" -ge 1 ]; then
    FIRST_SEEN=1
    say "FIRST_EPISODE_OK $LABEL after ${el_min}m"
  fi
  if [ "$done_n" -ge "$TARGET" ]; then
    say "DONE $LABEL: $done_n episodes in ${el_min}m"; exit 0
  fi
  if [ "$alive" = no ]; then
    say "PROCESS_GONE $LABEL at ${done_n}/${TARGET} after ${el_min}m"; exit 4
  fi
  if [ "$idle_min" -ge "$STALL_MIN" ]; then
    say "STALLED $LABEL: no new episode for ${idle_min}m at ${done_n}/${TARGET} (longest query ${lq}s)"
    exit 2
  fi
  if [ "$errs" -gt 0 ]; then
    say "ERRORS $LABEL: $errs error lines at ${done_n}/${TARGET}"; exit 3
  fi
done
