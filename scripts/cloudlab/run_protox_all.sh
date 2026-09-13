#!/usr/bin/env bash
#
# run_protox_all.sh -- harvest Proto-X on every runnable benchmark, in sequence.
#
# WHY SEQUENTIAL, not parallel
#   Three RL tunings on one node would contend for CPU and IO, and contention on a
#   shared host changes the latency numbers (docs/harvest_advise.md). The whole value
#   of the corpus is faithful measurement, so the runs are serialized on the one node.
#
# WHY ONLY job/tpch/dsb
#   Those are the loaded databases Proto-X can score by query/workload latency. TPC-C
#   is scored by BenchBase throughput and is not comparable; run_protox.sh refuses it.
#
# WHAT EACH RUN PRODUCES
#   run_protox.sh starts the run AND a background mirror of the raw trial to /proj
#   (survives the node). When a run finishes, this chain harvests its newest trial
#   into the corpus through the gate. The raw mirror is the safety net: if a harvest
#   ever fails, the trial is still on /proj and can be re-harvested.
#
# TIMING
#   ~30 h per benchmark, ~90 h total. If the allocation ends mid-run, the in-flight
#   trial's measured steps are already on /proj; harvest it with --truncated.
#
# USAGE
#   nohup scripts/cloudlab/run_protox_all.sh > node_artifacts/logs/protox_all.log 2>&1 &
#   scripts/cloudlab/run_protox_all.sh job dsb        # a subset, in that order
set -uo pipefail   # NOT -e: one benchmark failing must not abandon the rest

REPO=/proj/pmoss-PG0/protox
BUILD=/mnt/protox
# Trials are written directly under /proj (run_protox.sh sets TUNE_RESULT_DIR here).
RAY_RESULTS=$REPO/gendba_records/protox_trials
EP_DIR=$REPO/gendba_records/episodes
Q_DIR=$REPO/gendba_records/quarantine
ISE_PY=$BUILD/miniconda3/envs/ise/bin/python

BENCHES=("$@")
[[ ${#BENCHES[@]} -eq 0 ]] && BENCHES=(job tpch dsb)

c_hdr=$'\033[1;36m'; c_ok=$'\033[32m'; c_err=$'\033[31m'; c_off=$'\033[0m'
log() { echo "${c_hdr}[$(date '+%m-%d %H:%M:%S')]${c_off} $*"; }

cd "$REPO"
log "Proto-X chain: ${BENCHES[*]}   (~30 h each, sequential)"

newest_trial() {
    # The trial directory (contains repository/) most recently modified.
    find "$RAY_RESULTS" -maxdepth 3 -type d -name repository -printf '%T@ %h\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-
}

for b in "${BENCHES[@]}"; do
    log "==== $b : launching full run ===="
    before=$(newest_trial)

    # run_protox.sh blocks for the whole ~30 h run and starts/stops its own /proj
    # mirror. A non-zero exit (killed, crashed) still leaves measured steps on disk,
    # so we fall through to harvest whatever was produced rather than abandon it.
    ./scripts/cloudlab/run_protox.sh "$b" full
    rc=$?
    log "$b : run_protox.sh exited rc=$rc"

    trial=$(newest_trial)
    if [[ -z $trial || $trial == "$before" ]]; then
        log "${c_err}$b : no new trial directory appeared -- nothing to harvest${c_off}"
        continue
    fi

    # If the run did not exit cleanly, the last trajectory is incomplete -> --truncated.
    trunc=""
    [[ $rc -ne 0 ]] && trunc="--truncated"

    log "$b : harvesting $trial $trunc"
    PYTHONNOUSERSITE=1 GENDBA_REPO="$REPO" "$ISE_PY" scripts/gendba/protox_harvest.py \
        --trial "$trial" --benchmark "$b" --out-dir "$EP_DIR" --quarantine-dir "$Q_DIR" $trunc
    hrc=$?
    if [[ $hrc -eq 0 ]]; then
        log "${c_ok}$b : harvested into the corpus${c_off}"
    else
        log "${c_err}$b : harvest rc=$hrc (quarantined or failed). Raw trial is on /proj \
under gendba_records/protox_trials/ -- re-harvestable.${c_off}"
    fi
done

log "chain complete. corpus now: $(ls "$EP_DIR" | wc -l) episodes"
