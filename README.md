# TURN-Mapper

Floor plan → navigation graph module of **TURN** (FAST-NUCES Islamabad FYP, infrastructure-minimised indoor navigation).

Give it a floor plan (PDF, image, later DXF; one or many buildings/floors). It produces a JSON map (`venue.json`, or a zipped `.turnmap`) with metric walkable geometry, walls, doors, rooms, destinations and a routeable graph. The TURN Android app imports that package and adds positioning (PDR, particle filter, Wi-Fi) on top.

AI-assisted, human-verified: every automatic result is checked by validators and a QA report, and corrected by an operator where needed.

- Module boundary and integration: [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md)
- Output format: [`docs/MAP_PACKAGE_SCHEMA.md`](docs/MAP_PACKAGE_SCHEMA.md)
- Pipeline design: [`docs/PIPELINE1_SPEC.md`](docs/PIPELINE1_SPEC.md)
- **Mid-evaluation evidence index:** [`docs/mideval/00_INDEX.md`](docs/mideval/00_INDEX.md)
- Status and plan: [`docs/ROADMAP_AND_WORKFLOW.md`](docs/ROADMAP_AND_WORKFLOW.md), [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md)

Status: **v0.3.0**. Classical pipeline: 14/14 FAST floors give valid output, 11/12 synthetic drawing styles fully correct ([`docs/RESULTS_GENERALITY_2026-10-11.md`](docs/RESULTS_GENERALITY_2026-10-11.md)). Learned segmenter (U-Net, CubiCasa5K → fine-tune) scaffolded and tested offline, training pending: [`docs/ML_GUIDE.md`](docs/ML_GUIDE.md).

```bash
pip install -e ".[dev]"        # also needs the tesseract binary, version 5.x (4.x changes results on line drawings, see docs/mideval/05_TESTING.md F9)
turn-mapper run plan.png --out runs/try1      # -> runs/try1/venue.json (+ images/) + runs/try1/qa/index.html
pip install -e ".[ml]"                         # optional: learned segmenter (see docs/ML_GUIDE.md)
python eval/evaluate_synthetic.py --out runs/eval   # accuracy vs exact ground truth (6 drawing styles)
# GPU training: notebooks/train_segmenter_kaggle.ipynb (or _colab)
```

Team: Zaki Nabeel (map intelligence / CV, module owner), Shehryar Faisal (platform / app integration), M Sameer (positioning).
