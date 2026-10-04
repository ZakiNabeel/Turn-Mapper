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

## Layout (current)

```text
src/turn_mapper/
  api.py         # PUBLIC: convert(), process_floor(), validate_package(), load_package()
  cli.py         # `turn-mapper inspect | run | validate`
  config.py      # PipelineParams (generic defaults) + venue YAML loader (ADR-010)
  ir.py          # intermediate representation dataclasses
  ingest.py      # input adapters: pdf_embedded_image, pdf_render, image (+ inspect)
  preprocess.py  # grayscale, OCR text boxes, text erasure
  segment.py     # Segmenter interface; ClassicalSegmenter (histogram levels)
  vectorize.py   # orientation-aware wall-gap closing -> spaces, circulation, doors, walls
  scale.py       # two-point evidence, or door-width prior (flagged estimate)
  transitions.py # stairs (texture) + lifts (OCR) -> transition anchors
  graph.py       # skeleton -> polylines -> pruned/merged graph -> wall-safe door links + bridging
  pois.py        # per-room OCR labels -> POIs on door nodes
  validate.py    # schema + geometry validators on metric JSON; A* route sampling
  export.py      # floor.json (metres) + .turnmap writer/reader
  report.py      # QA overlays + HTML
  synthetic.py   # synthetic plans with known answers (tests, fixtures)
  schema/        # copy of contract/turnmap.schema.json (test keeps them in sync)
contract/        # turnmap.schema.json, fixtures/, CHANGELOG.md  ← the public contract
configs/venues/  # per-venue configs (fast_isb.yaml)
scripts/         # make_fixtures.py
tests/           # pytest (synthetic + contract)
docs/
data/ runs/ weights/ samples/private/ scratch/   # gitignored
```

Stages are flat modules for now; split into subpackages when a stage grows (e.g. `segment/learned.py` in M5).

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
# needs the tesseract binary (apt install tesseract-ocr / brew install tesseract / Windows installer)
pip install -e ".[dev]"
pytest -q                                     # 28 tests, ~10 s
ruff check . && ruff format --check .
python scripts/make_fixtures.py               # regenerate contract/fixtures
turn-mapper inspect samples/private/fast_blocks.pdf
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split dev --out runs/<name>
turn-mapper run any_plan.png --out runs/<name>                # single image, no config
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
