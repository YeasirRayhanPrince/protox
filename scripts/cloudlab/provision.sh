#!/usr/bin/env bash
#
# provision.sh -- stand up a complete Proto-X / Gen-DBA training-data collection
# environment on a bare CloudLab node.
#
#   WHAT PERSISTS:  /proj/pmoss-PG0  (the repo, and job_dump/)  -- NFS, survives the node
#   WHAT DOES NOT:  everything else. This script rebuilds all of it.
#
# Nothing is ever written into /proj. The repo and the JOB dump there are read-only
# inputs. All build output, databases and snapshots land on node-local disk.
#
# USAGE
#   ./provision.sh                 # run every phase (idempotent; skips completed ones)
#   ./provision.sh --list          # show phases and their status
#   ./provision.sh --phase 3       # run exactly one phase
#   ./provision.sh --from 6        # run phase 6 onwards
#   ./provision.sh --force         # ignore completion markers and redo
#   ./provision.sh --skip-dsb      # omit DSB (saves ~90 min; JOB+TPC-H only)
#
# Expect ~2.5-3.5 h unattended on a 64-core node, dominated by DSB generation
# (serial, ~35 min) and the DSB load + vacuum (~60 min). Safe to re-run after an
# interruption: it resumes at the first incomplete phase.
#
# Requirements: Ubuntu 22.04, passwordless sudo, >=64 GB RAM, a spare local disk.
#
set -euo pipefail

# ---------------------------------------------------------------- configuration
PROJ=/proj/pmoss-PG0
REPO=$PROJ/protox
JOB_DUMP=$PROJ/job_dump

BUILD=/mnt/protox           # code, postgres, conda, ray results
DATA=/data/protox           # databases, generated data, snapshots
STATE=$BUILD/.provision     # phase completion markers
LOGDIR=$BUILD/logs

PG_VERSION=15.7
PG_PREFIX=$BUILD/pg15
PG_BIN=$PG_PREFIX/bin
PGUSER_NAME=admin
PGPASS=password
PGDB=benchbase

CONDA=$BUILD/miniconda3
ENV_PROTOX=protox           # python 3.9 -- Proto-X tuner
ENV_ISE=ise                 # python 3.10 -- index_selection_evaluation

SF=10                       # scale factor for TPC-H and DSB
JOBS=$(nproc)
BUILD_JOBS=$(( JOBS > 32 ? 32 : JOBS ))

SKIP_DSB=0
FORCE=0
ONLY_PHASE=""
FROM_PHASE=0

# ---------------------------------------------------------------------- helpers
c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_hdr=$'\033[1;36m'; c_off=$'\033[0m'
log()  { echo "${c_hdr}[$(date +%H:%M:%S)]${c_off} $*"; }
ok()   { echo "  ${c_ok}OK${c_off}   $*"; }
warn() { echo "  ${c_warn}WARN${c_off} $*"; }
die()  { echo "  ${c_err}FAIL${c_off} $*" >&2; exit 1; }

done_marker() { echo "$STATE/phase$1.done"; }
is_done()     { [[ $FORCE -eq 0 && -f $(done_marker "$1") ]]; }
mark_done()   { mkdir -p "$STATE"; date -Is > "$(done_marker "$1")"; }

# psql against the local cluster
psql_() { PGPASSWORD=$PGPASS "$PG_BIN/psql" -h localhost -p "${1:?port}" -U "$PGUSER_NAME" -d "${2:-$PGDB}" -v ON_ERROR_STOP=1 "${@:3}"; }

pg_start() { "$PG_BIN/pg_ctl" -D "$1" -l "$2" -w -t 300 start; }
pg_stop()  { "$PG_BIN/pg_ctl" -D "$1" -m fast -w -t 300 stop || true; }

# Create a cluster with settings tuned for bulk loading.
# $1 pgdata  $2 port
init_cluster() {
    local pgd=$1 port=$2
    rm -rf "$pgd"; mkdir -p "$pgd"; chmod 700 "$pgd"
    "$PG_BIN/initdb" -D "$pgd" -U "$PGUSER_NAME" --encoding=UTF8 --locale=C > "$LOGDIR/initdb_$port.log" 2>&1
    cat >> "$pgd/postgresql.conf" <<EOF
port = $port
listen_addresses = 'localhost'
shared_preload_libraries = 'pg_hint_plan'
shared_buffers = 32GB
work_mem = 4GB
maintenance_work_mem = 8GB
max_wal_size = 8GB
checkpoint_timeout = 30min
max_worker_processes = 20
max_parallel_workers = 20
EOF
    echo "host all all 127.0.0.1/32 md5" >> "$pgd/pg_hba.conf"
}

# Roles, database and the extension set every snapshot carries.
#   pg_hint_plan : Proto-X force-appends it to shared_preload_libraries every restart
#   hypopg       : what-if indexes -- required by index_selection_evaluation
#   pg_prewarm   : used by load_tpch.py
bootstrap_db() {
    local port=$1
    psql_ "$port" postgres -q -c "ALTER ROLE $PGUSER_NAME WITH PASSWORD '$PGPASS' SUPERUSER;"
    psql_ "$port" postgres -q -c "SELECT 1 FROM pg_database WHERE datname='$PGDB'" | grep -q 1 \
        || psql_ "$port" postgres -q -c "CREATE DATABASE $PGDB OWNER $PGUSER_NAME;"
    psql_ "$port" "$PGDB" -q -c "CREATE EXTENSION IF NOT EXISTS pg_hint_plan;"
    psql_ "$port" "$PGDB" -q -c "CREATE EXTENSION IF NOT EXISTS hypopg;"
    psql_ "$port" "$PGDB" -q -c "CREATE EXTENSION IF NOT EXISTS pg_prewarm;"
}

# Clean shutdown -> drop recycled WAL -> tar with "pgdata" as first path component,
# because envs/pg_env.py:268 restores with --strip-components 1.
# A freshly loaded cluster carries ~17 GB of recycled WAL that CHECKPOINT will not
# release; pg_resetwal after a clean stop drops it to ~17 MB. Every trial untars its
# own copy, so this is worth doing.
snapshot() {
    local pgd=$1 out=$2
    pg_stop "$pgd"
    "$PG_BIN/pg_resetwal" -D "$pgd" > /dev/null 2>&1
    local parent base stage
    parent=$(dirname "$pgd"); base=$(basename "$pgd")
    if [[ $base == pgdata ]]; then
        ( cd "$parent" && tar cf "$out" pgdata )
    else
        stage=$parent/_snapstage; rm -rf "$stage"; mkdir -p "$stage"
        mv "$pgd" "$stage/pgdata"
        ( cd "$stage" && tar cf "$out" pgdata )
        mv "$stage/pgdata" "$pgd"; rmdir "$stage"
    fi
    ok "snapshot $(basename "$out") ($(du -h "$out" | cut -f1))"
}

# =============================================================================
# PHASE 0 -- preflight
# =============================================================================
phase0() {
    log "PHASE 0: preflight"
    [[ -d $PROJ ]]      || die "$PROJ not mounted"
    [[ -d $REPO ]]      || die "repo not found at $REPO"
    [[ -d $JOB_DUMP ]]  || die "JOB dump not found at $JOB_DUMP"
    sudo -n true 2>/dev/null || die "passwordless sudo required (needed for drop_caches during replay)"
    grep -q "22.04" /etc/os-release || warn "not Ubuntu 22.04 -- proceeding anyway"
    local memgb; memgb=$(free -g | awk '/^Mem:/{print $2}')
    (( memgb >= 60 )) || warn "only ${memgb}GB RAM; knob space allows shared_buffers=32GB"
    ok "proj mounted, job_dump present, sudo ok, ${memgb}GB RAM, ${JOBS} cores"
    mkdir -p "$LOGDIR"
}

# =============================================================================
# PHASE 1 -- local storage
# CloudLab's mkextrafs claims free space on the BOOT disk. Any additional disk is
# untouched and must be formatted by hand. Keeping snapshots and per-trial pgdata
# copies on separate devices is the reason we bother with the second one.
# =============================================================================
phase1() {
    log "PHASE 1: local storage"
    if ! mountpoint -q /mnt; then
        if [[ -x /usr/local/etc/emulab/mkextrafs.pl ]]; then
            sudo /usr/local/etc/emulab/mkextrafs.pl -f /mnt >> "$LOGDIR/mkextrafs.log" 2>&1 || warn "mkextrafs failed"
        fi
    fi
    mountpoint -q /mnt && ok "/mnt $(df -h /mnt | awk 'NR==2{print $4}') free" || die "could not provision /mnt"

    # Find a whole disk with no partitions and no filesystem -- the spare.
    if ! mountpoint -q /data; then
        local spare=""
        while read -r name type; do
            [[ $type == disk ]] || continue
            [[ -z $(lsblk -no NAME "/dev/$name" | tail -n +2) ]] || continue   # has partitions
            blkid "/dev/$name" >/dev/null 2>&1 && continue                     # has a filesystem
            spare=$name; break
        done < <(lsblk -dno NAME,TYPE)
        if [[ -n $spare ]]; then
            log "  formatting spare disk /dev/$spare -> /data"
            sudo mkfs.ext4 -F -m 0 "/dev/$spare" >> "$LOGDIR/mkfs.log" 2>&1
            sudo mkdir -p /data
            grep -q " /data " /etc/fstab || echo "/dev/$spare /data ext4 defaults,nofail 0 0" | sudo tee -a /etc/fstab >/dev/null
            sudo mount /data
        else
            warn "no spare disk found; placing /data under /mnt"
            sudo mkdir -p /mnt/_data; sudo ln -sfn /mnt/_data /data
        fi
    fi
    sudo mkdir -p "$BUILD" "$DATA" "$DATA/data" "$DATA/gen" "$BUILD/ray_results"
    sudo chown -R "$USER" "$BUILD" "$DATA"
    [[ -L /data ]] || ok "/data $(df -h /data | awk 'NR==2{print $4}') free"
    mark_done 1
}

# =============================================================================
# PHASE 2 -- OS packages
# =============================================================================
phase2() {
    log "PHASE 2: OS packages"
    sudo apt-get update -qq >> "$LOGDIR/apt.log" 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        build-essential libreadline-dev zlib1g-dev flex bison libxml2-dev \
        libxslt1-dev libssl-dev libicu-dev pkg-config wget curl git ca-certificates \
        bc zstd >> "$LOGDIR/apt.log" 2>&1
    ok "build toolchain installed"
    mark_done 2
}

# =============================================================================
# PHASE 3 -- PostgreSQL + extensions
# Version window is PG 13-16: pg_stat_bgwriter.buffers_backend (removed in 17) and
# n_ins_since_vacuum (added in 13) are both part of the agent's state vector.
# postgres_path must be a FLAT dir holding pg_ctl/psql/pg_isready/postgres, and it
# must be writable -- per-trial pgdata<port> dirs are created inside it.
# =============================================================================
phase3() {
    log "PHASE 3: PostgreSQL $PG_VERSION + extensions"
    mkdir -p "$BUILD/src"; cd "$BUILD/src"
    if [[ ! -x $PG_BIN/postgres ]]; then
        [[ -f postgresql-$PG_VERSION.tar.bz2 ]] || \
            wget -q "https://ftp.postgresql.org/pub/source/v$PG_VERSION/postgresql-$PG_VERSION.tar.bz2"
        rm -rf "postgresql-$PG_VERSION"; tar xf "postgresql-$PG_VERSION.tar.bz2"
        cd "postgresql-$PG_VERSION"
        ./configure --prefix="$PG_PREFIX" --with-openssl --with-libxml --with-icu \
            --enable-thread-safety > "$LOGDIR/pg_configure.log" 2>&1
        make -j "$BUILD_JOBS" -s > "$LOGDIR/pg_make.log" 2>&1
        make install -s >> "$LOGDIR/pg_make.log" 2>&1
        for m in pg_prewarm pg_stat_statements pageinspect; do
            ( cd "contrib/$m" && make -s && make install -s ) >> "$LOGDIR/pg_make.log" 2>&1
        done
        cd "$BUILD/src"
    fi
    ok "postgres $("$PG_BIN/postgres" --version | awk '{print $3}')"

    export PATH=$PG_BIN:$PATH
    if [[ ! -f $PG_PREFIX/lib/postgresql/pg_hint_plan.so ]]; then
        rm -rf pg_hint_plan
        git clone -q -b PG15 https://github.com/ossc-db/pg_hint_plan.git
        ( cd pg_hint_plan && make -s && make install -s ) > "$LOGDIR/pg_hint_plan.log" 2>&1
    fi
    ok "pg_hint_plan"

    if [[ ! -f $PG_PREFIX/lib/postgresql/hypopg.so ]]; then
        rm -rf hypopg
        git clone -q https://github.com/HypoPG/hypopg.git
        ( cd hypopg && make -s && make install -s ) > "$LOGDIR/hypopg.log" 2>&1
    fi
    ok "hypopg"
    mark_done 3
}

# =============================================================================
# PHASE 4 -- Python environments
# Three gaps in requirements.txt that will bite you:
#   * pglast==3.8 is gone from PyPI (only >=5.0 remains) and 5.x dropped the
#     pglast.node API that envs/workload_utils.py uses -> build 3.8 from the tag.
#   * psutil is imported by envs/pg_env.py:1 but is not in requirements.txt.
#   * agents/common/env_checker.py imports legacy `gym`, but nothing imports
#     env_checker -- it is dead code. Do NOT install gym.
# Also: conda now refuses the `defaults` channel without accepting Anaconda ToS,
# so everything here uses conda-forge explicitly.
# =============================================================================
phase4() {
    log "PHASE 4: Python environments"
    if [[ ! -x $CONDA/bin/conda ]]; then
        wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O "$BUILD/miniconda.sh"
        bash "$BUILD/miniconda.sh" -b -p "$CONDA" > "$LOGDIR/miniconda.log" 2>&1
    fi
    # shellcheck disable=SC1091
    source "$CONDA/etc/profile.d/conda.sh"

    if ! conda env list | grep -q "^$ENV_PROTOX "; then
        conda create -y -q -n "$ENV_PROTOX" -c conda-forge --override-channels python=3.9 \
            > "$LOGDIR/conda_protox.log" 2>&1
    fi
    conda activate "$ENV_PROTOX"
    export PYTHONNOUSERSITE=1
    if ! python -c "import torch, ray, pglast, psutil" 2>/dev/null; then
        # CPU-only torch: the RL nets are tiny (pi 128,128 / qf 1024) and these
        # nodes have no GPU. Dropping the nvidia cu11 wheels saves ~2 GB.
        grep -v -E '^(nvidia-|triton==|torch==|pglast==)' "$REPO/requirements.txt" > /tmp/req-cpu.txt
        pip install -q torch==2.0.0 --index-url https://download.pytorch.org/whl/cpu >> "$LOGDIR/pip_protox.log" 2>&1
        pip install -q -r /tmp/req-cpu.txt >> "$LOGDIR/pip_protox.log" 2>&1
        pip install -q psutil >> "$LOGDIR/pip_protox.log" 2>&1
        ( cd "$BUILD/src" && rm -rf pglast \
          && git clone -q --recursive -b v3.8 https://github.com/lelit/pglast.git \
          && cd pglast && pip install -q cython setuptools wheel && pip install -q . ) \
            >> "$LOGDIR/pip_protox.log" 2>&1
    fi
    ( cd /tmp && python -c "import torch,ray,gymnasium,psycopg,faiss,pglast,psutil" ) \
        || die "protox env incomplete -- see $LOGDIR/pip_protox.log"
    ok "env '$ENV_PROTOX' (python $(python -V | awk '{print $2}'), torch $(python -c 'import torch;print(torch.__version__)'))"
    conda deactivate

    if ! conda env list | grep -q "^$ENV_ISE "; then
        conda create -y -q -n "$ENV_ISE" -c conda-forge --override-channels python=3.10 \
            > "$LOGDIR/conda_ise.log" 2>&1
    fi
    conda activate "$ENV_ISE"
    pip install -q psycopg2-binary tqdm >> "$LOGDIR/pip_ise.log" 2>&1
    ok "env '$ENV_ISE' (index_selection_evaluation)"
    conda deactivate
    mark_done 4
}

# =============================================================================
# PHASE 5 -- repo preparation
# The repo lives on /proj and persists, so this is mostly idempotent no-ops on a
# second machine. It is still run every time so a fresh clone works.
#
# THE MAIN TRAP: agents/hpo.py and agents/wolp/config.py prefix mythril_dir onto
# config / benchmark_config / model_config / data_snapshot_path UNCONDITIONALLY.
# Absolute values silently become /repo//abs/path. They must be RELATIVE -- which
# is why the shipped params.json reads "data/job.tgz". Hence the data symlink.
# Conversely execute_query_directory/_order (DSB) are opened directly and must be
# ABSOLUTE. And agents/hpo.py:60 overwrites the benchmark YAML's whole query_spec
# with mythril_query_spec from params.json, so patching the YAML alone is not enough.
# =============================================================================
phase5() {
    log "PHASE 5: repo preparation"
    cd "$REPO"

    git submodule update --init --recursive >> "$LOGDIR/submodules.log" 2>&1 || warn "submodule init issues"
    ok "submodules: $(git submodule status --recursive | wc -l) checked out"

    # Shipped pre-trained embeddings, staged at the relative paths params.json expects.
    mkdir -p job2_models tpch2_models dsb_data_models/curated tpcc_worlds
    cp -rn results/latent_spaces/spaces/job/model6  job2_models/               2>/dev/null || true
    cp -rn results/latent_spaces/spaces/tpch/model0 tpch2_models/              2>/dev/null || true
    cp -rn results/latent_spaces/spaces/dsb/model0  dsb_data_models/curated/   2>/dev/null || true
    cp -rn results/latent_spaces/spaces/tpcc/model0 tpcc_worlds/               2>/dev/null || true
    [[ -f job2_models/model6/embedder_19.pth && -f job2_models/model6/config ]] \
        || die "JOB embedding missing (need both the .pth and the sibling 'config')"
    ok "embeddings staged"

    # Snapshots must be reachable relative to the repo (see header comment).
    ln -sfn "$DATA/data" "$REPO/data"

    # benchbase XML stub. A bare <url/> is NOT enough: once per-query knobs are on
    # (every OLAP config sets allow_per_query), envs/spaces/utils.py:319 calls
    # root.find("transactiontypes") and iterates it unconditionally -- a missing
    # element is a TypeError thrown only AFTER the baseline workload has run.
    # Empty is correct here: per-query knobs reach queries as /*+ ... */ hints via
    # envs/workload.py:595, not through this file.
    cat > stub_benchbase.xml <<'XML'
<?xml version="1.0"?>
<parameters>
  <url></url>
  <transactiontypes></transactiontypes>
</parameters>
XML

    # Machine-local config; configs/config.yaml is left untouched.
    sed -e "s|^  benchbase_path:.*|  benchbase_path: $BUILD/benchbase|" \
        -e "s|^  benchbase_config_path:.*|  benchbase_config_path: \"$REPO/stub_benchbase.xml\"|" \
        -e "s|^  postgres_path:.*|  postgres_path: $PG_BIN|" \
        -e "s|^  data_snapshot_path:.*|  data_snapshot_path: \"$DATA/data/job.tgz\"|" \
        -e "s|^  output_log_path:.*|  output_log_path: $BUILD/artifacts/|" \
        -e "s|^  tensorboard_path:.*|  tensorboard_path: $BUILD/artifacts/runs/|" \
        -e "s|^  repository_path:.*|  repository_path: $BUILD/artifacts/repository/|" \
        -e "s|^  dump_path:.*|  dump_path: $BUILD/artifacts/dump.pickle|" \
        configs/config.yaml > configs/config_cloudlab.yaml
    for b in job tpch dsb; do
        case $b in
            job)  snap=job_base.tgz ;;
            tpch) snap=tpch_sf${SF}_base.tgz ;;
            dsb)  snap=dsb_sf${SF}_base.tgz ;;
        esac
        sed "s|^  data_snapshot_path:.*|  data_snapshot_path: \"$DATA/data/$snap\"|" \
            configs/config_cloudlab.yaml > "configs/config_cloudlab_$b.yaml"
    done

    # Query paths: prefixed only when relative, so the shipped absolute ones stay broken.
    sed -i -E 's|"/home/wz2/mythril/(queries/[^"]*)"|"\1"|' configs/benchmark/*.yaml

    # initial_*.json -- a JSON ARRAY (hpo.py:203 iterates and asserts "mythril_args"),
    # with every path fixed to the relative/absolute convention described above.
    "$CONDA/envs/$ENV_PROTOX/bin/python" - "$REPO" <<'PY'
import json, glob, sys, os
repo = sys.argv[1]
SNAP = {"job": "data/job.tgz", "tpch": "data/tpch_sf10.tgz", "dsb": "data/dsb_sf10.tgz"}
BCFG = {"job": "configs/benchmark/job_full.yaml",
        "tpch": "configs/benchmark/tpch.yaml",
        "dsb":  "configs/benchmark/dsb_s10.yaml"}
QD   = {"job": "queries/job_full", "tpch": "queries/tpch", "dsb": "queries/dsb_10"}
QO   = {"job": "queries/job_full/order.txt", "tpch": "queries/tpch/order.txt",
        "dsb": "queries/dsb_10/d_order.txt"}
for b in ("job", "tpch", "dsb"):
    out = []
    for f in sorted(glob.glob(f"{repo}/results/{b}/us/*/params.json")):
        d = json.load(open(f)); ma = d["mythril_args"]
        ma["mythril_dir"]          = repo
        ma["config"]               = "configs/config_cloudlab.yaml"   # relative
        ma["benchmark_config"]     = BCFG[b]                          # relative
        ma["model_config"]         = "configs/wolp_params.yaml"       # relative
        ma["data_snapshot_path"]   = SNAP[b]                          # relative
        ma["benchbase_config_path"] = f"{repo}/stub_benchbase.xml"    # absolute
        qs = d["mythril_query_spec"]          # overrides the YAML at agents/hpo.py:60
        qs["query_directory"] = QD[b]
        qs["query_order"]     = QO[b]
        if "execute_query_order" in qs:       # DSB: opened directly, must be absolute
            qs["execute_query_directory"] = f"{repo}/queries/dsb_revise"
            qs["execute_query_order"]     = f"{repo}/queries/dsb_revise/d_order.txt"
        out.append(d)
    p = f"{repo}/initial_{b}.json"
    json.dump(out, open(p, "w"), indent=2)
    arr = json.load(open(p))
    assert isinstance(arr, list) and all("mythril_args" in c for c in arr), "hpo.py:203 assert would fail"
    print(f"  initial_{b}.json: {len(arr)} configs")
PY
    grep -l "/home/wz2" initial_*.json 2>/dev/null && die "author paths remain in initial_*.json"
    ok "configs patched, no author paths remain"
    mkdir -p "$BUILD/artifacts"

    # Ray defaults to ~/ray_results -- the NFS home with a small quota -- and
    # agents/hpo.py:102-105 redirects repository/, tboard/ and the log into the trial
    # dir, so the entire scientific output would land there. Redirect to local disk.
    rm -rf "$HOME/ray_results"
    ln -sfn "$BUILD/ray_results" "$HOME/ray_results"
    ok "ray_results -> $BUILD/ray_results (keeps artifacts off NFS)"
    mark_done 5
}

# =============================================================================
# PHASE 6a -- JOB / IMDb, restored from the persistent dump
# =============================================================================
phase6_job() {
    log "PHASE 6a: JOB / IMDb"
    local pgd=$DATA/pgdata_job port=5432
    init_cluster "$pgd" $port
    pg_start "$pgd" "$LOGDIR/pg_job.log"
    bootstrap_db $port

    # The dump was taken from a Bao-instrumented PG 12.5; cuckoo and pg_bao do not
    # exist in a vanilla build, so filter those TOC entries out.
    "$PG_BIN/pg_restore" -l "$JOB_DUMP" | grep -vE "EXTENSION" > "$LOGDIR/job_restore.list"
    PGPASSWORD=$PGPASS "$PG_BIN/pg_restore" -h localhost -p $port -U "$PGUSER_NAME" -d "$PGDB" \
        -L "$LOGDIR/job_restore.list" --no-owner --no-acl -j "$BUILD_JOBS" "$JOB_DUMP" \
        >> "$LOGDIR/job_restore.log" 2>&1
    local n; n=$(psql_ $port "$PGDB" -t -c "SELECT count(*) FROM cast_info;" | tr -d ' ')
    [[ $n == 36244344 ]] || warn "cast_info=$n (expected 36244344)"
    ok "restored: cast_info=$n"

    psql_ $port "$PGDB" -q -c "VACUUM (FULL, ANALYZE);"
    psql_ $port "$PGDB" -q -c "ANALYZE;"
    snapshot "$pgd" "$DATA/data/job_base.tgz"

    # Baseline starting configuration: the paper's 6 IMDb foreign-key indexes.
    apply_baseline job "$REPO/scripts/experiments/job_full/load_job_full.py" \
                   "--config-file $REPO/configs/config_cloudlab_job.yaml"
    finalize_snapshot "$DATA/data/job.tgz"
    mark_done 61
}

# =============================================================================
# PHASE 6b -- TPC-H SF10, generated locally
# dbgen writes SOME chunk files mode --x-----x; without chmod the COPY silently
# loads only a subset. Rows DO end with a trailing '|', so it is stripped.
# =============================================================================
phase6_tpch() {
    log "PHASE 6b: TPC-H SF$SF"
    local gen=$DATA/gen/tpch pgd=$DATA/pgdata_tpch port=5433
    if [[ ! -f $gen/.generated ]]; then
        cd "$BUILD/src"
        [[ -d tpch-dbgen ]] || git clone -q https://github.com/electrum/tpch-dbgen.git
        ( cd tpch-dbgen && make -s ) > "$LOGDIR/dbgen_build.log" 2>&1
        mkdir -p "$gen"; cp "$BUILD/src/tpch-dbgen/dists.dss" "$gen/"
        log "  generating (16-way)..."
        for i in $(seq 1 16); do
            ( cd "$gen" && DSS_PATH=$gen "$BUILD/src/tpch-dbgen/dbgen" -s "$SF" -C 16 -S "$i" -f >/dev/null 2>&1 ) &
        done; wait
        chmod 644 "$gen"/*.tbl*          # <-- essential, see comment above
        touch "$gen/.generated"
    fi
    ok "generated $(du -sh "$gen" | cut -f1)"

    init_cluster "$pgd" $port
    pg_start "$pgd" "$LOGDIR/pg_tpch.log"
    bootstrap_db $port
    write_tpch_ddl
    psql_ $port "$PGDB" -q -f "$BUILD/ddl/tpch_tables_nopk.sql"
    : > /tmp/tpch_copy.sql
    for t in region nation part supplier partsupp customer orders lineitem; do
        for f in "$gen/$t".tbl*; do
            [[ -e $f ]] || continue
            echo "COPY $t FROM PROGRAM 'sed -e ''s/|\$//'' $f' WITH (FORMAT csv, DELIMITER '|');" >> /tmp/tpch_copy.sql
        done
    done
    parallel_copy $port /tmp/tpch_copy.sql 16
    local n; n=$(psql_ $port "$PGDB" -t -c "SELECT count(*) FROM lineitem;" | tr -d ' ')
    [[ $n == 59986052 ]] || warn "lineitem=$n (expected 59986052)"
    ok "loaded: lineitem=$n"

    add_pks $port "$BUILD/ddl/tpch_pk.sql"
    psql_ $port "$PGDB" -q -c "VACUUM (FULL, ANALYZE);"
    snapshot "$pgd" "$DATA/data/tpch_sf${SF}_base.tgz"

    apply_baseline tpch "$REPO/scripts/experiments/tpch_sf10/load_tpch.py" \
                   "--config-file $REPO/configs/config_cloudlab_tpch.yaml"
    finalize_snapshot "$DATA/data/tpch_sf${SF}.tgz"
    mark_done 62
}

# =============================================================================
# PHASE 6c -- DSB SF10, generated locally
# Two traps. (1) The tools need -fcommon on GCC 11 or dsqgen fails to link and
# dsdgen segfaults. (2) Even rebuilt, -PARALLEL/-CHILD segfaults for every child
# but 1 -- DSB's own generate_dsb_db_files.py runs it serially, so we do too.
# (3) With -TERMINATE N there is NO trailing separator: unlike TPC-H you must NOT
# strip the last '|' or every row loses its final column.
# =============================================================================
phase6_dsb() {
    log "PHASE 6c: DSB SF$SF"
    local gen=$DATA/gen/dsb pgd=$DATA/pgdata_dsb port=5434
    if [[ ! -f $gen/.generated ]]; then
        cd "$BUILD/src"
        [[ -d dsb ]] || git clone -q https://github.com/microsoft/dsb.git
        ( cd dsb/code/tools && make -f Makefile.suite clean >/dev/null 2>&1 || true
          make -f Makefile.suite -j "$BUILD_JOBS" \
               LINUX_CFLAGS="-g -O2 -fcommon -Wno-format-security -Wno-implicit-function-declaration" ) \
            > "$LOGDIR/dsdgen_build.log" 2>&1
        mkdir -p "$gen"
        log "  generating serially (~35 min; parallel mode is broken upstream)..."
        ( cd "$BUILD/src/dsb/code/tools" && ./dsdgen -SCALE "$SF" -DIR "$gen" -TERMINATE N -FORCE ) \
            > "$LOGDIR/dsdgen.log" 2>&1
        chmod 644 "$gen"/*.dat
        touch "$gen/.generated"
    fi
    ok "generated $(du -sh "$gen" | cut -f1)"

    init_cluster "$pgd" $port
    pg_start "$pgd" "$LOGDIR/pg_dsb.log"
    bootstrap_db $port
    split_dsb_ddl
    psql_ $port "$PGDB" -q -f "$BUILD/ddl/dsb_tables_nopk.sql"
    : > /tmp/dsb_copy.sql
    for f in "$gen"/*.dat; do
        echo "COPY $(basename "$f" .dat) FROM '$f' WITH (FORMAT csv, DELIMITER '|', NULL '', QUOTE E'\b');" >> /tmp/dsb_copy.sql
    done
    parallel_copy $port /tmp/dsb_copy.sql 8
    local n; n=$(psql_ $port "$PGDB" -t -c "SELECT count(*) FROM store_sales;" | tr -d ' ')
    [[ $n == 28800991 ]] || warn "store_sales=$n (expected 28800991)"
    ok "loaded: store_sales=$n"

    add_pks $port "$BUILD/ddl/dsb_pk.sql"
    psql_ $port "$PGDB" -q -c "VACUUM (FULL, ANALYZE);"
    snapshot "$pgd" "$DATA/data/dsb_sf${SF}_base.tgz"

    apply_baseline dsb "$REPO/scripts/experiments/dsb_sf10/load_dsb.py" \
                   "--config-file $REPO/configs/config_cloudlab_dsb.yaml --sf $SF --stream 1"
    finalize_snapshot "$DATA/data/dsb_sf${SF}.tgz"
    mark_done 63
}

# ------------------------------------------------------------ phase 6 helpers
# Run COPY statements N ways in parallel.
parallel_copy() {
    local port=$1 file=$2 ways=$3 p
    rm -f /tmp/_cp_part_*; split -n "l/$ways" "$file" /tmp/_cp_part_
    for p in /tmp/_cp_part_*; do
        ( psql_ "$port" "$PGDB" -q -f "$p" > "$LOGDIR/copy_$(basename "$p").log" 2>&1 \
          || echo "COPY FAILED $p: $(tail -2 "$LOGDIR/copy_$(basename "$p").log")" ) &
    done; wait
}

# Add primary keys after loading -- far faster than loading into indexed tables.
add_pks() {
    local port=$1 file=$2 n=0
    while read -r stmt; do
        [[ -z $stmt ]] && continue
        ( psql_ "$port" "$PGDB" -q -c "SET maintenance_work_mem='3GB'; SET max_parallel_maintenance_workers=4; $stmt" \
          >/dev/null 2>&1 || echo "PK FAILED: $stmt" ) &
        n=$((n+1)); (( n % 6 == 0 )) && wait
    done < "$file"
    wait
    ok "primary keys built"
}

# Run the repo's own load_*.py to apply the paper's baseline starting configuration.
# Both scripts fail at the very end for benign reasons and we tolerate it:
#   load_tpch.py  -- CREATE EXTENSION pg_prewarm when it already exists; only cache
#                    warming follows, which a snapshot does not preserve anyway.
#   load_dsb.py   -- opens a hardcoded /mnt/nvme0n1/wz2/... path, assigns it to a
#                    local, and never uses it. Dead code at the end of the file.
# The indexes and knob changes complete before either failure.
apply_baseline() {
    local bench=$1 script=$2 args=$3
    # shellcheck disable=SC1091
    source "$CONDA/etc/profile.d/conda.sh"; conda activate "$ENV_PROTOX"
    export PYTHONNOUSERSITE=1
    cd "$REPO"
    # shellcheck disable=SC2086
    python "$script" $args > "$LOGDIR/load_$bench.log" 2>&1 || true
    local created; created=$(grep -c "Executing CREATE INDEX" "$LOGDIR/load_$bench.log" || true)
    (( created > 0 )) || die "no baseline indexes created for $bench -- see $LOGDIR/load_$bench.log"
    ok "baseline: $created indexes applied"
    conda deactivate
}

# load_*.py restores into $PG_BIN/pgdata; snapshot that as the starting state.
finalize_snapshot() {
    local out=$1 pgd=$PG_BIN/pgdata
    PGPASSWORD=$PGPASS "$PG_BIN/psql" -h localhost -p 5432 -U "$PGUSER_NAME" -d "$PGDB" \
        -q -c "ANALYZE;" >/dev/null 2>&1 || true
    snapshot "$pgd" "$out"
    rm -rf "$pgd"
}

write_tpch_ddl() {
    mkdir -p "$BUILD/ddl"
    cat > "$BUILD/ddl/tpch_tables_nopk.sql" <<'SQL'
DROP TABLE IF EXISTS lineitem, orders, partsupp, part, supplier, customer, nation, region CASCADE;
CREATE TABLE region   (r_regionkey INTEGER NOT NULL, r_name CHAR(25) NOT NULL, r_comment VARCHAR(152));
CREATE TABLE nation   (n_nationkey INTEGER NOT NULL, n_name CHAR(25) NOT NULL, n_regionkey INTEGER NOT NULL, n_comment VARCHAR(152));
CREATE TABLE part     (p_partkey INTEGER NOT NULL, p_name VARCHAR(55) NOT NULL, p_mfgr CHAR(25) NOT NULL, p_brand CHAR(10) NOT NULL, p_type VARCHAR(25) NOT NULL, p_size INTEGER NOT NULL, p_container CHAR(10) NOT NULL, p_retailprice DECIMAL(15,2) NOT NULL, p_comment VARCHAR(23) NOT NULL);
CREATE TABLE supplier (s_suppkey INTEGER NOT NULL, s_name CHAR(25) NOT NULL, s_address VARCHAR(40) NOT NULL, s_nationkey INTEGER NOT NULL, s_phone CHAR(15) NOT NULL, s_acctbal DECIMAL(15,2) NOT NULL, s_comment VARCHAR(101) NOT NULL);
CREATE TABLE partsupp (ps_partkey INTEGER NOT NULL, ps_suppkey INTEGER NOT NULL, ps_availqty INTEGER NOT NULL, ps_supplycost DECIMAL(15,2) NOT NULL, ps_comment VARCHAR(199) NOT NULL);
CREATE TABLE customer (c_custkey INTEGER NOT NULL, c_name VARCHAR(25) NOT NULL, c_address VARCHAR(40) NOT NULL, c_nationkey INTEGER NOT NULL, c_phone CHAR(15) NOT NULL, c_acctbal DECIMAL(15,2) NOT NULL, c_mktsegment CHAR(10) NOT NULL, c_comment VARCHAR(117) NOT NULL);
CREATE TABLE orders   (o_orderkey INTEGER NOT NULL, o_custkey INTEGER NOT NULL, o_orderstatus CHAR(1) NOT NULL, o_totalprice DECIMAL(15,2) NOT NULL, o_orderdate DATE NOT NULL, o_orderpriority CHAR(15) NOT NULL, o_clerk CHAR(15) NOT NULL, o_shippriority INTEGER NOT NULL, o_comment VARCHAR(79) NOT NULL);
CREATE TABLE lineitem (l_orderkey INTEGER NOT NULL, l_partkey INTEGER NOT NULL, l_suppkey INTEGER NOT NULL, l_linenumber INTEGER NOT NULL, l_quantity DECIMAL(15,2) NOT NULL, l_extendedprice DECIMAL(15,2) NOT NULL, l_discount DECIMAL(15,2) NOT NULL, l_tax DECIMAL(15,2) NOT NULL, l_returnflag CHAR(1) NOT NULL, l_linestatus CHAR(1) NOT NULL, l_shipdate DATE NOT NULL, l_commitdate DATE NOT NULL, l_receiptdate DATE NOT NULL, l_shipinstruct CHAR(25) NOT NULL, l_shipmode CHAR(10) NOT NULL, l_comment VARCHAR(44) NOT NULL);
SQL
    cat > "$BUILD/ddl/tpch_pk.sql" <<'SQL'
ALTER TABLE region ADD PRIMARY KEY (r_regionkey);
ALTER TABLE nation ADD PRIMARY KEY (n_nationkey);
ALTER TABLE part ADD PRIMARY KEY (p_partkey);
ALTER TABLE supplier ADD PRIMARY KEY (s_suppkey);
ALTER TABLE partsupp ADD PRIMARY KEY (ps_partkey, ps_suppkey);
ALTER TABLE customer ADD PRIMARY KEY (c_custkey);
ALTER TABLE orders ADD PRIMARY KEY (o_orderkey);
ALTER TABLE lineitem ADD PRIMARY KEY (l_orderkey, l_linenumber);
SQL
}

# DSB ships the TPC-DS DDL; split PKs out so COPY runs against heap-only tables.
split_dsb_ddl() {
    mkdir -p "$BUILD/ddl"
    "$CONDA/envs/$ENV_ISE/bin/python" - "$BUILD/src/dsb/scripts/create_tables.sql" "$BUILD/ddl" <<'PY'
import re, sys
src = re.sub(r'--.*', '', open(sys.argv[1]).read())
out = sys.argv[2]
tables, pks = [], []
for m in re.finditer(r'create\s+table\s+(\w+)\s*\((.*?)\n\)\s*;', src, re.S | re.I):
    name, body = m.group(1), m.group(2)
    lines, pk = [], None
    for ln in body.split('\n'):
        s = ln.strip().rstrip(',')
        if not s: continue
        if s.lower().startswith('primary key'):
            pk = re.search(r'\((.*?)\)', s).group(1)
        else:
            lines.append('    ' + s)
    tables.append(f"CREATE TABLE {name} (\n" + ",\n".join(lines) + "\n);")
    if pk: pks.append(f"ALTER TABLE {name} ADD PRIMARY KEY ({pk});")
names = [re.search(r'CREATE TABLE (\w+)', t).group(1) for t in tables]
open(f"{out}/dsb_tables_nopk.sql", "w").write(
    "DROP TABLE IF EXISTS " + ", ".join(names) + " CASCADE;\n\n" + "\n\n".join(tables) + "\n")
open(f"{out}/dsb_pk.sql", "w").write("\n".join(pks) + "\n")
print(f"  {len(tables)} tables, {len(pks)} primary keys")
PY
}

# =============================================================================
# PHASE 7 -- verification
# =============================================================================
phase7() {
    log "PHASE 7: verification"
    local pgd=$DATA/_verify port=5439 fail=0
    for f in "$PG_BIN/pg_ctl" "$PG_BIN/psql" "$PG_BIN/pg_isready" "$PG_BIN/postgres"; do
        [[ -x $f ]] || { warn "missing $f"; fail=1; }
    done
    [[ -w $PG_BIN ]] || { warn "$PG_BIN not writable (pgdata<port> dirs are created there)"; fail=1; }

    for s in job tpch_sf${SF} dsb_sf${SF}; do
        if [[ -f $DATA/data/$s.tgz ]]; then
            ok "snapshot $s.tgz ($(du -h "$DATA/data/$s.tgz" | cut -f1))"
        elif [[ $s == dsb_sf${SF} && $SKIP_DSB -eq 1 ]]; then
            warn "snapshot $s.tgz skipped (--skip-dsb)"
        else
            warn "snapshot $s.tgz MISSING"; fail=1
        fi
    done

    # Restore JOB and run the version-sensitive probes from the setup doc.
    rm -rf "$pgd"; mkdir -p -m 0700 "$pgd"
    tar xf "$DATA/data/job.tgz" -C "$pgd" --strip-components 1
    echo "port=$port" >> "$pgd/postgresql.conf"
    pg_start "$pgd" "$LOGDIR/pg_verify.log" >/dev/null
    psql_ $port "$PGDB" -tAc "SELECT buffers_backend FROM pg_stat_bgwriter;" >/dev/null \
        && ok "pg_stat_bgwriter.buffers_backend present (would fail on PG 17)" || { warn "bgwriter probe failed"; fail=1; }
    psql_ $port "$PGDB" -tAc "SELECT n_ins_since_vacuum FROM pg_stat_user_tables LIMIT 1;" >/dev/null \
        && ok "n_ins_since_vacuum present (would fail on PG 12)" || { warn "n_ins probe failed"; fail=1; }
    psql_ $port "$PGDB" -tAc "SELECT extname FROM pg_extension;" | tr '\n' ' ' | sed 's/^/  extensions: /'
    echo
    # Exercise the exact what-if sequence index_selection_evaluation depends on
    # (selection/dbms/postgres_dbms.py:32-128). Note hypopg >=1.4 renamed
    # hypopg_list_indexes() to hypopg(); ISE only calls the old name from
    # index_names(), which its own comment marks as never used -- so 1.4.x is fine.
    # Hypothetical indexes are session-local, hence the single -tA session below.
    if psql_ $port "$PGDB" -tA >/dev/null 2>&1 <<'SQL'
SET hypopg.use_real_oids = on;
SELECT indexname FROM hypopg_create_index('CREATE INDEX ON title (production_year)');
SELECT hypopg_relation_size(indexrelid) FROM hypopg();
SQL
    then ok "hypopg what-if path callable (index_selection_evaluation)"
    else warn "hypopg probe failed"; fail=1; fi
    pg_stop "$pgd"; rm -rf "$pgd"

    cd "$REPO"
    [[ -L data && -e data ]] && ok "data symlink resolves" || { warn "data symlink broken"; fail=1; }
    grep -q "/home/wz2" initial_*.json 2>/dev/null && { warn "author paths in initial_*.json"; fail=1; } \
        || ok "initial_*.json clean"
    [[ -d "$HOME/ray_results" ]] && ok "ray_results redirected off NFS"

    (( fail == 0 )) && echo "  ${c_ok}ALL CHECKS PASSED${c_off}" || echo "  ${c_err}SOME CHECKS FAILED${c_off}"
    mark_done 7
    return 0
}

# =============================================================================
# PHASE 8 -- Ray head node (hpo.py hard-connects to localhost:6379)
# =============================================================================
phase8() {
    log "PHASE 8: ray"
    # shellcheck disable=SC1091
    source "$CONDA/etc/profile.d/conda.sh"; conda activate "$ENV_PROTOX"
    export PYTHONNOUSERSITE=1
    ray status >/dev/null 2>&1 && { ok "ray already running"; mark_done 8; return; }
    OMP_NUM_THREADS=8 ray start --head --port=6379 --num-cpus=4 --temp-dir="$BUILD/ray" \
        > "$LOGDIR/ray.log" 2>&1
    sleep 5
    ray status >/dev/null 2>&1 && ok "ray head up on localhost:6379" || warn "ray did not start"
    mark_done 8
}

# ------------------------------------------------------------------------ main
PHASES="0:preflight 1:storage 2:packages 3:postgres 4:python 5:repo 61:job 62:tpch 63:dsb 7:verify 8:ray"

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --list)     for p in $PHASES; do
                        n=${p%%:*}; d=${p##*:}
                        is_done "$n" && s="${c_ok}done${c_off}" || s="${c_warn}pending${c_off}"
                        printf "  %-4s %-10s %b\n" "$n" "$d" "$s"
                    done; exit 0 ;;
        --phase)    ONLY_PHASE=$2; shift 2 ;;
        --from)     FROM_PHASE=$2; shift 2 ;;
        --force)    FORCE=1; shift ;;
        --skip-dsb) SKIP_DSB=1; shift ;;
        -h|--help)  usage ;;
        *) die "unknown argument: $1" ;;
    esac
done

run_phase() {
    local n=$1 fn=$2
    [[ -n $ONLY_PHASE && $ONLY_PHASE != "$n" ]] && return 0
    (( ${n%%[!0-9]*} < FROM_PHASE )) && return 0
    if is_done "$n"; then log "PHASE $n: already complete (--force to redo)"; return 0; fi
    $fn
}

mkdir -p "$LOGDIR" 2>/dev/null || true
phase0                      # always -- cheap, and catches a broken node early
run_phase 1  phase1
run_phase 2  phase2
run_phase 3  phase3
run_phase 4  phase4
run_phase 5  phase5
run_phase 61 phase6_job
run_phase 62 phase6_tpch
if (( SKIP_DSB == 0 )); then run_phase 63 phase6_dsb; else log "PHASE 63: skipped (--skip-dsb)"; fi
run_phase 7  phase7
run_phase 8  phase8

cat <<EOF

${c_hdr}Provisioning complete.${c_off}
  snapshots   $DATA/data/
  postgres    $PG_BIN
  envs        conda activate $ENV_PROTOX   (Proto-X)
              conda activate $ENV_ISE      (index_selection_evaluation)
  logs        $LOGDIR

  source $CONDA/etc/profile.d/conda.sh && conda activate $ENV_PROTOX
  cd $REPO && ./scripts/cloudlab/run_protox.sh job
EOF
