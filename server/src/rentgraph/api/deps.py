"""路由公共依赖：错误映射、工作台/房源/合同校验。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError, error_body, http_status
from ..models import Contract, House, Workspace


def http_error(exc: BaseException) -> HTTPException:
    return HTTPException(status_code=http_status(exc), detail={"error": error_body(exc)})


def raise_error(exc: BaseException) -> None:
    raise http_error(exc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def require_workspace(
    workspace_id: Annotated[str, Query(description="本次工作台 id")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise http_error(AppError("WORKSPACE_NOT_FOUND"))
    expires = _aware(workspace.expires_at)
    if expires is not None and expires < datetime.now(UTC):
        raise http_error(AppError("WORKSPACE_EXPIRED"))
    return workspace


async def load_workspace(db: AsyncSession, workspace_id: str | None) -> Workspace:
    if not workspace_id:
        raise http_error(AppError("WORKSPACE_NOT_FOUND", "缺少 workspace_id"))
    return await require_workspace(workspace_id, db)


async def load_house(db: AsyncSession, house_id: str | None) -> House:
    house = await db.get(House, house_id) if house_id else None
    if house is None:
        raise http_error(AppError("NOT_FOUND", "房源不存在或已被删除"))
    return house


async def load_contract(db: AsyncSession, contract_id: str | None) -> Contract:
    contract = await db.get(Contract, contract_id) if contract_id else None
    if contract is None:
        raise http_error(AppError("NOT_FOUND", "合同不存在或已被删除"))
    return contract
