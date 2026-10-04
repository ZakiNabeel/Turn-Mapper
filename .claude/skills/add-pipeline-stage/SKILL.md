---
name: add-pipeline-stage
description: How to add or replace a pipeline stage, segmenter or input adapter in TURN-Mapper without breaking the chain. Use when implementing a new stage, a new segmentation method, or support for a new floor-plan format.
---

# Adding a stage, segmenter or input adapter

## Principles
- The chain must keep running end to end after your change. A smarter stage that breaks the chain is a regression.
- New implementations go **behind the existing interface** (e.g. a new `Segmenter` next to `ClassicalSegmenter`), selected by config. Don't delete the old one — it's the baseline.
- No building-specific code. Building knowledge goes in `configs/venues/*.yaml` (ADR-010).

## Stage contract
- Signature: typed IR in → typed IR out (`src/turn_mapper/ir/`). No hidden globals.
- Writes artefacts to `runs/<run>/<NN_stage>/` (JSON + debug PNG overlay).
- Pure given (input, config); cached by hash of both; seeded.
- Records its parameters and timing into `run_manifest.json`.
- Every geometric output has provenance (`auto`, confidence).

## Input adapter contract (`src/turn_mapper/ingest/`)
- `can_handle(path, page|None) -> float` (0–1 score) and `load(path, page) -> IngestResult`.
- Register in the adapter registry; add a tiny sample file (synthetic, generated in tests if possible) and a test.
- Vector adapters must output the same IR as the raster branch after `vectorize`.

## Tests (write first)
1. Unit test on synthetic input with a known answer (use the synthetic plan generator in `tests/synthetic/`).
2. Chain test: full `api.convert` on the synthetic plan still produces a package that passes `validate_package`.
3. If behaviour on real plans changes, re-run `/run-floorplan` on the **dev** plan and attach before/after overlays to the PR.

## Done
`pytest`, `ruff check`, `ruff format --check` green; docs (`PIPELINE1_SPEC.md`) updated if the method changed; `/handoff`.
