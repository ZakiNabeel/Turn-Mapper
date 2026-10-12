# Task log: TURN-Mapper

One row per task, with its owner and the commit(s) that delivered it. Detailed notes are in `docs/SESSION_LOG.md`.

| Date | Task | Owner | Status | Commit / tag |
|---|---|---|---|---|
| 2026-10-04 | Repo setup: docs, contract draft, project skills, FAST PDF inventory | ZN | done | `9cf8406` |
| 2026-10-04 | M1 skeleton + contract v0.1 schema/fixtures + CI; M2 classical chain | ZN | done | `a606f67` |
| 2026-10-04 | Fix: accept junction openings that join two spaces as doors | ZN | done | `49606b4` |
| 2026-10-04 | Fix: orient skeleton polylines (edges cut through rooms) | ZN | done | `2b99f5f` |
| 2026-10-04 | Results v0.1, decisions, roadmap | ZN | done | `ae395f6` → tag `v0.1.0` |
| 2026-10-04 | C block: stairs → transitions, thin partitions, graph checks, bridging | ZN | done | `a147823` |
| 2026-10-04 | C block: 3-orientation OCR, door slabs, footprint scale transfer, circulation rule | ZN | done | `801d5e4` |
| 2026-10-04 | C-block results doc, ADR-009 accepted | ZN | done | `5d092b1` → tag `v0.2.0` |
| 2026-10-11 | JSON output (`venue.json`), `--format` | ZN | done | `9b6030d` |
| 2026-10-11 | Style-generic segmentation, style stress test, generality results | ZN | done | `f81b133` |
| 2026-10-11 | Learned segmenter scaffold, CubiCasa reader, training/eval, Colab notebook, ML guide | ZN | done | `7f6e5a1` |
| 2026-10-12 | Mid-eval package: requirements, design diagrams, ground-truth eval, edge-case and requirement tests, test logs, milestone log, demo script, report sections, contract 0.1.1 | ZN | done | tag `v0.3.0` |
| next | CubiCasa pre-training on GPU | ZN | planned 2026-10-19 | |
| next | Site measurements (2 per C floor) | ZN + MS | planned 2026-10-23 | |
| next | Annotate 5–8 B/C floors | ZN | planned 2026-10-26 | |
| next | App importer for `venue.json` | SF | owner to confirm | (app repo) |

Ownership: TURN-Mapper is owned by ZN (see `CODEOWNERS`). Positioning (MS) and the app (SF) are in `shehryarf67/TURN-Field-Test`. The two repos meet only at `contract/`. Changes to the contract need review from the app owner.
