"""QA report: overlays + one HTML page per run. This is what the operator reviews before import."""

from __future__ import annotations

import html
from pathlib import Path

import cv2
import numpy as np

from .ir import FloorResult

COL = {
    "walk": (255, 214, 150),
    "room_edge": (90, 90, 90),
    "door": (40, 170, 40),
    "edge": (40, 40, 230),
    "door_edge": (40, 170, 40),
    "junction": (180, 0, 180),
    "node": (40, 40, 230),
    "poi": (0, 110, 0),
}


def overlay(fr: FloorResult) -> np.ndarray:
    base = cv2.cvtColor(fr.image.rgb, cv2.COLOR_RGB2BGR)
    vis = (0.55 * base + 0.45 * 255).astype(np.uint8)
    walk = fr.geom.debug["walk_mask"]
    vis[walk] = (0.5 * vis[walk] + 0.5 * np.array(COL["walk"])).astype(np.uint8)
    for r in fr.geom.regions:
        if r.kind == "circulation":
            continue
        pts = np.array(r.polygon.exterior.coords, np.int32)
        color = (200, 0, 200) if r.kind == "transition" else COL["room_edge"]
        cv2.polylines(vis, [pts], True, color, 1, cv2.LINE_AA)
    for d in fr.geom.doors:
        (x0, y0), (x1, y1) = d.segment.coords[0], d.segment.coords[-1]
        cv2.line(vis, (int(x0), int(y0)), (int(x1), int(y1)), COL["door"], 3, cv2.LINE_AA)
    nodes = fr.graph.nodes
    for e in fr.graph.edges:
        a, b = nodes[e.a], nodes[e.b]
        c = COL["door_edge"] if e.type == "door" else COL["edge"]
        cv2.line(vis, (int(a.x), int(a.y)), (int(b.x), int(b.y)), c, 2, cv2.LINE_AA)
    for n in nodes.values():
        c = COL["junction"] if n.kind == "junction" else (COL["door"] if n.kind == "door" else COL["node"])
        cv2.circle(vis, (int(n.x), int(n.y)), 4 if n.kind == "junction" else 3, c, -1, cv2.LINE_AA)
    by_node = {}
    for p in fr.pois:
        by_node.setdefault(p.node_id, []).append(p)
    for nid, ps in by_node.items():
        n = nodes[nid]
        txt = ps[0].label or ps[0].name[:12]
        col = (0, 0, 200) if ps[0].needs_review else COL["poi"]
        cv2.putText(
            vis, txt, (int(n.x) + 4, int(n.y) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1, cv2.LINE_AA
        )
    return vis


def route_overlay(fr: FloorResult, routes: list) -> np.ndarray:
    vis = (0.55 * cv2.cvtColor(fr.image.rgb, cv2.COLOR_RGB2BGR) + 0.45 * 255).astype(np.uint8)
    nodes = fr.graph.nodes
    palette = [(230, 80, 30), (30, 140, 230), (40, 170, 40), (180, 0, 180), (0, 160, 200)]
    drawn = 0
    for _a, _b, length, path in routes:
        if not path or length is None:
            continue
        col = palette[drawn % len(palette)]
        pts = np.array([(nodes[p].x, nodes[p].y) for p in path], np.int32)
        cv2.polylines(vis, [pts], False, col, 3, cv2.LINE_AA)
        cv2.circle(vis, tuple(pts[0]), 6, col, -1)
        cv2.circle(vis, tuple(pts[-1]), 6, col, 2)
        drawn += 1
        if drawn >= 5:
            break
    return vis


def write_html(out_dir: Path, run: dict, floors: list[dict]) -> Path:
    rows = []
    for f in floors:
        errs = "".join(
            f"<li class=e><b>{html.escape(i['code'])}</b> {html.escape(i['ref'] or '')} "
            f"{html.escape(i['message'])}</li>"
            for i in f["errors"][:30]
        )
        warns = "".join(
            f"<li><b>{html.escape(i['code'])}</b> {html.escape(i['ref'] or '')} "
            f"{html.escape(i['message'])}</li>"
            for i in f["warnings"][:40]
        )
        more = len(f["warnings"]) - 40
        routes = "".join(
            f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{'—' if length is None else f'{length:.1f} m'}"
            f"</td></tr>"
            for a, b, length, _ in f["routes"][:10]
        )
        badge = "<span class=ok>PASSED</span>" if f["passed"] else "<span class=bad>FAILED</span>"
        split = (
            " · <span class=test>TEST floor — do not tune on it</span>" if f.get("split") == "test" else ""
        )
        rows.append(f"""
<section>
<h2>{html.escape(f["id"])} — {html.escape(f["name"])} {badge}{split}</h2>
<p class=stats>scale <b>{f["scale"]:.4f} m/px</b> ({html.escape(f["scale_source"])}) · rooms {f["n_rooms"]} ·
doors {f["n_doors"]} · nodes {f["n_nodes"]} · edges {f["n_edges"]} · POIs {f["n_pois"]}
(needs review {f["n_review"]}) · graph components {f["n_components"]} · {f["seconds"]:.1f}s</p>
<div class=imgs><figure><img src="{f["overlay"]}"><figcaption>walkable (orange), doors (green), graph
(red; purple = junction), labels (red = needs review)</figcaption></figure>
<figure><img src="{f["routes_img"]}"><figcaption>sample A* routes between random destinations</figcaption></figure>
</div>
<details open><summary>errors ({len(f["errors"])})</summary><ul>{errs or "<li>none</li>"}</ul></details>
<details><summary>warnings ({len(f["warnings"])})</summary><ul>{warns}{f"<li>… {more} more</li>" if more > 0 else ""}
</ul></details>
<details><summary>sample routes</summary><table>{routes}</table></details>
</section>""")
    doc = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>TURN-Mapper QA — {html.escape(run["run_id"])}</title><style>
body{{font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1300px;padding:16px;color:#142432;background:#f5f8fa}}
section{{background:#fff;border-radius:10px;padding:14px 18px;margin:14px 0;box-shadow:0 1px 3px #0002}}
h1{{font-size:22px}} h2{{font-size:17px;margin:4px 0}} .stats{{color:#445}}
.imgs{{display:flex;gap:12px;flex-wrap:wrap}} figure{{margin:0;flex:1 1 480px}} img{{width:100%;border:1px solid #ccd}}
figcaption{{font-size:12px;color:#667}} .ok{{background:#72E0B1;padding:2px 8px;border-radius:6px;font-size:12px}}
.bad{{background:#FF7C7C;padding:2px 8px;border-radius:6px;font-size:12px}} .test{{color:#b06000;font-size:12px}}
li.e{{color:#a00}} table td{{padding:2px 10px}} code{{background:#eef}}</style></head><body>
<h1>TURN-Mapper QA report</h1>
<p>run <code>{html.escape(run["run_id"])}</code> · generator {html.escape(run["generator"])} ·
method <b>{html.escape(run["method"])}</b> · git {html.escape(str(run.get("git_commit")))}<br>
All geometry is <b>auto-generated and must be reviewed</b> before use. Scales marked
<code>door_width_prior</code> are estimates, not measurements.</p>
{"".join(rows)}</body></html>"""
    p = out_dir / "qa" / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc)
    return p
