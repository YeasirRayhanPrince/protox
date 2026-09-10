#!/bin/bash
# unitune_run.sh <arm_method> <benchmark> <tuning_budget_s> <sub_budget_s> [tag]
#
# One UniTune run = one Gen-DBA episode of the META-decision. The arm_method is the
# axis worth sweeping: alter / rb / ts pick between the SAME sub-problems by
# different rules, so two such episodes differ only in how the choice was made.
#
# Launched with setsid so the run outlives the shell that started it -- these are
# multi-hour runs and the session must not be able to take one down by accident.
set -u
RULE=${1:?arm_method: alter|rb|ts}
BENCH=${2:-job}
BUDGET=${3:-14400}
SUB=${4:-900}
TAG=${5:-$RULE}

REPO=${GENDBA_REPO:-/proj/pmoss-PG0/protox}
BUILD=${GENDBA_BUILD:-/mnt/protox}
TASK="gendba_${BENCH}_${TAG}"
INI="$REPO/unitune_run/${TASK}.ini"

# output_file is a hardcoded path in the base config, and TopAdvisor.run() loads it
# as history when it exists (alternative_adviser.py:357). Left shared, the second and
# third runs would boot pre-seeded with the first run's observations -- which destroys
# the only property this sweep exists to provide, that the runs differ solely in the
# arm-selection rule. Give each run its own file.
sed -e "s|^output_file = .*|output_file = $REPO/unitune_run/logs/${TASK}.res|" \
    -e "s|^arm_method = .*|arm_method = $RULE|" \
    -e "s|^tuning_budget = .*|tuning_budget = $BUDGET|" \
    -e "s|^sub_budget = .*|sub_budget = $SUB|" \
    -e "s|^task_id = .*|task_id = $TASK|" \
    "$REPO/unitune_run/${BENCH}_knob_index.ini" > "$INI"

export PGUSER=admin PGPASSWORD=password PYTHONNOUSERSITE=1 PYTHONPATH=.
source "$BUILD/miniconda3/etc/profile.d/conda.sh"
conda activate unitune
cd "$REPO/unitune/UniTune" || exit 1
LOG="$BUILD/logs/unitune_${TASK}.log"
setsid nohup python "$REPO/scripts/gendba/unitune_harvest.py" \
  --config-ini "$INI" --benchmark "$BENCH" \
  --out "$REPO/gendba_records" >"$LOG" 2>&1 &
echo "launched $TASK  rule=$RULE budget=${BUDGET}s sub=${SUB}s  pid=$!"
echo "  log: $LOG"
