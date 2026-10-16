"""Input adapters (ADR-010). Each adapter turns a file (+page/image index) into a FloorImage.

Adapters register in ``ADAPTERS`` and are chosen by ``can_handle`` score, so new formats
(DXF, vector PDF, photos) are added without touching the rest of the pipeline.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .ir import FloorImage, FloorSpec


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Adapter(Protocol):
    name: str

    def can_handle(self, spec: FloorSpec) -> float: ...

    def load(self, spec: FloorSpec) -> FloorImage: ...


def _decode(buf: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("could not decode image")
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def _apply_crop(rgb: np.ndarray, spec: FloorSpec) -> np.ndarray:
    if spec.crop:
        x0, y0, x1, y1 = spec.crop
        rgb = rgb[y0:y1, x0:x1]
    return np.ascontiguousarray(rgb)


def pdf_page_images(doc, page_no: int) -> list[dict]:
    """Embedded images on a page, sorted top-to-bottom by their placement on the page."""
    page = doc[page_no - 1]
    out = []
    for info in page.get_images(full=True):
        xref = info[0]
        rects = page.get_image_rects(xref)
        y = rects[0].y0 if rects else 0.0
        out.append({"xref": xref, "width": info[2], "height": info[3], "y": y})
    out.sort(key=lambda d: d["y"])
    return out


class PdfEmbeddedImageAdapter:
    """Raster PDFs (e.g. Word exports of screenshots): take embedded images at native resolution."""

    name = "pdf_embedded_image"

    def can_handle(self, spec: FloorSpec) -> float:
        if not spec.source_file.lower().endswith(".pdf"):
            return 0.0
        return 0.9 if spec.image_index is not None else 0.4

    def load(self, spec: FloorSpec) -> FloorImage:
        import pymupdf

        doc = pymupdf.open(spec.source_file)
        if spec.page is None:
            raise ValueError(f"floor {spec.id}: page is required for PDF input")
        imgs = pdf_page_images(doc, spec.page)
        if not imgs:
            raise ValueError(f"floor {spec.id}: page {spec.page} has no embedded images")
        idx = spec.image_index or 0
        if idx >= len(imgs):
            raise ValueError(f"floor {spec.id}: page {spec.page} has only {len(imgs)} images")
        x = doc.extract_image(imgs[idx]["xref"])
        rgb = _apply_crop(_decode(x["image"]), spec)
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
            "page": spec.page,
            "image_index": idx,
            "native_ext": x["ext"],
        }
        return FloorImage(spec=spec, rgb=rgb, source_meta=meta)


PT_M = 0.0254 / 72  # one PDF point in metres (on paper)


def thicken_lines(rgb: np.ndarray, line_px: int = 2) -> np.ndarray:
    """Hairlines in vector drawings render faint and 1 px wide; the raster stages expect strokes of a few
    pixels. Darken anything drawn and grow it to about ``line_px``."""
    g = rgb.min(axis=2)
    ink = (g < 235).astype(np.uint8)
    if line_px > 1:
        ink = cv2.dilate(ink, np.ones((line_px, line_px), np.uint8))
    out = rgb.copy()
    out[ink > 0] = np.minimum(out[ink > 0], 60)
    return out


class PdfRasterPageAdapter:
    """PDF pages drawn as vectors (CAD exports) or scanned: render the page.

    Preferred over the embedded-image adapter when the page is mostly vector drawing. ``options``:
    ``dpi`` (default 300) and ``drawing_scale`` N for a 1:N drawing, which turns paper units into a measured
    scale (``cad_units``)."""

    name = "pdf_render"

    def can_handle(self, spec: FloorSpec) -> float:
        if not spec.source_file.lower().endswith(".pdf"):
            return 0.0
        if spec.image_index is not None:
            return 0.3
        try:
            import pymupdf

            page = pymupdf.open(spec.source_file)[(spec.page or 1) - 1]
            vec = len(page.get_drawings())
            return 0.6 if vec > 50 or not page.get_images() else 0.3
        except Exception:
            return 0.3

    def load(self, spec: FloorSpec) -> FloorImage:
        import pymupdf

        doc = pymupdf.open(spec.source_file)
        ratio = spec.options.get("drawing_scale")
        # with a known drawing scale, render at about 2.5 cm per pixel (what the raster stages are tuned for)
        default_dpi = int(round(0.0254 * float(ratio) / 0.025)) if ratio else 300
        dpi = int(spec.options.get("dpi", default_dpi))
        page = doc[(spec.page or 1) - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
        vector = not page.get_images()
        if vector and spec.options.get("thicken", True):
            rgb = thicken_lines(rgb, int(spec.options.get("line_px", 2)))
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
            "page": spec.page,
            "dpi": dpi,
            "vector_only": vector,
            "vector_drawings": len(page.get_drawings()),
            "paper_m_per_px": PT_M * 72 / dpi,
        }
        if ratio:
            meta["cad_m_per_px"] = PT_M * 72 / dpi * float(ratio)
            meta["units"] = f"paper 1:{ratio}"
        return FloorImage(spec=spec, rgb=_apply_crop(rgb.copy(), spec), source_meta=meta)


class SvgAdapter:
    """SVG drawings, rendered with PyMuPDF.

    ``options``: ``dpi`` (default 150), ``drawing_scale`` (1:N; one SVG user unit = 1 CSS px = 1/96 inch)."""

    name = "svg"

    def can_handle(self, spec: FloorSpec) -> float:
        return 0.9 if spec.source_file.lower().endswith(".svg") else 0.0

    def load(self, spec: FloorSpec) -> FloorImage:
        import pymupdf

        doc = pymupdf.open(spec.source_file)
        dpi = int(spec.options.get("dpi", 150))
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
            "dpi": dpi,
        }
        ratio = spec.options.get("drawing_scale")
        if ratio:
            meta["cad_m_per_px"] = 0.0254 / dpi * float(ratio)
            meta["units"] = f"svg 1:{ratio}"
        return FloorImage(spec=spec, rgb=_apply_crop(rgb.copy(), spec), source_meta=meta)


# DXF $INSUNITS code -> metres per drawing unit
DXF_UNITS = {1: ("in", 0.0254), 2: ("ft", 0.3048), 4: ("mm", 0.001), 5: ("cm", 0.01), 6: ("m", 1.0)}
DXF_SKIP_LAYERS = ("DIM", "ANNO", "DEFPOINTS", "FURN", "GRID", "TITLE", "VIEWPORT", "XREF")


class DxfAdapter:
    """AutoCAD DXF. Draws model space (selected layers) in black on white with ezdxf and reports the exact
    metres per pixel from the drawing units, so CAD floors get a measured scale without a site visit.

    ``options``: ``m_per_px`` raster resolution (default 0.02) or ``target_px`` long side; ``line_px``
    (default 2); ``layers_exclude`` / ``layers_include`` (names or prefixes, case-insensitive); ``units`` to
    override a missing or wrong $INSUNITS ("mm", "cm", "m", "in", "ft")."""

    name = "dxf"

    def can_handle(self, spec: FloorSpec) -> float:
        return 0.9 if spec.source_file.lower().endswith(".dxf") else 0.0

    @staticmethod
    def layers(path: str) -> list[dict]:
        import ezdxf

        doc = ezdxf.readfile(path)
        counts: dict[str, int] = {}
        for e in doc.modelspace():
            counts[e.dxf.layer] = counts.get(e.dxf.layer, 0) + 1
        return [
            {"name": k, "entities": v, "default_on": not _skip_layer(k)} for k, v in sorted(counts.items())
        ]

    def load(self, spec: FloorSpec) -> FloorImage:
        import ezdxf
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from ezdxf import bbox
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

        doc = ezdxf.readfile(spec.source_file)
        msp = doc.modelspace()
        opt = spec.options
        inc = [x.upper() for x in opt.get("layers_include", [])]
        exc = [x.upper() for x in opt.get("layers_exclude", [])]

        def keep(e) -> bool:
            name = e.dxf.layer.upper()
            if inc:
                return any(name.startswith(x) for x in inc)
            if exc:
                return not any(name.startswith(x) for x in exc)
            return not _skip_layer(name) and e.dxftype() not in ("DIMENSION", "VIEWPORT")

        ents = [e for e in msp if keep(e)]
        ext = bbox.extents(ents, fast=True)
        if not ext.has_data:
            raise ValueError(f"floor {spec.id}: no drawable entities in the selected DXF layers")
        (x0, y0, _), (x1, y1, _) = ext.extmin, ext.extmax
        pad = 0.02 * max(x1 - x0, y1 - y0)
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        code = doc.header.get("$INSUNITS", 0)
        unit_name, unit_m = DXF_UNITS.get(code, (None, None))
        if opt.get("units"):
            unit_name = opt["units"]
            unit_m = {v[0]: v[1] for v in DXF_UNITS.values()}[unit_name]
        span = max(x1 - x0, y1 - y0)
        if "target_px" in opt:
            px_per_unit = int(opt["target_px"]) / span
        elif unit_m:
            # raster stages are tuned for ~2-4 cm/px: aim for 2 cm, keep the image 800-6000 px
            px_per_unit = min(max(unit_m / float(opt.get("m_per_px", 0.02)), 800 / span), 6000 / span)
        else:
            px_per_unit = 3000 / span
        w, h = int(round((x1 - x0) * px_per_unit)), int(round((y1 - y0) * px_per_unit))
        dpi = 100
        fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_axis_off()
        cfg = Configuration(
            color_policy=ColorPolicy.BLACK,
            background_policy=BackgroundPolicy.WHITE,
            min_lineweight=float(opt.get("line_px", 2.0)) / dpi * 300,  # ezdxf unit: 1/300 inch
        )
        Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_entities(ents)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("auto")
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
        plt.close(fig)
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
            "entities": len(ents),
            "extents": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
            "px_per_unit": px_per_unit,
            "insunits": code,
        }
        if unit_m:
            meta["cad_m_per_px"] = unit_m / px_per_unit
            meta["units"] = unit_name
        else:
            meta["units_warning"] = "DXF has no drawing units ($INSUNITS); set options.units to get a scale"
        return FloorImage(spec=spec, rgb=_apply_crop(buf, spec), source_meta=meta)


def _skip_layer(name: str) -> bool:
    n = name.upper()
    return any(k in n for k in DXF_SKIP_LAYERS) or "TEXT" in n and "CONTEXT" not in n


class ImageAdapter:
    name = "image"

    def can_handle(self, spec: FloorSpec) -> float:
        return (
            0.9
            if Path(spec.source_file).suffix.lower()
            in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
            else 0.0
        )

    def load(self, spec: FloorSpec) -> FloorImage:
        rgb = _apply_crop(_decode(Path(spec.source_file).read_bytes()), spec)
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
        }
        return FloorImage(spec=spec, rgb=rgb, source_meta=meta)


ADAPTERS: list[Adapter] = [
    PdfEmbeddedImageAdapter(),
    PdfRasterPageAdapter(),
    ImageAdapter(),
    SvgAdapter(),
    DxfAdapter(),
]


def find_dwg_converter() -> list[str] | None:
    """Command prefix of a DWG->DXF converter, or None. Env ``TURN_DWG_CONVERTER`` overrides the search.
    Supported: ODA File Converter (``ODAFileConverter``) and libredwg (``dwg2dxf``)."""
    import os
    import shutil

    cand = [os.environ.get("TURN_DWG_CONVERTER") or "", "ODAFileConverter", "dwg2dxf"]
    for c in cand:
        exe = shutil.which(c) if c else None
        if exe:
            return [exe]
    return None


def dwg_to_dxf(path: str | Path, out_dir: str | Path) -> Path:
    """Convert a DWG to DXF with an installed converter; clear error when none is available."""
    import subprocess
    import tempfile

    src, out = Path(path), Path(out_dir)
    conv = find_dwg_converter()
    if conv is None:
        raise ValueError(
            "DWG is a closed format and no converter was found. Install the free ODA File Converter "
            "(or libredwg's dwg2dxf) and restart, or 'Save As DXF' in AutoCAD/LibreCAD, then load the DXF"
        )
    out.mkdir(parents=True, exist_ok=True)
    dest = out / (src.stem + ".dxf")
    if Path(conv[0]).name.lower().startswith("dwg2dxf"):
        cmd = [*conv, "-y", "-o", str(dest), str(src)]
    else:  # ODAFileConverter works on folders: in, out, version, type, recurse, audit
        tmp = Path(tempfile.mkdtemp())
        (tmp / src.name).write_bytes(src.read_bytes())
        cmd = [*conv, str(tmp), str(out), "ACAD2018", "DXF", "0", "1"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not dest.exists():
        raise ValueError(f"DWG conversion failed: {(r.stderr or r.stdout).strip()[:300]}")
    return dest


def load_floor(spec: FloorSpec) -> FloorImage:
    best = max(ADAPTERS, key=lambda a: a.can_handle(spec))
    if best.can_handle(spec) <= 0:
        raise ValueError(f"no adapter can read {spec.source_file}")
    return best.load(spec)


def inspect_file(path: str) -> dict:
    """Describe a plan file so an operator can write a venue config."""
    p = Path(path)
    info: dict = {"file": p.name, "sha256": sha256_file(p), "pages": []}
    if p.suffix.lower() == ".dxf":
        info["kind"] = "dxf"
        info["layers"] = DxfAdapter.layers(str(p))
        info["pages"].append({"page": 1, "images": [], "branch": "cad"})
        return info
    if p.suffix.lower() == ".svg":
        info["kind"] = "svg"
        info["pages"].append({"page": 1, "images": [], "branch": "vector"})
        return info
    if p.suffix.lower() == ".dwg":
        raise ValueError("DWG must be converted to DXF first (Studio does this if a converter exists)")
    if p.suffix.lower() != ".pdf":
        rgb = _decode(p.read_bytes())
        info["kind"] = "image"
        info["pages"].append(
            {"page": 1, "images": [{"index": 0, "width": rgb.shape[1], "height": rgb.shape[0]}]}
        )
        return info
    import pymupdf

    doc = pymupdf.open(p)
    info["kind"] = "pdf"
    info["metadata"] = {k: v for k, v in (doc.metadata or {}).items() if v}
    for i, page in enumerate(doc, start=1):
        imgs = pdf_page_images(doc, i)
        text = " ".join(page.get_text().split())
        info["pages"].append(
            {
                "page": i,
                "vector_drawings": len(page.get_drawings()),
                "images": [
                    {"index": k, "width": d["width"], "height": d["height"]} for k, d in enumerate(imgs)
                ],
                "text": text[:300],
                "branch": "vector" if len(page.get_drawings()) > 50 else ("raster" if imgs else "empty"),
            }
        )
    return info
