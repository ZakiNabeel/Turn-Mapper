# Results: multi-floor routing (2026-11-10)

Plan: `docs/PLAN_MULTIFLOOR_2026-11-10.md`. Every number below comes from a recorded run in this session
(`runs/` is gitignored; the commands are listed so anyone can reproduce them). Segmenter: classical.
A block floors (frozen test split, ADR-009) were run for the venue checks only; nothing was tuned on them.

## What was built

- **Venue routing** (`route.py`): one graph over all floors. `find_place` takes `FLOOR:node`, a room label or a
  name. A route is returned as legs per floor, floor changes, length, an estimated time and turn-by-turn steps
  ("Take the stairs up 2 floors to …"). **Step-free** routes use lifts, ramps and walkways only. Costs are time
  based: walking 1.3 m/s, stairs 20 s per level, lift 30 s wait + 5 s per level.
- **Building frames** (`link.py`): floors of one building are aligned by their wall drawings.
  - Method: scale search 0.67–1.5, FFT cross-correlation, score = share of wall pixels within 0.5 m.
  - Below the score threshold it falls back to footprint alignment.
  - Each frame is written as `floor.building_frame`, with a confidence.
- **Scale correction**:
  - A floor whose scale is an *estimate* is rescaled when it aligns (confidence ≥ 0.5) with a *measured* floor
    of the same building.
  - Measured floors are never changed; if they disagree, that is only a warning.
  - Studio can switch this off (`correct_scales`).
- **Link matching**:
  - Optimal assignment in the building frame, capped at 8 m.
  - A middle floor's stair can link both up and down.
  - Shafts get a shared id.
  - `LINK_SHAFT_GAP` reports a lift seen on non-adjacent floors at the same place.
- **Connections between buildings**:
  - Listed in the venue config (`multifloor.connections`: `FLOOR:node|label|x,y`, type `walkway|ramp|stairs|lift`)
    or drawn in Studio.
  - They are never guessed.
- **Venue checks** (QA report, run manifest, `turn-mapper validate`):
  - which floors reach which, floors cut off from their building, buildings not joined, stranded stairs/lifts;
  - sampled cross-floor routes (all and step-free);
  - a per-floor grade: ready / usable / needs work, with reasons.
- **CLI**: `turn-mapper route venue.json --from … --to … [--step-free] [--json]`.
- **Studio**:
  - a route panel in the Check tab (the leg drawn on each floor, steps listed);
  - a per-floor grade in the links panel;
  - API: `GET …/places`, `POST …/route`.
- **Per-floor fix (B1/B2), in `graph.py`**: routed links now avoid wall pixels. A lone node can move up to 1 m into
  the free area before it is bridged: a door centre in its wall gap, or a stair/lift anchor on a wall line.
- **Contract 0.1.3**, additive (ADR-019, `contract/CHANGELOG.md`):
  - typed `transitions` (adds `walkway`, `ramp`);
  - `floor.building_frame`;
  - fixture `json_synthetic_multifloor`;
  - a note for the Android team in `docs/POSITIONING_INTEGRATION.md`.

## FAST, 14 floors (A, B, C blocks)

`turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --out runs/<name>`. The
baseline (`runs/base_1110`, code at abcc809) was re-checked with the same venue checker
(`venue_checks(VenueGraph.from_package(...))`, 200 sampled routes, seed 0).

| | before (`base_1110`) | after (`mf4`) |
|---|---|---|
| floor links (stairs/lifts) | 6 | 18 |
| floor pairs connected, within a building | 8 / 60 | **60 / 60** |
| floor pairs connected, whole venue | 8 / 182 | 60 / 182 |
| floors cut off from the rest of their building (`W_FLOOR_UNLINKED`) | 6 | 0 |
| sampled cross-floor routes found | 7 / 200 | 58 / 200 |
| … step-free | 0 / 200 | 0 / 200 |
| stair/lift nodes off their floor's main graph | 7 of 29 | 0 of 29 |
| floors with more than one graph piece | 7 (A-GF 3, A-F2 4, A-F3 2, B-F1 2, C-GF 2, C-F2 4, C-F5 4) | **0** |
| floor grade ready / usable / needs work | 3 / 4 / 7 | 4 / 10 / 0 |
| rooms / doors / destinations per floor | — | identical to before on all 14 floors |

Why the rest is still missing:

- **Cross-floor routes (58/200).** The other 142 sampled pairs are in different blocks. The plans do not show
  how A, B and C are joined, so `W_BUILDINGS_SEPARATE` stays. Fix: site walk, then enter the walkways under
  `multifloor.connections` in `fast_isb.yaml` (Track C).
- **Step-free (0).** A lift was detected only on C-B1, C-F2 and C-F5. `LINK_SHAFT_GAP` places the C-F2/C-F5 lift at
  the same spot (building frame 8.6, 16.3 m) and lists C-F3 and C-F4 as the floors to mark it on in Studio. No
  lift was detected in the A or B blocks.
- **"Usable" rather than "ready".** On 10 floors the scale is still an estimate, and 5 floors have one stair or lift
  with no partner on the next level. Unmatched: A-GF n111, A-F2 n104, A-F3 n110, C-GF n27, n29, plus the lifts.
- **Scales corrected by wall alignment (unverified).**
  - The factors: B-F2 ×0.891, C-F5 ×1.046, C-F2 ×1.044, C-F1 ×1.157, C-GF ×1.257.
  - Precision check on measured pairs: C-F3/C-F4 registered at 1.0025 and B-GF/B-F1 at 1.023, so about 2 %.
  - The C-block confidences are only 0.56–0.57. The C-GF and C-F1 corrections are large, so they need a site
    tape measurement before they are trusted.

Example: `turn-mapper route runs/mf4/venue.json --from "B-15" --to "B-116"` goes from B-15 MARS Lab (B-GF) to
B-116 Maker Lab (B-F2). It is 118 m, about 2.0 min, via B-F1. The steps are "Walk 17 m … Take the stairs up
2 floors … Arrive". Stair lengths are flagged as estimates.

## Synthetic multi-floor case (known answers)

The new `tower` plan (stair core + lift) is placed on 3 levels, plus an annex joined by a configured 25 m walkway
(`tests/test_multifloor.py`, fixture `json_synthetic_multifloor`). Results:

- 5 links: stairs and lift for T0–T1 and T1–T2, plus the walkway.
- Building frames registered at scale 1.0.
- 12 of 12 floor pairs connected.
- 100 of 100 sampled routes found, all step-free.
- T0:R-102 → T2:R-106 takes the stairs: 44 m, about 1.1 min.
- The step-free version takes the lift: 37 m, about 1.5 min with the lift wait.
- T2:R-103 → W0:R-106 goes down the stairs, then over the walkway.

## Regressions

- Synthetic evaluation (`eval/evaluate_synthetic.py`): the mean row is identical to HEAD (abcc809). That is
  12/12 valid, free-space IoU 0.983, corridor IoU 0.976, rooms P/R 1.0/1.0, doors P/R 0.988/1.0, routes found
  1.0, 0 wall crossings.
- Style stress (`scripts/style_stress.py`): 11/12 cases fully correct, the same as HEAD.
- Tests: 131 passed, 1 skipped (before this round: 100 passed, 3 skipped; Studio tests now run because
  `httpx` was installed).
