# Session Log — TURN-Mapper

Newest entry at the top. Every Claude Code session (and every human session that changes the module) adds one. `/handoff` writes it.

## Template

```markdown
## YYYY-MM-DD — <who> — <milestone/step>
**Goal:**
**Changed:** (files / modules)
**Verified:** (exact commands and real results; QA report paths)
**Not verified / unknown:**
**Broken or risky:**
**Decisions / ADRs proposed:**
**Next step:**
```

---

## 2026-10-04 — Zaki (+Claude in claude.ai) — FAST PDF first look
**Goal:** inspect Floor_Plans_2.pdf before planning.
**Changed:** docs/PLAN_INVENTORY.md, docs/img/proto_*.png, configs/venues/fast_isb.yaml (draft), ADR-009 proposal, ADR-011.
**Verified:** PyMuPDF inventory: 8 pages, 0 vector drawings, 16 embedded images (14 floors + site plan + logo). Grey levels floor≈238 / wall≈191,153 / bg 255 on all floors. Throwaway classical test on A-GF and B-F1: walls/floor separate trivially; many rooms merge with the corridor through open door gaps; text holes and wide areas break the skeleton.
**Not verified / unknown:** whether the drawings are to scale; image_index order on multi-image pages; permission to use the PDF.
**Next step:** team picks the ADR-009 split; measure distances on site; Prompt 1 (verify inventory) in Claude Code.

---

## 2026-10-04 — Zaki — Repo setup
**Goal:** create TURN-Mapper module repo with docs, contract plan, project skills/agents.
**Changed:** CLAUDE.md, docs/*, .claude/skills/*, .claude/agents/*, samples/README.md.
**Verified:** nothing run yet; docs only.
**Not verified / unknown:** whether the FAST A/B/C PDF is vector or raster; app coordinate frame; how the app stores walkable/graph/POIs.
**Next step:** Prompt 1 (inspect FAST PDF) in TURN-Mapper; Prompt A1 (app audit) in TURN-Field-Test.
