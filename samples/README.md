# Sample floor plans

Only commit plans you have permission to keep in the repo. Otherwise store them under `$TURN_DATA_DIR/plans/` and list them here.

## Files

| file | contents | format (fill after `turn-mapper inspect`) | source + permission | notes |
|---|---|---|---|---|
| fast_blocks.pdf | FAST-NUCES Islamabad A, B, C block floor plans (= Floor_Plans_2.pdf, sha256 8316d9d7…) | raster (embedded PNG/JPEG, see docs/PLAN_INVENTORY.md) | from: ____ , permission: ____ | split per ADR-009 |

## Page → building/floor

See `configs/venues/fast_isb.yaml` (draft) and `docs/PLAN_INVENTORY.md` §2.

## Measured distances (scale ground truth)

Copy them into `configs/venues/fast_isb.yaml` like this (pixel coordinates from the floor image, e.g. read off `runs/<run>/qa/<floor>_overlay.png` in any image viewer):

```yaml
scale_evidence:
  C-F3:
    - { p1_px: [12, 230], p2_px: [975, 230], distance_m: 41.3 }   # first = used to fit
    - { p1_px: [140, 180], p2_px: [140, 285], distance_m: 2.9 }   # others = checked, residual reported
```

Measure with a laser meter or tape, wall face to wall face, straight lines along corridors. At least 3 per floor you will demo; the first is used to fit the scale, the rest check it.

| floor | point A (describe precisely) | point B | distance (m) | tool | by / date |
|---|---|---|---|---|---|
| C-F1 | | | | | |
| C-F1 | | | | | |
| C-F1 | | | | | |

## Manual ground truth

- App JSON export of the floor built by hand in TURN: `____` (who built it, minutes taken: ____)
