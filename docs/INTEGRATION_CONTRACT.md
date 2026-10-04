# Integration Contract — how TURN-Mapper plugs into TURN

Status: draft v0.1 (2026-10-04). This document is shared with the owners of the other TURN modules (positioning, app). Changes need agreement from both sides.

## 1. TURN as modules

```text
                ┌──────────────────────┐        .turnmap         ┌──────────────────────────────┐
 floor plans ──►│  TURN-Mapper (this)  │ ──────────────────────► │  TURN app (TURN-Field-Test)  │
 (PDF/IMG/DXF)  │  Python, offline     │   (versioned contract)  │  Android/Kotlin              │
                │  map intelligence    │                         │  ┌────────────┐ ┌──────────┐ │
                └──────────────────────┘                         │  │ Map store  │ │ Routing  │ │
                          ▲                                       │  │ (Room)     │ │ (A*)     │ │
                          │ ground-truth export (.turnmap)        │  └─────┬──────┘ └────▲─────┘ │
                          └────────────────────────────────────── │        │  map constraints  │ │
                                                                  │  ┌─────▼────────────┴─────┐ │
                                                                  │  │ Positioning: PDR + PF  │ │
                                                                  │  │ + Wi-Fi (+BLE later)   │ │
                                                                  │  └────────────────────────┘ │
                                                                  └──────────────────────────────┘
```

- **Mapper produces** the navigable world. **The app consumes** it: walkable polygons and walls become particle-filter map constraints; the graph feeds A*; POIs become destinations; reference points for Wi-Fi survey are added later in the app on top of the imported map.
- The only coupling is the `.turnmap` format. The mapper never reads Room; the app never imports Python.

## 2. What the mapper guarantees (provider side)

1. Output validates against `contract/turnmap.schema.json` for the declared `schema_version`.
2. All coordinates in metres, frame per `MAP_PACKAGE_SCHEMA.md` §2.
3. Graph edges: never cross walls (except door edges through their door), stay within walkable (5 cm tolerance), `length_m` = Euclidean length.
4. Every POI references an existing graph node; validation results are embedded (`validation` block), including any forced export.
5. Stable IDs across re-runs of the same input + config where possible.
6. `provenance` on every element.

## 3. What the app is expected to do (consumer side)

1. Reject packages with an unsupported MAJOR `schema_version`; accept unknown optional fields (forward compatibility).
2. Import each floor into a **new** project/floor — never overwrite existing data in v1.
3. Map what it can represent; for anything it cannot (e.g. rooms, doors, provenance, multiple walkable polygons), either store additively (Room migration with tests) or drop with a visible warning listing what was dropped.
4. Provide an **export of a manually built floor** in the same format (ground truth for evaluation).
5. Never rescale an imported floor once fingerprints/checkpoints depend on it.

## 4. How the contract travels between repos

- Source of truth: this repo's `contract/` folder.
- Each contract release is a git tag: `contract-v0.1.0`.
- The Android repo **vendors** a copy at `app/src/test/resources/turnmap/` (schema + fixtures) and records the tag in a `CONTRACT_VERSION` file. Updating = copy the new tagged folder in a PR + run importer tests. (A git submodule also works; vendoring is simpler for a 3-person team.)
- Shared fixtures in `contract/fixtures/` are the integration test: Python writes/validates them; Kotlin importer tests read them.

## 5. Public Python API (for scripts, notebooks, a future web service)

```python
from turn_mapper import api

pkg = api.convert(
    inputs=["fast_blocks.pdf"],            # one or more files
    venue_config="configs/venues/fast_isb.yaml",   # page→building/floor mapping, scale evidence, crops
    out_dir="runs/fast_v1",
)                                           # -> VenuePackage (also writes runs/fast_v1/venue.turnmap + QA report)

report = api.validate_package("runs/fast_v1/venue.turnmap")   # -> ValidationReport
pkg = api.load_package("runs/fast_v1/venue.turnmap")          # -> VenuePackage
```

A REST wrapper (FastAPI, `POST /convert`) is a possible later addition for an admin portal; it must call `api.convert` and add no logic.

## 6. Ownership

| Item | Owner |
|---|---|
| TURN-Mapper repo, contract releases | Zaki Nabeel |
| Android importer/exporter, vendored contract | Shehryar Faisal (with Zaki) |
| Use of map constraints in positioning | M Sameer |

## 7. Change process

1. Propose change in `docs/DECISIONS.md` (Proposed ADR) + open an issue tagged `contract`.
2. Both owners agree.
3. One PR in TURN-Mapper (schema, docs, fixtures, tests, CHANGELOG) → tag.
4. One PR in the app repo updating the vendored copy + importer.
