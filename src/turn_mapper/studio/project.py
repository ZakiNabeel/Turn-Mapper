"""TURN Studio projects: files on disk, pipeline runs, hand corrections and exports.

A project is a folder::

    <studio dir>/<project id>/
        project.json                 floors, settings
        input/<uploaded files>
        floors/<floor id>/base.png   the plan as loaded (after crop/rotate)
                         erase.png   input-level erase mask (white = erase)
                         masks.png   label map 0 outside, 1 wall, 2 floor (auto, or hand-corrected)
                         auto.json   last automatic floor.json (metres)
                         floor.json  current floor.json, including manual edits

Everything the app imports comes from ``floor.json``, so manual edits always survive export. Coordinates
in ``floor.json`` are metres (``px * scale``, y down, origin at the image's top-left), as in the contract.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import cv2
import networkx as nx
import numpy as np

from .. import __version__
from ..api import process_floor
from ..config import PipelineParams, VenueConfig
from ..export import floor_to_dict, png_bytes, venue_dict, write_json_package, write_package
from ..ingest import inspect_file, load_floor
from ..ir import FloorSpec, Segmentation
from ..learned.classes import BG, DOOR, ROOM, STAIRS, WALKABLE, WALL
from ..segment import estimate_levels
from ..validate import route_lengths, validate_floor

OUTSIDE, M_WALL, M_FLOOR = 0, 1, 2
MASK_RGB = {OUTSIDE: (255, 255, 255), M_WALL: (40, 40, 40), M_FLOOR: (120, 190, 240)}
ACCEPT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".dxf", ".svg", ".dwg"}


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", s.strip()).strip("-")
    return s or "project"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_png(path: Path, flags=cv2.IMREAD_COLOR) -> np.ndarray:
    a = cv2.imread(str(path), flags)
    if a is None:
        raise FileNotFoundError(path)
    return a


class Studio:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------------- projects ----------------
    def list_projects(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            d = json.loads(p.read_text())
            out.append(
                {"id": d["id"], "name": d["name"], "floors": len(d["floors"]), "updated": d.get("updated")}
            )
        return out

    def create_project(self, name: str) -> dict:
        pid = _slug(name)
        base, i = pid, 2
        while (self.root / pid).exists():
            pid, i = f"{base}-{i}", i + 1
        d = {
            "id": pid,
            "name": name.strip() or pid,
            "venue_id": pid.lower(),
            "created": _now(),
            "updated": _now(),
            "files": [],
            "buildings": [],
            "floors": [],
        }
        (self.root / pid / "input").mkdir(parents=True)
        self._save(d)
        return d

    def project(self, pid: str) -> dict:
        p = self.root / _slug(pid) / "project.json"
        if not p.exists():
            raise KeyError(f"no project {pid}")
        return json.loads(p.read_text())

    def _save(self, d: dict) -> None:
        d["updated"] = _now()
        (self.root / d["id"] / "project.json").write_text(json.dumps(d, indent=1))

    def pdir(self, pid: str) -> Path:
        return self.root / _slug(pid)

    def fdir(self, pid: str, fid: str) -> Path:
        p = self.pdir(pid) / "floors" / _slug(fid)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ---------------- files ----------------
    def add_file(self, pid: str, filename: str, data: bytes) -> dict:
        d = self.project(pid)
        name = Path(filename).name
        if Path(name).suffix.lower() not in ACCEPT:
            raise ValueError(f"unsupported file type {Path(name).suffix}; use PDF, image, DXF or SVG")
        dest = self.pdir(pid) / "input" / name
        dest.write_bytes(data)
        info = inspect_file(str(dest))  # raises a clear error for DWG
        d["files"] = [f for f in d["files"] if f["name"] != name] + [{"name": name, "kind": info["kind"]}]
        self._save(d)
        return info

    def inspect(self, pid: str, name: str) -> dict:
        return inspect_file(str(self.pdir(pid) / "input" / Path(name).name))

    def thumbnail(
        self, pid: str, name: str, page: int = 1, image_index: int | None = None, w: int = 360
    ) -> bytes:
        path = self.pdir(pid) / "input" / Path(name).name
        spec = FloorSpec(
            id="thumb",
            building="B",
            level=0,
            name="",
            source_file=str(path),
            page=page,
            image_index=image_index,
        )
        suffix = path.suffix.lower()
        if suffix == ".pdf" and image_index is None:
            import pymupdf

            pg = pymupdf.open(path)[page - 1]
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(w / pg.rect.width, w / pg.rect.width), alpha=False)
            rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        else:
            if suffix == ".dxf":
                spec = replace(spec, options={"target_px": 900})
            rgb = load_floor(spec).rgb
        f = w / rgb.shape[1]
        small = cv2.resize(rgb, (w, max(1, int(rgb.shape[0] * f))), interpolation=cv2.INTER_AREA)
        return png_bytes(small)

    # ---------------- floors ----------------
    def floor(self, pid: str, fid: str) -> dict:
        d = self.project(pid)
        for f in d["floors"]:
            if f["id"] == fid:
                return f
        raise KeyError(f"no floor {fid}")

    def _put_floor(self, pid: str, rec: dict) -> dict:
        d = self.project(pid)
        d["floors"] = [f for f in d["floors"] if f["id"] != rec["id"]] + [rec]
        d["floors"].sort(key=lambda f: (f["building"], f["level"], f["id"]))
        if rec["building"] not in {b["id"] for b in d["buildings"]}:
            d["buildings"].append({"id": rec["building"], "name": f"{rec['building']} Block"})
        self._save(d)
        return rec

    def add_floor(self, pid: str, body: dict) -> dict:
        d = self.project(pid)
        src = Path(body["source"]).name
        if src not in {f["name"] for f in d["files"]}:
            raise ValueError(f"upload {src} first")
        fid = _slug(body.get("id") or f"F{len(d['floors']) + 1}")
        if any(f["id"] == fid for f in d["floors"]):
            raise ValueError(f"floor id {fid} already exists")
        rec = {
            "id": fid,
            "building": _slug(body.get("building") or "B1"),
            "level": int(body.get("level", 0)),
            "name": body.get("name") or fid,
            "source": src,
            "page": body.get("page"),
            "image_index": body.get("image_index"),
            "options": body.get("options") or {},
            "crop": None,
            "rotate": 0,
            "segmenter": "classical",
            "scale_evidence": [],
            "status": "new",
            "source_meta": {},
            "stats": {},
        }
        self._put_floor(pid, rec)
        self.prepare(pid, fid)
        return self.floor(pid, fid)

    def update_floor_meta(self, pid: str, fid: str, body: dict) -> dict:
        rec = self.floor(pid, fid)
        for k in ("name", "level", "building", "segmenter"):
            if k in body:
                rec[k] = int(body[k]) if k == "level" else body[k]
        return self._put_floor(pid, rec)

    def delete_floor(self, pid: str, fid: str) -> None:
        d = self.project(pid)
        d["floors"] = [f for f in d["floors"] if f["id"] != fid]
        self._save(d)

    def prepare(
        self,
        pid: str,
        fid: str,
        crop: list[int] | None = None,
        rotate: int | None = None,
        options: dict | None = None,
    ) -> dict:
        """(Re)load the source file into ``base.png``; crop is in the *loaded, rotated* image's pixels."""
        rec = self.floor(pid, fid)
        if options is not None:
            rec["options"] = options
        if rotate is not None:
            rec["rotate"] = int(rotate) % 360
        rec["crop"] = crop if crop is None or len(crop) == 4 else None
        spec = FloorSpec(
            id=fid,
            building=rec["building"],
            level=rec["level"],
            name=rec["name"],
            source_file=str(self.pdir(pid) / "input" / rec["source"]),
            page=rec["page"],
            image_index=rec["image_index"],
            options=rec["options"],
        )
        img = load_floor(spec)
        rgb = img.rgb
        k = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
        if k[rec["rotate"]] is not None:
            rgb = cv2.rotate(rgb, k[rec["rotate"]])
        if rec["crop"]:
            x0, y0, x1, y1 = (int(v) for v in rec["crop"])
            x0, x1 = sorted((max(0, x0), min(rgb.shape[1], x1)))
            y0, y1 = sorted((max(0, y0), min(rgb.shape[0], y1)))
            if x1 - x0 > 20 and y1 - y0 > 20:
                rgb = rgb[y0:y1, x0:x1]
        fd = self.fdir(pid, fid)
        cv2.imwrite(str(fd / "base.png"), cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR))
        for stale in ("erase.png", "masks.png"):
            (fd / stale).unlink(missing_ok=True)
        rec["source_meta"] = {k2: v for k2, v in img.source_meta.items() if not isinstance(v, bytes)}
        rec["size"] = [int(rgb.shape[1]), int(rgb.shape[0])]
        rec["status"] = "new"
        # the old scale points were in the old pixels
        rec["scale_evidence"] = []
        return self._put_floor(pid, rec)

    def plan_rgb(self, pid: str, fid: str) -> np.ndarray:
        fd = self.fdir(pid, fid)
        bgr = _read_png(fd / "base.png")
        er = fd / "erase.png"
        if er.exists():
            m = _read_png(er, cv2.IMREAD_GRAYSCALE) > 127
            if m.shape == bgr.shape[:2]:
                bgr[m] = 255
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def save_erase(self, pid: str, fid: str, png: bytes) -> None:
        m = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
        if m.ndim == 3:  # RGBA from a canvas: painted where alpha > 0
            m = m[:, :, 3] if m.shape[2] == 4 else cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
        cv2.imwrite(str(self.fdir(pid, fid) / "erase.png"), ((m > 127) * 255).astype(np.uint8))

    # ---------------- running the pipeline ----------------
    def _spec_cfg(self, pid: str, fid: str) -> tuple[FloorSpec, VenueConfig, Path]:
        d = self.project(pid)
        rec = self.floor(pid, fid)
        fd = self.fdir(pid, fid)
        plan = fd / "_plan.png"
        cv2.imwrite(str(plan), cv2.cvtColor(self.plan_rgb(pid, fid), cv2.COLOR_RGB2BGR))
        ev = list(rec["scale_evidence"])
        cad = rec.get("source_meta", {}).get("cad_m_per_px")
        if cad and not any(e.get("method") == "cad_units" for e in ev):
            ev.insert(0, {"method": "cad_units", "m_per_px": cad, "units": rec["source_meta"].get("units")})
        spec = FloorSpec(
            id=fid,
            building=rec["building"],
            level=rec["level"],
            name=rec["name"],
            source_file=str(plan),
            scale_evidence=ev,
        )
        cfg = VenueConfig(
            id=d["venue_id"],
            name=d["name"],
            buildings=d["buildings"],
            floors=[spec],
            params=PipelineParams(**d.get("params", {})),
        )
        return spec, cfg, fd

    def run(self, pid: str, fid: str, segmenter: str | None = None, from_masks: bool = False) -> dict:
        rec = self.floor(pid, fid)
        if segmenter:
            rec["segmenter"] = segmenter
        spec, cfg, fd = self._spec_cfg(pid, fid)
        override = None
        if from_masks:
            m = _read_png(fd / "masks.png", cv2.IMREAD_GRAYSCALE)
            gray = cv2.cvtColor(self.plan_rgb(pid, fid), cv2.COLOR_RGB2GRAY)
            if m.shape != gray.shape:
                raise ValueError("mask size does not match the plan; run the floor again")
            override = Segmentation(
                wall=m == M_WALL,
                floor=m == M_FLOOR,
                background=m == OUTSIDE,
                levels=estimate_levels(gray),
                method="corrected",
            )
        t0 = time.perf_counter()
        fr = process_floor(spec, cfg, rec["segmenter"], seg_override=override)
        fdict = floor_to_dict(fr)
        fdict["image"]["file"] = "floorplan.png"
        source = "corrected" if from_masks else "auto"
        if from_masks:
            for key in ("walkable",):
                fdict[key]["provenance"]["source"] = source
            for coll in ("walls", "doors", "rooms"):
                for x in fdict[coll]:
                    x["provenance"]["source"] = source
        lab = np.zeros(fr.seg.wall.shape, np.uint8)
        lab[fr.seg.floor] = M_FLOOR
        lab[fr.seg.wall] = M_WALL
        if not from_masks:
            cv2.imwrite(str(fd / "masks.png"), lab)
        (fd / "auto.json").write_text(json.dumps(fdict, indent=1))
        rec["status"] = "corrected" if from_masks else "auto"
        rec["stats"] = {
            "seconds": round(time.perf_counter() - t0, 2),
            "timings": {k: round(v, 2) for k, v in fr.timings.items() if not k.startswith("_")},
        }
        rec["auto_warnings"] = [w.to_dict() for w in fr.warnings]
        self._put_floor(pid, rec)
        return self.save_floor_json(pid, fid, fdict)

    # ---------------- edits ----------------
    def floor_json(self, pid: str, fid: str) -> dict | None:
        p = self.fdir(pid, fid) / "floor.json"
        return json.loads(p.read_text()) if p.exists() else None

    def save_masks(self, pid: str, fid: str, png: bytes) -> None:
        """Label map from the editor, as an RGB(A) image in ``MASK_RGB`` colours (nearest colour wins)."""
        a = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        rgb = cv2.cvtColor(a, cv2.COLOR_BGR2RGB).astype(np.int32)
        cols = np.array([MASK_RGB[k] for k in (OUTSIDE, M_WALL, M_FLOOR)], np.int32)
        d = ((rgb[:, :, None, :] - cols[None, None]) ** 2).sum(-1)
        cv2.imwrite(str(self.fdir(pid, fid) / "masks.png"), d.argmin(-1).astype(np.uint8))

    def mask_rgb(self, pid: str, fid: str) -> np.ndarray:
        m = _read_png(self.fdir(pid, fid) / "masks.png", cv2.IMREAD_GRAYSCALE)
        pal = np.array([MASK_RGB[k] for k in (OUTSIDE, M_WALL, M_FLOOR)] + [(255, 0, 255)] * 253, np.uint8)
        return pal[m]

    def save_floor_json(self, pid: str, fid: str, fdict: dict) -> dict:
        """Tidy an edited floor (drop dangling references, recompute edge lengths), validate and save."""
        fdict = tidy_floor(fdict)
        errs, warns = validate_floor(fdict)
        rec = self.floor(pid, fid)
        routes = route_lengths(fdict, pairs=30)
        ok_routes = sum(1 for r in routes if r[2] is not None)
        g = nx.Graph([(e["from"], e["to"]) for e in fdict["graph"]["edges"]])
        g.add_nodes_from(n["id"] for n in fdict["graph"]["nodes"])
        fdict["validation"] = {
            "passed": not errs,
            "forced": False,
            "errors": [e.to_dict() for e in errs],
            "warnings": [w.to_dict() for w in warns] + rec.get("auto_warnings", []),
        }
        (self.fdir(pid, fid) / "floor.json").write_text(json.dumps(fdict, indent=1))
        rec["summary"] = {
            "passed": not errs,
            "rooms": len(fdict["rooms"]),
            "doors": len(fdict["doors"]),
            "nodes": len(fdict["graph"]["nodes"]),
            "edges": len(fdict["graph"]["edges"]),
            "pois": len(fdict["pois"]),
            "components": nx.number_connected_components(g) if len(g) else 0,
            "routes_ok": ok_routes,
            "routes_tried": len(routes),
            "scale_m_per_px": fdict["transform"]["scale_m_per_px"],
            "scale_source": fdict["transform"]["scale_source"],
        }
        if rec["status"] in ("auto", "corrected") and fdict.get("_edited"):
            rec["status"] = "edited"
        fdict.pop("_edited", None)
        self._put_floor(pid, rec)
        return {"floor": fdict, "record": rec}

    def set_scale(self, pid: str, fid: str, pairs: list[dict]) -> dict:
        """Operator two-point measurements in plan pixels. The first pair fits the scale, the others are
        held-out checks. Rescales the current floor.json in place (manual edits are kept)."""
        from ..scale import scale_from_evidence

        rec = self.floor(pid, fid)
        ev = [
            {
                "p1_px": [float(v) for v in p["p1_px"]],
                "p2_px": [float(v) for v in p["p2_px"]],
                "distance_m": float(p["distance_m"]),
                "used_for_fit": i == 0,
            }
            for i, p in enumerate(pairs)
        ]
        s_new, ev_out = scale_from_evidence(ev)
        rec["scale_evidence"] = ev
        self._put_floor(pid, rec)
        fdict = self.floor_json(pid, fid)
        if fdict is None:
            return {"scale_m_per_px": s_new, "evidence": ev_out}
        s_old = fdict["transform"]["scale_m_per_px"]
        fdict = rescale_floor(fdict, s_new / s_old)
        fdict["transform"].update(
            {
                "px_to_m": [[s_new, 0.0, 0.0], [0.0, s_new, 0.0]],
                "scale_m_per_px": s_new,
                "scale_source": "operator_two_point",
                "scale_evidence": ev_out,
            }
        )
        fdict["validation"]["warnings"] = [
            w for w in fdict["validation"]["warnings"] if not w["code"].startswith("SCALE_")
        ]
        rec["auto_warnings"] = [w for w in rec.get("auto_warnings", []) if not w["code"].startswith("SCALE_")]
        self._put_floor(pid, rec)
        return self.save_floor_json(pid, fid, fdict)

    def edit_walkable(self, pid: str, fid: str, polygon: list[list[float]], op: str) -> dict:
        """``op="remove"``: cut a polygon (metres) out of the walkable area (voids, shafts, blocked areas);
        graph nodes inside it and their edges go too. ``op="add"``: add walkable area."""
        fdict = self.floor_json(pid, fid)
        if fdict is None:
            raise ValueError("run the floor first")
        return self.save_floor_json(pid, fid, walkable_edit(fdict, polygon, op))

    def revert(self, pid: str, fid: str) -> dict:
        auto = self.fdir(pid, fid) / "auto.json"
        return self.save_floor_json(pid, fid, json.loads(auto.read_text()))

    # ---------------- exports ----------------
    def _ready_floors(self, pid: str, include_failed: bool = False) -> list[tuple[dict, dict]]:
        out = []
        for rec in self.project(pid)["floors"]:
            fdict = self.floor_json(pid, rec["id"])
            if fdict and (fdict["validation"]["passed"] or include_failed):
                out.append((rec, fdict))
        return out

    def _venue(self, pid: str, floors: list[tuple[dict, dict]]) -> dict:
        d = self.project(pid)
        vfloors = [
            {
                "id": r["id"],
                "building_id": r["building"],
                "level": r["level"],
                "name": r["name"],
                "path": f"floors/{r['id']}/floor.json",
                "source": r.get("source_meta", {}),
                "validation_passed": f["validation"]["passed"],
            }
            for r, f in floors
        ]
        used = {r["building"] for r, _ in floors}
        return venue_dict(
            d["venue_id"],
            d["name"],
            [b for b in d["buildings"] if b["id"] in used],
            vfloors,
            f"studio-{_now()}",
            None,
            "studio",
        )

    def export(self, pid: str, fmt: str, include_failed: bool = False) -> tuple[bytes, str, str]:
        floors = self._ready_floors(pid, include_failed)
        if not floors and fmt != "annotations":
            raise ValueError("no floor passes validation yet; fix the errors or export with include_failed")
        pdir = self.pdir(pid)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = pdir / "exports" / stamp
        out_dir.mkdir(parents=True, exist_ok=True)
        pngs = {r["id"]: png_bytes(self.plan_rgb(pid, r["id"])) for r, _ in floors}
        if fmt in ("venue.json", "json"):
            vd = self._venue(pid, floors)
            path = write_json_package(
                out_dir / "venue.json", vd, {r["id"]: (f, pngs[r["id"]]) for r, f in floors}
            )
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(path, "venue.json")
                for img in (out_dir / "images").glob("*.png"):
                    z.write(img, f"images/{img.name}")
            return buf.getvalue(), f"{pid}_venue_json.zip", "application/zip"
        if fmt == "turnmap":
            vd = self._venue(pid, floors)
            path = write_package(
                out_dir / "venue.turnmap", vd, {r["id"]: (f, pngs[r["id"]]) for r, f in floors}
            )
            return path.read_bytes(), f"{pid}.turnmap", "application/zip"
        if fmt == "geojson":
            gj = {
                "type": "FeatureCollection",
                "features": [],
                "properties": {
                    "crs": "local metres, origin top-left of each floor image, y down",
                    "generator": f"turn-mapper {__version__} studio",
                },
            }
            for r, f in floors:
                gj["features"] += floor_geojson(r["id"], f)
            data = json.dumps(gj, indent=1).encode()
            (out_dir / "venue.geojson").write_bytes(data)
            return data, f"{pid}.geojson", "application/geo+json"
        if fmt == "svg":
            if len(floors) == 1:
                data = floor_svg(floors[0][1]).encode()
                return data, f"{pid}_{floors[0][0]['id']}.svg", "image/svg+xml"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for r, f in floors:
                    z.writestr(f"{r['id']}.svg", floor_svg(f))
            return buf.getvalue(), f"{pid}_svg.zip", "application/zip"
        if fmt == "annotations":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for rec in self.project(pid)["floors"]:
                    f = self.floor_json(pid, rec["id"])
                    mp = self.fdir(pid, rec["id"]) / "masks.png"
                    if f is None or not mp.exists():
                        continue
                    gray = cv2.cvtColor(self.plan_rgb(pid, rec["id"]), cv2.COLOR_RGB2GRAY)
                    lab = training_mask(_read_png(mp, cv2.IMREAD_GRAYSCALE), f)
                    name = f"{pid}_{rec['id']}"
                    z.writestr(f"images/{name}.png", cv2.imencode(".png", gray)[1].tobytes())
                    z.writestr(f"masks/{name}.png", cv2.imencode(".png", lab)[1].tobytes())
                z.writestr(
                    "README.txt",
                    "TURN segmentation annotations from TURN Studio. masks: class ids "
                    "(0 background, 1 wall, 2 room, 3 walkable, 4 door, 5 stairs); same format as "
                    "`turn-mapper ml bootstrap-masks`. Private data: never commit.\n",
                )
            return buf.getvalue(), f"{pid}_annotations.zip", "application/zip"
        raise ValueError(f"unknown export format {fmt}")


# ---------------- helpers (pure functions, unit-tested) ----------------
def tidy_floor(fd: dict) -> dict:
    fd = json.loads(json.dumps(fd))
    nodes = {n["id"]: n for n in fd["graph"]["nodes"]}
    seen, edges = set(), []
    for e in fd["graph"]["edges"]:
        a, b = e["from"], e["to"]
        key = tuple(sorted((a, b)))
        if a == b or a not in nodes or b not in nodes or key in seen:
            continue
        seen.add(key)
        e["length_m"] = round(
            float(np.hypot(nodes[a]["x"] - nodes[b]["x"], nodes[a]["y"] - nodes[b]["y"])), 3
        )
        edges.append(e)
    fd["graph"]["edges"] = edges
    door_ids = {d["id"] for d in fd["doors"]}
    for n in fd["graph"]["nodes"]:
        if n.get("door_id") and n["door_id"] not in door_ids:
            n["door_id"] = None
            if n["kind"] == "door":
                n["kind"] = "junction"
    room_ids = {r["id"] for r in fd["rooms"]}
    for d in fd["doors"]:
        if d.get("room_id") not in room_ids:
            d["room_id"] = None
    fd["pois"] = [p for p in fd["pois"] if p["node_id"] in nodes]
    for p in fd["pois"]:
        if p.get("room_id") not in room_ids:
            p["room_id"] = None
    return fd


def walkable_edit(fd: dict, polygon: list[list[float]], op: str) -> dict:
    from shapely.geometry import MultiPolygon, Point, Polygon, mapping

    from ..validate import walkable_geom

    if len(polygon) < 3:
        raise ValueError("draw at least 3 points")
    fd = json.loads(json.dumps(fd))
    poly = Polygon(polygon).buffer(0)
    walk = walkable_geom(fd)
    new = walk.difference(poly) if op == "remove" else walk.union(poly)
    if new.geom_type == "Polygon":
        new = MultiPolygon([new])
    elif new.geom_type != "MultiPolygon":
        new = MultiPolygon([g for g in getattr(new, "geoms", []) if g.geom_type == "Polygon"])
    coords = mapping(new)["coordinates"]
    fd["walkable"]["coordinates"] = [
        [[[round(x, 3), round(y, 3)] for x, y in ring] for ring in p] for p in coords
    ]
    fd["walkable"]["provenance"] = {"source": "corrected", "confidence": 1.0}
    if op == "remove":
        gone = {n["id"] for n in fd["graph"]["nodes"] if poly.contains(Point(n["x"], n["y"]))}
        fd["graph"]["nodes"] = [n for n in fd["graph"]["nodes"] if n["id"] not in gone]
        fd["rooms"] = [
            r for r in fd["rooms"] if not poly.buffer(0.05).contains(Polygon(r["polygon"]).buffer(0))
        ]
    fd["_edited"] = True
    return fd


def _scale_pts(v, k):
    if isinstance(v, (int, float)):
        return round(v * k, 3)
    return [_scale_pts(x, k) for x in v]


def rescale_floor(fd: dict, k: float) -> dict:
    """Multiply every metric coordinate by ``k`` (used when the scale changes)."""
    fd = json.loads(json.dumps(fd))
    fd["walkable"]["coordinates"] = _scale_pts(fd["walkable"]["coordinates"], k)
    for w in fd["walls"]:
        w["a"], w["b"] = _scale_pts(w["a"], k), _scale_pts(w["b"], k)
        w["thickness_m"] = round(w["thickness_m"] * k, 3)
    for d in fd["doors"]:
        d["a"], d["b"] = _scale_pts(d["a"], k), _scale_pts(d["b"], k)
    for r in fd["rooms"]:
        r["polygon"] = _scale_pts(r["polygon"], k)
    for n in fd["graph"]["nodes"]:
        n["x"], n["y"] = round(n["x"] * k, 3), round(n["y"] * k, 3)
    for e in fd["graph"]["edges"]:
        e["length_m"] = round(e["length_m"] * k, 3)
    b = fd["bounds_m"]
    for key in b:
        b[key] = round(b[key] * k, 3)
    return fd


def training_mask(lab3: np.ndarray, fd: dict) -> np.ndarray:
    """3-class editor mask + floor.json -> TURN learned classes (rooms vs walkable, doors, stairs)."""
    s = fd["transform"]["scale_m_per_px"]
    out = np.full(lab3.shape, BG, np.uint8)
    out[lab3 == M_FLOOR] = WALKABLE
    for r in fd["rooms"]:
        pts = (np.array(r["polygon"]) / s).round().astype(np.int32)
        cls = STAIRS if r.get("category") == "stairs_or_lift" else ROOM
        room = np.zeros(lab3.shape, np.uint8)
        cv2.fillPoly(room, [pts], 1)
        out[(room > 0) & (lab3 == M_FLOOR)] = cls
    out[lab3 == M_WALL] = WALL
    t = max(2, int(round(np.median([w["thickness_m"] for w in fd["walls"]] or [0.15]) / s)))
    for d in fd["doors"]:
        a = tuple(int(round(v / s)) for v in d["a"])
        b = tuple(int(round(v / s)) for v in d["b"])
        cv2.line(out, a, b, int(DOOR), t + 2)
    return out


def floor_geojson(fid: str, fd: dict) -> list[dict]:
    feats = []

    def feat(geom, **props):
        feats.append({"type": "Feature", "geometry": geom, "properties": {"floor": fid, **props}})

    feat({"type": "MultiPolygon", "coordinates": fd["walkable"]["coordinates"]}, layer="walkable")
    for w in fd["walls"]:
        feat(
            {"type": "LineString", "coordinates": [w["a"], w["b"]]},
            layer="wall",
            id=w["id"],
            thickness_m=w["thickness_m"],
        )
    for d in fd["doors"]:
        feat(
            {"type": "LineString", "coordinates": [d["a"], d["b"]]},
            layer="door",
            id=d["id"],
            room_id=d.get("room_id"),
        )
    for r in fd["rooms"]:
        feat(
            {"type": "Polygon", "coordinates": [r["polygon"]]},
            layer="room",
            id=r["id"],
            label=r.get("label"),
            name=r.get("name"),
            category=r.get("category"),
            source=r["provenance"]["source"],
        )
    nodes = {n["id"]: n for n in fd["graph"]["nodes"]}
    for n in nodes.values():
        feat({"type": "Point", "coordinates": [n["x"], n["y"]]}, layer="node", id=n["id"], kind=n["kind"])
    for e in fd["graph"]["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        feat(
            {"type": "LineString", "coordinates": [[a["x"], a["y"]], [b["x"], b["y"]]]},
            layer="edge",
            id=e["id"],
            length_m=e["length_m"],
        )
    for p in fd["pois"]:
        n = nodes[p["node_id"]]
        feat(
            {"type": "Point", "coordinates": [n["x"], n["y"]]},
            layer="poi",
            id=p["id"],
            name=p["name"],
            label=p.get("label"),
            category=p.get("category"),
        )
    return feats


def floor_svg(fd: dict, px_per_m: float = 20.0) -> str:
    b = fd["bounds_m"]
    W, H = b["max_x"] * px_per_m, b["max_y"] * px_per_m

    def pt(p):
        return f"{p[0] * px_per_m:.1f},{p[1] * px_per_m:.1f}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for poly in fd["walkable"]["coordinates"]:
        d = " ".join("M" + " L".join(pt(p) for p in ring) + " Z" for ring in poly)
        parts.append(f'<path d="{d}" fill="#dceefb" fill-rule="evenodd"/>')
    for r in fd["rooms"]:
        parts.append(
            f'<polygon points="{" ".join(pt(p) for p in r["polygon"])}" fill="#fff4d6" '
            'stroke="#c9a54a" stroke-width="1"/>'
        )
    for w in fd["walls"]:
        parts.append(
            f'<line x1="{w["a"][0] * px_per_m:.1f}" y1="{w["a"][1] * px_per_m:.1f}" '
            f'x2="{w["b"][0] * px_per_m:.1f}" y2="{w["b"][1] * px_per_m:.1f}" stroke="#333" '
            f'stroke-width="{max(1.5, w["thickness_m"] * px_per_m):.1f}"/>'
        )
    for d in fd["doors"]:
        parts.append(
            f'<line x1="{d["a"][0] * px_per_m:.1f}" y1="{d["a"][1] * px_per_m:.1f}" '
            f'x2="{d["b"][0] * px_per_m:.1f}" y2="{d["b"][1] * px_per_m:.1f}" stroke="#2e9d4f" '
            'stroke-width="3"/>'
        )
    nodes = {n["id"]: n for n in fd["graph"]["nodes"]}
    for e in fd["graph"]["edges"]:
        a, b2 = nodes[e["from"]], nodes[e["to"]]
        parts.append(
            f'<line x1="{a["x"] * px_per_m:.1f}" y1="{a["y"] * px_per_m:.1f}" x2="{b2["x"] * px_per_m:.1f}"'
            f' y2="{b2["y"] * px_per_m:.1f}" stroke="#d33" stroke-width="1.5"/>'
        )
    for p in fd["pois"]:
        n = nodes[p["node_id"]]
        label = (p.get("label") or p["name"] or "").replace("&", "&amp;").replace("<", "&lt;")
        parts.append(
            f'<text x="{n["x"] * px_per_m + 4:.1f}" y="{n["y"] * px_per_m - 4:.1f}" font-size="11" '
            f'fill="#1b3f8b">{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
