# Evaluation Protocol — Pipeline 1

Status: draft v0.1. Freeze this (with a dated entry in `DECISIONS.md`) before running final experiments.

Three levels: pixels → geometry/topology → usefulness (routes + effort). The report needs all three; the effort and route results are the headline because they match the FYP's contribution.

## 1. Level A — Segmentation (pixels)

On TURN-Inst test buildings and TURN-Test floors:

- per-class IoU, mean IoU, per-class F1;
- boundary F1 for walls (tolerance 2–3 px at fixed resolution);
- report separately: CubiCasa-only model, fine-tuned model, classical baseline.

## 2. Level B — Geometry and topology

Compare predicted package vs ground-truth package (both in metres):

| Metric | Definition |
|---|---|
| Walkable IoU | area IoU of walkable MultiPolygons |
| Wall precision/recall | wall segments matched within 0.3 m and 10° |
| Door recall | GT doors with a predicted door within 0.75 m |
| Room detection F1 | room polygons matched at IoU ≥ 0.5 |
| Label accuracy | matched rooms whose OCR label equals GT label |
| Scale error | % error on held-out measured distances |
| Graph topology | junction precision/recall (within 1.5 m); connected components count vs GT |

## 3. Level C — Usefulness

### C1. Route validity
For N (≥ 30) random POI pairs present in both GT and prediction:
- route found (yes/no);
- route crosses a wall (must be 0 after validators);
- route length ratio = predicted / GT shortest length (report median, P90);
- POI reachability = fraction of GT POIs reachable in the predicted graph.

### C2. Mapping effort (headline)
Compare, for the same floor, by the same operator(s):

1. **Manual**: start from image, do full setup in the app (scale, layout, paths, destinations) until the floor passes validators and the route checklist.
2. **AI-assisted**: run turn-mapper, import, then correct in the app until it passes the same checks.

Measure: wall-clock time (excluding pipeline compute, reported separately), number of editor operations (if logged), and final quality (Level B/C1 metrics against GT). Effort reduction = 1 − assisted/manual.

Controls: counterbalance order (operator A does manual first on floor X, assisted first on floor Y) to reduce learning effects; at least 2 operators and 2 floors if possible; record everything, including failed attempts. The ≥60% reduction is a **provisional target**, not a claim.

## 4. Reporting rules

- Every number comes from a script in `eval/` with a run manifest.
- Report failures and the floors where the pipeline was poor.
- No tuning on TURN-Test. If a threshold was chosen, say on which data.
- Tables include: method, data split, n, metric, and the command that produced it.
