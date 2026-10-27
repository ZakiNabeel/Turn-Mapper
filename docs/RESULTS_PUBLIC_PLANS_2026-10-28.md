# Real plans, round 2: vector-PDF input and door-based corridors (2026-10-28)

**Plan, diagnosis and industry comparison:** `docs/PLAN_REAL_PLANS_2026-10-28.md`.
**Previous round:** `docs/RESULTS_PUBLIC_PLANS_2026-10-27.md`.

## Setup

**Code:** this commit, classical segmenter, one generic config for every plan (as in round 1).

**Plans:**
- **Development, 19 plans / 16 institutions:** batch 1. The rules were built while looking at these.
- **Held out, 9 plans / 8 institutions.** Not looked at until the rules were frozen.
  - Batch 2: AA, Michigan, Bern, UW, Warwick.
  - Batch 3, downloaded 2026-10-27 evening: UK Department for Education primary and secondary GA plans, Conwy County Borough Council school, Truman State.
  - A Southwest Minnesota State file arrived truncated and could not be used.
- **In total:** 28 plans from 24 institutions.

**Before vs after:**
- **Before:** the pipeline as released (v0.3.x). Page rendered as a picture, circulation = largest space, no frame rule.
- **After:** vector-PDF adapter plus the new corridor rules.
- Run with `scripts/eval_public_plans.py` (`--no-vector` and `TURN_PARAMS_JSON` reproduce "before").

**Regression checks (all unchanged after the change):**

| check | result |
|---|---|
| FAST, all 14 floors | identical counts and scales |
| Synthetic evaluation | identical table |
| Style stress | 11/12 |
| pytest | 111 passed (2 new tests) |

## Objective score: printed room numbers (`scripts/score_textlayer.py`)

Plans whose PDF text layer holds at least 10 room numbers are scored.

- **separated:** the number lies in its own room space.
- **reachable:** that room is a destination on the main route graph.
- **named:** the destination carries that number.

Title-block numbers also count, so the scores are lower bounds.

| set | plan | numbers | separated | reachable | named |
|---|---|---|---|---|---|
| dev | Bangor Brigantia 1 | 92 | 0.457 → 0.707 | 0.283 → **0.174** | 0.011 → 0.174 |
| dev | Bangor Main Arts 1 | 113 | 0.106 → 0.496 | 0.000 → 0.071 | 0.000 → 0.071 |
| dev | Cal Poly Business 1 | 40 | 0.450 → 0.300 | 0.000 → 0.250 | 0.000 → 0.225 |
| dev | Cal Poly Engineering 1 | 59 | 0.644 → 0.508 | 0.034 → **0.407** | 0.034 → 0.407 |
| dev | Cronulla HS | 11 | 0.636 → 0.909 | 0 → 0 | 0 → 0 |
| dev | Minnesota State Armstrong 1 | 124 | 0.000 → 0.532 | 0 → 0 | 0 → 0 |
| dev | Minnesota State Library 2 | 14 | 0.000 → 0.143 | 0 → 0 | 0 → 0 |
| dev | Reading library 1 | 10 | 0.000 → 1.000 | 0 → 0 | 0 → 0 |
| dev | Simmons | 25 | 0.000 → 0.040 | 0 → 0 | 0 → 0 |
| dev | Tufts Tisch | 54 | 0.056 → 0.000 | 0 → 0 | 0 → 0 |
| dev | Wesleyan (scan) | 30 | 0 → 0 | 0 → 0 | 0 → 0 |
| **dev mean (11)** | | | **0.214 → 0.421** | **0.029 → 0.082** | **0.004 → 0.080** |
| held out | AA | 22 | 0.273 → 0.182 | 0 → 0 | 0 → 0 |
| held out | Bern ExWi | 45 | 0.022 → 0.044 | 0.022 → 0.000 | 0 → 0 |
| held out | UW 840 | 11 | 0.273 → 0.273 | 0 → 0 | 0 → 0 |
| held out | Warwick L02 | 79 | 0.671 → 0.304 | 0.000 → 0.076 | 0.000 → 0.063 |
| held out | Conwy school | 79 | 0.000 → 0.076 | 0.000 → 0.013 | 0 → 0 |
| held out | Truman Baldwin | 52 | 0.019 → 0.019 | 0 → 0 | 0 → 0 |
| **held-out mean (6)** | | | 0.210 → 0.150 | **0.004 → 0.015** | 0.000 → 0.011 |

The two DfE GA plans have fewer than 10 printed room numbers, so they are graded visually only.

## Visual grade (rubric unchanged from round 1)

- **A:** usable after light review.
- **B:** routes run on the real corridors inside the building, but destinations are missing or wrong.
- **C:** not usable.

| set | before: A / B / C | after: A / B / C | changed grades |
|---|---|---|---|
| dev (19) | 0 / 3 / 16 | 0 / **6** / 13 | Bangor Main Arts, Cal Poly Engineering and Minnesota State Library move C → B |
| held out (9) | 0 / 1 / 8 | 0 / **3** / 6 | Michigan Fine Arts and Warwick move C → B; Bern stays B |
| all 28 | 0 / 4 / 24 | 0 / **9** / 19 | |

**Notes on individual plans:**
- **Cal Poly Engineering** (the plan in the user's screenshot). Routes now run through the interior corridor network and reach 41% of the printed room numbers (was 3%).
  - Cal Poly's corridors are partly open-air walkways, so routes also run outside the building.
  - The sheet margin is still walkable on this plan. An outdoor strip limited to the building edge was tried (`vector_outdoor_apron_gaps`), but it lowered Cal Poly Business, so it is off.
- **Bangor Brigantia:** rooms are better separated (0.46 → 0.71), but fewer are reachable (0.28 → 0.17). The corridor graph is split into 19 pieces where fire doors cut the corridor.

## What this shows

1. **Diagnosis confirmed.** On CAD sheets drawn like Cal Poly's and Bangor's (lines, door swings with gaps, text in the PDF), reading the drawing's own vectors and text more than doubles room separation and makes destinations reachable. Labels are now exact where they are found (named = reachable).
2. **Small held-out gain.** It does not yet generalise.
   - Held-out plans use other conventions: furniture drawn on the same layer as walls (Warwick, Bern), coloured room fills, plans with no door swings (AA), and GA sheets with solid-filled existing buildings (DfE).
   - Reachable rose only from 0.4% to 1.5%. Visual B grades rose from 1 to 3 of 9.
3. **A new fault on colour wayfinding maps (Reading, Michigan State, Tufts, Simmons, Cronulla).** Mid-grey room fills are now drawn as solid wall, because the dark-fill threshold is luminance < 0.45. A stricter threshold (near-black only) is the obvious next fix, but it was not applied after the held-out run.
4. **No plan reaches grade A.** Industry tools (Pointr reports 90% detection on 19 plans) get there with models trained on thousands of digitised buildings and a human QA step. Rules alone are not enough for "any institution".

## Next steps

1. **Annotate** the 9 held-out plans and the FAST A block (rooms, doors, corridors) for a real scored benchmark.
2. **Learn which vector entities are walls, doors and furniture.** FloorPlanCAD labels exactly these CAD primitives (about 15,000 drawings). This replaces stroke-style heuristics.
3. **Dark-fill threshold:** treat only near-black fills as walls. Then re-check the wayfinding maps.
4. **Corridor graph:** join corridor pieces across fire doors (Bangor: 19 pieces), and clip the sheet margin round the building.
5. **Studio:** show the operator the known doors and corridor choice so one click fixes a wrong corridor.

---

# Round 3 (same day): next steps 3 and 4 done

**Code:** commits `16e50c8` (fills) and `8aaa108` (flattened arcs, Studio, drafts). Same 28 plans, same generic config, same scorer.
**Rules were built on the dev plans only** (Bangor Brigantia for the fire doors, Cal Poly for the margin). The
held-out plans were run once, after the change was frozen. Note that the held-out plans were already seen once
in round 2, so they are "seen-once" rather than pristine.

## What changed

1. **Fills:** only near-black fills are walls (luminance < 0.2, was < 0.45). Grey and colour room fills on
   wayfinding maps are no longer drawn as solid wall.
2. **Fire doors / flattened arcs:** some CAD writers export a door swing as a chain of 10-20 short straight
   segments instead of a curve. These chains are now recognised as arcs (`polyline_arcs`: equal-length
   segments that fit a circle within 5% of its radius). On Bangor Brigantia this finds 102 swings instead of 63,
   including every fire door across the corridor, so the corridor is no longer cut into pieces.
3. **Sheet margin (tried, off):** a building outline inside the sheet frame (walls closed over gaps up to 4 door
   widths) with a 2-door-width strip kept along the walls. On Cal Poly Engineering it removed the margin but also
   the open-air walkways that its rooms open onto, so reachable fell 0.407 → 0.186; on Cal Poly Business 0.25 →
   0.05. Left in the code as `frame_footprint_gaps`, default off. Cal Poly's walkways are real routes; the margin
   is a cosmetic fault, not a routing one.
4. **Studio:** doors read from a door swing are drawn solid and exported with confidence 0.95; doors that are
   only a gap in the walls are dashed (confidence 0.7), so the operator checks those first. No contract change.
5. **Annotation drafts:** `scripts/make_annotation_drafts.py` creates one Studio project per plan with the
   automatic map already run, for the team to correct into ground truth (`docs/DATA_AND_ANNOTATION.md`).

## Printed-room-number score (round 2 → round 3)

| set | plan | separated | reachable | named |
|---|---|---|---|---|
| dev | Bangor Brigantia 1 | 0.707 → 0.663 | 0.174 → **0.326** | 0.174 → **0.315** |
| dev | Tufts Tisch | 0.000 → **0.463** | 0 → 0 | 0 → 0 |
| dev | other 9 | unchanged | unchanged | unchanged |
| **dev mean (11)** | | 0.421 → **0.459** | 0.082 → **0.096** | 0.080 → **0.093** |
| held out | Warwick L02 | 0.304 → **0.582** | 0.076 → **0.342** | 0.063 → **0.291** |
| held out | Conwy school | 0.076 → **0.367** | 0.013 → 0.025 | 0 → 0.025 |
| held out | Bern ExWi | 0.044 → 0.067 | 0 → 0 | 0 → 0 |
| held out | AA, UW, Truman | unchanged | unchanged | unchanged |
| **held-out mean (6)** | | 0.150 → **0.248** | 0.015 → **0.061** | 0.011 → **0.053** |

From the released pipeline (round 1) to now: dev reachable 0.029 → 0.096, held-out reachable 0.004 → 0.061.

## Visual grades (same rubric)

| set | round 2: A / B / C | round 3: A / B / C | changed |
|---|---|---|---|
| dev (19) | 0 / 6 / 13 | 0 / **8** / 11 | Bangor Brigantia C → B (one connected corridor ring); Reading C → B (open library floor now routed) |
| held out (9) | 0 / 3 / 6 | 0 / 3 / 6 | Warwick stays B but its routes now follow the corridors instead of spreading through the offices |
| all 28 | 0 / 9 / 19 | 0 / **11** / 17 | |

## Regression checks

FAST 14 floors: identical counts and scales. Synthetic evaluation: identical (timings only). Style stress
11/12. pytest 112 passed (1 new test for flattened arcs).

## Known costs

- Bern ExWi now takes 26 min (was 9): 352 graph pieces, and the bridging step routes each one over the whole
  page. A per-pair window or caching unroutable pieces would fix this.
- No plan reaches grade A yet.

---

# Learned vs classical on the real plans (Kaggle GPU, 2026-10-28)

**Run:** `notebooks/public_eval_kaggle.ipynb` (`scripts/kaggle_public_eval.py`), Kaggle T4, code at commit `16e50c8`
(round 2 rules + near-black fills, *before* the flattened-arc fix). Plans downloaded from each institution at
run time. Configs as frozen in RESULTS_ML_V2: learned = S2 fine-tuned weights, network doors, scales
0.7/1.0/1.4; hybrid = classical walls plus network walls where p(wall) > 0.6. Same scorer. Run time: classical
42 min, learned 94 min, hybrid 50 min for the 28 plans.

| set | config | separated | reachable | named |
|---|---|---|---|---|
| dev (11) | classical | 0.464 | 0.082 | 0.080 |
| dev (11) | **learned** | 0.467 | **0.163** | **0.128** |
| dev (11) | hybrid | **0.584** | 0.138 | 0.103 |
| held out (6) | classical | 0.157 | 0.015 | 0.011 |
| held out (6) | **learned** | 0.241 | **0.055** | **0.055** |
| held out (6) | hybrid | **0.290** | 0.011 | 0.006 |

Per plan (reachable): learned is higher on Bangor Brigantia (0.17 → 0.55), Bangor Main Arts (0.07 → 0.20),
Minnesota State Armstrong (0 → 0.13) and Library (0 → 0.29), Cal Poly Engineering (0.41 → 0.46), Warwick
(0.08 → 0.25) and Conwy (0.01 → 0.08); lower on Cal Poly Business (0.26 → 0.13). Separation drops on the
colour wayfinding maps (Cronulla 0.91 → 0.09, Tufts 0.46 → 0.13). Hybrid separates rooms best but its
corridors break up on unseen plans.

**By eye (contact sheets):** learned routes along the corridors on Bangor (both), Minnesota State (both),
Reading, App State and Warwick; it also produces faint spurious room outlines in empty sheet areas and floods
the outdoors on Cal Poly like classical. No plan reaches grade A with any configuration.

**Reading:** this is the first evidence on real drawings that the learned segmenter is better than the rules
where it matters (rooms reachable and named), including on unseen plans (3.7x). It is not yet promoted: the
promotion rule (ADR / ML_IMPROVEMENT_PLAN) also needs the held-out FAST A block, which still has no ground
truth; the drafts for that are now generated by `scripts/make_annotation_drafts.py`. The classical round-3
fix (flattened arcs) gives classical 0.061 held-out reachable on its own, so the two are compared again on the
same new code (Kaggle version 2, learned only).
