# OFFLOAD — read this first (session ending 2026-09-16)

You are picking up a Gen-DBA training-data harvest. This file is the resume point for
the session that ran **Proto-X** for the first time. For the full project context read
`HANDOVER.md` (deep background) and `docs/dba_loop.md` + `docs/training_record.md`
(the record format). This file is the delta: what THIS session did, exact state, and
what to do next.

`/proj/pmoss-PG0/` is the ONLY filesystem that survives a CloudLab allocation. `/mnt`
and `/data` are node-local and rebuilt by `scripts/cloudlab/provision.sh` (~3 h).

---

## 1. One-line status

Proto-X ran and produced the corpus's **first RL trajectory episodes** (job + tpch).
dsb is **blocked** on an embedder/config dimension mismatch. Nothing is running; the
node is idle and safe to release or keep. Everything is committed on branch
`gendba-harvest` (not pushed; the repo lives on /proj so history survives anyway).

## 2. Exact state

* **Corpus: 293 episodes** (was 290) + 10 quarantined. The 3 new ones, in
  `gendba_records/episodes/`:

  | file (prefix `protox-`) | steps | speedup | note |
  |---|---|---|---|
  | `job-…57d14_00000…` | 921 | **5.50x** | full 30h run; 2.4 GB JSON (383 MB on ZFS) |
  | `job-…57d14_00001…` | 154 | 4.73x | 2nd config, truncated |
  | `tpch-…0165d_00000…` | 440 | **2.69x** | full 30h run, complete |

  All gate-clean, `multi_component_tuning`, full six-move spine
  (orient/decide/apply/measure/keep-revert per step; hypothesize+screen absent).
* **Raw trials kept** on /proj: `gendba_records/protox_trials/` (2 dirs, job + tpch,
  3.3 GB apparent). These are the raw traces the episodes were harvested from — keep
  them; a future parser fix can re-derive without re-running (6 parser bugs were found
  and fixed this session, so re-derivability matters).
* **Nothing running.** Confirmed no `hpo.py` / `run_protox*` / postgres cluster.
* /proj: ~97 G free.

## 3. What this session built (all committed)

* **`scripts/gendba/protox_harvest.py`** — turns one Ray trial into one trajectory
  episode. The schema decision (settled): an RL trajectory is **N decisions in ONE
  episode, not N episodes**. Six parser traps fixed along the way — see its docstring
  and `docs/training_record.md §7`. Key ones: the baseline run is not step 0 (marker
  is logged AFTER it, and misspelled `Baseilne` in `tune.py:128`); a trial holds
  several RL episodes (horizon resets) recorded as boundaries; the `PENALTY` row is
  not a query; the speedup must be like-for-like over the common query set.
* **`scripts/cloudlab/run_protox.sh`** — the launcher (`preflight|smoke|full`) the
  provision banner always pointed at but never existed. Enforces the relative/absolute
  path rule, bounds smoke to 0.5 h, and trims initial configs to **one trial per run**
  (see trap below). Writes trials directly to /proj.
* **`scripts/cloudlab/run_protox_all.sh`** — runs `job tpch dsb` (or a subset)
  sequentially, harvesting each into the corpus.
* Gate (`validate.py`) gained trajectory invariants; format documented in
  `training_record.md §7`.

## 4. Traps this session hit — do NOT rediscover

* **`--num-trials 1` does NOT cap the run.** `initial_*.json` has 4 configs, each a
  `points_to_evaluate` trial, so Ray runs 4 × `duration` (= 120 h for one benchmark).
  `run_protox.sh` now trims to the first config. If you ever bypass it, watch for a
  second trial starting after the first completes.
* **A full-run episode is huge** — the 921-step job episode is 2.4 GB JSON. It loads
  and gates fine on a 188 GB node but a consumer that can't hold 2.4 GB needs a
  projection that drops per-step `run.plans`. Capture-losslessly-project-later applies.
* **Never edit a running `.sh`.** Bash reads by byte offset; an in-place edit corrupts
  the live process. Bit this session twice.
* **Verify a launch actually measures** — postgres up + Ray `1 RUNNING` + active
  queries — never report "running" from the launch line alone.

## 5. dsb is BLOCKED — the one real open item

dsb via Proto-X has **never worked** (Proto-X was never run on dsb before this
session). It dies at startup loading its pretrained embedder:

```
size mismatch VAE encoder: checkpoint [256,432] vs current model [256,408]   (Δ 24)
```

Diagnosis (confirmed):
* The shipped embedder `dsb_data_models/curated/model0/embedder_22.pth` was trained on
  a **curated 136-column schema** (see its `config` → `class_mapping`, 136 entries)
  that yields a **432-dim** index space.
* The repo's current dsb config yields **408**. The dim comes from the index-space
  ENCODING (`envs/spaces/index_policy.py` `OneHotIndexPolicy`: tables ×
  `max_num_columns` × the aux flags `index_space_aux_{type,brin,include,md}`), NOT the
  raw column count.
* Two dead ends already tried and reverted/kept:
  * Added the two missing yaml keys `index_space_aux_brin`/`_md` (real bug, **kept** —
    gets past `hpo.py:170`).
  * Fixed the `web_returns` list-marker typo (24 cols → 425). Did **NOT** change the
    408 dim — **reverted**. The training_record claim that the embedder "does not
    contain web_returns" is wrong, but the fix still doesn't bridge the dim.

To finish dsb (pick one):
1. **Match the config to the embedder.** Reverse-engineer which
   `OneHotIndexPolicy(tables, max_num_columns, aux_type, aux_brin, aux_include,
   aux_md)` combination yields 432, and set the dsb benchmark config + `initial_dsb.json`
   `mythril_index_space_aux_*` to it. Fastest if it converges; the dim formula is in
   `index_policy.py` + `index_space.py`. job/tpch load fine, so compare their
   aux-flag/`max_num_columns` settings against their embedders to learn the mapping.
2. **Regenerate the dsb embedder** for the 408-dim schema via
   `embeddings/gen_index_data.py` + the VAE training stage. Hours; the "expensive
   stage" `docs/cloudlab_setup.md §5` says to normally skip.

job and tpch prove the harness is correct end-to-end — dsb is purely this embedder
reconciliation.

## 6. How to resume Proto-X on a fresh node

```bash
scripts/cloudlab/provision.sh                 # rebuild PG15, envs, load job/tpch/dsb (~3h)
scripts/cloudlab/run_protox.sh job preflight  # checks only
scripts/cloudlab/run_protox.sh job smoke      # ~30 min end-to-end sanity
scripts/cloudlab/run_protox_all.sh job tpch   # full runs (dsb only after the fix above)
```
Harvest is resumable/idempotent; episodes already on disk are skipped.

## 7. Honest notes for the next agent

* Two process mistakes cost time this session: an ~11.5 h idle gap where a relaunch was
  claimed but never issued (always VERIFY the process exists), and one commit whose
  message overclaimed a fix that didn't work (reverted + corrected). Verify state; don't
  trust intentions.
* The user's framing for where this is heading (worth carrying): Gen-DBA as an
  autoresearch-style **budgeted investigate→verdict loop**, RSI through the *harness*
  (not the engine), trained offline because deploy is non-destructive — so the measured
  outcome is a **label, never a decision input**, and Moves 1–3 are the deploy-time
  inputs. This reframes harvesting priority toward **breadth** (objectives beyond
  latency: cost, throughput, concurrency; a load-generator harness) over depth.

Branch `gendba-harvest`. Everything is on /proj.
