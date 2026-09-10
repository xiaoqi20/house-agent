"""RentGraph API 装配（模块化单体，路由分组见 doc/plan/后端-v1.1-接口契约.md §4）。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import (
    contracts,
    conversations,
    health,
    houses,
    import_batches,
    preferences,
    recommendations,
    runs,
    verifications,
    workspaces,
)
from .config import settings
from .db import Base, engine
from .errors import AppError, error_body, http_status

logger = structlog.get_logger()
SERVER_DIR = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (SERVER_DIR / "openapi.json").write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    yield


app = FastAPI(title="RentGraph API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(status_code=exc.status, content={"error": error_body(exc)})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ARG001
    """统一错误体：{error:{code,message,hint}}，与契约 §2 一致。"""

    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(detail), "hint": ""}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    logger.error("unhandled_error", error=type(exc).__name__, message=str(exc)[:300])
    return JSONResponse(status_code=http_status(exc), content={"error": error_body(exc)})


app.include_router(health.router)
for router in (
    workspaces.router,
    import_batches.router,
    houses.router,
    preferences.router,
    recommendations.router,
    contracts.router,
    verifications.router,
    conversations.router,
    runs.router,
):
    app.include_router(router, prefix="/api/v1")
