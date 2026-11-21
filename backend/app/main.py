"""FastAPI app: JSON API under /api and, if built, the React app at /.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError

from . import config
from .routers.api import router

app = FastAPI(title="Line Engineer Agent", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(OperationalError)
async def db_down(_: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={
        "detail": "The database is not reachable. Start PostgreSQL and check DATABASE_URL in the .env file."})


dist = config.FRONTEND_DIST
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = dist / path
        if path and candidate.is_file() and dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
