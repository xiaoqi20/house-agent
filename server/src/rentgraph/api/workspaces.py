"""工作台：一期临时数据边界（PRD §1.3）。"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..models import Contract, House, Preference, Workspace, uid, utcnow
from ..schemas.workspace import CtxUpdate, WorkspaceOut

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _out(workspace: Workspace, house_count: int, contract_count: int) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        title=workspace.title,
        created_at=workspace.created_at,
        expires_at=workspace.expires_at,
        house_count=house_count,
        contract_count=contract_count,
        ctx_house_id=workspace.ctx_house_id,
        ctx_contract_id=workspace.ctx_contract_id,
    )


async def _counts(db: AsyncSession, workspace_id: str) -> tuple[int, int]:
    houses = (
        await db.execute(
            select(func.count()).select_from(House).where(House.workspace_id == workspace_id, House.status == "active")
        )
    ).scalar_one()
    contracts = (
        await db.execute(select(func.count()).select_from(Contract).where(Contract.workspace_id == workspace_id))
    ).scalar_one()
    return houses, contracts


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(db: Annotated[AsyncSession, Depends(get_db)]) -> WorkspaceOut:
    workspace = Workspace(id=uid(), expires_at=utcnow() + timedelta(hours=settings.workspace_ttl_hours))
    db.add(workspace)
    db.add(
        Preference(
            workspace_id=workspace.id,
            version=1,
            budget=None,
            commute=None,
            need_bathroom=False,
            allow_shared=True,
            soft={},
        )
    )
    await db.commit()
    await db.refresh(workspace)
    return _out(workspace, 0, 0)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> WorkspaceOut:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        from ..errors import AppError
        from .deps import http_error

        raise http_error(AppError("WORKSPACE_NOT_FOUND"))
    houses, contracts = await _counts(db, workspace_id)
    return _out(workspace, houses, contracts)


@router.put("/{workspace_id}/ctx", response_model=WorkspaceOut)
async def set_context(
    workspace_id: str, payload: CtxUpdate, db: Annotated[AsyncSession, Depends(get_db)]
) -> WorkspaceOut:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        from ..errors import AppError
        from .deps import http_error

        raise http_error(AppError("WORKSPACE_NOT_FOUND"))
    workspace.ctx_house_id = payload.house_id
    workspace.ctx_contract_id = payload.contract_id
    await db.commit()
    await db.refresh(workspace)
    houses, contracts = await _counts(db, workspace_id)
    return _out(workspace, houses, contracts)
