#!/usr/bin/env bash
#
# run_protox.sh -- launch Proto-X itself (not a baseline) on a provisioned node.
#
# provision.sh's completion banner has always pointed at this script; it did not
# exist. Every previous allocation ran Proto-X's BASELINES and never Proto-X, so the
# invocation was re-derived by hand each time and got the paths wrong each time.
# This file is that invocation, written down once.
#
# USAGE
#   ./run_protox.sh                      # smoke test on JOB (~30 min) -- DO THIS FIRST
#   ./run_protox.sh job smoke
#   ./run_protox.sh job full             # the real run: 30 h (duration is the ONLY bound)
#   ./run_protox.sh tpch full
#   ./run_protox.sh job preflight        # checks only, launch nothing
#
# The smoke test is not optional. It exercises the whole DB lifecycle -- untar,
# start, run, index DDL, restart, reset -- which is where every path mistake
# surfaces. A path error in the full run costs 30 h to discover.
#
# ---------------------------------------------------------------------------------
# THE PATH RULE, which is the single biggest source of lost time here.
#
#   RELATIVE (agents/hpo.py prefixes each with mythril_dir, unconditionally):
#       --config  --model-config  --benchmark-config  --data-snapshot-path
#         agents/hpo.py:48   open(f"{mythril_dir}/{benchmark_config}")
#         agents/hpo.py:72   open(f"{mythril_dir}/{config}")
#         agents/hpo.py:102  "{mythril_dir}/{snapshot}".format(...)
#         agents/wolp/config.py:80  open(f"{mythril_dir}/{model_config}")
#       Passing $PWD/... yields /proj/.../protox//proj/.../protox/configs/... and
#       fails. HANDOVER.md's example command has this bug in three of four flags.
#
#   ABSOLUTE (consumed directly, never prefixed):
#       --benchbase-config-path     agents/hpo.py:80  ET.parse(benchbase_config_path)
#       --mythril-dir
# ---------------------------------------------------------------------------------
set -euo pipefail

REPO=/proj/pmoss-PG0/protox
BUILD=/mnt/protox
DATA=/data/protox
CONDA=$BUILD/miniconda3
ENV_PROTOX=protox

BENCH=${1:-job}
MODE=${2:-smoke}

c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_hdr=$'\033[1;36m'; c_off=$'\033[0m'
log()  { echo "${c_hdr}[$(date +%H:%M:%S)]${c_off} $*"; }
ok()   { echo "  ${c_ok}OK${c_off}   $*"; }
warn() { echo "  ${c_warn}WARN${c_off} $*"; }
die()  { echo "  ${c_err}FAIL${c_off} $*" >&2; exit 1; }

case "$BENCH" in
    job)  BCFG=configs/benchmark/job_full.yaml; SNAP=data/job.tgz;        INIT=initial_job.json  ;;
    tpch) BCFG=configs/benchmark/tpch.yaml;     SNAP=data/tpch_sf10.tgz;  INIT=initial_tpch.json ;;
    dsb)  BCFG=configs/benchmark/dsb_s10.yaml;  SNAP=data/dsb_sf10.tgz;   INIT=initial_dsb.json  ;;
    *) die "unknown benchmark '$BENCH' (job|tpch|dsb). TPC-C is not supported here: \
Proto-X scores it by BenchBase throughput, not query latency." ;;
esac

cd "$REPO"

# ------------------------------------------------------------------ preflight
# Each check below corresponds to a failure that has actually happened.
log "preflight: $BENCH / $MODE"

[[ -d $CONDA/envs/$ENV_PROTOX ]] || die "conda env '$ENV_PROTOX' missing -- run scripts/cloudlab/provision.sh"

# Snapshot. Resolved the way hpo.py will resolve it, not the way we hope it will.
resolved="$REPO/$SNAP"
[[ -e $resolved ]] || die "snapshot $SNAP does not resolve to an existing file ($resolved).
       It MUST be relative -- hpo.py prefixes it with mythril_dir."
ok "snapshot $SNAP -> $(readlink -f "$resolved") ($(du -h "$resolved" | cut -f1))"

# Relative-path flags. An absolute value here is the bug documented above.
for p in "configs/config_cloudlab_${BENCH}.yaml" "$BCFG" configs/wolp_params.yaml "$SNAP"; do
    [[ $p != /* ]] || die "path '$p' is absolute; these four flags must be relative"
    [[ -e $REPO/$p ]] || die "missing $REPO/$p"
done
ok "config/model/benchmark/snapshot paths are relative and present"

# benchbase stub: a missing <transactiontypes> is a TypeError thrown only AFTER the
# baseline workload has already run, so it costs minutes to discover (envs/spaces/
# utils.py:319 iterates it unconditionally once per-query knobs are on).
grep -q "<transactiontypes>" "$REPO/stub_benchbase.xml" \
    || die "stub_benchbase.xml has no <transactiontypes> element"
ok "benchbase stub has <transactiontypes>"

# initial_*.json must be a JSON ARRAY whose entries carry mythril_args (hpo.py:203
# asserts this), with relative inner paths for the same reason as above.
"$CONDA/envs/$ENV_PROTOX/bin/python" - "$REPO/$INIT" "$REPO" <<'PY' || die "$INIT is not usable"
import json, sys, os
p, repo = sys.argv[1], sys.argv[2]
d = json.load(open(p))
assert isinstance(d, list) and d, f"{p} must be a non-empty JSON array"
for i, c in enumerate(d):
    assert "mythril_args" in c, f"entry {i} has no mythril_args"
    ma = c["mythril_args"]
    for k in ("config", "benchmark_config", "model_config", "data_snapshot_path"):
        v = ma.get(k)
        assert v and not str(v).startswith("/"), f"entry {i}: {k}={v!r} must be relative"
        assert os.path.exists(os.path.join(repo, v)), f"entry {i}: {k}={v!r} does not exist"
    assert str(ma.get("benchbase_config_path", "")).startswith("/"), \
        f"entry {i}: benchbase_config_path must be ABSOLUTE"
print(f"  {len(d)} initial config(s) validated")
PY
ok "$INIT validated"

# Ray must write to node-local disk. On NFS the run is both slow and lost at teardown.
export TUNE_RESULT_DIR=$BUILD/ray_results
mkdir -p "$TUNE_RESULT_DIR"
if [[ -e $HOME/ray_results && ! -L $HOME/ray_results ]]; then
    warn "$HOME/ray_results is a real directory on NFS, not a symlink"
fi
ok "TUNE_RESULT_DIR=$TUNE_RESULT_DIR"

# ---------------------------------------------------------------------------------
# hypopg: the snapshot must not carry it.
#
# pg_stat_user_tables is a PER-TABLE state source (envs/spaces/utils.py:71), so every
# TABLE in `public` contributes keys to the agent's state vector, and an unexpected
# one breaks it with a KeyError. provision.sh's bootstrap_db creates hypopg in EVERY
# snapshot because index_selection_evaluation requires it.
#
# MEASURED on hypopg 1.4.3 (2026-09-13): it creates only VIEWS -- hypopg_list_indexes
# and hypopg_hidden_indexes -- and views do NOT appear in pg_stat_user_tables. So the
# extension is harmless to the state vector on this version, and the JOB smoke test
# ran to completion with it installed. HANDOVER.md's blanket "do NOT install hypopg
# on the Proto-X cluster" is therefore not true here.
#
# The check stays because it is cheap and version-dependent: if a future hypopg ships
# a real table, this names the cause immediately instead of a bare KeyError 30 h in.
# ---------------------------------------------------------------------------------
PG_BIN=$BUILD/pg15/bin
probe_pgd=$DATA/_protox_preflight
probe_port=5447
if [[ -x $PG_BIN/pg_ctl ]]; then
    rm -rf "$probe_pgd"; mkdir -p -m 0700 "$probe_pgd"
    tar xf "$resolved" -C "$probe_pgd" --strip-components 1
    echo "port=$probe_port" >> "$probe_pgd/postgresql.conf"
    "$PG_BIN/pg_ctl" -D "$probe_pgd" -l "$probe_pgd/pg.log" -w start >/dev/null 2>&1 \
        || die "could not start the snapshot for the hypopg probe (see $probe_pgd/pg.log)"
    stray=$("$PG_BIN/psql" -h localhost -p $probe_port -U admin -d benchbase -tAc \
        "SELECT string_agg(relname, ' ') FROM pg_stat_user_tables WHERE relname LIKE 'hypopg%'" 2>/dev/null || true)
    ext=$("$PG_BIN/psql" -h localhost -p $probe_port -U admin -d benchbase -tAc \
        "SELECT 1 FROM pg_extension WHERE extname='hypopg'" 2>/dev/null || true)
    "$PG_BIN/pg_ctl" -D "$probe_pgd" -w stop >/dev/null 2>&1 || true
    rm -rf "$probe_pgd"

    if [[ -n ${stray// /} ]]; then
        die "snapshot $SNAP carries hypopg table(s) in public: $stray
       These enter Proto-X's per-table state vector and break it with a KeyError.
       Rebuild a Proto-X snapshot with the extension dropped:
         restore $SNAP, then  DROP EXTENSION hypopg CASCADE;  then re-tar."
    fi
    if [[ -n $ext ]]; then
        warn "hypopg extension is installed in the snapshot but contributes no table to
       public; harmless for the state vector, but drop it if a KeyError appears."
    else
        ok "snapshot carries no hypopg extension"
    fi
else
    warn "pg_ctl not found; skipped the hypopg snapshot probe"
fi

[[ $MODE == preflight ]] && { log "preflight only -- nothing launched"; exit 0; }

# ------------------------------------------------------------------ ray head
# shellcheck disable=SC1091
source "$CONDA/etc/profile.d/conda.sh"; conda activate "$ENV_PROTOX"
export PYTHONNOUSERSITE=1
if ! ray status >/dev/null 2>&1; then
    log "starting ray head"
    OMP_NUM_THREADS=8 ray start --head --port=6379 --num-cpus=4 --temp-dir="$BUILD/ray" \
        > "$BUILD/logs/ray.log" 2>&1
    sleep 5
fi
ray status >/dev/null 2>&1 && ok "ray head up" || die "ray head is not running"

# ------------------------------------------------------------------ launch
# ---------------------------------------------------------------------------------
# BOUNDING THE RUN -- neither flag below does what its name suggests.
#
# --max-iterations is a NO-OP on this path. It is read only at tune.py:211, inside
#   tune.py's own __main__ loop. hpo.py/Ray never looks at it.
#
# --duration is OVERRIDDEN. initial_*.json is passed as points_to_evaluate, so for
#   those trials ITS mythril_args win over the command line, and initial_job.json
#   carries duration: 30.0. hpo.py's only stop condition is
#   TimeoutChecker(mythril_args["duration"]) (hpo.py:79, :105).
#
# Net effect: `smoke` with --duration 0.5 was configured to run for THIRTY HOURS and
# would never have stopped on its own. Verified on a real trial, whose episode
# recorded constraint.value = 108000 s.
#
# So smoke mode patches duration inside a throwaway copy of the initial configs.
# Everything else stays identical to the real run -- which is the entire point of a
# smoke test: bound the clock, change nothing else.
# ---------------------------------------------------------------------------------
HORIZON=5; TRIALS=1
if [[ $MODE == smoke ]]; then
    DURATION=0.5
    SMOKE_INIT=$(mktemp /tmp/protox_initial_smoke_XXXXXX.json)
    "$CONDA/envs/$ENV_PROTOX/bin/python" - "$REPO/$INIT" "$SMOKE_INIT" "$DURATION" <<'PY'
import json, sys
src, dst, dur = sys.argv[1], sys.argv[2], float(sys.argv[3])
d = json.load(open(src))
for c in d:
    c["mythril_args"]["duration"] = dur
json.dump(d, open(dst, "w"), indent=2)
print(f"  smoke: duration forced to {dur} h in {len(d)} initial config(s)")
PY
    INIT=$SMOKE_INIT
    trap 'rm -f "$SMOKE_INIT"' EXIT
else
    DURATION=30.0
fi

stamp=$(date +%Y%m%d_%H%M%S)
LOG=$REPO/node_artifacts/logs/protox_${BENCH}_${MODE}_${stamp}.log
mkdir -p "$(dirname "$LOG")"

log "launching Proto-X: $BENCH / $MODE  (duration=${DURATION}h, horizon=$HORIZON)"
echo "  log: $LOG"

set -x
python3 hpo.py \
    --config "configs/config_cloudlab_${BENCH}.yaml" \
    --agent wolp \
    --model-config configs/wolp_params.yaml \
    --benchmark-config "$BCFG" \
    --mythril-dir "$REPO" \
    --num-trials "$TRIALS" \
    --max-concurrent 1 \
    --horizon "$HORIZON" \
    --duration "$DURATION" \
    --target latency \
    --data-snapshot-path "$SNAP" \
    --workload-timeout 600 \
    --timeout 15 \
    --benchbase-config-path "$REPO/stub_benchbase.xml" \
    --initial-configs "$INIT" \
    --initial-repeats 1 \
    2>&1 | tee "$LOG"
