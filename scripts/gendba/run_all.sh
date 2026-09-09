#!/usr/bin/env bash
#
# run_all.sh -- run the remaining harvests back to back, each with a monitor.
#
#   1. DSB          pk_only     67 queries (one per shape), 30s query timeout
#   2. TPC-H        pk_only     22 queries, 30s   (greenfield; Q17 censors)
#   3. TPC-H        configured  22 queries, 30s   (paper baseline: lineitem_lk etc.)
#
# Timeouts match what the paper shipped (results/*/us/*/params.json): 30s per query
# for TPC-H and DSB. initial_state.kind is stamped on every record, so the two TPC-H
# starting states never mix silently.
#
# Each stage gets monitor.sh, which detects a STALL (alive but not producing), not
# just completion -- the failure mode that has cost us hours on this project.
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

load_snapshot () {   # $1 snapshot file  $2 label
  local pgd=/data/protox/pgdata_ise
  $PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
  rm -rf $pgd; mkdir -p -m 0700 $pgd
  tar xf /data/protox/data/"$1" -C $pgd --strip-components 1
  sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
  echo "port = 5492" >> $pgd/postgresql.conf
  $PGBIN/pg_ctl -D $pgd -l /data/protox/pg_ise.log -w -t 600 start >/dev/null
  echo "[run_all] $2 up: $($PGBIN/psql -h localhost -p 5492 -d benchbase -tAc \
    "SELECT (SELECT count(*) FROM pg_indexes WHERE schemaname='public')||' indexes'")"
}

stage () {           # $1 label  $2 bench  $3 queries  $4 select  $5 extra-args
  local label=$2_$1 bench=$2 nq=$3 sel=$4 extra=${5:-}
  local log="$LOGD/harvest_${label}.log"
  local before; before=$(eps)
  echo "[run_all] === $label starting at $(date -Is) (episodes so far: $before) ==="
  ( python scripts/gendba/harvest.py --benchmarks "$bench" \
      --algorithms extend,relaxation,auto_admin \
      --budgets 50,100,250,500,1000,2500 --widths 1,2 \
      --queries "$nq" --query-select "$sel" --query-timeout 30 --adjudicate-k 5 \
      --out "$OUT" $extra
    python scripts/gendba/harvest.py --benchmarks "$bench" --algorithms drop \
      --budgets 50,100,250,500,1000,2500 --widths 2 \
      --queries "$nq" --query-select "$sel" --query-timeout 30 --adjudicate-k 5 \
      --out "$OUT" $extra ) > "$log" 2>&1 &
  local hp=$!
  "$REPO/scripts/gendba/monitor.sh" "$log" "$OUT/episodes" $((before + 42)) 35 "$label" \
      > "$LOGD/monitor_${label}.log" 2>&1 &
  local mp=$!
  wait $hp; local rc=$?
  kill $mp 2>/dev/null || true
  echo "[run_all] === $label done rc=$rc, episodes now $(eps) ==="
}

load_snapshot dsb_sf10_base.tgz     "DSB pk_only"
stage pk_only dsb 67 one-per-shape

load_snapshot tpch_sf10_base.tgz    "TPC-H pk_only"
stage pk_only tpch 22 head

load_snapshot tpch_sf10.tgz         "TPC-H configured"
stage configured tpch 22 head

echo "[run_all] ALL DONE at $(date -Is): $(eps) episodes total"
