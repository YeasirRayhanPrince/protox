#!/bin/bash
# tpcc_setup.sh -- build BenchBase, stand up a cluster, load TPC-C.
#
# TPC-C is the only WRITE workload available to this corpus. Every benchmark we have
# harvested so far (JOB, TPC-H, DSB) is read-only, which means every measured index in
# 215 episodes is priced at storage cost alone -- write amplification and index
# maintenance appear nowhere. A model trained on that will over-index anything with an
# update stream and nothing in the data would warn it. This fixes that.
#
# Runs on its OWN cluster (port 5493) so the JOB database on 5492 is left intact.
# The data directory follows UniTune's expected <postgres_path>/pgdata<port> layout,
# because UniTune's _close_db loops forever if it cannot find the cluster there.
set -euo pipefail

REPO=${GENDBA_REPO:-/proj/pmoss-PG0/protox}
BUILD=${GENDBA_BUILD:-/mnt/protox}
PORT=${TPCC_PORT:-5493}
WAREHOUSES=${TPCC_WAREHOUSES:-100}
PGBIN=$BUILD/pg15/bin
PGDATA=$PGBIN/pgdata$PORT
BB=$BUILD/benchbase_src
LOG=$BUILD/logs/tpcc_setup.log

say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

# ---- 1. build BenchBase -------------------------------------------------
# BenchBase HEAD needs EXACTLY JDK 23: 17 is too old for its -source/-target, and a
# newer JDK makes javac emit a warning that its own -Werror turns into an error. The
# fmt plugin also breaks on anything newer, hence -Dfmt.skip.
if [ ! -f "$BB/target/benchbase-postgres/benchbase.jar" ]; then
  say "building BenchBase (postgres profile, JDK 23)..."
  source "$BUILD/miniconda3/etc/profile.d/conda.sh"; conda activate jvm
  ( cd "$BB" && nice -n 5 mvn -B -q -P postgres clean package -DskipTests -Dfmt.skip=true ) \
    >> "$LOG" 2>&1
  ( cd "$BB/target" && tar xzf benchbase-postgres.tgz )
  say "  built"
else
  say "BenchBase already built"
fi
BBDIR=$BB/target/benchbase-postgres

# ---- 2. cluster ---------------------------------------------------------
if [ ! -d "$PGDATA" ]; then
  say "initdb $PGDATA"
  # trust, matching every other cluster in this harness: it listens on localhost
  # only, and env.py connects without a password. A stricter setting here bought no
  # security and failed all 36 episodes with "no password supplied".
  "$PGBIN/initdb" -D "$PGDATA" -U admin --auth-local=trust --auth-host=trust >> "$LOG" 2>&1
  # Same knobs the other clusters run, so a TPC-C episode is comparable with a JOB one.
  cat >> "$PGDATA/postgresql.conf" <<CONF
port = $PORT
shared_buffers = '32GB'
effective_cache_size = '96GB'
work_mem = '512MB'
maintenance_work_mem = '4GB'
max_parallel_workers = 16
max_parallel_workers_per_gather = 8
random_page_cost = 1.1
seq_page_cost = 1.0
max_wal_size = '32GB'
checkpoint_timeout = '30min'
listen_addresses = 'localhost'
CONF
  echo "host all all 127.0.0.1/32 trust" >> "$PGDATA/pg_hba.conf"
fi

"$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1 || {
  say "starting cluster on $PORT"
  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGBIN/pg.log.$PORT" -w -t 300 start >> "$LOG" 2>&1
}
export PGPASSWORD=password
"$PGBIN/psql" -h localhost -p "$PORT" -U admin -d postgres -Atc \
  "select 1 from pg_database where datname='benchbase'" | grep -q 1 || {
  say "creating database benchbase"
  "$PGBIN/psql" -h localhost -p "$PORT" -U admin -d postgres -c "CREATE DATABASE benchbase" >> "$LOG" 2>&1
}
"$PGBIN/psql" -h localhost -p "$PORT" -U admin -d postgres -c \
  "ALTER USER admin WITH PASSWORD 'password'" >> "$LOG" 2>&1

# ---- 3. load ------------------------------------------------------------
CFG=$REPO/unitune_run/tpcc_load.xml
sed -e "s|localhost:5432/benchbase|localhost:$PORT/benchbase|" \
    -e "s|<scalefactor>1</scalefactor>|<scalefactor>$WAREHOUSES</scalefactor>|" \
    "$BB/config/postgres/sample_tpcc_config.xml" > "$CFG"

n=$("$PGBIN/psql" -h localhost -p "$PORT" -U admin -d benchbase -Atc \
      "select count(*) from information_schema.tables where table_schema='public'")
if [ "$n" -lt 9 ]; then
  say "loading TPC-C, $WAREHOUSES warehouses (this is the long step)"
  source "$BUILD/miniconda3/etc/profile.d/conda.sh"; conda activate jvm
  ( cd "$BBDIR" && java -jar benchbase.jar -b tpcc -c "$CFG" \
      --create=true --load=true --execute=false ) >> "$LOG" 2>&1
  say "  loaded"
else
  say "TPC-C already loaded ($n tables)"
fi

say "ANALYZE"
"$PGBIN/psql" -h localhost -p "$PORT" -U admin -d benchbase -c "ANALYZE" >> "$LOG" 2>&1

say "done. tables and sizes:"
"$PGBIN/psql" -h localhost -p "$PORT" -U admin -d benchbase -c \
  "SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid)) AS size
     FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC" | tee -a "$LOG"
