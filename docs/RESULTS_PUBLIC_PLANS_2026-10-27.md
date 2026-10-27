# Real plans from other institutions (2026-10-27)

**Question:** does the pipeline work on floor plans it has never seen, drawn by other institutions?

Until now it had been tested only on two kinds of plan: the FAST plans, and generated plans with exact answers.

## Data

- **24 public floor plans from 21 institutions:** 15 universities, 3 colleges (Lone Star, UC Blue Ash, the Architectural Association), 2 schools and 1 hospital. Three institutions contribute two plans each (Bangor, Cal Poly, Minnesota State).
- **Sources:** each institution's own website. The URLs are in the eval sources list (kept with the evaluation files, not in git). The user downloaded them on 2026-10-27 because the dev container has no general internet.
- **Kinds of drawing:**
  - CAD exports (Cal Poly, Minnesota State, Bangor, Warwick, Bern, AA);
  - colour wayfinding maps (Reading, Surrey, Michigan State, Tufts, Simmons, Michigan, UW, Evelina);
  - line maps (Appalachian State, Lone Star, Missouri S&T, UC Blue Ash);
  - a scanned PDF (Wesleyan);
  - school maps (Cronulla, Wheaton).
- **Licensing:** the plans are third-party material. They are not committed, and no overlay of them is committed.
- **Two batches:**
  - Batch 1: 19 plans from 16 institutions. These were looked at while developing the fix below.
  - Batch 2: 5 plans from 5 more institutions (AA, Michigan, Bern, UW, Warwick). These arrived later and were **not** looked at before the fix was frozen.

## Method (the same for every plan, nothing set per plan)

- **Script:** `scripts/eval_public_plans.py`. Classical segmenter.
- **Input:** each file goes through the normal input adapters.
  - Vector PDFs use the CAD-aware renderer, with resolution capped at 5,000 px on the long side.
  - Page 1 is used. For AA and Bern, page 1 is a cover or site plan, so the first floor-plan page was picked, as an operator would in Studio.
- **Config:** one generic venue config, with room-number pattern `(?:[A-Z]{1,3}[-.]?)?\d{2,4}(?:\.\d)?[A-Z]?`.
- **Ground truth:** these plans have none. Measured instead:
  - **Automatic metrics:** structural validity, counts, graph pieces, wall-crossing edges and run time.
  - **Room-number reading:** for PDFs with a text layer, the share of the printed room numbers that the map reads as a room label. Printed tokens are those matching the pattern above; years are removed. The token list may include a few numbers that are not rooms.
  - **Visual grade.** The overlay of every plan was inspected by eye. Rubric, fixed before grading:
    - **A** usable after light review: corridors right, destinations linked.
    - **B** editable: the graph runs on the real corridors inside the building, but destinations are missing or wrong, so it needs substantial Studio correction.
    - **C** not usable: the graph is mostly outside the building, in a legend or title block, or absent.

## Result: classical pipeline as released (v0.3.x)

| institution | floor | valid | rooms | doors | destinations | graph pieces | room numbers read | s | grade | main cause |
|---|---|---|---|---|---|---|---|---|---|---|
| Architectural Association | Bedford Sq basement+ground | yes | 134 | 70 | 0 | 1 | 0.00 | 85 | C | street fill taken as corridor |
| Appalachian State | Belk Library 1 | yes | 57 | 0 | 0 | 2 | — | 29 | C | doors drawn as swings, no gaps |
| Bangor | Brigantia 1st | yes | 99 | 60 | 29 | 3 | 0.17 | 85 | **B** | lower-left corridor missed; some rooms called corridor |
| Bangor | Main Arts 1st (1:200) | yes | 75 | 42 | 0 | 1 | 0.05 | 76 | C | title block taken as corridor |
| Cal Poly | Business, floor 1 | yes | 232 | 16 | 3 | 3 | 0.28 | 118 | C | sheet frame: outdoors taken as corridor |
| Cal Poly | Engineering, floor 1 | yes | 260 | 26 | 6 | 2 | 0.32 | 99 | C | sheet frame: outdoors taken as corridor |
| Cronulla High School | school map | yes | 58 | 16 | 13 | 2 | 0.64 | 63 | C | campus map, not a floor plan |
| Evelina London (NHS) | Southwark Wing LG | yes | 12 | 0 | 0 | 1 | — | 31 | C | colour wayfinding map |
| Lone Star College | University Center 1 | yes | 1 | 0 | 0 | 1 | — | 9 | C | line map, doors as swings |
| Minnesota State Mankato | Armstrong Hall 1 | yes | 19 | 6 | 4 | 3 | 0.00 | 129 | C | sheet frame |
| Minnesota State Mankato | Memorial Library 2 | yes | 65 | 45 | 21 | 2 | 0.00 | 91 | C | sheet frame |
| Missouri S&T | Library 1 | yes | 7 | 2 | 0 | 1 | — | 42 | C | page border |
| Michigan State | Main Library 1 | yes | 27 | 0 | 0 | 1 | 0.00 | 73 | C | colour wayfinding map |
| Reading | Library 1 | yes | 6 | 0 | 0 | 1 | 0.00 | 69 | **B** | open-plan floor graph right, no destinations |
| Simmons | Main College ground | no | 24 | 2 | 0 | 0 | 0.00 | 169 | C | colour wayfinding map |
| Surrey | Library 1 | no | 1 | 0 | 0 | 0 | — | 7 | C | colour wayfinding map (960 px) |
| Tufts | Tisch Library (4 levels on one sheet) | yes | 44 | 5 | 2 | 5 | 0.00 | 240 | C | colour wayfinding map |
| UC Blue Ash | Muntz Hall 1 | no | 38 | 29 | 9 | 5 | — | 18 | **B** | corridors mostly right; edges leave the walkable area |
| Michigan | Fine Arts Library 1 | yes | 41 | 15 | 0 | 1 | — | 32 | C | colour wayfinding map |
| Bern | ExWi, 1st basement | yes | 135 | 158 | 38 | 20 | 0.00 | 166 | **B** | corridors right but split into 20 pieces |
| Washington (UW) | 840 Level 2 | yes | 25 | 6 | 0 | 1 | 0.00 | 80 | C | colour map on dark background |
| Warwick | Physics L02 GA plan | yes | 139 | 57 | 5 | 1 | 0.26 | 165 | C | colour-coded CAD; atrium only |
| Wesleyan | Bennet Hall 2 | no | 0 | 0 | 0 | 0 | 0.00 | 4 | C | scanned PDF, nothing found |
| Wheaton High School | school map | yes | 13 | 1 | 0 | 1 | 0.00 | 40 | C | legend frame taken as corridor |

**Summary, 24 plans:**

| | count |
|---|---|
| Structurally valid output | 20 / 24 |
| Grade A (usable after light review) | **0 / 24** |
| Grade B (editable in Studio) | **4 / 24** |
| Grade C (not usable) | **20 / 24** |

**Further measurements:**

- **Destinations:** at least one destination on 10/24 plans, often in the wrong places.
- **Room numbers read:** on the 15 PDFs with at least 10 printed room numbers, a mean of 0.11 and a median of 0. Best: Cal Poly 0.32 and 0.28, Warwick 0.26.
- **Wall crossings:** 0 graph edges cross a wall on any plan.
- **Run time:** median 75 s per plan at about 5,000 px, ranging from 4 to 240 s, on 2 shared CPU cores.

**Main causes (primary cause of the 20 C grades):**

| cause | plans |
|---|---|
| Drawing border, title block or legend taken as the corridor | 7 |
| Colour wayfinding maps (walls not drawn as lines) | 8 |
| Line maps with doors drawn as swings, or a street fill | 3 |
| Scanned PDF | 1 |
| Campus map rather than a floor plan | 1 |

## A general fix tried: the drawing-sheet frame

**Rule:** `sheet_frame_outside`, in `vectorize.py`. It is on by default.

- A wall component counts as a sheet frame when:
  - it spans at least 60% of the image in both directions;
  - it runs along at least 3 of its bounding-box edges.
- The space just inside the frame then counts as outdoors (background, not corridor) when:
  - it touches at least half of the frame's inner perimeter;
  - it covers at least a quarter of the framed area.
- Entrances are first sealed with twice the door gap.

**Regression checks:** none of these changed.

| check | result with the rule |
|---|---|
| Synthetic evaluation (12 cases) | identical numbers to the rule switched off |
| Style stress test | still 11/12 |
| FAST, all 14 floors | identical counts and scales (14/14 PASS) |
| pytest | 109 passed |

**Effect:**

- **Batch 1 (seen while building the rule):**
  - The false outdoor corridor network disappears on the frame-enclosed plans.
  - Only Cal Poly Engineering becomes usable as a graph: the main corridor loop is found inside the building, so it moves C → B, though it still has 0 destinations.
  - On Minnesota State and Cal Poly Business the outdoors is removed, but the corridors are still not found. The likely causes are entrances wider than the sealing and door swings drawn without gaps.
  - Grade B: 4 → 5 of 24.
- **Batch 2 (held out):** identical output with and without the rule. None of the 5 plans has a sheet frame.
- **Reading:** the rule removes a class of false maps without changing anything else. It is not enough on its own: doors drawn as swings and colour wayfinding maps are the next blockers.

## Learned segmenter on these plans

- **Not run at scale.**
  - One trial: S3a with the tuned settings (network doors, scales 0.7/1.0/1.4) on the smallest plan, UC Blue Ash, 702 × 1280 px.
  - It took 148 s on 2 CPU cores and the graph came out in 159 pieces.
- **Next:** the 24-plan run needs a GPU (Kaggle), with the S2 weights, which are stored only on Kaggle.

## Conclusion

The classical pipeline is reliable on the FAST plans and on generated plans with exact answers. It does **not** yet generalise to other institutions' drawings. Even with the frame rule, none of the 24 plans gives a map usable after light review, and 5 are editable.

"Any floor plan" is therefore true only in the weak sense of the project definition: any plan is accepted and gets a best-effort proposal. For other buildings, today, most of the map would be drawn by hand in Studio.

**The next work, in order:**

1. **Ground truth.** Annotate 10 of these plans (rooms, doors, corridors), together with the FAST A block, to turn this test into a scored benchmark.
2. **Learned and hybrid models.** Run them on the 24 plans on a Kaggle GPU. ResPlan and the institutional training data include door swings and coloured fills.
3. **Classical rules:**
   - door swings: treat an arc plus a leaf as an opening;
   - legend and title-block masking;
   - a crop and page picker in Studio, so the operator removes the sheet furniture before running.
4. **Fine-tuning data:** FloorPlanCAD (about 15,000 CAD drawings with labelled walls and doors, including schools and hospitals).
