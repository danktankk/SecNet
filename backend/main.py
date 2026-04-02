from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers.api import router as api_router
from routers.ws import router as ws_router
from db import init_db
from services.discovery import run_discovery
import os
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        run_discovery()
    except Exception:
        logger.exception("Discovery failed — continuing with existing hosts")
    yield


app = FastAPI(title="Security Posture Dashboard", version="1.0.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        resp = FileResponse(os.path.join(static_dir, "index.html"))
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
