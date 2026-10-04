# TURN-Mapper

Floor plan → navigation graph module of **TURN** (FAST-NUCES Islamabad FYP, infrastructure-minimised indoor navigation).

Give it a floor plan (PDF, image, later DXF; one or many buildings/floors). It produces a `.turnmap` package with metric walkable geometry, walls, doors, rooms, destinations and a routeable graph. The TURN Android app imports that package and adds positioning (PDR, particle filter, Wi-Fi) on top.

AI-assisted, human-verified: every automatic result is checked by validators and a QA report, and corrected by an operator where needed.

- Module boundary and integration: [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md)
- Output format: [`docs/MAP_PACKAGE_SCHEMA.md`](docs/MAP_PACKAGE_SCHEMA.md)
- Pipeline design: [`docs/PIPELINE1_SPEC.md`](docs/PIPELINE1_SPEC.md)
- Status and plan: [`docs/ROADMAP_AND_WORKFLOW.md`](docs/ROADMAP_AND_WORKFLOW.md), [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md)

Status: setup — no code yet.

Team: Zaki Nabeel (map intelligence / CV, module owner), Shehryar Faisal (platform / app integration), M Sameer (positioning).
