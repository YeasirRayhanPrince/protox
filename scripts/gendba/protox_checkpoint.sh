#!/usr/bin/env bash
#
# protox_checkpoint.sh -- make a 30 h Proto-X run survive losing the node.
#
# THE RISK, stated precisely
#   hpo.py:130 save_checkpoint is a no-op, so Ray cannot resume a killed trial. That
#   is survivable: we do not need to RESUME the agent, we need to KEEP WHAT IT
#   MEASURED. Every evaluation is already written whole to repository/<timestamp>/
#   and never touched again (envs/repository.py:29), so the trial directory is itself
#   a complete, append-only record of the run so far.
#
#   The real exposure is WHERE it is written: /mnt/protox/ray_results is node-local
#   and dies with the allocation, taking every measured step with it. /proj is the
#   only filesystem that survives.
#
# WHY THIS MIRRORS RAW ARTIFACTS RATHER THAN CHECKPOINTING AN EPISODE
#   docs/harvest_advise.md, learned the expensive way: "Persist RAW first, derive
#   later. A fix to your parsing/derivation cannot be applied to records that only
#   stored the derived value -- that single mistake was our #1 cause of full
#   re-harvests."
#
#   Six parsing bugs were found in this harness against the FIRST real trial. There
#   will be more. If a checkpoint stored only the derived episode, every one of those
#   fixes would be unappliable to the run that produced it. Mirroring the raw trial
#   costs a few hundred MB and makes every future fix retroactive.
#
#   It is also far cheaper: rsync copies only the new step directories, whereas
#   re-deriving the episode means re-reading every run.plans and rebuilding a
#   multi-GB JSON on each tick.
#
# USAGE
#   scripts/gendba/protox_checkpoint.sh                   # auto-detect newest trial
#   scripts/gendba/protox_checkpoint.sh --interval 300
#   scripts/gendba/protox_checkpoint.sh --trial <dir> --once
#
# Harvest from the mirror exactly as from the original:
#   python3 scripts/gendba/protox_harvest.py \
#       --trial gendba_records/protox_trials/<name> --benchmark job [--truncated]
set -euo pipefail

REPO=${GENDBA_REPO:-/proj/pmoss-PG0/protox}
BUILD=${GENDBA_BUILD:-/mnt/protox}
RAY_RESULTS=$BUILD/ray_results
DEST_ROOT=$REPO/gendba_records/protox_trials

INTERVAL=600
TRIAL=""
ONCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval) INTERVAL=$2; shift 2 ;;
        --trial)    TRIAL=$2;    shift 2 ;;
        --once)     ONCE=1;      shift ;;
        -h|--help)  sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_hdr=$'\033[1;36m'; c_off=$'\033[0m'
log()  { echo "${c_hdr}[$(date +%H:%M:%S)]${c_off} $*"; }
ok()   { echo "  ${c_ok}OK${c_off}   $*"; }
warn() { echo "  ${c_warn}WARN${c_off} $*"; }

# Newest trial directory: the one containing repository/, not the experiment wrapper.
find_trial() {
    find "$RAY_RESULTS" -maxdepth 3 -type d -name "repository" -printf '%T@ %h\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-
}

if [[ -z $TRIAL ]]; then
    TRIAL=$(find_trial)
    [[ -n $TRIAL ]] || { echo "no Proto-X trial found under $RAY_RESULTS" >&2; exit 1; }
fi
[[ -d $TRIAL ]] || { echo "not a directory: $TRIAL" >&2; exit 1; }

NAME=$(basename "$TRIAL")
DEST=$DEST_ROOT/$NAME
mkdir -p "$DEST"

log "checkpointing $NAME"
echo "  from: $TRIAL"
echo "  to:   $DEST   (/proj -- survives the node)"
echo "  every ${INTERVAL}s"

checkpoint() {
    # --inplace is deliberately NOT used: rsync's default write-to-temp-then-rename
    # is what makes a checkpoint interrupted mid-copy leave the previous complete
    # file rather than a half-written one. Step directories are immutable once
    # written, so already-copied steps are skipped outright.
    rsync -a --no-perms --no-owner --no-group \
          --exclude='*.partial' \
          "$TRIAL"/ "$DEST"/ 2>/dev/null || { warn "rsync returned non-zero"; return 1; }

    local steps size
    steps=$(find "$DEST/repository" -maxdepth 1 -type d -name '2*' 2>/dev/null | wc -l)
    # Apparent size, so the number is comparable to the source. /proj is ZFS with
    # compression on (~5x on EXPLAIN JSON), so plain `du` reports far less and reads
    # like the copy is incomplete.
    size=$(du -sh --apparent-size "$DEST" 2>/dev/null | cut -f1)

    # A cheap parse check on the MIRROR, so we learn that the trace is still
    # readable now rather than at hour 30. Deliberately does NOT build the episode:
    # that would restore a snapshot and rebuild a multi-GB JSON on every tick.
    local parsed
    parsed=$(PYTHONNOUSERSITE=1 "$BUILD/miniconda3/envs/ise/bin/python" - "$DEST" <<'PY' 2>&1 || true
import sys
from pathlib import Path
sys.path.insert(0, "/proj/pmoss-PG0/protox/scripts/gendba")
try:
    import protox_harvest as ph
    base, steps = ph.parse_steps(Path(sys.argv[1]))
    eps = sorted({s.get("rl_episode") for s in steps if s.get("rl_episode") is not None})
    best = min((s["metric"] for s in steps), default=None)
    print(f"parsed {len(steps)} step(s), {len(eps)} RL episode(s), "
          f"baseline={base['metric'] if base else None}, best_metric={best}")
except Exception as e:
    print(f"PARSE FAILED: {type(e).__name__}: {e}")
PY
)
    if [[ $parsed == PARSE\ FAILED* ]]; then
        warn "$parsed"
    else
        ok "$steps step dir(s), $size on /proj -- $parsed"
    fi
}

if (( ONCE )); then
    checkpoint
    exit 0
fi

# Stop when the trial stops advancing AND no Proto-X driver is alive. Matched on the
# exact script/driver, never a loose pattern -- `pkill -f`/`pgrep -f` on a broad
# pattern matches this very shell and has killed sessions on this project before.
driver_alive() {
    pgrep -f "[h]po\.py --config" >/dev/null 2>&1
}

idle=0
while true; do
    checkpoint || true
    if ! driver_alive; then
        idle=$((idle + 1))
        if (( idle >= 2 )); then
            log "no Proto-X driver for two consecutive ticks -- final checkpoint"
            checkpoint || true
            ok "done: $DEST"
            exit 0
        fi
        warn "driver not seen (tick $idle/2)"
    else
        idle=0
    fi
    sleep "$INTERVAL"
done
