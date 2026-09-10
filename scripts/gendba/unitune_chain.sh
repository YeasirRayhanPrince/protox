#!/bin/bash
# unitune_chain.sh -- run the meta-rule sweep back to back, with no idle gaps.
#
# Each run holds the same cluster and restarts it to apply knobs, so they cannot
# overlap. The chain exists so the machine is never sitting idle between them.
#
# The sweep varies ONLY the arm-selection rule. Same benchmark, same arms, same
# sub-tuners, same budget -- so the four episodes are directly comparable and the
# difference between them is attributable to the meta-decision alone.
set -u
REPO=${GENDBA_REPO:-/proj/pmoss-PG0/protox}
BUILD=${GENDBA_BUILD:-/mnt/protox}
BENCH=${BENCH:-job}
BUDGET=${BUDGET:-14400}
SUB=${SUB:-900}
# `acq` is deliberately absent: TopAdvisor.run() dispatches only alter/rb/ts (and
# udo), so passing acq spins the budget loop calling nothing until the time is gone.
# optimize_acq exists but is unreachable -- it would need a dispatch patch and it is
# untested against our surrogates, so it is not worth spending a 4h slot on blind.
RULES=${RULES:-"ts rb alter"}
# Stop starting new runs once the machine's remaining time cannot hold one.
DEADLINE_EPOCH=${DEADLINE_EPOCH:-$(date -u -d '2026-09-11 01:59' +%s)}

for rule in $RULES; do
  left=$(( DEADLINE_EPOCH - $(date -u +%s) ))
  if [ "$left" -lt $(( BUDGET + 1800 )) ]; then
    echo "$(date -u +%FT%TZ) SKIP $rule: ${left}s left < budget+overhead" ; continue
  fi
  echo "$(date -u +%FT%TZ) START $rule (${left}s left)"
  "$REPO/scripts/gendba/unitune_run.sh" "$rule" "$BENCH" "$BUDGET" "$SUB" "$rule"
  sleep 30
  # Wait for it. The pattern is assembled at runtime so this script's own argv can
  # never match it -- an earlier pkill on the literal name killed the calling shell.
  pat="unitune_"$'harvest'".py"
  while pgrep -f "$pat" >/dev/null; do sleep 60; done
  echo "$(date -u +%FT%TZ) DONE $rule"
done
echo "$(date -u +%FT%TZ) chain complete"
