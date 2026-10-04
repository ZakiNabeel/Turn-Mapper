# Roadmap and Team Workflow — TURN-Mapper

Status: draft v0.2 (2026-10-04). Targets are weeks from repo creation; the master plan (Prompt 2) refines them. Mapper work must not delay the one-floor positioning demo in the app.

## 1. Milestones

| M | Name | Output | Done when | Owner | Target |
|---|---|---|---|---|---|
| M0 | Repo + audit + plan | repo, docs, `inspect` on FAST PDF, app audit (A1), MASTER_PLAN, ADR-007/008/009 | team reviewed plan; test split frozen | Zaki (+Shehryar for A1) | wk 1 |
| M1 | Skeleton + contract v0.1 | package, CLI (`inspect`/`run`/`validate`), IR, run manifest, JSON Schema, fixtures, CI | synthetic plan → valid `.turnmap`; tag `contract-v0.1.0` | Zaki | wk 1–2 |
| M2 | Thin chain (classical) | ingest (PDF raster + image) → preprocess → classical segment → vectorize → scale → walkable → graph → POIs (no OCR yet) → validate → QA HTML → export | FAST **dev** block floor gives a valid, routable package | Zaki | wk 2–4 |
| M3 | App integration (in app repo) | vendored contract, Kotlin importer, ground-truth exporter, migration if needed | imported FAST floor routes in the app on a phone; existing data untouched; tests green | Shehryar (+Zaki) | wk 4–5 |
| M4 | Data | CubiCasa mapped; 20+ institutional plans collected/annotated; splits frozen | `plans_index.csv`, masks, test checksums in ADR-009 | Zaki (+team) | wk 2–6 |
| M5 | Learned segmentation | model behind `segment` interface; Level A results vs classical | beats classical on val; checkpoint + manifest | Zaki | wk 6–9 |
| M6 | OCR + POIs | labels → rooms → POIs on door nodes | label accuracy reported on val | Zaki | wk 8–10 |
| M7 | Vector branch | vector PDF + DXF adapters into same IR | a vector page/CAD file gives a valid package | Zaki | wk 10–12 |
| M8 | Evaluation | Level B/C metrics + effort study (≥2 operators) | reproducible tables from `eval/` | All | wk 12–14 |
| M9 | Multi-floor (stretch) | building frames + transitions + linker | two FAST floors linked by stairs | Zaki + Sameer | later |

If the FAST PDF turns out to be **vector**, M7 (vector branch) may move before M5 — that decision is made after `inspect`.

## 2. Git workflow

- GitHub repo `TURN-Mapper` (private), `main` always green (pytest + ruff in GitHub Actions).
- Branches: `m<N>/<short-name>`, e.g. `m2/skeleton-graph`. One plan step per PR.
- PR description: what changed, how verified (commands + output), QA screenshots where relevant.
- Any PR touching `contract/` needs review from the app owner.
- Tags: `contract-vX.Y.Z` for contract releases; `vX.Y.Z` for tool releases.

## 3. Definition of done (every PR)

- [ ] Step was planned and approved.
- [ ] Tests added/updated; `pytest`, `ruff check`, `ruff format --check` green locally and in CI.
- [ ] No data/weights/plans-without-permission committed.
- [ ] Docs updated if behaviour or contract changed.
- [ ] `SESSION_LOG.md` entry (`/handoff`).
- [ ] No unverified claims anywhere.

## 4. Weekly rhythm

- Monday (20 min): pick the week's step(s).
- Thursday: integration check — run the chain on the FAST dev floor, import on a real phone.
- Friday: SESSION_LOG summary to the group; blockers (plan files, permissions, GPU).

## 5. Working with Claude Code

- One plan step per session: start with Prompt R, end with `/handoff`.
- Plan mode for anything touching `contract/`, the IR, or > 3 files.
- Commit after each green sub-step.
- If Claude Code wants to change an Accepted decision it writes a Proposed ADR and stops.
