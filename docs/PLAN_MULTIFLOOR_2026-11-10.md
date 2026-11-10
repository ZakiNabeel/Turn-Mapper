# Plan: multi-floor routing and the next round of improvements (2026-11-10)

Goal: a person picks any destination in a venue (any floor, any building) and gets one route, with the
stairs/lift legs, from the `.turnmap` / `venue.json` that TURN-Mapper produces. At the same time, make the
per-floor maps more routable, because a multi-floor route is only as good as its weakest floor.

What exists today (start of this round):

- `link.py` pairs stair/lift nodes on **adjacent levels of one building** by type and position after
  aligning the floors' bounding boxes (greedy, 4 m cap). Manual links from Studio override. Links go into
  `venue.transitions` (loosely typed in the schema). `cross_floor_path_m` returns only a length.
- The positioning export already turns `transitions` into connectors + edges.
- No route object, no instructions, no step-free option, no inter-building links, no check that floors are
  actually reachable from each other, no shared building frame (`building_frame` is documented as optional
  but never written).

Status (end of 2026-11-10): A1–A10 and B1–B3 done; results in `RESULTS_MULTIFLOOR_2026-11-10.md`. Track C open.

## Track A — multi-floor routing (this round, Claude)

| # | Item | Done when |
|---|---|---|
| A1 | **Baseline** on all 14 FAST floors: per-floor graph pieces, transitions found, links made, which floors reach which | numbers recorded in `RESULTS_MULTIFLOOR_2026-11-10.md` |
| A2 | **Venue routing module** `route.py`: one graph over all floors (floor edges + transitions + inter-building connections); `find_place()` by room label/name or `FLOOR:node`; `route()` returning per-floor legs, floor changes, total length, estimated time and turn-by-turn instructions; **step-free** option (no stairs/escalators); time-based costs (lift wait, stairs per level) | unit tests + synthetic end-to-end test |
| A3 | **Floor registration**: estimate each floor's offset in a shared building frame by aligning wall drawings of adjacent levels (phase correlation on rasterised walls, bounds alignment as fallback, confidence reported); write `building_frame` per floor | FAST C block: offsets found with confidence; stairs line up across levels |
| A4 | **Better link matching**: optimal assignment (Hungarian) in the building frame instead of greedy bounds alignment; stair *shafts* (chains through several levels) get one id; lengths from a venue `floor_height_m` (still flagged as estimates) | link tests; FAST link count before/after, unmatched list |
| A5 | **Inter-building and manual connections in the venue config** (`connections:`), resolved to the nearest graph node by room label or metric point; type `walkway`/`ramp`/`stairs`/`lift` | config test |
| A6 | **Venue validation**: floors not reachable from the rest (`W_FLOOR_ISOLATED`), transitions stranded in a small graph piece (`W_TRANSITION_STRANDED`), sampled cross-floor routes (success rate) in the QA report, manifest and `validate` | validator tests; FAST numbers |
| A7 | **CLI** `turn-mapper route venue.json --from … --to … [--step-free]`; `validate` reports the venue checks | CLI test |
| A8 | **Studio**: route panel (start, destination, step-free) drawing the leg of the floor on screen and listing the instructions; links panel shows building-frame confidence | Studio API test |
| A9 | **Contract 0.1.3** (additive, backward compatible): typed `transitions` items, types `walkway`/`ramp` added, optional `floor.building_frame`; CHANGELOG, MAP_PACKAGE_SCHEMA, fixture `json_synthetic_multifloor`, writer/reader tests, schema copy in sync, note for the Android team; positioning export maps `walkway` to a plain edge | contract tests |
| A10 | **Synthetic multi-floor test case** with known answers: same building on 3 levels with a stair core and a lift; end-to-end run → links → routes between floors, step-free route uses the lift | test passes |

## Track B — per-floor quality that blocks multi-floor routes (this round, Claude)

| # | Item | Done when |
|---|---|---|
| B1 | Floors with several graph pieces (D-10: B-F1, C-GF, C-F2, C-F5): find why the pieces are not joined and fix the rule if it is general (not a FAST special case) | pieces per floor before/after; synthetic/style/public-plan regressions unchanged |
| B2 | A stair/lift node must sit on the floor's main graph piece; if bridging fails, report it (feeds A6) | test |
| B3 | Map-quality score per floor (destinations reachable, graph pieces, estimated scale, transitions) shown in the report and Studio, the basis for an automatic classical/learned choice later | in report |

## Track C — needs the team (cannot be done from here)

- Correct the annotation drafts (A block + 9 public plans) in Studio → answer key; then fine-tune the
  learned model on them (Kaggle) and apply the promotion rule.
- Site measurements: floor-to-floor height and one stair run per block (replaces the 6 m estimate); the
  real walking links between A, B and C blocks (entered as `connections:` in `fast_isb.yaml` or in Studio).
- Android team: read typed `transitions` (contract 0.1.3) and route across floors in the app.

## Rules kept

- No FAST-specific code paths; venue facts only in `configs/venues/*.yaml`.
- No tuning on the A block (ADR-009): A floors are run for the venue checks only, nothing is tuned on them.
- Every number in the results doc comes from a recorded run.
- Contract change is additive (MINOR-compatible 0.1.x bump), with all the steps in CLAUDE.md.
