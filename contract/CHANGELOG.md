# Contract changelog — .turnmap

## 0.1.2 (2026-10-24, backward compatible)
- `transform.scale_source` gains two values:
  - `measured_room_size`: scale fitted to site-measured room sizes (a named room, or the typical room size of a
    building matched by the most agreeing rooms); `scale_evidence` lists the rooms used and any checks.
  - `door_width_calibrated`: still an estimate, but from the door width drawn on this venue's plans as measured on
    its measured floors (run manifest `door_width_calibration`), not the generic 0.9 m prior.
- Writer emits `schema_version: "0.1.2"`. Readers that accept `^0\.1\.\d+$` need no change; treat any
  `scale_source` other than `measured_room_size`, `operator_two_point` and `cad_units` as an estimate.
- Note for the app teams: `turn-mapper export-positioning venue.json --out dir` writes the positioning app's own
  venue package (schemaVersion 1) and TURN Floor GeoJSON v1; see `docs/POSITIONING_INTEGRATION.md`.

## 0.1.1 (2026-10-11, backward compatible)
- JSON output: `venue.json` may embed each floor under `floors[i].floor` (and reference `images/<id>.png`
  via `floor.image.file`) instead of pointing to `floors[i].path` in a zip. Exactly one of `path` / `floor`
  is required. Readers that only support `.turnmap` keep working on `.turnmap` packages.
- New fixtures: `fixtures/json_synthetic_{basic,lshape}/venue.json`.
- Tool versions: package `0.3.0`.

## Unreleased
- No schema change: `venue.transitions` (reserved, loosely typed) is now populated by multi-floor linking with the
  shape documented in `MAP_PACKAGE_SCHEMA.md` section 3. Note for the Android team: readers may ignore it
  (single-floor import is unaffected); when multi-floor routing is added, treat `length_estimated: true` links
  as placeholders.
- 0.1.0 (implemented, not tagged): venue-level package (venue.json + floors/<id>/floor.json + floorplan.png).
  JSON Schema in turnmap.schema.json. Fixtures: valid_synthetic_basic/lshape.turnmap, invalid_*.floor.json
  (`_expect_error` gives the code the consumer must report). scale_source includes `door_width_prior` (an estimate).
  Frame: metres, origin image top-left, x right, y down — provisional until the app audit confirms (ADR-007).
  Tag `contract-v0.1.0` once ADR-007/008 are accepted.
- 0.1.0 additions (2026-10-04, still untagged, backward compatible): graph node `transition` (stairs|lift|escalator)
  on `kind: transition` nodes; POI `category` filled (stairs, lift, washroom, lab, office, classroom); `scale_source`
  value `footprint_transfer`. Fixtures regenerated.
