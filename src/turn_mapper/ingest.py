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


class PdfRasterPageAdapter:
    """Fallback for PDFs: render the whole page (vector or scanned) at 300 DPI."""

    name = "pdf_render"

    def can_handle(self, spec: FloorSpec) -> float:
        return 0.3 if spec.source_file.lower().endswith(".pdf") else 0.0

    def load(self, spec: FloorSpec) -> FloorImage:
        import pymupdf

        doc = pymupdf.open(spec.source_file)
        pix = doc[(spec.page or 1) - 1].get_pixmap(dpi=300)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        meta = {
            "adapter": self.name,
            "file": Path(spec.source_file).name,
            "sha256": sha256_file(spec.source_file),
            "page": spec.page,
            "dpi": 300,
        }
        return FloorImage(spec=spec, rgb=_apply_crop(rgb.copy(), spec), source_meta=meta)


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


ADAPTERS: list[Adapter] = [PdfEmbeddedImageAdapter(), PdfRasterPageAdapter(), ImageAdapter()]


def load_floor(spec: FloorSpec) -> FloorImage:
    best = max(ADAPTERS, key=lambda a: a.can_handle(spec))
    if best.can_handle(spec) <= 0:
        raise ValueError(f"no adapter can read {spec.source_file}")
    return best.load(spec)


def inspect_file(path: str) -> dict:
    """Describe a plan file so an operator can write a venue config."""
    p = Path(path)
    info: dict = {"file": p.name, "sha256": sha256_file(p), "pages": []}
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
