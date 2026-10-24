# TURN-Mapper → live positioning app (SMR202/turn-indoor-navigation)

The positioning app already defines two map inputs. TURN-Mapper now writes both of them:

| file | the app's definition | how the app loads it |
|---|---|---|
| `venue.package.json` | Venue package v1, `packages/venue-model/src/schema.ts` (`schemaVersion: 1`) | `npm run venue:load -- venue.package.json`, then `npm run venue:validate` |
| `<floor>.turn-floor.geojson` | TURN Floor GeoJSON v1, `docs/MAP_IMPORT_FORMAT.md` | TURN Studio: Venue → Map → drop the file (the app builds its own walk graph) |

The **venue package is the recommended path**. It carries TURN-Mapper's own navigation graph, which follows corridor centre lines and is checked against walls. The GeoJSON route lets the app derive a simpler room–door graph. On FAST that leaves more places unreachable: 0 unreachable on C-F3/C-F4, but many on floors with open halls.

## Make the files

```bash
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split all --out runs/fast
turn-mapper export-positioning runs/fast/venue.json --out runs/fast/positioning
# runs/fast/positioning/floors/C-F4/venue.package.json      one floor, always fully routable
# runs/fast/positioning/C/venue.package.json                C block, floors joined where stairs/lifts matched
# runs/fast/positioning/export_report.json                  counts, dropped destinations, scale sources
```

Then, in the positioning repository:

```bash
npm run venue:load -- /path/to/runs/fast/positioning/floors/C-F4/venue.package.json
npm run venue:validate
npm run mobile
```

The FAST packages contain private plan geometry. `venue:load` keeps them in the app's ignored `work/private/`; do not commit them.

## What the export does

- **Frame:**
  - TURN-Mapper: metres, origin at the image's top-left, y down.
  - App: metres, x right, y **up**.
  - Every y becomes `floor height − y`, where the floor height is image height × scale. Floor width and height are the image size in metres.
- **IDs:** prefixed with the floor id (`C-F4:n12`), so floors can share one package.
- **Rooms:** OCR label + name. Stairs/lift rooms have `kind: stairs`. Corridors are added as `circulation` polygons (walkable area minus rooms).
- **Doors:** the centre of the opening, with its width.
- **Walls:** wall centre lines.
- **Edges:** our edge length, never shorter than the straight line (the app's schema rejects that). `stepFree` is false only where the map says not accessible.
- **Connectors:** stairs/lift links from multi-floor linking (`venue.transitions`) become `connectors` plus a cross-floor edge.
  - The length is an estimate (6 m for stairs, 4 m for a lift).
  - Stairs are not step-free.
- **Anchors:** a `manual` start anchor at every stairs/lift node in the main graph. With none, one goes at the busiest corridor junction. QR anchors are for the team to place on site.
- **Destinations:** limited to those connected to the anchors, because `venue:validate` requires a route from every anchor to every destination. The rest are listed in `export_report.json` (`--keep-unreachable` keeps them).
- **Provenance:**
  - `kind: plan-derived`, with a private-rights statement.
  - One note per floor with its scale source. Anything other than `measured_room_size`, `operator_two_point` or `cad_units` is marked *(estimate)*.

## Verified (2026-10-24)

The 17 FAST packages (14 single floors and 3 buildings) were run through the positioning app's own code: `parseVenuePackage`, `wallCrossings` and `calculateRoute` from `@turn/venue-model` and `@turn/routing`. The code was copied unchanged from branch `codex/native-step-comparison` at `575ecea`, and its 27 unit tests pass in the check environment.

- All 17 pass the schema.
- 0 graph edges cross a wall.
- Every anchor → destination route is found: 579 routes, 0 failures.
- All 14 GeoJSON files import with `importFloorGeoJson`.

Run commands:

- Python side: `tests/test_positioning_export.py`.
- App side: `scripts/check_positioning_export.ts`. Run it inside a checkout of the positioning repository; see the header of that file.

## Known limits

- **Scale:** C-F3, C-F4, B-GF and B-F1 are measured; the other floors use the calibrated door estimate (`docs/RESULTS_SCALE_2026-10-24.md`).
- **Multi-floor links:** only 6 links were matched (A 1, B 1, C 4), so the building packages leave out destinations on unlinked floors. The single-floor packages are complete.
- **Every map is automatic:** check it in TURN Studio (and correct it) before a walk test.
