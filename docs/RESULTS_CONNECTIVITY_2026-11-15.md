# Results: connections between buildings, lifts, real-CAD training stage (2026-11-15)

Every number comes from a recorded run in this session (`runs/` is gitignored). Segmenter: classical.
Nothing was tuned on the A block (ADR-009); the lift work was done on the C block (dev split).

## What changed

- **Connections between buildings, generic.** A connection end may be an edge of the floor's drawing
  (`FLOOR@left|right|top|bottom`): the tool takes the corridor node nearest that edge. Ends that name a
  building with `levels: [...]` make one connection per level. Such links are marked `auto` 0.5 and reported as
  `LINK_ENDPOINT_ESTIMATED` until the ends are replaced with exact nodes. Which floors are joined is never
  guessed. Studio has a "Connections between buildings" panel for the same thing.
- **FAST block links** (`configs/venues/fast_isb.yaml`), from the team's site facts: A-GF joins B-GF; on floors
  1 and 2, A, B and C are joined; everything else stands alone. From the site plan on page 1 the blocks form a
  chain A–B–C, so the config has A↔B on levels 0–2 and B↔C on levels 1–2 (5 walkways, length 0: the blocks meet).
- **Lifts.**
  - A lift is now also read from an "Elevator" / "Lift" word anywhere on the plan, not only when the shaft was
    detected as a room, and from the learned model's lift class (previously predicted and thrown away).
  - A lift found on two floors but not on a floor between them gets a *proposed* stop there if a graph node is
    within 4 m of the shaft and the floors are aligned by their walls (`LINK_SHAFT_INFERRED`, `auto` 0.4).
    Otherwise `LINK_SHAFT_GAP` names the floor.
- **Route wording.** Where two buildings meet, the step reads "Continue into B Block – level 1."
- **Training stage S4** (real CAD drawings, FloorPlanCAD): converter, partial-label loss, Kaggle script and
  notebook. Written and tested on fake tiles; **not yet run on the real data** (needs the Kaggle GPU).

## FAST, 14 floors

`turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --out runs/<name>`;
before = `runs/mf4` (commit d1dc32a), after = `runs/mf6`.

| | before (`mf4`) | after (`mf6`) |
|---|---|---|
| floor pairs connected, whole venue | 60 / 182 | **182 / 182** |
| floor pairs connected, within a building | 60 / 60 | 60 / 60 |
| sampled cross-floor routes found (200, seed 0) | 58 | **200** |
| … step-free (lifts, walkways only) | 0 | **86** |
| links: stairs / lift / walkway | 18 / 0 / 0 | 18 / 4 / 5 |
| C floors with a lift detected | 3 of 7 | 6 of 7 |
| buildings not joined (`W_BUILDINGS_SEPARATE`) | A, B, C separate | none |
| rooms / doors per floor | — | identical on all 14 floors |
| destinations per floor | — | identical, plus one "Lift" on C-F1, C-F3, C-F4 |

Example: `turn-mapper route runs/mf6/venue.json --from "A-F1:Conference Hall" --to "C-F2:C209"` gives 271 m,
about 3.7 min, floors A-F1 > B-F1 > C-F1 > C-F2 ("Continue into B Block", "Continue into C Block", "Take the
stairs up 1 floor").

Still open on FAST:

- **The five walkway ends are estimates.** Each joins the corridor node nearest the stated edge of the drawing.
  The edges come from reading the site plan (A's drawing is turned 180°, C's 90°); they need a check on site
  or in Studio.
- **C-GF lift.** The reader does not pick up the small "Elevator" label on that drawing, and the nearest graph
  node is 8 m from the shaft, so no stop is proposed (`LINK_SHAFT_GAP`). Mark it in Studio.
- **Step-free is 86 of 200**, not 200: no lift was found in the A or B block, so floors A-F3 and anything
  reached only by stairs has no step-free route.
- Scales of 10 floors are still estimates (unchanged from 2026-11-10).

## Regressions

- Synthetic evaluation: mean row identical to the previous run (12/12 valid, free-space IoU 0.983, corridor IoU
  0.976, rooms P/R 1.0/1.0, doors P/R 0.988/1.0, routes found 1.0, 0 wall crossings).
- Style stress: 11/12 cases fully correct (same).
- Tests: 145 passed, 0 skipped (the ML tests now run here; before: 131 passed, 1 skipped).
