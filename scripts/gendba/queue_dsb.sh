#!/usr/bin/env bash
#
# queue_dsb.sh -- waits for the running harvest to finish, then swaps the cluster to
# DSB and harvests it.
#
# DSB is not JOB. It ships 489 queries over 34 templates x {aggregate, _spj} = 67
# distinct shapes, and individual queries are far heavier. So:
#   * queries are chosen one-per-shape, not head-of-list, or we would sample a
#     handful of templates ten times over and call it coverage
#   * a timing probe runs BEFORE the sweep, because at ~6 min/pass the full sweep
#     would not fit in a day and we would rather know that up front than at episode 30
#
set -euo pipefail
PGBIN=/mnt/protox/pg15/bin
REPO=/proj/pmoss-PG0/protox
OUT=$REPO/gendba_records
LOG=/mnt/protox/logs
export PGUSER=admin PGPASSWORD=password
export GENDBA_PARALLEL=1 GENDBA_ISOLATION=dedicated_cluster_sequential

echo "[queue] waiting for the current harvest to finish ..."
while pgrep -f "[h]arvest.py" >/dev/null; do sleep 60; done
echo "[queue] previous harvest done at $(date -Is)"

echo "[queue] swapping cluster to DSB SF10 ..."
pgd=/data/protox/pgdata_ise
$PGBIN/pg_ctl -D $pgd -m fast -w stop >/dev/null 2>&1 || true
rm -rf $pgd; mkdir -p -m 0700 $pgd
tar xf /data/protox/data/dsb_sf10_base.tgz -C $pgd --strip-components 1
sed -i -E '/^\s*port\s*=/d' $pgd/postgresql.conf
echo "port = 5492" >> $pgd/postgresql.conf
$PGBIN/pg_ctl -D $pgd -l /data/protox/pg_dsb_ise.log -w -t 600 start >/dev/null
$PGBIN/psql -h localhost -p 5492 -d benchbase -tAc \
  "SELECT 'dsb up: '||current_setting('shared_buffers')||' | indexes='||
   (SELECT count(*) FROM pg_indexes WHERE schemaname='public')||
   ' | store_sales='||(SELECT count(*) FROM store_sales);"

source /mnt/protox/miniconda3/etc/profile.d/conda.sh
conda activate ise
cd $REPO

echo "[queue] timing probe: one baseline pass over the selected workload ..."
python - <<'PY'
import sys, time
sys.path.insert(0, "/proj/pmoss-PG0/protox/scripts/gendba")
from env import IndexTuningEnv, Task
t = Task(benchmark="dsb", n_queries=67, query_select="one-per-shape", budget_mb=500)
env = IndexTuningEnv(t, port=5492, query_timeout_s=300)
env.reset()
print(f"  selected {len(env.queries)} queries")
t0 = time.time(); env.prime(); print(f"  prime pass: {time.time()-t0:.0f}s")
t0 = time.time(); per_q, proto = env._measure(env.queries)
dur = time.time() - t0
print(f"  measured pass: {dur:.0f}s  workload={sum(per_q.values())/1000:.1f}s")
print(f"  failed/timeout: {proto['failed'] or 'none'}")
slow = sorted(per_q.items(), key=lambda x: -x[1])[:5]
print("  slowest:", ", ".join(f"{q}={ms/1000:.1f}s" for q, ms in slow))
print(f"  ESTIMATE per episode ~= {2*dur + 60:.0f}s  -> 42 episodes ~= {(2*dur+60)*42/3600:.1f}h")
env.conn.close()
PY

echo "[queue] starting DSB harvest ..."
python scripts/gendba/harvest.py --benchmarks dsb \
  --algorithms extend,relaxation,auto_admin \
  --budgets 50,100,250,500,1000,2500 --widths 1,2 \
  --queries 67 --query-select one-per-shape --adjudicate-k 5 --out "$OUT"
python scripts/gendba/harvest.py --benchmarks dsb --algorithms drop \
  --budgets 50,100,250,500,1000,2500 --widths 2 \
  --queries 67 --query-select one-per-shape --adjudicate-k 5 --out "$OUT"
echo "[queue] DSB harvest complete at $(date -Is)"
