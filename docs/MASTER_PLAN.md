# TURN-Mapper master plan (from 2026-10-16)

Goal: on any laptop, open **TURN Studio**, drop in a floor plan (scanned/raster PDF, vector PDF, image, DXF/CAD,
SVG), get an automatic map, **fix it by hand**, and export a validated `venue.json` (and other formats) that the
Android app imports. Behind it, a learned segmenter fine-tuned for institutional plans that beats the classical
one on held-out floors.

Status words: **done**, **now** (this sprint), **next**, **later**. Every number below comes from a run already
recorded in `docs/RESULTS_*.md`; nothing here is a promise of a result.

---

## 0. Where we are (2026-10-16)

| Area | State |
|---|---|
| Classical pipeline | **done** (v0.3.0): 14/14 FAST floors valid, 11/12 drawing-style cases fully correct, 48 tests |
| Learned segmenter | pre-trained on CubiCasa5K (Kaggle, run 2): test **mIoU 0.650** (wall 0.745, door 0.635). In the pipeline it matches classical on 4/12 synthetic cases and fails on thin/double-line drawings. Classical stays default |
| Inputs | raster PDF, PNG/JPG; **since 10-16:** DXF (measured `cad_units` scale), SVG, vector-aware PDF |
| Output | `venue.json` / `.turnmap` (schema 0.1.1), QA HTML |
| Editing | **since 10-16:** TURN Studio (`turn-mapper studio`), input and output corrections |
| Scale | two-point evidence in YAML, footprint transfer, door-width prior (flagged); site measurements pending |
| Open defects | D-07 stairs false positive on door arcs, D-08 void marked walkable (A-F1), D-09 low ingest/cli coverage, D-10 C-F2 suites disconnected |

## 1. Decisions taken in this plan

1. **GUI = local web app**, `turn-mapper studio` → opens `http://127.0.0.1:8765` in the browser. Python backend
   (FastAPI) wraps the existing `turn_mapper` pipeline; the frontend is one static page (plain JS + SVG, no build
   step, no internet needed). Same code on Windows, macOS, Linux. Rejected: Streamlit (weak for drawing/editing),
   Electron/Qt (heavy install, second codebase).
2. **Two edit levels**, as requested:
   - *input level* — crop, rotate, erase marks/legends (brush), paint/erase **wall** and **walkable** masks, then
     re-run the downstream stages from the edited masks (a `MaskSegmenter` replaces the segmenter);
   - *output level* — move/add/delete graph nodes and edges, add/delete doors, rename/re-categorise rooms and
     POIs, mark rooms as not walkable (voids, D-08), set the scale with a two-point measurement.
   Every edited element gets `provenance: "corrected"` or `"manual"`; validators re-run on every save and gate export.
3. **Corrections become training data.** Each saved project writes the corrected masks as an annotation
   (`image.png` + `mask.png`, our class ids). The Studio is therefore also the annotation tool for fine-tuning.
4. **CAD/vector inputs carry real units**, so DXF and vector PDFs give a *measured* scale with no site visit.
5. **WAFFLE is not a training set for us.** It has ~18.5K Wikimedia floor plans but **no pixel masks**; only a
   separate 110-image benchmark has wall/door/window/interior labels, and the paper states no licence. We use
   WAFFLE as an **out-of-domain test set** (and, later, for unlabeled pseudo-label experiments). Supervised
   fine-tuning uses ResPlan (CC BY 4.0) rendered in many styles + our own annotated institutional floors.
6. **Model stays U-Net / ResNet-34** (98 MB, runs on a laptop CPU in seconds). One stronger encoder is tried
   only as an ablation if time allows.

## 2. Workstreams

### W1 — TURN Studio (GUI) · **1.1–1.10 done 10-16** (1.11 multi-floor linking next)

| # | Feature | Detail | Done when |
|---|---|---|---|
| 1.1 | Launcher | `turn-mapper studio [--port] [--no-browser]`; `pip install -e ".[studio]"` | opens on Windows laptop |
| 1.2 | Projects | `studio_projects/<name>/` holds input, page/image choice, params, masks, edited floor JSON, history | reopen after restart |
| 1.3 | Upload + inspect | drag-drop file; list pages/embedded images with thumbnails; pick floor; building/level/name fields | FAST PDF pages selectable |
| 1.4 | Run | segmenter classical/learned (if weights present), progress, timings, warnings list | same output as CLI |
| 1.5 | Layers view | plan image + toggles: walls, walkable, rooms, doors, graph, POIs, warnings; zoom/pan | |
| 1.6 | Input edits | crop, rotate 90°, erase brush, wall/walkable paint & erase, "re-run from masks" | void fixed on A-F1 by painting |
| 1.7 | Output edits | node add/move/delete, edge add/delete, door add/delete, room rename/category/non-walkable, POI rename | edits survive re-validation |
| 1.8 | Scale tool | click two points, type metres; repeat for more pairs; residuals shown | scale_source = `measured` |
| 1.9 | Validate | schema + geometry validators + route sampling after every save; errors block export | |
| 1.10 | Export | `venue.json`, `.turnmap`, **GeoJSON** (for GIS/debug), **SVG** (for printing/report), annotation PNG pair | app fixtures still validate |
| 1.11 | Multi-floor | several floors per project/venue, one export; **floor links** (auto + manual) in the Check tab | **done 10-16**: 10 FAST floors in one `venue.json` with 12 auto links (unverified vs truth) |

### W2 — Input formats · **2.1–2.4 done 10-16**

| # | Format | Approach | Status |
|---|---|---|---|
| 2.1 | Raster PDF, PNG/JPG, scans | existing adapters | done |
| 2.2 | **Vector PDF** | detect vector content (`page.get_drawings()`); render at chosen DPI; if the PDF declares a scale/units, convert to measured scale; keep the line widths as a wall hint | now |
| 2.3 | **DXF** (AutoCAD exchange) | `ezdxf`: read units (`$INSUNITS`), list layers; rasterise selected layers (default: all except text/dimension/hatch); scale = known units → **measured**; layer names like `WALL`, `DOOR` give wall/door hints | now |
| 2.4 | **SVG** | render with PyMuPDF; units from viewBox if given | now |
| 2.5 | DWG | convert to DXF with ODA File Converter or libredwg if installed (auto-detected), else a clear message | **done 10-16** (tested with a stand-in converter; try a real DWG) |
| 2.7 | **Any input -> editable CAD** | Studio exports the extracted plan as DXF (`floor_dxf`), edited in any CAD tool, re-loaded as a measured DXF | **done 10-17**; round trip exact on synthetic, C-F3, C-F4; lossy on C-F5 |
| 2.6 | Photos of printed plans | perspective correction (4 clicks in Studio) | later |

### W3 — Data and fine-tuning · **S2 done 10-17** (docs/RESULTS_ML_S2_2026-10-17.md): ResPlan test mIoU 0.43 → 0.78, CubiCasa 0.650 → 0.634; synthetic ≥ classical on 8/12 → classical stays default; S3 next

**Datasets**

| Dataset | What it gives us | Licence | Use |
|---|---|---|---|
| CubiCasa5K | 5K residential raster plans + polygons | CC BY-NC 4.0 | pre-training (**done**) |
| **ResPlan** | 17K residential plans as metric vector geometry (walls, doors, windows, rooms), no images | CC BY 4.0 | render ourselves in 8 drawing styles → exact masks; stage-2 training |
| Synthetic institutional (ours) | corridors, lecture halls, labs, stair cores, voids, double-loaded corridors | ours | stage-2 training, exact ground truth |
| **FAST B and C blocks** (ours) | real institutional plans corrected in Studio | private, never in git | stage-3 fine-tuning (A block never used) |
| WAFFLE | ~18.5K Wikimedia plans of public buildings; no masks; 110-image segmentation benchmark | not stated; Wikimedia per-image licences | out-of-domain test; later pseudo-labels |
| FloorPlanCAD | CAD drawings with symbol labels | CC BY-NC 4.0 | later: door/stair symbols in DXF |

**Training stages** (Kaggle T4; weights never in git, sha256 in a manifest)

| Stage | Init | Data | Settings | Expected cost |
|---|---|---|---|---|
| S1 | ImageNet | CubiCasa5K | done, 25 epochs | done |
| S2 (done 10-17) | S1 | 17K ResPlan + 3K institutional + 1.5K CubiCasa | 20 epochs fp32, best epoch 16 | 10.7 h on T4 (the next runs use `--amp --max-minutes`) |
| S2 | S1 | ResPlan renders (8 styles incl. thin-line, double-line, scanned) + synthetic institutional | crop 512, lr 2e-4, 20 epochs | ~4 h on one T4 |
| S3 | S2 | FAST B/C corrected floors (target 20–40 floors × tiles) + 30% replay of S2 | lr 5e-5, 15 epochs, frozen encoder for 3 epochs | < 1 h |
| Ablation | S2 | same as S3 | stronger encoder (e.g. EfficientNet-B4 U-Net) | ~2 h |

**Evaluation** (fixed before training, ADR-009): CubiCasa test mIoU; the 12 synthetic style cases (room/door
recall, wall crossings, routable %); FAST **A block held out** (needs measured ground truth from Studio);
WAFFLE benchmark wall/door IoU if obtainable. **Promotion rule:** learned becomes the default only if on the A
block it has 0 wall-crossing edges and routable % ≥ classical, and on synthetic it is ≥ classical on 10/12 cases.

### W4 — Remaining mapping requirements · **next**

| # | Item | Plan |
|---|---|---|
| 4.1 | FR-18 multi-floor linking | **done 10-16** (`link.py`): stair/lift nodes on adjacent levels paired by type + position; manual link tool in Studio; 5 tests. On FAST: 12 links; C-B1/C-GF footprints differ 39%, so unmatched and flagged |
| 4.2 | FR-19 correction step | = W1 |
| 4.3 | D-07 stairs FP on door arcs | **partly done 10-16**: blobs under 1 m2 (arcs, symbols) are dropped, tested on a synthetic arc; FAST results unchanged (12 links, same transitions). A stricter fat-blob test was tried and rejected: it removed a real staircase on C-F2. The learned-model arc case itself is not reproduced (no weights here) |
| 4.4 | D-08 voids | Studio "not walkable" tool now; learned class `other` later |
| 4.5 | D-09 coverage | **mostly done 10-16**: adapters, DWG, CLI run/validate/inspect/make-institutional, Studio links; 83 tests pass |
| 4.6 | D-10 C-F2 disconnected | not auto-fixed: latest run still has 2-4 graph parts on B-F1, C-GF, C-F2, C-F5. Fix by hand in Studio (door/edge tools); re-check after S3 |
| 4.7 | Site measurements | 2–3 tape measurements per floor entered with the scale tool (team visit) |
| 4.8 | Mapping-effort study | time to a valid map with Studio vs manual tracing, ≥ 2 operators |

### W5 — Integration with the app (with Shehryar) · **next**

GeoJSON/`venue.json` fixtures from Studio exports; confirm the y-down → y-up conversion in his importer (M3);
one end-to-end C-floor demo: Studio export → app import → route on phone.

## 3. Order of work

| Week (from) | Work |
|---|---|
| 1 (Oct 16) | W1.1–1.5, 1.9–1.10 (Studio runs and exports); W2.2–2.4 adapters; ResPlan renderer; this plan |
| 2 (Oct 23) | W1.6–1.8 editing + scale; annotation export; site measurements; S2 training run on Kaggle |
| 3 (Oct 30) | Correct 8–10 B/C floors in Studio; S3 fine-tune; first A-block comparison |
| 4 (Nov 6) | W1.11 multi-floor + FR-18; D-07/D-10; app import demo (M3) |
| 5–6 | more annotated floors (to 20–40), ablation, effort study, results document, v0.4.0 |

## 4. Who does what

- **Code, renderers, notebooks, tests, docs:** Claude with Zaki reviewing.
- **Kaggle runs:** Zaki opens the prepared notebook and presses *Run all* (no account tokens handled by Claude).
- **Annotation/correction of FAST floors:** Zaki (and teammates) in Studio, ~20–30 min per floor after bootstrap.
- **Site measurements:** team visit with a tape measure (2–3 distances per floor).
