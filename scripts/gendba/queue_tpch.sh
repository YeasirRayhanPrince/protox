#!/usr/bin/env bash
#
# queue_tpch.sh -- run TPC-H from BOTH starting states once DSB finishes.
#
# Settings follow what the paper actually shipped (results/tpch/us/*/params.json):
#   per-query timeout 30s, workload timeout 300s -- not the 90s I had guessed.
#
# Two starting states, because they answer different questions and the corpus
# currently only contains one of them:
#   pk_only    tpch_sf10_base.tgz  -- greenfield. ISE selects from scratch, so its
#                                     decisions are meaningful. Q17 has no
#                                     lineitem(l_partkey) and censors at 30s.
#   configured tpch_sf10.tgz       -- the paper's own baseline: lineitem_lk,
#                                     orders_ck, ps_sk + the revenue0_PID view. The
#                                     realistic case, tuning an already-tuned system.
# initial_state.kind is stamped on every record, so the two never mix silently.
#
# The paper never ran TPC-H on pk_only -- it always gave it lineitem(l_partkey).
set -uo pipefail
PGBIN=/mnt/protox/pg15/bin
REPO=/proj/pmoss-PG0/protox
OUT=$REPO/gendba_records
LOGD=/mnt/protox/logs
export PGUSER=admin PGPASSWORD=password
export GENDBA_PARALLEL=1 GENDBA_ISOLATION=dedicated_cluster_sequential

echo "[tpch-queue] waiting for the current harvest ..."
while pgrep -f "[h]arvest.py" >/dev/null; do sleep 60; done
echo "[tpch-queue] free at $(date -Is)"

run_state () {                       # $1 snapshot  $2 label
  local snap=$1 label=$2
  echo "[tpch-queue] === $label ($snap) ==="
  local pgd=/data/protox/pgdata_ise
  $PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
  rm -rf $pgd; mkdir -p -m 0700 $pgd
  tar xf /data/protox/data/$snap -C $pgd --strip-components 1
  sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
  echo "port = 5492" >> $pgd/postgresql.conf
  $PGBIN/pg_ctl -D $pgd -l /data/protox/pg_tpch_ise.log -w -t 600 start >/dev/null
  $PGBIN/psql -h localhost -p 5492 -d benchbase -tAc \
    "SELECT '$label up: indexes='||(SELECT count(*) FROM pg_indexes WHERE schemaname='public')||
     ' views='||(SELECT count(*) FROM pg_views WHERE schemaname='public' AND viewname ILIKE 'revenue0%')||
     ' lineitem='||(SELECT count(*) FROM lineitem);"

  local before after
  before=$(ls "$OUT/episodes" 2>/dev/null | grep -c '\.json$' || echo 0)

  ( source /mnt/protox/miniconda3/etc/profile.d/conda.sh && conda activate ise && cd "$REPO" && \
    python scripts/gendba/harvest.py --benchmarks tpch \
      --algorithms extend,relaxation,auto_admin \
      --budgets 50,100,250,500,1000,2500 --widths 1,2 --queries 22 \
      --query-timeout 30 --adjudicate-k 5 --out "$OUT" && \
    python scripts/gendba/harvest.py --benchmarks tpch --algorithms drop \
      --budgets 50,100,250,500,1000,2500 --widths 2 --queries 22 \
      --query-timeout 30 --adjudicate-k 5 --out "$OUT" \
  ) > "$LOGD/harvest_tpch_$label.log" 2>&1 &
  local hp=$!

  # active monitor: stall detection, not just exit-waiting
  "$REPO/scripts/gendba/monitor.sh" "$LOGD/harvest_tpch_$label.log" \
      "$OUT/episodes" $((before + 42)) 20 "tpch_$label" &
  local mp=$!
  wait $hp; local rc=$?
  kill $mp 2>/dev/null || true
  echo "[tpch-queue] $label finished rc=$rc, episodes now $(ls "$OUT/episodes" | grep -c '\.json$')"
}

run_state tpch_sf10_base.tgz pk_only
run_state tpch_sf10.tgz      configured
echo "[tpch-queue] ALL TPC-H DONE at $(date -Is)"
