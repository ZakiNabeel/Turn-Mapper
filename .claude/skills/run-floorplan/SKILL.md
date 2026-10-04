---
name: run-floorplan
description: Run the TURN-Mapper pipeline on a floor plan (or inspect a new one) and visually review the QA output. Use when asked to try, run, test or debug the pipeline on a real plan, or to onboard a new building's plan.
argument-hint: "[plan path] [venue config]"
---

# Run a floor plan through TURN-Mapper

Arguments: `$ARGUMENTS` (plan path, optional venue config).

## 1. Check the plan is allowed for what you're about to do
- Read `docs/DECISIONS.md` ADR-009. If the plan/page is in the **held-out test set**, you may run the pipeline and report results, but you must **not** change thresholds, heuristics, configs or code based on what you see. Say so explicitly in your reply.
- If ADR-009 is still OPEN, only run `inspect` and stop with a reminder to freeze the split.

## 2. New plan? Inspect first
```bash
turn-mapper inspect <plan> --out runs/inspect_<name>
```
Open the contact sheet / thumbnails with the Read tool (it shows images). Report per page: vector or raster, drawing/text counts, which building/floor it appears to be, title block / legend location, whether a scale bar or dimension text exists. Propose (don't silently write) the `configs/venues/<venue>.yaml` entries.

## 3. Run
```bash
turn-mapper run <plan> --venue <config> --out runs/<yyyy-mm-dd>_<name>
turn-mapper validate runs/<...>/venue.turnmap
```

## 4. Look at the result — actually look
Use the Read tool on the overlay PNGs in `runs/<...>/qa/` (mask, walls, walkable, graph, POIs, sample routes). Do not judge from numbers alone. For a thorough review, delegate to the `qa-inspector` agent.

Report:
- validator errors/warnings (counts + top 5);
- nodes / edges / POIs / connected components;
- scale residuals on held-out measured distances;
- the 5 most expensive problems for a human to fix in the app (e.g. corridor split into two components, doors missing on one wall, lobby skeleton full of spurs), each with the overlay path and the stage that caused it.

## 5. Never
- Never report a metric you didn't compute in this session.
- Never "fix" a test-set result by editing the venue config for that page beyond what ADR-009 allows (page mapping, crop of title block, measured distances are allowed; thresholds are not).
