#!/usr/bin/env bash
#
# Proto-X starter pack for a bare CloudLab node.
#
# Assumes: freshly instantiated Ubuntu 22.04/24.04 CloudLab node, nothing installed,
#          passwordless sudo, network access. Nothing else.
#
# Usage:
#   scp docs/cloudlab_bootstrap.sh <node>:~/ && ssh <node>
#   chmod +x cloudlab_bootstrap.sh
#   ./cloudlab_bootstrap.sh                  # run every phase
#   ./cloudlab_bootstrap.sh claude           # just onboard Claude Code, then stop
#   ./cloudlab_bootstrap.sh --from postgres  # resume from a phase
#   ./cloudlab_bootstrap.sh --list           # show phases
#
# Every phase is idempotent: re-running skips work that is already done.
# Full log lands in $ROOT/bootstrap.log
#
set -Eeuo pipefail

# ----------------------------------------------------------------------------
# Tunables (override from the environment)
# ----------------------------------------------------------------------------
ROOT="${ROOT:-/mnt/protox}"           # everything lives here, on LOCAL disk
PG_VERSION="${PG_VERSION:-15.8}"      # 13..16 are valid; see docs/CLOUDLAB_SETUP.md
PG_MAJOR="${PG_VERSION%%.*}"
PROTOX_REPO="${PROTOX_REPO:-https://github.com/17zhangw/protox.git}"
PROTOX_BRANCH="${PROTOX_BRANCH:-vldb24}"
CONDA_ENV="${CONDA_ENV:-protox}"
PY_VERSION="${PY_VERSION:-3.9}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
WITH_SUBMODULES="${WITH_SUBMODULES:-0}"   # 1 = also fetch baseline submodules (UDO, Auto-Steer, ...)

PHASES=(preflight storage packages claude conda postgres extensions protox pyenv verify)

# ----------------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_B=$'\033[1m'; C_G=$'\033[32m'; C_Y=$'\033[33m'; C_R=$'\033[31m'; C_D=$'\033[2m'; C_0=$'\033[0m'
else
  C_B=""; C_G=""; C_Y=""; C_R=""; C_D=""; C_0=""
fi
phase()  { printf '\n%s==> [%s] %s%s\n' "$C_B" "$1" "$2" "$C_0"; }
info()   { printf '    %s\n' "$*"; }
ok()     { printf '    %s✓%s %s\n' "$C_G" "$C_0" "$*"; }
skip()   { printf '    %s·%s %s %s(already done)%s\n' "$C_D" "$C_0" "$*" "$C_D" "$C_0"; }
warn()   { printf '    %s!%s %s\n' "$C_Y" "$C_0" "$*" >&2; }
die()    { printf '\n%sFAILED:%s %s\n' "$C_R" "$C_0" "$*" >&2; exit 1; }
trap 'die "${FUNCNAME[0]:-main}() line $LINENO: $BASH_COMMAND"' ERR

have()   { command -v "$1" >/dev/null 2>&1; }

# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------
START_AT=""; ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)  printf '%s\n' "${PHASES[@]}"; exit 0 ;;
    --from)  START_AT="${2:?--from needs a phase}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *)       ONLY="$1"; shift ;;
  esac
done

in_phases() { local q; for q in "${PHASES[@]}"; do [[ "$q" == "$1" ]] && return 0; done; return 1; }
for _p in ${ONLY:-} ${START_AT:-}; do
  in_phases "$_p" || { printf '%sunknown phase:%s %s\n    valid: %s\n' "$C_R" "$C_0" "$_p" "${PHASES[*]}" >&2; exit 2; }
done

should_run() {
  local p="$1"
  [[ -n "$ONLY" ]] && { [[ "$p" == "$ONLY" ]]; return; }
  if [[ -n "$START_AT" ]]; then
    local seen=0
    for q in "${PHASES[@]}"; do
      [[ "$q" == "$START_AT" ]] && seen=1
      [[ "$q" == "$p" ]] && { [[ $seen == 1 ]]; return; }
    done
  fi
  return 0
}

# ============================================================================
# Phase: preflight
# ============================================================================
do_preflight() {
  phase preflight "Checking the node"

  [[ "$(uname -s)" == "Linux" ]] || die "not Linux"
  local osname; osname="$(. /etc/os-release && echo "$PRETTY_NAME")"
  info "OS:      $osname"
  info "CPUs:    $(nproc)"
  info "Memory:  $(free -g | awk '/^Mem:/{print $2}') GB"

  local memgb; memgb=$(free -g | awk '/^Mem:/{print $2}')
  if (( memgb < 60 )); then
    warn "only ${memgb} GB RAM. configs/config.yaml lets the agent set shared_buffers up to"
    warn "32 GB and work_mem up to 4 GB; <64 GB will cause OOM-driven restarts during tuning."
  fi

  sudo -n true 2>/dev/null || die "passwordless sudo is required (expected on CloudLab)"
  ok "passwordless sudo"

  # drop_caches is used by the replay path (envs/pg_env.py:126)
  if sudo -n sh -c 'sync' 2>/dev/null; then ok "can sync/drop_caches (needed by replay)"; fi

  if [[ -d /usr/local/etc/emulab ]]; then
    ok "CloudLab/Emulab node detected"
  else
    warn "no /usr/local/etc/emulab — not a CloudLab node? storage phase will fall back."
  fi

  cat <<EOF

    ${C_Y}Reminder:${C_0} CloudLab experiments expire after 16h by default. A faithful
    Proto-X run is --duration 30.0, and hpo.py:130 save_checkpoint() is a no-op,
    so an expiring experiment loses the trial entirely. Extend the experiment in
    the portal BEFORE starting a long run, and keep artifacts/ rsync'd off-node.
EOF
}

# ============================================================================
# Phase: storage   -- never put 13 GB pgdata copies on the NFS home
# ============================================================================
do_storage() {
  phase storage "Provisioning local disk at $ROOT"

  if mountpoint -q /mnt && [[ -w /mnt ]]; then
    skip "/mnt already a mounted filesystem"
  elif [[ -x /usr/local/etc/emulab/mkextrafs.pl ]]; then
    info "running mkextrafs.pl (formats the spare local disk onto /mnt)"
    sudo /usr/local/etc/emulab/mkextrafs.pl /mnt \
      || warn "mkextrafs failed (already run, or no spare disk) — continuing on the root fs"
  else
    warn "mkextrafs.pl not present; using the root filesystem"
  fi

  sudo mkdir -p "$ROOT"
  sudo chown "$USER:$(id -gn)" "$ROOT"
  mkdir -p "$ROOT"/{src,data,artifacts}

  local avail; avail=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc '0-9')
  info "free space at $ROOT: ${avail} GB"
  if (( avail < 120 )); then
    warn "under 120 GB free. Each concurrent trial untars its own full pgdata copy"
    warn "(JOB ~13 GB); --max-concurrent 4 needs ~55 GB live plus archives."
  fi

  # Loudly discourage the classic mistake.
  case "$ROOT" in
    /users/*|"$HOME"/*) die "ROOT=$ROOT is on the NFS home. Use local disk (/mnt/...)." ;;
  esac
  ok "workspace ready at $ROOT"
}

# ============================================================================
# Phase: packages
# ============================================================================
do_packages() {
  phase packages "Installing base + Postgres build dependencies"

  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get update -qq
  sudo apt-get install -y -qq --no-install-recommends \
    build-essential gcc g++ make pkg-config \
    curl wget ca-certificates git unzip xz-utils \
    flex bison \
    libreadline-dev zlib1g-dev libssl-dev libicu-dev \
    libxml2-dev libxslt1-dev uuid-dev libossp-uuid-dev \
    python3 python3-venv \
    rsync htop tmux jq \
    >/dev/null
  ok "apt packages installed"
}

# ============================================================================
# Phase: claude   -- ONBOARDING FIRST, as requested
# ============================================================================
do_claude() {
  phase claude "Onboarding Claude Code"

  # Native installer: no Node.js dependency, installs to ~/.local/share/claude
  # with a symlink at ~/.local/bin/claude. This is the layout verified on the
  # group's existing machine.
  if have claude || [[ -x "$HOME/.local/bin/claude" ]]; then
    skip "claude already installed ($("$HOME/.local/bin/claude" --version 2>/dev/null || claude --version))"
  else
    info "fetching the native installer from claude.ai/install.sh"
    curl -fsSL https://claude.ai/install.sh | bash
  fi

  # ~/.local/bin is often not on PATH on a fresh node.
  if ! grep -qs 'HOME/.local/bin' "$HOME/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    info "added ~/.local/bin to PATH in ~/.bashrc"
  fi
  export PATH="$HOME/.local/bin:$PATH"

  have claude || die "claude not on PATH after install"
  ok "claude $(claude --version 2>/dev/null || echo installed)"

  cat <<EOF

    ${C_B}Log in once:${C_0}  run ${C_B}claude${C_0} and follow the browser prompt.

    Credentials go to ~/.claude/ which on CloudLab is the ${C_B}persistent NFS home${C_0},
    so this survives node re-instantiation within the same cluster — you should
    only need to authenticate once per cluster, not once per experiment.

    On a headless node the browser flow prints a URL; open it on your laptop and
    paste the code back. If SSH port-forwarding is easier:
        ssh -L 54545:localhost:54545 <node>
EOF
}

# ============================================================================
# Phase: conda    -- on local disk; the NFS home has a quota
# ============================================================================
do_conda() {
  mkdir -p "$ROOT/src"
  phase conda "Installing Miniconda at $ROOT/miniconda3"

  if [[ -x "$ROOT/miniconda3/bin/conda" ]]; then
    skip "miniconda present"
  else
    local inst="$ROOT/src/miniconda.sh"
    curl -fsSL -o "$inst" \
      https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash "$inst" -b -p "$ROOT/miniconda3"
    rm -f "$inst"
  fi

  # Keep pkgs/envs off NFS too.
  "$ROOT/miniconda3/bin/conda" config --system --set auto_activate_base false || true
  ok "conda $("$ROOT/miniconda3/bin/conda" --version | awk '{print $2}')"
}

# ============================================================================
# Phase: postgres -- source build, FLAT bin layout (envs/spec.py:78 requires it)
# ============================================================================
do_postgres() {
  mkdir -p "$ROOT/src"
  phase postgres "Building PostgreSQL $PG_VERSION"

  local prefix="$ROOT/pg$PG_MAJOR"
  if [[ -x "$prefix/bin/postgres" ]]; then
    skip "postgres $("$prefix/bin/postgres" --version | awk '{print $3}') already built"
    return
  fi

  case "$PG_MAJOR" in
    13|14|15|16) : ;;
    *) die "PG major $PG_MAJOR is outside the supported window 13..16.
       <13 lacks n_ins_since_vacuum (envs/spaces/utils.py:71) and 3 tuned knobs;
       17 moved pg_stat_bgwriter columns that envs/spaces/utils.py:46 reads." ;;
  esac

  local tarball="$ROOT/src/postgresql-$PG_VERSION.tar.bz2"
  [[ -f "$tarball" ]] || curl -fL --retry 3 -o "$tarball" \
    "https://ftp.postgresql.org/pub/source/v$PG_VERSION/postgresql-$PG_VERSION.tar.bz2"

  rm -rf "$ROOT/src/postgresql-$PG_VERSION"
  tar xf "$tarball" -C "$ROOT/src"

  pushd "$ROOT/src/postgresql-$PG_VERSION" >/dev/null
    ./configure --prefix="$prefix" --with-openssl --with-libxml --with-icu \
      >"$ROOT/src/pg-configure.log" 2>&1 || { tail -30 "$ROOT/src/pg-configure.log"; die "configure failed"; }
    make -j"$BUILD_JOBS" >"$ROOT/src/pg-build.log" 2>&1 \
      || { tail -30 "$ROOT/src/pg-build.log"; die "make failed"; }
    make install >>"$ROOT/src/pg-build.log" 2>&1
  popd >/dev/null

  ok "postgres installed to $prefix"
  info "postgres_path for configs/config.yaml is ${C_B}$prefix/bin${C_0}"
  info "(the code needs pg_ctl/psql/pg_isready in ONE flat dir -- envs/spec.py:78)"
}

# ============================================================================
# Phase: extensions -- pg_hint_plan (mandatory) + HypoPG (diagnostics/embeddings)
# ============================================================================
do_extensions() {
  mkdir -p "$ROOT/src"
  phase extensions "Building pg_hint_plan + HypoPG for PG $PG_MAJOR"

  local prefix="$ROOT/pg$PG_MAJOR"
  local pgconfig="$prefix/bin/pg_config"
  [[ -x "$pgconfig" ]] || die "no pg_config at $pgconfig; run the postgres phase first"

  # --- pg_hint_plan: REQUIRED. envs/pg_env.py:107 appends it to
  #     shared_preload_libraries on every single restart.
  if [[ -f "$prefix/lib/pg_hint_plan.so" ]]; then
    skip "pg_hint_plan present"
  else
    local d="$ROOT/src/pg_hint_plan"
    [[ -d "$d" ]] || git clone -q --depth 1 -b "PG$PG_MAJOR" \
      https://github.com/ossc-db/pg_hint_plan.git "$d"
    make -C "$d" -j"$BUILD_JOBS" PG_CONFIG="$pgconfig" >"$ROOT/src/hint-build.log" 2>&1 \
      || { tail -30 "$ROOT/src/hint-build.log"; die "pg_hint_plan build failed"; }
    make -C "$d" install PG_CONFIG="$pgconfig" >>"$ROOT/src/hint-build.log" 2>&1
    ok "pg_hint_plan built"
  fi

  # --- HypoPG: needed for hypothetical-index diagnostics and for
  #     embeddings/gen_index_data.py:243 (training new embeddings).
  if [[ -f "$prefix/lib/hypopg.so" ]]; then
    skip "hypopg present"
  else
    local d="$ROOT/src/hypopg"
    [[ -d "$d" ]] || git clone -q --depth 1 https://github.com/HypoPG/hypopg.git "$d"
    make -C "$d" -j"$BUILD_JOBS" PG_CONFIG="$pgconfig" >"$ROOT/src/hypopg-build.log" 2>&1 \
      || { tail -30 "$ROOT/src/hypopg-build.log"; die "hypopg build failed"; }
    make -C "$d" install PG_CONFIG="$pgconfig" >>"$ROOT/src/hypopg-build.log" 2>&1
    ok "hypopg built"
  fi

  ls "$prefix/lib/"{pg_hint_plan,hypopg}.so >/dev/null || die "extension .so missing"
  ok "both extensions installed under $prefix/lib"
}

# ============================================================================
# Phase: protox
# ============================================================================
do_protox() {
  phase protox "Cloning Proto-X"

  local d="$ROOT/protox"
  if [[ -d "$d/.git" ]]; then
    skip "repo present at $d"
  else
    git clone -q -b "$PROTOX_BRANCH" "$PROTOX_REPO" "$d"
    ok "cloned $PROTOX_BRANCH"
  fi

  if [[ "$WITH_SUBMODULES" == "1" ]]; then
    info "fetching baseline submodules (UDO, Auto-Steer, index_selection_evaluation, UniTune)"
    git -C "$d" submodule update --init --recursive
  else
    info "skipping submodules — they are BASELINES only (UDO/Auto-Steer/UniTune),"
    info "not needed for Proto-X itself. Re-run with WITH_SUBMODULES=1 if you want them."
  fi

  # Stage the pre-trained embeddings so the embedding-training pipeline can be skipped.
  # Paths on the right are what results/<bench>/us/*/params.json reference, resolved
  # relative to --mythril-dir (agents/hpo.py:127). spec.py:69-71 loads the sibling
  # `config` file too, so copy whole directories.
  pushd "$d" >/dev/null
    local staged=0
    [[ -d job2_models/model6 ]]              || { mkdir -p job2_models && cp -r results/latent_spaces/spaces/job/model6 job2_models/ && staged=1; }
    [[ -d tpch2_models/model0 ]]             || { mkdir -p tpch2_models && cp -r results/latent_spaces/spaces/tpch/model0 tpch2_models/ && staged=1; }
    [[ -d dsb_data_models/curated/model0 ]]  || { mkdir -p dsb_data_models/curated && cp -r results/latent_spaces/spaces/dsb/model0 dsb_data_models/curated/ && staged=1; }
    [[ -d tpcc_worlds/model0 ]]              || { mkdir -p tpcc_worlds && cp -r results/latent_spaces/spaces/tpcc/model0 tpcc_worlds/ && staged=1; }
    (( staged )) && ok "staged pre-trained embeddings for all 4 benchmarks" || skip "embeddings staged"

    # Minimal BenchBase XML. _mutate_common_config ET.parse()s this unconditionally
    # and sets root.find("url").text, even for the OLAP benchmarks that never use it.
    if [[ ! -f stub_benchbase.xml ]]; then
      printf '<?xml version="1.0"?>\n<parameters><url></url></parameters>\n' > stub_benchbase.xml
      ok "wrote stub_benchbase.xml"
    fi
  popd >/dev/null
}

# ============================================================================
# Phase: pyenv
# ============================================================================
do_pyenv() {
  mkdir -p "$ROOT/src"
  phase pyenv "Creating the '$CONDA_ENV' python environment"

  local conda="$ROOT/miniconda3/bin/conda"
  [[ -x "$conda" ]] || die "conda missing; run the conda phase first"

  if "$conda" env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    skip "env '$CONDA_ENV' exists"
  else
    "$conda" create -y -q -n "$CONDA_ENV" "python=$PY_VERSION" >/dev/null
    "$conda" env config vars set -n "$CONDA_ENV" PYTHONNOUSERSITE=1 >/dev/null
    ok "created python $PY_VERSION env"
  fi

  local pip="$ROOT/miniconda3/envs/$CONDA_ENV/bin/pip"
  local req="$ROOT/protox/requirements.txt"
  [[ -f "$req" ]] || die "requirements.txt not found; run the protox phase first"

  # CloudLab nodes have no GPU. requirements.txt pins ~2 GB of nvidia-*-cu11 wheels
  # plus triton, all useless here. Strip them and take torch from the CPU index.
  # The nets are tiny (pi 128,128 / qf 1024 in the shipped params) so CPU is fine.
  local cpureq="$ROOT/src/requirements-cpu.txt"
  grep -viE '^(nvidia-|triton==|torch==)' "$req" > "$cpureq"

  info "installing torch 2.0.0 (CPU build)"
  "$pip" install -q torch==2.0.0 --index-url https://download.pytorch.org/whl/cpu
  info "installing the remaining $(wc -l < "$cpureq") pinned requirements"
  "$pip" install -q -r "$cpureq"
  ok "python environment ready"
}

# ============================================================================
# Phase: verify
# ============================================================================
do_verify() {
  phase verify "Checking the install"

  local prefix="$ROOT/pg$PG_MAJOR"
  local py="$ROOT/miniconda3/envs/$CONDA_ENV/bin/python"
  local fail=0
  chk() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else warn "$1 -- FAILED"; fail=1; fi; }

  chk "claude on PATH"            "command -v claude"
  chk "pg_ctl/psql/pg_isready flat in $prefix/bin" \
      "[[ -x $prefix/bin/pg_ctl && -x $prefix/bin/psql && -x $prefix/bin/pg_isready ]]"
  chk "pg_hint_plan.so"           "[[ -f $prefix/lib/pg_hint_plan.so ]]"
  chk "hypopg.so"                 "[[ -f $prefix/lib/hypopg.so ]]"
  chk "protox checkout"           "[[ -f $ROOT/protox/hpo.py ]]"
  chk "embeddings staged"         "[[ -f $ROOT/protox/job2_models/model6/embedder_19.pth && -f $ROOT/protox/job2_models/model6/config ]]"
  chk "python $PY_VERSION"        "$py --version"
  chk "torch imports"             "$py -c 'import torch'"
  chk "ray imports"               "$py -c 'import ray'"
  chk "gymnasium imports"         "$py -c 'import gymnasium'"
  chk "psycopg imports"           "$py -c 'import psycopg'"
  chk "pglast imports"            "$py -c 'import pglast'"

  # Environment file for later shells.
  cat > "$ROOT/env.sh" <<EOF
# source this before working with Proto-X
export PROTOX_ROOT="$ROOT"
export PGBIN="$prefix/bin"
export PATH="\$PGBIN:\$HOME/.local/bin:\$PATH"
source "$ROOT/miniconda3/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"
cd "$ROOT/protox"
EOF
  ok "wrote $ROOT/env.sh"

  (( fail )) && warn "some checks failed — see above" || true

  cat <<EOF

${C_B}Done.${C_0} Next, in order:

  1. ${C_B}source $ROOT/env.sh${C_0}
  2. ${C_B}claude${C_0}                     -- log in (once per cluster; ~/.claude is persistent NFS)
  3. Get the data. This repo ships NO schema DDL and NO loader; you supply the
     database. For JOB: load IMDb into PG $PG_MAJOR as db=benchbase user=admin,
     then VACUUM FULL; VACUUM; ANALYZE; stop the server, and
        cd <parent-of-pgdata> && tar cf $ROOT/data/job.tgz pgdata
     (untar uses --strip-components 1, so the archive's first component is dropped)
  4. Apply the paper's baseline config:
        python3 scripts/experiments/job_full/load_job_full.py --config-file configs/config.yaml
     then re-tar to capture the starting snapshot.
  5. Patch paths: configs/config.yaml lines 3,4,6 and
     configs/benchmark/job_full.yaml lines 9,10 -- the query paths MUST be made
     relative, because agents/hpo.py only prefixes mythril_dir onto relative paths
     and the shipped absolute /home/wz2/... values silently stay broken.
  6. Build initial_job.json as a JSON *array* wrapping a params.json:
        python3 -c 'import json,sys; json.dump([json.load(open(sys.argv[1]))], open(sys.argv[2],"w"), indent=2)' \\
          results/job/us/TuneOpt_f5769_00000_0_2024-05-08_20-17-14/params.json initial_job.json
     then fix mythril_dir / data_snapshot_path / benchbase_config_path inside it
     (its values OVERRIDE the command line -- README.md:101).
  7. Smoke test with --duration 0.5 before committing 30 hours.

Log: $ROOT/bootstrap.log
EOF
}

# ============================================================================
# Driver
# ============================================================================
main() {
  mkdir -p "$(dirname "$ROOT")" 2>/dev/null || true
  for p in "${PHASES[@]}"; do
    # NB: must be an if-statement, not `should_run && do_x`. As the last command
    # in the loop body the latter makes main() inherit a skipped phase's exit
    # status 1, which under `set -e` + `pipefail` fails the `| tee` pipeline.
    if should_run "$p"; then
      "do_$p"
    fi
  done
  return 0
}

# Tee everything once $ROOT exists; storage phase creates it.
main "$@" 2>&1 | tee -a "/tmp/protox-bootstrap.$$.log"
if [[ -d "$ROOT" ]]; then
  cat "/tmp/protox-bootstrap.$$.log" >> "$ROOT/bootstrap.log" 2>/dev/null || true
  rm -f "/tmp/protox-bootstrap.$$.log"
fi
