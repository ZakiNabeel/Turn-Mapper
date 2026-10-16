"""TURN Studio web server (local only). Start with ``turn-mapper studio``."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..export import png_bytes
from .project import Studio

STATIC = Path(__file__).parent / "static"


def _learned_available() -> tuple[bool, str]:
    if (
        importlib.util.find_spec("torch") is None
        or importlib.util.find_spec("segmentation_models_pytorch") is None
    ):
        return False, 'install the ML extra: pip install -e ".[ml]"'
    from ..learned.segmenter import weights_path

    p = weights_path()
    return (True, str(p)) if p.exists() else (False, f"no weights at {p} (set TURN_SEG_WEIGHTS)")


def create_app(root: str | Path) -> FastAPI:
    st = Studio(root)
    app = FastAPI(title="TURN Studio", version=__version__)

    def guard(fn, *a, **k):
        try:
            return fn(*a, **k)
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'")) from e
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/info")
    def info():
        ok, why = _learned_available()
        return {
            "version": __version__,
            "root": str(st.root.resolve()),
            "segmenters": {"classical": {"available": True}, "learned": {"available": ok, "detail": why}},
            "accept": ".pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,.dxf,.dwg,.svg",
        }

    @app.get("/api/projects")
    def projects():
        return st.list_projects()

    @app.post("/api/projects")
    def new_project(body: dict = Body(...)):
        return guard(st.create_project, body.get("name", "venue"))

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        return guard(st.project, pid)

    @app.post("/api/projects/{pid}/files")
    async def upload(pid: str, file: UploadFile = File(...)):
        data = await file.read()
        return guard(st.add_file, pid, file.filename or "plan", data)

    @app.get("/api/projects/{pid}/files/{name}")
    def inspect(pid: str, name: str):
        return guard(st.inspect, pid, name)

    @app.get("/api/projects/{pid}/files/{name}/thumb")
    def thumb(pid: str, name: str, page: int = 1, image_index: int | None = None, w: int = 360):
        return Response(guard(st.thumbnail, pid, name, page, image_index, w), media_type="image/png")

    @app.post("/api/projects/{pid}/floors")
    def add_floor(pid: str, body: dict = Body(...)):
        return guard(st.add_floor, pid, body)

    @app.get("/api/projects/{pid}/floors/{fid}")
    def get_floor(pid: str, fid: str):
        rec = guard(st.floor, pid, fid)
        return {"record": rec, "floor": st.floor_json(pid, fid)}

    @app.patch("/api/projects/{pid}/floors/{fid}")
    def patch_floor(pid: str, fid: str, body: dict = Body(...)):
        return guard(st.update_floor_meta, pid, fid, body)

    @app.delete("/api/projects/{pid}/floors/{fid}")
    def del_floor(pid: str, fid: str):
        guard(st.delete_floor, pid, fid)
        return {"ok": True}

    @app.post("/api/projects/{pid}/floors/{fid}/prepare")
    def prepare(pid: str, fid: str, body: dict = Body(...)):
        return guard(st.prepare, pid, fid, body.get("crop"), body.get("rotate"), body.get("options"))

    @app.get("/api/projects/{pid}/floors/{fid}/image/{kind}")
    def image(pid: str, fid: str, kind: str):
        if kind == "plan":
            data = guard(lambda: png_bytes(st.plan_rgb(pid, fid)))
        elif kind == "base":
            data = guard(lambda: (st.fdir(pid, fid) / "base.png").read_bytes())
        elif kind == "masks":
            data = guard(lambda: png_bytes(st.mask_rgb(pid, fid)))
        elif kind == "erase":
            p = st.fdir(pid, fid) / "erase.png"
            if not p.exists():
                return Response(status_code=204)
            data = p.read_bytes()
        else:
            raise HTTPException(404, kind)
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})

    def _png_from(body: dict) -> bytes:
        s = body.get("png", "")
        return base64.b64decode(s.split(",", 1)[1] if s.startswith("data:") else s)

    @app.put("/api/projects/{pid}/floors/{fid}/erase")
    def erase(pid: str, fid: str, body: dict = Body(...)):
        guard(st.save_erase, pid, fid, _png_from(body))
        return {"ok": True}

    @app.put("/api/projects/{pid}/floors/{fid}/masks")
    def masks(pid: str, fid: str, body: dict = Body(...)):
        guard(st.save_masks, pid, fid, _png_from(body))
        return {"ok": True}

    @app.post("/api/projects/{pid}/floors/{fid}/run")
    def run(pid: str, fid: str, body: dict = Body(default={})):
        return guard(st.run, pid, fid, body.get("segmenter"), bool(body.get("from_masks")))

    @app.put("/api/projects/{pid}/floors/{fid}/floor")
    def save_floor(pid: str, fid: str, body: dict = Body(...)):
        return guard(st.save_floor_json, pid, fid, body)

    @app.post("/api/projects/{pid}/floors/{fid}/scale")
    def scale(pid: str, fid: str, body: dict = Body(...)):
        return guard(st.set_scale, pid, fid, body.get("pairs", []))

    @app.post("/api/projects/{pid}/floors/{fid}/walkable")
    def walkable(pid: str, fid: str, body: dict = Body(...)):
        return guard(st.edit_walkable, pid, fid, body.get("polygon", []), body.get("op", "remove"))

    @app.post("/api/projects/{pid}/floors/{fid}/revert")
    def revert(pid: str, fid: str):
        return guard(st.revert, pid, fid)

    @app.get("/api/projects/{pid}/links")
    def links(pid: str):
        return guard(st.links, pid)

    @app.put("/api/projects/{pid}/links")
    def set_links(pid: str, body: dict = Body(...)):
        return guard(st.set_manual_links, pid, body.get("manual", []))

    @app.get("/api/projects/{pid}/export/{fmt}")
    def export(pid: str, fmt: str, include_failed: bool = False):
        data, name, mime = guard(st.export, pid, fmt, include_failed)
        return Response(
            data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'}
        )

    @app.exception_handler(Exception)
    async def crash(_req, exc):  # show the reason in the UI instead of a bare 500
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve(root: str, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    url = f"http://{host}:{port}"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"TURN Studio {__version__} at {url}  (projects in {Path(root).resolve()}; Ctrl+C to stop)")
    uvicorn.run(create_app(root), host=host, port=port, log_level="warning")
