#!/usr/bin/env bash
#
# normalize_knobs.sh -- put every *_base snapshot on the paper's knob settings.
#
# WHY: the base snapshots were configured ad hoc during bulk loading and drifted
# apart from each other and from the paper's baseline:
#   * max_parallel_workers_per_gather was left at the default 2, vs the paper's 10
#   * effective_cache_size was left at the 512MB default alongside 32GB of
#     shared_buffers -- which actively biases the planner AGAINST index scans, i.e.
#     against the exact decision we are harvesting
#   * default_statistics_target was 100, vs the paper's 500
#   * dsb_sf10_base had autovacuum=off; the other two did not
#
# Knobs match scripts/experiments/*/load_*.py shift_state(), so ISE traces are
# comparable across benchmarks AND to Proto-X, which starts from these settings.
#
# Note: work_mem is set to the paper's 10485kB. Measured on JOB, 10485kB vs 4GB
# produces zero spilled operations and identical runtime -- so for JOB this is a
# comparability choice, not a performance one. Untested for TPC-H/DSB.
#
set -euo pipefail

PGBIN=/mnt/protox/pg15/bin
DATA=/data/protox/data
PORT=5493
STAGE=/data/protox/_norm
export PGUSER=admin PGPASSWORD=password

# benchmark:shared_buffers  (the paper uses 32GB for TPC-H, 8GB for JOB and DSB)
TARGETS=("job_base:8GB" "tpch_sf10_base:32GB" "dsb_sf10_base:8GB")

common_knobs() {
cat <<EOF
ALTER SYSTEM SET shared_buffers = '$1';
ALTER SYSTEM SET effective_cache_size = '24GB';
ALTER SYSTEM SET maintenance_work_mem = '2GB';
ALTER SYSTEM SET work_mem = '10485kB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 500;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET min_wal_size = '4GB';
ALTER SYSTEM SET max_wal_size = '16GB';
ALTER SYSTEM SET max_worker_processes = 20;
ALTER SYSTEM SET max_parallel_workers_per_gather = 10;
ALTER SYSTEM SET max_parallel_workers = 20;
ALTER SYSTEM SET max_parallel_maintenance_workers = 4;
ALTER SYSTEM SET max_connections = 40;
ALTER SYSTEM SET autovacuum = on;
EOF
}

for entry in "${TARGETS[@]}"; do
    snap=${entry%%:*}; sb=${entry##*:}
    tgz=$DATA/$snap.tgz
    [[ -f $tgz ]] || { echo "SKIP $snap (missing)"; continue; }
    echo "=== $snap  (shared_buffers=$sb) ==="

    rm -rf $STAGE; mkdir -p -m 0700 $STAGE
    tar xf "$tgz" -C $STAGE --strip-components 1

    # strip stale port lines and any hand-set knobs from bulk loading; the paper's
    # values go into postgresql.auto.conf via ALTER SYSTEM, matching shift_state().
    sed -i -E '/^\s*(port|autovacuum|shared_buffers|work_mem|maintenance_work_mem|max_wal_size|checkpoint_timeout|max_worker_processes|max_parallel_workers)\s*=/d' \
        $STAGE/postgresql.conf
    echo "port = $PORT" >> $STAGE/postgresql.conf

    $PGBIN/pg_ctl -D $STAGE -l /tmp/norm_$snap.log -w -t 300 start >/dev/null
    common_knobs "$sb" | $PGBIN/psql -h localhost -p $PORT -d benchbase -q -v ON_ERROR_STOP=1
    $PGBIN/pg_ctl -D $STAGE -m fast -w stop >/dev/null
    $PGBIN/pg_ctl -D $STAGE -l /tmp/norm_$snap.log -w -t 300 start >/dev/null

    echo "  re-ANALYZE at default_statistics_target=500 ..."
    $PGBIN/psql -h localhost -p $PORT -d benchbase -q -c "ANALYZE;"

    $PGBIN/psql -h localhost -p $PORT -d benchbase -c "
      SELECT name, setting, unit FROM pg_settings WHERE name IN
      ('shared_buffers','effective_cache_size','work_mem','random_page_cost',
       'max_parallel_workers_per_gather','default_statistics_target','autovacuum')
      ORDER BY name;"

    $PGBIN/pg_ctl -D $STAGE -m fast -w stop >/dev/null
    $PGBIN/pg_resetwal -D $STAGE >/dev/null 2>&1

    rm -rf /data/protox/_ns && mkdir -p /data/protox/_ns
    mv $STAGE /data/protox/_ns/pgdata
    ( cd /data/protox/_ns && tar cf "$tgz" pgdata )
    rm -rf /data/protox/_ns
    echo "  rewrote $tgz ($(du -h "$tgz" | cut -f1))"
done
echo "done"
