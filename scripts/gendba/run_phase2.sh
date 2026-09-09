#!/usr/bin/env bash
#
# run_phase2.sh -- add `anytime` and `db2advis` across all three benchmarks.
#
# Waits for phase 1 (run_all.sh: DSB + TPC-H x2) to finish, then sweeps the two
# additional ISE algorithms that are actually usable:
#
#   anytime   budget_MB + max_runtime_minutes  -- the only algorithm here bounded by
#             TIME as well as storage, a task dimension the corpus otherwise lacks
#   db2advis  budget_MB + try_variations_seconds -- one-shot advisor plus randomised
#             variation, a different search shape from greedy grow/shrink
#
# Not included, and why:
#   dexter       adapter that shells out to the Ruby `dexter` tool; not installed
#   cophy_input  returns [] -- it emits MIP solver input, not a configuration, so
#                there is nothing to apply or measure
#
# 2 algorithms x 6 budgets x 2 widths x 4 benchmark-states = 96 episodes.
set -uo pipefail
REPO=/proj/pmoss-PG0/protox
OUT=$REPO/gendba_records
LOGD=/mnt/protox/logs
PGBIN=/mnt/protox/pg15/bin
export PGUSER=admin PGPASSWORD=password
export GENDBA_PARALLEL=1 GENDBA_ISOLATION=dedicated_cluster_sequential
source /mnt/protox/miniconda3/etc/profile.d/conda.sh
conda activate ise
cd "$REPO"

eps() { ls "$OUT/episodes" 2>/dev/null | grep -c '[.]json$'; }

# Wait on phase 1's COMPLETION MARKER, not on process absence.
#
# Process-absence is an unsafe guard and it has already burned us: killing a harvest
# to apply a fix made queue_dsb.sh conclude the previous stage had finished, and it
# swapped the cluster to DSB mid-repair. A marker only appears when run_all.sh
# genuinely reaches the end.
PHASE1_LOG=/mnt/protox/logs/run_all.log
echo "[phase2] waiting for phase 1 completion marker in $PHASE1_LOG ..."
while true; do
  if grep -q "ALL DONE" "$PHASE1_LOG" 2>/dev/null; then
    echo "[phase2] phase 1 reported ALL DONE"; break
  fi
  if ! pgrep -f 'run_all[.]sh' >/dev/null; then
    # phase 1 died without finishing -- do NOT take the cluster; a half-finished
    # phase 1 needs a human decision, not an automatic successor.
    echo "[phase2] ABORT: run_all.sh is gone but never reported ALL DONE." >&2
    echo "[phase2] phase 1 must be resumed or explicitly abandoned first." >&2
    exit 1
  fi
  sleep 120
done
echo "[phase2] starting at $(date -Is), corpus = $(eps) episodes"

load_snapshot () {
  local pgd=/data/protox/pgdata_ise
  $PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
  rm -rf $pgd; mkdir -p -m 0700 $pgd
  tar xf /data/protox/data/"$1" -C $pgd --strip-components 1
  sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
  echo "port = 5492" >> $pgd/postgresql.conf
  $PGBIN/pg_ctl -D $pgd -l /data/protox/pg_ise.log -w -t 600 start >/dev/null
  echo "[phase2] $2 up"
}

stage () {   # $1 label  $2 bench  $3 queries  $4 select  $5 timeout
  local label=$2_$1 log
  log="$LOGD/harvest_p2_${label}.log"
  local before; before=$(eps)
  echo "[phase2] === $label starting $(date -Is), corpus $before ==="
  python scripts/gendba/harvest.py --benchmarks "$2" --algorithms anytime,db2advis \
    --budgets 50,100,250,500,1000,2500 --widths 1,2 \
    --queries "$3" --query-select "$4" --query-timeout "$5" --adjudicate-k 5 \
    --out "$OUT" > "$log" 2>&1 &
  local hp=$!
  # stall threshold 120m: anytime can legitimately search for 10 minutes before it
  # even starts verifying, and DSB relaxation episodes have run to 88m
  "$REPO/scripts/gendba/monitor.sh" "$log" "$OUT/episodes" 24 120 "p2_$label" \
      > "$LOGD/monitor_p2_${label}.log" 2>&1 &
  local mp=$!
  wait $hp; local rc=$?
  kill $mp 2>/dev/null || true
  echo "[phase2] === $label done rc=$rc, corpus $(eps) ==="
}

load_snapshot job_base.tgz        "JOB pk_only";        stage pk_only    job  25 head          15
load_snapshot dsb_sf10_base.tgz   "DSB pk_only";        stage pk_only    dsb  67 one-per-shape 30
load_snapshot tpch_sf10_base.tgz  "TPC-H pk_only";      stage pk_only    tpch 22 head          30
load_snapshot tpch_sf10.tgz       "TPC-H configured";   stage configured tpch 22 head          30

echo "[phase2] ALL DONE $(date -Is): $(eps) episodes total"
