---
name: turnmap-contract
description: Checklist for any change to the .turnmap contract (contract/ folder, JSON Schema, package writer/reader, MAP_PACKAGE_SCHEMA.md). Use whenever a change would alter what the Android app receives.
paths:
  - "contract/**"
  - "src/turn_mapper/export/**"
  - "docs/MAP_PACKAGE_SCHEMA.md"
---

# Changing the TURN map package contract

The `.turnmap` format is the only interface between this module and the Android app (`docs/INTEGRATION_CONTRACT.md`). Another team depends on it.

## Before changing
1. Is the change really needed, or can it be an **optional** field (MINOR bump, backward compatible)? Prefer optional.
2. Write a Proposed ADR in `docs/DECISIONS.md` describing the change, the version bump (MAJOR for breaking, MINOR for additive, PATCH for docs/clarification) and the impact on the app importer. **Stop and ask the human to confirm** unless the step in `docs/MASTER_PLAN.md` already approved it.

## The change (all in one PR)
- [ ] `contract/turnmap.schema.json` updated; `schema_version` bumped
- [ ] `docs/MAP_PACKAGE_SCHEMA.md` updated (example JSON + rules)
- [ ] `contract/CHANGELOG.md` entry: version, date, what changed, what the app must do
- [ ] writer (`export/`) and reader (`api.load_package`) updated
- [ ] fixtures in `contract/fixtures/` regenerated **and** still validate; old-version fixture kept if reader supports it
- [ ] tests: schema validation of every fixture; write → read round-trip; validator rules
- [ ] `pytest` + `ruff` green

## After merge
- Tag `contract-vX.Y.Z`.
- Tell the human to open the matching PR in the app repo (vendored copy at `app/src/test/resources/turnmap/` + importer change). Draft that PR description for them.
