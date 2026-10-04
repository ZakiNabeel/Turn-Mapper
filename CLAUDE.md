# CLAUDE.md — TURN-Mapper (floor plan → navigation graph module)

## What this repo is

TURN-Mapper is **one module** of the TURN indoor-navigation FYP (FAST-NUCES Islamabad). It takes **any floor plan** (PDF, image, DXF; one or many floors/buildings) and produces a **TURN Map Package (`.turnmap`)**: metric walkable geometry, walls, doors, rooms, destinations and a routeable navigation graph.

It does **not** do positioning, PDR, Wi-Fi or UI. Those live in the main app repo (`shehryarf67/TURN-Field-Test`, Android/Kotlin). The two meet at exactly one place: the **contract** in `contract/` (JSON Schema + fixtures + `docs/MAP_PACKAGE_SCHEMA.md`). Read `docs/INTEGRATION_CONTRACT.md` before touching anything that crosses that boundary.

"Any floor plan" means: any plan can be ingested and gets a best-effort automatic map, which a human verifies and corrects. We never claim fully automatic mapping.

Authoritative project context: `docs/TURN_FYP_CONTEXT.md` (parts about Android are background only).

## Read before working

1. `docs/INTEGRATION_CONTRACT.md` — the module boundary
2. `docs/PIPELINE1_SPEC.md` — stages and algorithms
3. `docs/MAP_PACKAGE_SCHEMA.md` — output format
4. `docs/DECISIONS.md` — accepted decisions (don't silently override)
5. Last 3 entries of `docs/SESSION_LOG.md`
6. The current step in `docs/MASTER_PLAN.md` (once it exists)

## Layout (target)

```text
src/turn_mapper/
  api.py            # public Python API: convert(), validate_package(), load_package()
  cli.py            # `turn-mapper` CLI (thin wrapper over api.py)
  ir/               # intermediate representation dataclasses (pixel + metric)
  ingest/           # input adapters: pdf_vector, pdf_raster, image, dxf (registry, pluggable)
  preprocess/
  segment/          # interface + classical + learned implementations
  ocr/
  vectorize/
  scale/
  walkable/
  graph/
  pois/
  validate/
  report/           # QA HTML
  export/           # .turnmap writer/reader
  learned/          # training code (imported by notebooks)
contract/           # turnmap.schema.json, fixtures/*.turnmap, CHANGELOG.md  ← the public contract
configs/            # YAML configs, incl. per-venue configs (e.g. venues/fast_isb.yaml)
samples/            # small sample plans with permission + README with measured distances
eval/               # evaluation scripts
notebooks/          # thin Colab/Kaggle wrappers
tests/
docs/
data/  runs/  weights/   # gitignored
```

## Hard rules

- **The contract is sacred.** Changing anything in `contract/` requires: schema_version bump, `contract/CHANGELOG.md` entry, updated `MAP_PACKAGE_SCHEMA.md`, updated fixtures, writer/reader tests — in one PR — plus a note for the Android team. Breaking change = MAJOR bump.
- **Module boundary.** No Android code here. No positioning logic here. The public surface is `turn_mapper.api` + CLI + `.turnmap`. Everything else is internal and may change.
- **Pluggable inputs.** New input formats are new adapters in `ingest/` registered in the registry; never special-case a building inside pipeline code. Venue-specific settings go in `configs/venues/*.yaml`.
- **Metres, one frame.** All exported geometry is in metres in the frame defined in `MAP_PACKAGE_SCHEMA.md` §2. Pixels never leave the module.
- **AI output is a proposal.** Every auto element carries `provenance` (`auto|manual|corrected`) + confidence; validators gate export.
- **No fabricated results.** Only report numbers produced by running code on recorded data. Never tune on frozen test floors (ADR-009).
- **No data/weights in git.** Paths via `TURN_DATA_DIR`, `TURN_WEIGHTS_DIR`. Respect dataset licences.
- **Plan → approve → small steps → verify → log.** Use plan mode for anything touching `contract/`, the IR, or > 3 files.

## Conventions

- Python 3.11, `pyproject.toml` (src layout), `ruff`, `pytest`, type hints on public functions, `mypy` on `api.py` and `ir/`.
- Each stage: typed input → typed output, writes artefacts to `runs/<run>/<NN_stage>/`, re-runnable alone, cached by input+config hash.
- Every run writes `run_manifest.json` (git commit, config, input hashes, model checksum, timings, versions).
- Deterministic (seeded). CPU inference for one floor in < 2 min target.

## Commands (update as they become real)

```bash
pip install -e ".[dev]"            # add ".[ml]" for training extras
pytest
ruff check . && ruff format --check .
turn-mapper inspect samples/<plan>.pdf                       # list pages, vector/raster, text
turn-mapper run samples/<plan>.pdf --venue configs/venues/fast_isb.yaml --out runs/<name>
turn-mapper validate runs/<name>/venue.turnmap
```

## Project skills and agents

- `/run-floorplan` — run the pipeline on a plan and visually review the QA output
- `/turnmap-contract` — the checklist for any contract change
- `/add-pipeline-stage` — how to add a stage or input adapter correctly
- `/handoff` — end-of-session log entry
- Agents: `plan-reviewer` (red-teams plans), `qa-inspector` (looks at overlay images and reports geometry problems)

## End of every session

Run `/handoff` (or append to `docs/SESSION_LOG.md` manually).
