# Contract changelog — .turnmap

## Unreleased
- 0.1.0 (implemented, not tagged): venue-level package (venue.json + floors/<id>/floor.json + floorplan.png).
  JSON Schema in turnmap.schema.json. Fixtures: valid_synthetic_basic/lshape.turnmap, invalid_*.floor.json
  (`_expect_error` gives the code the consumer must report). scale_source includes `door_width_prior` (an estimate).
  Frame: metres, origin image top-left, x right, y down — provisional until the app audit confirms (ADR-007).
  Tag `contract-v0.1.0` once ADR-007/008 are accepted.
- 0.1.0 additions (2026-10-04, still untagged, backward compatible): graph node `transition` (stairs|lift|escalator)
  on `kind: transition` nodes; POI `category` filled (stairs, lift, washroom, lab, office, classroom); `scale_source`
  value `footprint_transfer`. Fixtures regenerated.
