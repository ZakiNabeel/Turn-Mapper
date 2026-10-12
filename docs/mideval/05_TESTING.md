# Testing: plan, logged results, failure cases

## 1. Test plan

| Level | What it checks | Where | How often |
|---|---|---|---|
| Unit / stage | each stage on small known inputs: grey-level estimation, masks, gap closing, scale maths, graph edge direction, OCR box rotation, stairs texture, door slabs | `tests/test_stages.py`, `tests/test_cblock_features.py` | every commit (CI) |
| Contract | schema copy in sync; valid fixtures pass; each invalid fixture fails with its named error code | `tests/test_contract.py` | every commit |
| Integration | full chain on synthetic plans gives a valid, routable map with metric lengths; validators catch planted errors; CLI works | `tests/test_pipeline.py` | every commit |
| Generality | same layout in 5 drawing conventions gives the exact room/door count and one connected graph | `tests/test_generality.py`; full 12-case matrix in `scripts/style_stress.py` | every commit / before releases |
| Edge and failure | blank page, random noise, unsupported file, missing model weights, runtime budget | `tests/test_edge_cases.py` | every commit |
| Requirements | QA report + manifest, determinism, provenance, no private data in git | `tests/test_requirements.py` | every commit |
| ML plumbing | CubiCasa SVG → mask (incl. transforms), 2 training iterations, pipeline with `--segmenter learned`, bootstrap masks | `tests/test_learned.py` (skips without torch) | every commit with `.[ml]` |
| Accuracy (ground truth) | Level B/C metrics on synthetic plans with exact truth | `eval/evaluate_synthetic.py` | before releases |
| Regression (real plans) | all 14 FAST floors: valid / counts / graph pieces / scale source vs previous run | `turn-mapper run … --split all` | after every algorithm change |
| Planned | FAST ground-truth geometry (needs site measurements + annotated floors); learned vs classical IoU; mapping-effort study (≥ 2 operators); app import of fixtures | `eval/`, app repo | M5, M8 |

## 2. Logged results (2026-10-12)

- **Unit and module tests:** 47 tests passed (38 earlier + 9 added today for edge cases and requirements). Line coverage is 87%.
  - Log: [`evidence/pytest_log_2026-10-12.txt`](evidence/pytest_log_2026-10-12.txt)
  - JUnit XML: [`evidence/pytest_junit.xml`](evidence/pytest_junit.xml)
- **Ground-truth evaluation:** 12 synthetic cases, from [`evidence/eval_synthetic_METRICS.md`](evidence/eval_synthetic_METRICS.md):

  | metric | mean over 12 cases |
  |---|---|
  | valid output | 12/12 |
  | free-space IoU | 0.983 |
  | corridor IoU | 0.976 |
  | room precision / recall | 1.000 / 1.000 |
  | door precision / recall | 0.988 / 1.000 |
  | label accuracy (OCR) | 0.702 |
  | mean \|scale error\| without measurements | 8.7% (worst: doubleline +28.6%) |
  | destination pairs routable | 1.000 |
  | route length / true shortest walk | 1.245 (median per case) |
  | route edges through a wall | 0 |

  The route ratio above 1 is expected. The true distance is the geometric shortest path hugging corners, while our routes follow corridor centre lines and enter rooms through door nodes.

- **Generality:** 11/12 cases fully correct ([`evidence/style_stress_RESULTS.md`](evidence/style_stress_RESULTS.md)).
- **Real plans:** 14/14 FAST floors produce valid output ([`evidence/fast_regression_summary.md`](evidence/fast_regression_summary.md)). There is no ground truth for FAST yet, so these are validity and count checks, not accuracy.

## 3. Failure cases (discussed in the demo)

### F1. A real bug caught by a test: divide-by-zero in tiled inference

- **Symptom:** `test_train_and_run_learned` failed with `ZeroDivisionError` in `predict_proba`.
- **Cause:** the tile overlap was fixed at 128 px. With a 128 px tile (used in the CPU test), the stride became 0.
- **Fix:** the overlap now defaults to a quarter of the tile and is capped at half (`learned/model.py`).
- **Lesson:** the bug would have crashed on any small-tile configuration. The test caught it before any GPU time was spent.

### F2. Regression caught by the FAST run: measuring door width everywhere

- **Change:** without a known scale, the door-gap size was switched to be *measured* from wall-end pairs on every plan, because that fixed line drawings.
- **What broke:** the FAST regression run (`runs/fast_regress_2`) showed:
  - A-F2: 2 doors and a scale of 0.30 m/px, against about 0.027 m/px before;
  - B-F1: scale 0.064 m/px.
- **Cause:** on dense real plans, wall-end pairs also catch furniture and corridor ends, which inflates the gap.
- **Fix:** measure only on paper-floor (line) drawings, and keep the wall-thickness ratio for filled plans (ADR-017). After the fix, FAST counts returned to the earlier reference and the synthetic styles stayed at 11/12.
- **Lesson:** every algorithm change is run on both the synthetic matrix and the real plans.

### F3. Historic bug: graph edges cutting through rooms (fixed in `2b99f5f`)

- **Symptom:** skeleton polylines were attached to nodes in the wrong direction, so some edges jumped across rooms.
- **Fix:** orient each polyline before anchoring it.
- **Guard:** the validator `EDGE_CROSSES_WALL` now makes this an *error* that blocks packaging (NFR-04), and `test_graph_edges_keep_their_geometry_regardless_of_direction` keeps the fix in place.

### F4. Open failure: C-F2 graph splits into 4 pieces

- **Situation:** C-F2's faculty-office suites are subdivided into cubicles (A–G), and their doors onto the hallway are not drawn as gaps.
- **Result:** the classical rule cannot find those doors, so the suites form separate graph pieces.
- **Handling:** the validator reports `GRAPH_DISCONNECTED` and the unreachable POIs, so the operator sees the problem. Nothing is silently wrong.
- **Planned fix:** the learned segmenter, fine-tuned on corrected C-block masks, plus the correction step (FR-19).

### F5. Open failures on synthetic plans

- One extra door on the *scanned* basic plan.
- 43–56% label accuracy on thin-line and double-line drawings, where OCR is confused by thin strokes touching text.
- Scale error of up to +28.6% on double-line plans when no measurement is given. That error disappears when two measured points are supplied (FR-07a).

### F6. Unusable input (graceful rejection)

| Input | Result |
|---|---|
| Blank page | floor fails with `WALKABLE_EMPTY`, nothing is packaged, exit code 1 |
| Random noise | same as blank page |
| `.txt` file | one-line error `no adapter can read …` (no traceback) |
| `--segmenter learned` without weights | one-line error saying where to put the weights |

All four are covered by tests in `tests/test_edge_cases.py`.

## 4. How to reproduce

```bash
pip install -e ".[dev]"            # + ".[ml]" for the ML tests; needs the tesseract binary
python3 -m pytest -v --cov=turn_mapper
python eval/evaluate_synthetic.py --out runs/eval_synth
python scripts/style_stress.py --out runs/style_stress
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split all --out runs/fast
```
