#!/usr/bin/env bash
#
# chain_phase2.sh -- start phase 2 once TPC-H configured has actually finished.
#
# Guards on the RESULT (episode count reaching the target), not on process absence.
# Process-absence has burned us twice: killing a harvest to apply a fix made a queued
# successor conclude the previous stage was complete and seize the cluster mid-repair.
#
# Phase 2 = anytime + db2advis across the benchmark-states that are viable:
#   job pk_only · dsb pk_only · tpch configured
# tpch pk_only is deliberately excluded -- on a PK-only TPC-H base a single query (Q20)
# is 100% of total estimated cost, so no candidate can clear extend's 0.3% improvement
# threshold and every search returns empty. That decision is pending with the user; if
# they want it, add it back here.
set -uo pipefail
REPO=/proj/pmoss-PG0/protox
OUT=$REPO/gendba_records
LOGD=/mnt/protox/logs
PGBIN=/mnt/protox/pg15/bin
TARGET_TPCH=42
export PGUSER=admin PGPASSWORD=password
export GENDBA_PARALLEL=1 GENDBA_ISOLATION=dedicated_cluster_sequential

tpch_eps() { ls "$OUT/episodes" 2>/dev/null | grep -c '^tpch.*[.]json$'; }
eps()      { ls "$OUT/episodes" 2>/dev/null | grep -c '[.]json$'; }

echo "[chain] waiting for TPC-H configured to reach $TARGET_TPCH episodes ..."
while true; do
  n=$(tpch_eps)
  if [ "$n" -ge "$TARGET_TPCH" ]; then
    echo "[chain] TPC-H reached $n episodes"; break
  fi
  if ! pgrep -f 'harvest[.]py' >/dev/null; then
    echo "[chain] harvest.py gone at $n/$TARGET_TPCH tpch episodes." >&2
    echo "[chain] Proceeding anyway ONLY if most of the stage completed." >&2
    if [ "$n" -lt $((TARGET_TPCH - 6)) ]; then
      echo "[chain] ABORT: too few episodes ($n) -- needs a human look." >&2
      exit 1
    fi
    break
  fi
  sleep 120
done

source /mnt/protox/miniconda3/etc/profile.d/conda.sh
conda activate ise
cd "$REPO"

load_snapshot () {
  local pgd=/data/protox/pgdata_ise
  $PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
  rm -rf $pgd; mkdir -p -m 0700 $pgd
  tar xf /data/protox/data/"$1" -C $pgd --strip-components 1
  sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
  echo "port = 5492" >> $pgd/postgresql.conf
  $PGBIN/pg_ctl -D $pgd -l /data/protox/pg_ise.log -w -t 600 start >/dev/null
  echo "[chain] $2 up"
}

stage () {   # $1 label  $2 bench  $3 queries  $4 select  $5 timeout
  local label=$2_$1 log before
  log="$LOGD/harvest_p2_${label}.log"
  before=$(eps)
  echo "[chain] === p2 $label starting $(date -Is), corpus $before ==="
  python scripts/gendba/harvest.py --benchmarks "$2" --algorithms anytime,db2advis \
    --budgets 50,100,250,500,1000,2500 --widths 1,2 \
    --queries "$3" --query-select "$4" --query-timeout "$5" --adjudicate-k 5 \
    --out "$OUT" > "$log" 2>&1 &
  local hp=$!
  "$REPO/scripts/gendba/monitor.sh" "$log" "$OUT/episodes" 24 120 "p2_$label" \
      > "$LOGD/monitor_p2_${label}.log" 2>&1 &
  local mp=$!
  wait $hp; local rc=$?
  kill $mp 2>/dev/null || true
  echo "[chain] === p2 $label done rc=$rc, corpus $(eps) ==="
}

load_snapshot job_base.tgz       "JOB pk_only";      stage pk_only    job  25 head          15
load_snapshot dsb_sf10_base.tgz  "DSB pk_only";      stage pk_only    dsb  67 one-per-shape 30
load_snapshot tpch_sf10.tgz      "TPC-H configured"; stage configured tpch 22 head          30

echo "[chain] PHASE2 ALL DONE $(date -Is): $(eps) episodes total"
