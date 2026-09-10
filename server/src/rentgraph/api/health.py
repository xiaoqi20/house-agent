"""健康检查：DB 与模型提供方状态（前端用于判断"服务异常"）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    db_ok = True
    db_error = ""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 健康检查必须返回而不是抛错
        db_ok = False
        db_error = type(exc).__name__
    return {
        "ok": db_ok,
        "db": "ok" if db_ok else f"error:{db_error}",
        "llm_provider": settings.llm_provider,
        "version": "1.1.0",
    }
