# Data and Annotation Guide — Pipeline 1

Status: draft v0.1. Owner: Zaki Nabeel.

## 1. Principle

**Public data to learn on, our own buildings to prove it on.** Keep them separate. The held-out test floor(s) are never used for training, tuning, threshold selection or prompt/heuristic design.

## 2. Datasets

Licences and exact contents must be verified from the official source before use and recorded in the table (`VERIFY` = not yet checked).

| Dataset | What it is | Use in TURN | Licence |
|---|---|---|---|
| CubiCasa5K | ~5,000 annotated floor plans (Finnish, residential) with SVG annotations for walls, rooms, doors, icons | Pretraining segmentation; mapped to TURN classes | VERIFY (believed non-commercial; matters for any Centaurus/commercial use) |
| R2V (Raster-to-Vector) | Several hundred residential plans with vector annotations | Optional extra pretraining / benchmark | VERIFY |
| CVC-FP | Small set of architectural plans with wall/door/room labels | Optional benchmark | VERIFY |
| MLSTRUCT-FP | Larger multi-unit plans with wall annotations | Optional wall pretraining | VERIFY |
| **TURN-Inst (ours)** | Institutional/commercial plans we collect and annotate | Fine-tuning (train/val) | Internal; permission from plan owners |
| **TURN-Test (ours)** | The FAST-NUCES floor(s) used for the demo + at least one other building | **Test only** | Internal |

Never commit datasets. Store under a path set by `TURN_DATA_DIR`.

## 3. Collecting TURN-Inst plans

Targets: 30–60 non-residential plans (more is better; even 20 well-annotated helps).

Sources, in order of preference:
1. FAST-NUCES estate/admin office: DWG/DXF or original PDFs of each block/floor (ask formally; get written permission).
2. Other universities / hospitals / malls: public evacuation plans, tender documents, published brochures (check usage rights).
3. Photos of evacuation signage (keep separately; perspective-corrected subset only).

For each plan record in `plans_index.csv`: id, building type, source, permission status, format, resolution, has_scale_bar, notes. Remove personal data (names on office doors) if the plan will be shared outside the team.

## 4. Class definitions (TURN v1)

| id | class | definition | notes |
|---|---|---|---|
| 0 | background | outside the building, title block, legend | |
| 1 | wall | any structural or partition wall, including columns | label wall thickness as drawn |
| 2 | room | enclosed space a visitor enters via a door (office, lab, shop, washroom) | |
| 3 | walkable | corridors, lobbies, atriums, open circulation | the class routing cares about most |
| 4 | door | door opening + swing arc region | must break the wall between room and walkable |
| 5 | stairs | stairwell footprint | |
| 6 | lift | lift shaft footprint | |
| 7 | escalator | escalator footprint | rare in universities, common in malls |
| 8 | other/obstacle | furniture blocks, fixed counters, voids, restricted areas | excluded from walkable |

CubiCasa → TURN mapping must be written as a table in code (`turn_mapper/data/cubicasa_mapping.py`) and documented here once implemented. Residential "living room / kitchen / bedroom" → room; "corridor/hall/entry" → walkable; "stairs" icon/room → stairs.

## 5. Annotation

- Tool: CVAT or Label Studio (polygon annotation), exported to COCO-style polygons; a converter rasterises polygons to masks at a fixed resolution.
- Additionally annotate per plan: room labels (text), two scale points with known distance if available.
- Rules: draw walls as polygons following drawn thickness; door polygons overlap the wall gap; walkable polygons stop at door openings.
- Quality: each plan annotated by one person, reviewed by another. Spot-check agreement on 5 plans (mean IoU between annotators) and report it.
- Time each annotation — the manual-effort numbers are useful for the effort study.

### Correcting a draft (fastest route to ground truth)

`python scripts/make_annotation_drafts.py PLANS_DIR SOURCES_TSV --studio studio_projects --set heldout` makes one
Studio project per plan (`annotate-<id>`) with the automatic map already run; for the FAST A block use
`--files fast_blocks.pdf:<page>,...`. The annotator fixes walls/doors (dashed doors first), corridors (walkable /
not walkable) and room names in the Map tab and saves; the saved `floor.json` is the reference. Record who
corrected it and the minutes taken. The drafts and plans are local (gitignored); only the scores are reported.
Corrected drafts are scored against the pipeline, never fed back into tuning for the same plans (ADR-009).

## 6. Splits

- Split **by building**, never by tile or by floor of the same building (floors of one building leak style).
- TURN-Inst: ~70/15/15 train/val/test by building.
- TURN-Test: the demo floor + ≥1 unseen building, frozen before any tuning. Checksum the files and record in `DECISIONS.md`.
- **FAST A/B/C block PDF:** split by block (ADR-009). Proposal: one block = development (you may look at it, tune heuristics, fine-tune on it); the remaining blocks = held-out test, including the floor used for the live demo. Never put floors of the same block on both sides. Decide and record this **before** running anything on those pages beyond `turn-mapper inspect`.

## 7. Ground truth for graph/route evaluation

For TURN-Test floors, create ground-truth Map Packages manually (in the Android app, then export, or in the annotation tool + converter). These contain walkable, walls, doors, graph and POIs. Record who made them and how long it took.
