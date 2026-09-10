#!/bin/bash
# run_tpcc.sh -- harvest the corpus's only WRITE workload.
#
# Waits for any in-flight harvest to exit, loads TPC-C if it is not loaded, derives
# the measurement protocol from the loaded database, then harvests every ISE
# algorithm. Self-contained and idempotent: safe to re-run, and safe to run as the
# only thing a fresh machine is told to do.
#
# Why this exists as a script and not a command line: the run parameters ARE the
# experiment. A TPC-C episode differs from a JOB one in more than the benchmark name
# -- different port, different cluster, different repeat count, different timeout --
# and none of that should live only in someone's shell history.
set -u
REPO=${GENDBA_REPO:-/proj/pmoss-PG0/protox}
BUILD=${GENDBA_BUILD:-/mnt/protox}
PORT=${TPCC_PORT:-5493}
WAREHOUSES=${TPCC_WAREHOUSES:-100}
LOG=$BUILD/logs/run_tpcc.log
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

# ---- 0. do not contend with a running harvest -------------------------------
# Latency measurements are the product here; a concurrent load would corrupt both
# this run and whatever is already in flight. Pattern assembled at runtime so this
# script's own argv cannot match it.
for pat in "unitune_"$'harvest'".py" $'harvest'".py"; do
  while pgrep -f "$pat" | grep -qv "^$$\$"; do
    say "waiting for an in-flight harvest to finish ($pat)"; sleep 120
  done
done

# ---- 1. load ----------------------------------------------------------------
GENDBA_REPO="$REPO" TPCC_WAREHOUSES="$WAREHOUSES" TPCC_PORT="$PORT" \
  "$REPO/scripts/gendba/tpcc_setup.sh" || { say "setup FAILED"; exit 1; }

# ---- 2. derive the measurement protocol -------------------------------------
# warmup=0/repeats=1 was derived for an ~18s analytic pass. TPC-C is point lookups,
# so a pass is milliseconds: repeating is nearly free and NOT repeating measures
# mostly noise. Measure the noise here rather than assuming a number that was
# calibrated on a completely different cost structure.
say "deriving repeat count from the loaded database"
source "$BUILD/miniconda3/etc/profile.d/conda.sh"; conda activate unitune
REPEATS=$(PYTHONNOUSERSITE=1 GENDBA_REPO="$REPO" python "$REPO/scripts/gendba/noise.py" \
            --benchmark tpcc --port "$PORT" --queries 33 --suggest-repeats \
            2>/dev/null | tail -1)
case "$REPEATS" in ''|*[!0-9]*) REPEATS=5; say "  noise probe gave nothing usable; defaulting to $REPEATS" ;;
  *) say "  using repeats=$REPEATS" ;; esac

# ---- 3. harvest -------------------------------------------------------------
ALGOS=${TPCC_ALGOS:-extend,auto_admin,relaxation,drop,anytime,db2advis}
BUDGETS=${TPCC_BUDGETS:-50,100,250,500,1000,2500}
say "harvesting: algos=$ALGOS budgets=$BUDGETS repeats=$REPEATS"
PYTHONNOUSERSITE=1 GENDBA_REPO="$REPO" python "$REPO/scripts/gendba/harvest.py" \
  --benchmarks tpcc --port "$PORT" --queries 33 \
  --algorithms "$ALGOS" --budgets "$BUDGETS" \
  --measure-repeats "$REPEATS" --measure-warmup 1 \
  --query-timeout 60 --initial-kind pk_only \
  --out "$REPO/gendba_records" 2>&1 | tee -a "$LOG"
say "harvest finished"
