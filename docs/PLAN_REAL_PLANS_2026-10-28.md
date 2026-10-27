# Making real plans work: diagnosis, industry practice, plan (2026-10-28)

## Why the routes sat only on the blue area

Routes are built only inside the space classified as **circulation**, shown blue in the overlays.

The old rule was "circulation = the largest open space, plus door-rich spaces reached from it through doors". A stage-by-stage diagnostic on Cal Poly Engineering (`/home/claude/eval_public/diag.py`, not committed) showed four separate faults:

1. **Sheet border.** It closes off the outdoors. The outdoors was 39% of the page, so it won "largest space" and carried the routes. The real corridors were separate spaces that never became circulation.
2. **Door swings.** Each door is drawn as a leaf line plus an arc inside the wall gap. The raster stages read both as wall, so the gap is sealed and no room joins the corridor. Result: 0 destinations.
3. **Hatching.** The diagonal fill lines are read as walls, and every hatched room shatters into dozens of slivers.
4. **Room numbers.** They were read with OCR from pixels, although the PDF holds every number as text with exact coordinates.

## What industry tools do

- **Pointr** (US patent 12,100,083, MapScale®):
  - First strips text, cross-hatching, leader lines and duplicate furniture from the CAD file, and keeps the text as a database.
  - Finds the floor outline (ML plus an active contour) to drop extraneous entities such as title blocks.
  - Detects rooms with ML and names them from the text.
  - Exports per-floor GeoJSON/IMDF.
  - Published benchmark (19 plans): detection 90.2%, classification 81.5%, identification 71.5%.
- **Esri ArcGIS Indoors:**
  - Builds rooms (units) from the CAD polylines of chosen layers. Door layers are closed. There are gap tolerances, a minimum unit width and a minimum unit area.
  - CAD text is mapped to unit names.
  - Pathways are generated over the level, with walls, windows and columns as obstacles and unit centroids as destinations.
- **Navigine and visioglobe-style CMS:** upload, georeference, then edit the graph largely by hand.
- **IMDF** (Apple / OGC community standard): units with categories (room, walkway…), openings, levels and anchors.
- **The common lesson:** work from the drawing's own vectors and text, clean the sheet first, and treat an opening as a first-class object that joins two spaces.

## Plan and status

| step | what | status |
|---|---|---|
| P0 | Objective score without annotation: the PDF text layer's room numbers as known points (`scripts/score_textlayer.py`): **separated** (in its own room), **reachable** (a destination on the main graph), **named** | done |
| P1 | Vector-PDF adapter (`vector_pdf.py`), described below | done |
| P2 | Room labels from the PDF text layer (no OCR) | done |
| P3 | Building outline / outdoors. Sheet-frame rule; an outdoor apron was tried and then switched off (`vector_outdoor_apron_gaps=0`), because the apron became the main graph component | partly |
| P4 | Corridor classification, described below | done |
| P5 | Re-run the development set and the held-out sets; deck and report | running |
| later | Raster door swings, wayfinding colour maps, learned model on GPU, annotation of 10 plans + A block | open |

**P1, the vector-PDF adapter:**

- door swings (one arc or several arc pieces, with a leaf as a line or thin rectangle) are removed and kept as known openings;
- 45° hatching is removed;
- text is not drawn;
- dark fills are kept;
- the door width read from the swings sets the gap size.

**P4, corridor classification:**

- the seed is the space most doors open onto, not the largest space;
- door-rich elongated spaces count as circulation (perimeter² / 4·area ≥ 4; a square scores 4, so any irregular or longer shape qualifies);
- narrow links between two circulation spaces count as circulation;
- every known opening joins the two spaces on either side of it.

**Development discipline:**

- Rules are built on the batch-1 plans. Batch 2 (5 plans) and batch 3 (4 plans) are run only after the rules are frozen.
- The FAST floors, the synthetic evaluation, the style stress test and pytest are re-run after every change.
- Results: `docs/RESULTS_PUBLIC_PLANS_2026-10-28.md`.
