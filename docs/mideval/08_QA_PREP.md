# Q&A preparation: mapping module (ownership)

The panel can point at any file and ask "explain this". Work through this list until you can answer every question **without notes and in your own words**. Practise by opening the named file and explaining it out loud while scrolling.

## 1. The pipeline in 60 seconds (memorise this)

1. Read the floor image from the PDF.
2. Find and remove text, keeping the room labels.
3. Decide for every pixel whether it is wall, floor or outside.
4. Close the gaps in walls. Each closed gap is a door, and the closed walls cut the floor into rooms and corridors.
5. Work out metres per pixel.
6. Draw a skeleton through the free space, simplify it into a graph, and connect every room through its door.
7. Put a destination on each room's door node, named by OCR.
8. Check everything: no edge through a wall, no dangling edge, and all destinations reachable.
9. Export JSON in metres for the app.

## 2. Walk-through questions per file

| File | Question you should be able to answer |
|---|---|
| `segment.py: ink_map` | Why compare each pixel with a *grey closing* of the image and not use a fixed threshold? (The closing estimates the local paper or fill colour, so coloured rooms, grey floors and uneven scan lighting all become "no ink". Only strokes darker than their surroundings remain.) |
| `segment.py` thick vs thin | How do you tell solid walls from line drawings? (Open the ink mask with a 3×3 kernel. If most ink survives, the walls are thick. Otherwise keep only long straight strokes, found with line-shaped kernels, and fuse double lines with an 11×11 closing.) |
| `segment.py` half-max trim | Why trim walls on paper-floor plans? (Blur spreads ink sideways. A pixel counts as wall only if it is at least half as dark as the typical wall, which keeps the thickness, and so the door size and the scale, correct. It is not applied on filled plans because it broke thin grey walls there: we measured that.) |
| `vectorize.py: close_wall_gaps` | Why is a closed gap a door? Why "orientation-aware"? (Doors are breaks in walls. Closing with horizontal, vertical and diagonal line kernels fills a gap only along the wall's direction, so room corners and narrow rooms are not filled in.) |
| `vectorize.py` gap size | How big a gap counts as a door? (With known scale: 1.2 m. Without scale: 8.5 × wall thickness on filled plans, or 1.35 × the measured opening width on line drawings, where wall thickness says nothing about door size.) |
| `vectorize.py: carve_door_slabs` | What is a door slab? (Some exports draw the door leaf as a light bar *over* the wall. The wall looks unbroken, so we carve the bar out as a known opening.) |
| `vectorize.py` circulation | How do you know a space is a corridor? (The largest space, plus spaces that connect to at least 3 *different* neighbours through doors and are reachable from it. ADR-016.) |
| `scale.py` | Where do metres come from? (Two measured points if we have them, using least squares. Otherwise another floor of the same footprint. Otherwise the median door width is assumed to be 0.9 m, and that map is flagged as an estimate.) |
| `graph.py` | How is the graph built and why is it safe? (Skeletonise the free space, cut short spurs, merge close nodes, simplify each polyline only while it stays inside free space, then link door nodes to the corridor without crossing walls. Validators re-check every edge in metres.) |
| `validate.py` | What does the validator check, and why on the JSON? (Schema plus geometry rules: edges inside walkable space, not through walls, lengths match, POIs reachable, and so on. It runs on the exported JSON, so it also checks hand-edited maps and the app's maps.) |
| `export.py` | What is in `venue.json`? (Venue, buildings and floors. Each floor has `transform.px_to_m`, walls, rooms, doors, the walkable area, the graph, POIs and validation, all in metres, with provenance on each element.) |
| `learned/cubicasa.py` | How do you turn CubiCasa SVGs into training masks? (Parse labelled polygons, apply SVG transforms, pick the image the coordinates belong to, and paint in priority order: spaces, then railings, then walls, then doors.) |
| `learned/data.py: restyle` | Why redraw training images from masks? (So the network learns shape rather than CubiCasa's colours. This bridges to FAST-style and other plans.) |
| `learned/segmenter.py` | How is the network used at inference? (Estimate wall thickness, rescale the plan so walls look as they did in training, predict overlapping tiles, blend them, then pass the masks to the same vectorize → graph → validate chain.) |

## 3. Likely panel questions

**"Isn't this just thresholding? Where is the complexity?"**

Thresholding gets pixels. The hard part is topology: a connected, metric graph that never crosses a wall, from drawings that follow no single convention.

- Door gaps have to be closed without merging rooms.
- Scale has to come from somewhere.
- Every map is validated.

We showed that a change which fixed one convention broke real plans (testing doc, failure F2). That trade-off is why this is a complex problem.

**"Why not use deep learning from the start?"**

There were no labelled institutional plans. The classical pipeline gives a working baseline, a comparison point, and *starting labels* for annotation. The learned model plugs into the same interface, so we can compare them on the same downstream metrics.

**"How do you know it works?"**

Three kinds of evidence:

- Exact ground truth on synthetic plans in 6 drawing conventions: room and door recall 1.0, 0 wall crossings.
- 14/14 FAST floors produce valid output.
- Failures are reported: C-F2, labels on thin-line plans.

FAST accuracy against ground truth comes after site measurements and annotation. We don't claim it yet.

**"Is anything hardcoded for FAST?"**

No. `grep` for FAST or floor ids in `src/` finds nothing. The venue YAML only says which PDF page holds which floor. Colours and thresholds are estimated per image.

**"What happens with a plan your system can't handle?"**

The validators reject it or flag it, the QA report shows why, and the operator corrects it. We never ship an unvalidated map. Show C-F2 and the blank page.

**"How accurate is the scale?"**

On synthetic plans, without measurements, the mean error is 8.7% and the worst is 28.6% (double-line). Every map records its scale source, and two measured points replace the estimate.

**"Which parts did AI write? Explain this code."**

Be honest: Claude helped write and debug much of the code and docs. This is disclosed in the report and in every commit trailer. Then explain the code using sections 1 and 2 above. The design decisions and every number are ours to defend: `DECISIONS.md` and `eval/`.

**"Why JSON / why a contract?"**

The app team and the mapping module develop independently. The contract has a schema, fixtures and named error codes, and it is versioned, so a change can't silently break the app.

**"What's left?"**

GPU training, then annotating 5–8 floors, then fine-tuning and comparing with classical on A block. After that: site measurements, multi-floor links, the correction step, and app import. Dates are in the milestone log.

## 4. Practise

Ask Claude (or a teammate) to quiz you: "pick a random function in `src/turn_mapper/` and ask me what it does and why".
