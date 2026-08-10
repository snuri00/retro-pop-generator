"""Retro Pop - Generator, a local web UI for resort illustration on SDXL."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import engine
from palettes import PALETTE_NAMES

HOST = os.environ.get("RETROPOP_HOST", "127.0.0.1")
PORT = int(os.environ.get("RETROPOP_PORT", "7801"))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
META = os.path.join(OUT, "gallery.json")
os.makedirs(OUT, exist_ok=True)

app = FastAPI(title="Retro Pop - Generator")

_jobs: dict[str, engine.Job] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_ready = {"value": False}


def _on_disk(entries: list[dict]) -> list[dict]:
    """Keep only entries whose image is still in out/, so files deleted by hand
    do not leave broken slots in the history strip."""
    kept = []
    for e in entries:
        name = e.get("file") or ""
        if name and os.path.exists(os.path.join(OUT, os.path.basename(name))):
            kept.append(e)
    return kept


def _save_gallery() -> None:
    json.dump(_gallery, open(META, "w"), indent=2, ensure_ascii=False)


_loaded: list[dict] = json.load(open(META)) if os.path.exists(META) else []
_gallery: list[dict] = _on_disk(_loaded)
if len(_gallery) != len(_loaded):
    _save_gallery()


class GenerateBody(BaseModel):
    prompt: str
    negative: str = engine.DEFAULT_NEGATIVE
    style: str = "ksenii"
    style_weight: float = 0.35
    steps: int = 24
    guidance: float = 6.0
    size: str = "square"
    seed: int = -1
    palette: str = "none"
    palette_strength: float = 0.7
    pixelate_to: int = 0
    pixel_colors: int = 24


def _worker() -> None:
    started = time.time()
    engine.warm()
    _ready["value"] = True
    print(f"  model ready in {time.time() - started:.0f}s\n", flush=True)
    while True:
        job_id = _queue.get()
        job = _jobs[job_id]
        job.status = "running"
        job.total = job.request.steps
        try:
            name, seed, took, w, h = engine.generate(
                job.request,
                OUT,
                on_step=lambda s, t: setattr(job, "step", s),
            )
            job.filename = name
            job.seconds = took
            job.status = "done"
            entry = {
                **job.request.__dict__,
                "file": name,
                "seconds": took,
                "width": w,
                "height": h,
                "seed": seed,
            }
            _gallery.insert(0, entry)
            del _gallery[200:]
            _save_gallery()
        except Exception as exc:
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            _queue.task_done()


@app.get("/api/config")
def config():
    return {
        "ready": _ready["value"],
        "styles": [
            {
                "id": k,
                "label": v["label"],
                "negative": v["negative"],
                "hasLora": bool(v["repo"]),
                "weight": v.get("weight", 0.35),
                "steps": v.get("steps", 24),
                "guidance": v.get("guidance", 6.0),
                "pixelateTo": v.get("pixelate_to", 0),
                "pixelColors": v.get("pixel_colors", 24),
                "palette": v.get("palette", "none"),
            }
            for k, v in engine.STYLES.items()
        ],
        "sizes": list(engine.SIZES),
        "palettes": ["none", *PALETTE_NAMES],
        "pixelSizes": [0, 48, 64, 96, 128, 192, 256],
        "defaultNegative": engine.DEFAULT_NEGATIVE,
        "queued": _queue.qsize(),
    }


@app.post("/api/generate")
def generate(body: GenerateBody):
    if body.style not in engine.STYLES:
        return JSONResponse({"error": "unknown style"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    req = engine.Request(**body.model_dump())
    _jobs[job_id] = engine.Job(id=job_id, request=req)
    _queue.put(job_id)
    return {"id": job_id, "position": _queue.qsize()}


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {
        "id": job.id,
        "status": job.status,
        "step": job.step,
        "total": job.total,
        "file": job.filename,
        "seconds": job.seconds,
        "error": job.error,
    }


@app.get("/api/gallery")
def gallery():
    global _gallery
    alive = _on_disk(_gallery)
    if len(alive) != len(_gallery):
        _gallery = alive
        _save_gallery()
    return _gallery[:60]


@app.get("/out/{name}")
def image(name: str):
    path = os.path.join(OUT, os.path.basename(name))
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True))

if __name__ == "__main__":
    url = f"http://{HOST}:{PORT}"
    print(f"\n  Retro Pop - Generator")
    print(f"  listening on {HOST}:{PORT}")
    print(f"  open  {url}\n")
    print("  loading SDXL, the page shows 'ready' when it can generate.")
    print("  the first run also downloads the model, about 7 GB.", flush=True)

    threading.Thread(target=_worker, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
