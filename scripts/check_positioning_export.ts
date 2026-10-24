// Check TURN-Mapper exports with the positioning app's own code.
// Run inside a checkout of SMR202/turn-indoor-navigation (after npm install):
//   npx tsx /path/to/Turn-Mapper/scripts/check_positioning_export.ts out/floors/*/venue.package.json out/floors/*/*.geojson
// Exit code 0 = schema valid, no graph edge crosses a wall, every anchor reaches every destination.
import { readFileSync } from 'node:fs';
import { parseVenuePackage, wallCrossings, importFloorGeoJson } from '@turn/venue-model';
import { calculateRoute } from '@turn/routing';
let failed = 0;
for (const path of process.argv.slice(2)) {
  try {
    if (path.endsWith('.geojson')) {
      const { report } = importFloorGeoJson(JSON.parse(readFileSync(path, 'utf8')), { venueId: 'check', name: 'check' });
      console.log(JSON.stringify({ path: path.split('/').slice(-2).join('/'), geojson: true, rooms: report.rooms, doors: report.doors, places: report.places, edges: report.edges, unreachable: report.unreachablePlaces.length, warnings: report.warnings }));
      continue;
    }
    const venue = parseVenuePackage(JSON.parse(readFileSync(path, 'utf8')));
    const crossings = wallCrossings(venue);
    let routes = 0, noRoute = 0;
    for (const a of venue.anchors) for (const p of venue.pois) {
      const r = calculateRoute(venue, a.nodeId, p.nodeId);
      if (r.status === 'ok') routes++; else noRoute++;
    }
    const ok = crossings.length === 0 && noRoute === 0;
    if (!ok) failed++;
    console.log(JSON.stringify({ path: path.split('/').slice(-3).join('/'), schema: 'ok', floors: venue.floors.length, nodes: venue.nodes.length, pois: venue.pois.length, anchors: venue.anchors.length, routes, noRoute, wallCrossings: crossings.length, crossingSample: crossings.slice(0, 3), ok }));
  } catch (e) {
    failed++;
    console.log(JSON.stringify({ path, error: String(e).slice(0, 600) }));
  }
}
process.exit(failed ? 1 : 0);
