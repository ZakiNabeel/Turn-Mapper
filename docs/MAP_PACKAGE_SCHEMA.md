# TURN Map Package (`.turnmap`) — Schema v0.1 (draft)

Status: **v0.1.1 implemented** (0.1.1 adds embedded-floor JSON output, backward compatible) in `contract/turnmap.schema.json` + `src/turn_mapper/export.py`; fixtures in `contract/fixtures/`. Not tagged yet. Items marked `VERIFY` must be reconciled with the Android app's Room entities (via the app audit, Prompt A1) before `contract-v0.1.0` is tagged.

Machine-checkable source of truth: `contract/turnmap.schema.json` (JSON Schema 2020-12). This document explains it.

---

## 1. Container — one venue, many buildings and floors

A `.turnmap` is a ZIP:

```text
venue.turnmap
├── venue.json                      # venue index, buildings, floors list, cross-floor transitions
├── floors/
│   ├── C-F1/
│   │   ├── floor.json              # geometry + graph for this floor
│   │   └── floorplan.png           # the image the app displays (pixels referenced by transform)
│   ├── B-GF/ …
│   └── A-F2/ …
└── qa/                             # optional; ignored by the app (QA report, overlays)
```

The app's v1 importer may import one floor at a time (user picks from `venue.json.floors`). Multi-floor routing uses `transitions` later.

## 2. Coordinate frame

- Units: **metres**. Each floor has its own frame.
- Origin / axis direction: **VERIFY** from the app source (Prompt A1). Default proposal until verified: origin at the floor image top-left, x → right, y → down (image-aligned). The app audit must confirm or change this, and the decision is recorded as ADR-007.
- `transform.px_to_m`: 2×3 affine mapping image pixel `(u, v)` → `(x, y)` metres.
- Optional `building_frame`: a 2×3 affine from floor frame to a shared building frame, so floors of one block stack correctly (needed for multi-floor; may be identity/absent in v0.1).

## 3. `venue.json`

```jsonc
{
  "schema_version": "0.1.1",
  "generator": { "name": "turn-mapper", "version": "0.3.0", "git_commit": "…", "run_id": "…",
                 "model": { "name": "classical", "checksum": null } },
  "venue": { "id": "fast-isb", "name": "FAST-NUCES Islamabad" },
  "buildings": [ { "id": "A", "name": "A Block" }, { "id": "B", "name": "B Block" }, { "id": "C", "name": "C Block" } ],
  "floors": [
    { "id": "C-F1", "building_id": "C", "level": 1, "name": "C Block – First Floor",
      "path": "floors/C-F1/floor.json",
      "source": { "file": "fast_blocks.pdf", "page": 7, "sha256": "…" },
      "validation_passed": true }
  ],
  "transitions": [
    // reserved for multi-floor; empty in v0.1
    // { "id": "t1", "type": "stairs", "from": {"floor_id":"C-GF","node_id":"n12"}, "to": {"floor_id":"C-F1","node_id":"n3"}, "length_m": 6.0, "accessible": null }
  ]
}
```

### 3.1 JSON output (default since 0.1.1)

`turn-mapper run` writes `venue.json` with every floor **embedded**: each `floors[i]` has `"floor": { …floor.json… }`
instead of `"path"`, and the floor image is a sibling file referenced by `floor.image.file` (`images/<id>.png`).
Exactly one of `path` (zipped `.turnmap`) or `floor` (plain JSON) is present. `--format turnmap|both` still writes the zip.

## 4. `floor.json`

```jsonc
{
  "floor_id": "C-F1",
  "image": { "file": "floorplan.png", "width_px": 4200, "height_px": 2800, "sha256": "…" },
  "transform": {
    "px_to_m": [[0.0125, 0, 0], [0, 0.0125, 0]],
    "scale_m_per_px": 0.0125,
    "scale_source": "operator_two_point",            // operator_two_point | ocr_dimension | cad_units | scale_bar | door_width_prior (estimate!) | footprint_transfer (from another floor of the same building)
    "scale_evidence": [
      { "p1_px": [100, 400], "p2_px": [1092, 400], "distance_m": 12.4, "used_for_fit": true },
      { "p1_px": [100, 900], "p2_px": [500, 900],  "distance_m": 5.0,  "used_for_fit": false, "residual_m": 0.06 }
    ]
  },
  "bounds_m": { "min_x": 0, "min_y": 0, "max_x": 52.5, "max_y": 35.0 },

  "walkable": { "type": "MultiPolygon", "coordinates": [ … ], "provenance": { "source": "auto", "confidence": 0.82 } },

  "walls":  [ { "id": "w1", "a": [0,0], "b": [52.5,0], "thickness_m": 0.2, "provenance": { "source": "auto", "confidence": 0.95 } } ],
  "doors":  [ { "id": "d1", "a": [10.0,5.0], "b": [10.9,5.0], "room_id": "r1", "provenance": { "source": "auto", "confidence": 0.71 } } ],
  "rooms":  [ { "id": "r1", "polygon": [[8,5],[14,5],[14,12],[8,12],[8,5]], "label": "C-405", "name": "Lab 2",
                "category": "lab", "provenance": { "source": "auto", "confidence": 0.66, "ocr_confidence": 0.91 } } ],

  "graph": {
    "nodes": [
      { "id": "n1", "x": 10.4, "y": 3.5, "kind": "corridor" },           // corridor | junction | door | transition
      { "id": "n2", "x": 10.4, "y": 5.0, "kind": "door", "door_id": "d1" },
      { "id": "n9", "x": 2.1, "y": 9.0, "kind": "transition", "transition": "stairs" }   // stairs | lift | escalator
    ],
    "edges": [
      { "id": "e1", "from": "n1", "to": "n2", "length_m": 1.5, "type": "door",   // corridor | door | stairs | lift | escalator
        "bidirectional": true, "accessible": null, "provenance": { "source": "auto" } }
    ]
  },

  "pois": [ { "id": "p1", "name": "Lab 2", "label": "C-405", "node_id": "n2", "room_id": "r1",
              "category": "lab", "needs_review": false, "provenance": { "source": "auto" } },
            { "id": "p2", "name": "Stairs 1", "label": null, "node_id": "n9", "room_id": null, "category": "stairs",
              "needs_review": false, "provenance": { "source": "auto" } } ],

  "validation": { "passed": true, "forced": false, "errors": [], "warnings": [ { "code": "ROOM_NO_DOOR", "ref": "r7", "message": "…" } ] }
}
```

## 5. Rules

- IDs: strings, unique within a floor (`floor_id` + `id` unique within venue).
- `provenance.source ∈ {auto, manual, corrected}`; `confidence ∈ [0,1]`, absent for manual.
- `accessible`: `null` unless verified (context §5.12).
- Edge rules: endpoints exist; `length_m` = Euclidean ±1 cm; no wall intersection except a door edge through its own door; inside walkable (5 cm tolerance).
- Every POI references an existing node on the same floor.
- Consumers ignore unknown optional fields; reject unknown MAJOR versions.

## 6. Mapping to the Android app (filled by Prompt A1 in the app repo)

| Package field | App entity / column | Supported? | Plan |
|---|---|---|---|
| floor image | VERIFY | | |
| transform | VERIFY (calibration) | | |
| walkable (MultiPolygon) | VERIFY (single polygon?) | | |
| walls | VERIFY | | |
| doors | VERIFY | | |
| rooms | probably none | | |
| graph nodes/edges | VERIFY | | |
| pois | VERIFY (destinations) | | |
| provenance | probably none | | |

## 7. Versioning

Semantic versioning; tag `contract-vX.Y.Z`; every change logged in `contract/CHANGELOG.md`.
