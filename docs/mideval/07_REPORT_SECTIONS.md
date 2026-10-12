# Report material: mapping module (for the Form 3 template)

These are mapping-module inputs for the report sections. Paste them into the official template and adapt them. **Write the literature review prose yourselves.** Below you get the sources, the gap and the challenge as bullet points, because the rubric penalises generic AI-style text and each member must be able to explain every paragraph.

---

## A. Scope table (mapping module)

| Module / component | In scope (FYP) | Measurable success criterion | How measured | Feasibility / status |
|---|---|---|---|---|
| Plan ingestion | PDF (embedded or rendered raster), PNG/JPG; multi-floor venue config | 14/14 FAST floors ingested | `turn-mapper run … --split all` | ✅ done |
| Segmentation (classical) | walls / floor / outside across drawing conventions | ≥ 10/12 synthetic style cases fully correct | `scripts/style_stress.py` | ✅ 11/12 |
| Segmentation (learned) | U-Net pre-trained on CubiCasa5K, fine-tuned on 5–8 own floors | fine-tuned mIoU > classical mIoU on held-out annotated floors | `turn-mapper ml eval` | 🟡 code done, training pending (≈ 4 GPU-h) |
| Doors, rooms, circulation | gap-closing door detection; rooms vs corridors | door recall ≥ 0.9, room F1 ≥ 0.9 (synthetic now; annotated FAST later) | `eval/evaluate_synthetic.py` | ✅ synthetic 1.0 / 1.0 |
| Metric scale | two-point measurement; footprint transfer; flagged door prior | ≤ 5% error with measurements; estimates always flagged | eval script + site measurements | 🟡 measurement visit pending |
| Navigation graph + POIs | wall-safe graph, door nodes, OCR labels → POIs | 0 wall-crossing edges; ≥ 95% destinations routable on valid floors | validators + eval | ✅ synthetic |
| Validation + QA | schema + geometry validators gate export; QA report | 100% of exported floors pass validators | `turn-mapper validate` | ✅ |
| Output contract | `venue.json` (schema 0.1.1), optional `.turnmap` | fixtures validate in Python and in the app importer | contract tests; app (M3) | 🟡 app importer pending |
| Multi-floor linking | stairs/lift transitions linked across floors of one building | route between 2 C floors | planned test | ⏳ M9 |
| Correction step | operator fixes rooms/doors/labels; provenance = corrected | effort reduction vs manual mapping (target ≥ 60%, provisional) | effort study (≥ 2 operators) | ⏳ |
| **Out of scope** | vector/DXF input (FAST PDF is raster), iOS, fully automatic mapping, buildings beyond the pilot venue | — | — | deferred |

---

## B. Literature: source pack, gap and complex computing challenge

### Sources to read and cite

Check each reference before citing it: venue, year and page numbers.

1. **Macé, Locteau, Valveny, Tabbone (2010).** *A system to detect rooms in architectural floor plan images*. DAS 2010. Classical room detection with walls plus doors and windows. This is our closest classical ancestor.
2. **Ahmed, Liwicki, Weber, Dengel (2011).** *Improved automatic analysis of architectural floor plans*. ICDAR 2011. Wall and text separation, room labelling.
3. **de las Heras, Terrades, Robles, Sánchez (2015).** *CVC-FP and SGT: a new database for structural floor plan analysis*. IJDAR. A benchmark of real plans with a structural ground truth.
4. **Dodge, Xu, Stenger (2017).** *Parsing floor plan images*. MVA 2017. FCN wall segmentation and scale from OCR'd room sizes. Relevant to our scale problem.
5. **Liu, Wu, Kohli, Furukawa (2017).** *Raster-to-Vector: Revisiting floor plan transformation*. ICCV 2017. Junction detection plus integer programming to produce vector plans.
6. **Kalervo, Ylioinas, Häikiö, Karhu, Kannala (2019).** *CubiCasa5K: a dataset and an improved multi-task model for floorplan image analysis*. SCIA 2019. Our pre-training data.
7. **Zeng, Li, Yu, Fu (2019).** *Deep floor plan recognition using a multi-task network with room-boundary-guided attention*. ICCV 2019.
8. **Lv et al. (2021).** *Residential floor plan recognition and reconstruction*. CVPR 2021.
9. **Ronneberger, Fischer, Brox (2015).** *U-Net*. MICCAI 2015. The architecture we use.
10. **Indoor network models:** the OGC **IndoorGML** standard (navigation graphs from indoor spaces), and medial-axis or skeleton-based network extraction in indoor GIS. Find 1–2 papers here, for example on automatic indoor network generation from floor plans.
11. **Commercial systems:** Pointr, Mappedin and others. Use vendor claims only, labelled as such. They support "CAD-first, enterprise onboarding".

### What the literature does, and what it does not

- Most floor-plan recognition work stops at **pixels or vectors**: walls, rooms, icons. It is evaluated with segmentation IoU, mainly on **residential** plans (CubiCasa, R2V).
- Few systems produce a **navigable, metric, validated graph**. Doing so needs correct door connectivity, scale in metres, and a graph that never crosses walls.
- **Scale** is usually assumed or taken from dimension text. Institutional plans often have neither.
- Commercial indoor mapping relies on **CAD files and enterprise onboarding**.

### Research gap (state it in your own words)

There is no low-cost, self-service way to turn an **ordinary raster floor plan of an institutional building**, of the kind a university or hospital actually has, into a **metric navigation graph that is checked for routing safety and corrected by a human**, with measured evaluation of both accuracy and mapping effort.

### Complex computing challenge (map it to the template's criteria)

- **No single correct method:** drawing conventions conflict. Filled, line and double-line walls, and doors drawn as gaps, arcs or slabs, each break a different rule. Our evidence: one rule fixed line drawings but broke real plans (`05_TESTING.md` F2).
- **Conflicting requirements:** closing more wall gaps finds more doors but merges rooms. Fewer graph nodes are more readable but may cut corners. Estimated scale makes maps usable now but risks wrong distances.
- **No ground truth or labelled data for the target domain:** this needed synthetic ground truth, a held-out building, bootstrap annotation and transfer learning from residential data.
- **Depth across fields:** image processing, OCR, computational geometry, graph algorithms, deep learning and a versioned data contract with a mobile app.
- **Must fail safely:** wrong maps can send people through walls. Validators must gate output.

---

## C. Architecture: see `04_DESIGN.md` §1

Take the layers, components, dependencies, interface contracts and the design-choice table from `04_DESIGN.md` §1. The data and process diagrams are in §2–§7, each with explanatory text, and the changes since the proposal are in §8.

---

## D. Implementation documentation

### Setup (reproducible on Windows, macOS or Linux)

1. Install **Python 3.11+** and **Tesseract OCR**:
   - Windows: the UB-Mannheim installer, then add it to PATH.
   - macOS: `brew install tesseract`.
   - Ubuntu: `sudo apt install tesseract-ocr`.

   Check with `tesseract --version`.
2. Clone and install:

   ```bash
   git clone https://github.com/ZakiNabeel/Turn-Mapper.git && cd Turn-Mapper
   python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"                                  # add ".[ml]" for the learned segmenter
   ```
3. Verify: `python -m pytest -q`. Expected: all tests pass, with ML tests skipped if `.[ml]` is not installed.
4. Run on any plan with `turn-mapper run my_plan.png --out runs/try`. This writes `runs/try/venue.json` and `runs/try/qa/index.html`.
5. For a multi-floor venue, copy `configs/venues/fast_isb.yaml`, set the page and image index per floor, then run `turn-mapper run plan.pdf --venue my_venue.yaml`.
6. Learned segmenter: follow `docs/ML_GUIDE.md`, or open `notebooks/train_segmenter_colab.ipynb`.

### Key files, classes and algorithms

| File | Key classes / functions | Algorithm |
|---|---|---|
| `api.py` | `convert`, `process_floor`, `validate_package` | orchestration, scale_like ordering, packaging gate |
| `ingest.py` | `ADAPTERS`, `PdfEmbeddedImageAdapter`, `ImageAdapter` | adapter registry chosen by score; PDF images at native resolution |
| `preprocess.py` | `run_ocr`, `erase_text` | Tesseract at 0/90/270°; inpaint text with the surrounding fill colour |
| `segment.py` | `ClassicalSegmenter`, `ink_map`, `straight_strokes`, `detect_stairs` | ink = darkness relative to local paper (grey closing); line-kernel openings for wall strokes; 11×11 closing fuses double lines; half-maximum trim for blur; texture density for stairs |
| `vectorize.py` | `close_wall_gaps`, `carve_door_slabs`, `estimate_door_width_px`, `vectorize` | orientation-aware morphological closing (closed gap = door); mutual wall-end pairs to measure openings; sliver filter by distance transform; circulation = spaces with ≥ 3 distinct neighbours |
| `scale.py` | `scale_from_evidence`, `estimate_scale` | least squares over measured point pairs; median door width / 0.9 m prior |
| `graph.py` | `build_graph` | skeletonise free space → polylines → spur pruning → greedy simplification checked for containment → door links that avoid walls → bridging components with `route_through_array` |
| `pois.py` | `label_rooms`, `make_pois` | OCR boxes inside room polygons, label patterns per building, needs_review below a confidence threshold |
| `validate.py` | `validate_floor`, `route_lengths` | JSON Schema plus Shapely geometry rules; A* route sampling |
| `export.py` | `floor_to_dict`, `write_json_package`, `write_package` | px → metres affine; venue.json / .turnmap writer |
| `learned/*` | `cubicasa.prepare`, `MaskDataset`, `train`, `LearnedSegmenter` | SVG → mask rasterisation; U-Net + CE + Dice; tiled inference with Hann blending; rescaling to the training wall thickness |

### Trade-offs (be ready to defend each)

- **Classical first:** works now and explainable, but it is a set of hand rules, so new conventions can break it. The learned model is the answer to that.
- **Door-width prior for scale:** routable maps without a site visit, at about ±10–30% error. It is flagged, and replaced by measurements.
- **Skeleton graph:** few nodes and follows corridor centres. Routes are about 1.25× the geometric shortest path, which is acceptable for wayfinding.
- **Validators as a hard gate:** some imperfect floors are rejected rather than shipped (`--force` exists and is recorded).
- **JSON default:** larger than a zip, but it can be inspected and diffed.

---

## E. Test plan and early results: see `05_TESTING.md`

---

## F. Risk and privacy analysis (mapping module)

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Permission to use the FAST plan PDF (authored by a student) | medium / high | PDF is kept out of git (`samples/private/`, `.gitignore`, `test_no_private_data_in_git`); only counts are published; formal permission requested |
| Floor plans are security-sensitive (building layout) | low / high | maps stay in the team's private repos and devices; no public hosting of plan images |
| Dataset licence: CubiCasa5K is CC BY-NC 4.0 | — / medium | non-commercial academic use only; dataset and derived weights never committed; attribution in the report |
| Wrong scale gives wrong distances and confuses PDR | medium / medium | `scale_source` on every map; estimates flagged; site measurements planned |
| Missing door gives an unreachable destination | medium / medium | `GRAPH_DISCONNECTED` / `POI_NOT_IN_MAIN_COMPONENT` warnings; QA report; correction step |
| Route through a wall gives an unsafe instruction | low / high | `EDGE_CROSSES_WALL` and `EDGE_OUTSIDE_WALKABLE` are blocking errors |
| Over-claiming results | medium / high | rule: only numbers produced by scripts; held-out building A; failures reported |
| GPU or compute availability for training | medium / medium | free Colab or Kaggle; checkpoints to Drive; the classical pipeline remains the fallback |
| Personal data | low | the mapping module processes no personal data. Positioning data is handled in the app module, see its own analysis. |

---

## G. Disclosure of external tools and GenAI

**Libraries and tools:**

- Python, NumPy, OpenCV (Apache-2.0), scikit-image (BSD), SciPy (BSD), Shapely (BSD), NetworkX (BSD), PyMuPDF (AGPL-3.0, academic use), Tesseract OCR via pytesseract (Apache-2.0), jsonschema, Click, PyYAML;
- PyTorch (BSD) and segmentation_models_pytorch (MIT) for the learned segmenter;
- pytest, pytest-cov, ruff and GitHub Actions for testing and CI;
- Mermaid CLI for the diagrams.

**Datasets:** CubiCasa5K (Kalervo et al., 2019; CC BY-NC 4.0). FAST-NUCES floor-plan PDF, used privately and pending permission.

**Generative AI:**

- **Claude (Anthropic)**, used through claude.ai, assisted with:
  - writing and refactoring code;
  - debugging;
  - writing tests;
  - drafting documentation, diagrams and this report material.
- Commits made with AI assistance carry a `Co-Authored-By: Claude` trailer in the git history.
- All design decisions are recorded in `docs/DECISIONS.md`.
- All reported numbers come from scripts run on recorded data.
- The module owner reviewed, ran and is responsible for all code and text.
- *[Each member adds any other AI tools they used, e.g. for slides or for writing.]*
