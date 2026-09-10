#!/usr/bin/env bash
# run_qo.sh -- self-driven query-optimization episodes across all three benchmarks.
# Per-query episodes take seconds, so the whole query set is affordable everywhere.
set -uo pipefail
REPO=/proj/pmoss-PG0/protox
PGBIN=/mnt/protox/pg15/bin
OUT=$REPO/gendba_records
export PGUSER=admin PGPASSWORD=password
source /mnt/protox/miniconda3/etc/profile.d/conda.sh; conda activate ise
cd "$REPO"

load () {
  local pgd=/data/protox/pgdata_ise
  $PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
  rm -rf $pgd; mkdir -p -m 0700 $pgd
  tar xf /data/protox/data/"$1" -C $pgd --strip-components 1
  sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
  echo "port = 5492" >> $pgd/postgresql.conf
  $PGBIN/pg_ctl -D $pgd -l /data/protox/pg_ise.log -w -t 600 start >/dev/null
  echo "[qo] $2 up"
}

stage () {  # snapshot label bench nqueries timeout
  load "$1" "$2"
  echo "[qo] === $2 starting $(date -Is) ==="
  python scripts/gendba/qo_harvest.py --benchmark "$3" --queries "$4" \
    --query-timeout "$5" --measure-k 4 --repeats 3 --out "$OUT" \
    > /mnt/protox/logs/qo_$2.log 2>&1
  echo "[qo] === $2 done, corpus $(ls $OUT/episodes | grep -c '[.]json$') ==="
}

stage job_base.tgz       job_pkonly       job  113 30
stage tpch_sf10.tgz      tpch_configured  tpch  22 30
stage dsb_sf10_base.tgz  dsb_pkonly       dsb    0 30
echo "[qo] ALL DONE $(date -Is): $(ls $OUT/episodes | grep -c '[.]json$') episodes"
