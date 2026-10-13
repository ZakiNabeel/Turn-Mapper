# Mid-evaluation evidence index: mapping module (TURN-Mapper)

Owner: **Zaki Nabeel**. Release: tag **`v0.3.0`** (contract schema 0.1.1). Date: 2026-10-12.

Open this page in the meeting. Every rubric item links to evidence you can open live.

## Form 2: Presentation & Demo

| Rubric item | Evidence |
|---|---|
| Proposal actions (10) | [01_PANEL_ACTION_REGISTER.md](01_PANEL_ACTION_REGISTER.md). **Before the meeting:** complete the rows from the official feedback sheet. |
| Iteration plan (10) | [02_MILESTONE_LOG.md](02_MILESTONE_LOG.md) (owners, plan vs actual, delays with recovery dates) · [TASK_LOG.md](TASK_LOG.md) |
| Live demo (25) | [06_DEMO_SCRIPT.md](06_DEMO_SCRIPT.md) (11 live steps incl. 3 failure cases) · inputs: `python scripts/demo_prepare.py` |
| Requirements (10) | [03_REQUIREMENTS.md](03_REQUIREMENTS.md) (FR-01…19, NFR-01…10, each with an acceptance test + status) |
| Design artefacts (15) | [04_DESIGN.md](04_DESIGN.md): architecture, DFD, sequence, activity, state, data model, ML flow, each explained; changes since the proposal in §8 · sources in [diagrams/](diagrams/) |
| Repository (10) | tags `v0.1.0`, `v0.2.0`, `v0.3.0` (**run `bash scripts/create_release_tags.sh` once on your laptop to publish them**) · [TASK_LOG.md](TASK_LOG.md) · [`.github/CODEOWNERS`](../../.github/CODEOWNERS) · CI in `.github/workflows/ci.yml` · `docs/SESSION_LOG.md` |
| Testing (10) | [05_TESTING.md](05_TESTING.md) (plan, logged results, 9 failure cases) · [evidence/pytest_log_2026-10-12.txt](evidence/pytest_log_2026-10-12.txt) · [evidence/pytest_junit.xml](evidence/pytest_junit.xml) |
| Q&A and ownership (10) | [08_QA_PREP.md](08_QA_PREP.md) |

## Form 3: Report (mapping-module inputs)

| Rubric item | Evidence |
|---|---|
| R&D and gap (15) | [07_REPORT_SECTIONS.md §B](07_REPORT_SECTIONS.md): sources, gap, complex-computing challenge. **Write the prose yourselves.** |
| Scope (10) | [07_REPORT_SECTIONS.md §A](07_REPORT_SECTIONS.md) |
| Requirements (15) | [03_REQUIREMENTS.md](03_REQUIREMENTS.md) |
| Architecture (15) | [04_DESIGN.md §1](04_DESIGN.md) |
| Data/process design (10) | [04_DESIGN.md §2–7](04_DESIGN.md) |
| Implementation docs (15) | [07_REPORT_SECTIONS.md §D](07_REPORT_SECTIONS.md) · [../ML_GUIDE.md](../ML_GUIDE.md) · [../../README.md](../../README.md) |
| Testing and disclosure (15) | [05_TESTING.md](05_TESTING.md) · [07_REPORT_SECTIONS.md §F–G](07_REPORT_SECTIONS.md) (risk, privacy, full tool and GenAI disclosure) |

## Headline numbers (each one produced by a script; command in the linked file)

- 47 automated tests pass; 87% line coverage.
- Synthetic ground truth (12 cases, 6 drawing conventions):
  - room recall 1.00 and door recall 1.00;
  - free-space IoU 0.983;
  - 0 route edges through walls;
  - label accuracy 0.70;
  - mean |scale error| 8.7% with no measurements.

  Source: [evidence/eval_synthetic_METRICS.md](evidence/eval_synthetic_METRICS.md).
- Generality: 11/12 style cases fully correct. Source: [evidence/style_stress_RESULTS.md](evidence/style_stress_RESULTS.md).
- FAST plans: 14/14 floors valid, 3.6–13.2 s per floor. There is no ground truth yet. Source: [evidence/fast_regression_summary.md](evidence/fast_regression_summary.md).
- Learned segmenter (U-Net, CubiCasa5K, trained on a Kaggle T4): **test mIoU 0.65** (wall 0.75, door 0.64). Run 1 (0.32) exposed a label-alignment bug, which is fixed and has a regression test. In the pipeline it matches classical on filled, solid-wall, coloured and scanned plans but fails on thin and double-line drawings, so classical stays the default. Source: [../RESULTS_ML_2026-10-12.md](../RESULTS_ML_2026-10-12.md).
- Known failures: C-F2 graph in 4 pieces; weak labels on thin-line plans. See [05_TESTING.md](05_TESTING.md) §3.
