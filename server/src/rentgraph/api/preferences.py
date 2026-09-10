"""偏好：硬约束（淘汰）与软偏好（排序）分开保存并版本化（PRD §7.1）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError
from ..models import Preference
from ..schemas.preference import PreferenceIn, PreferenceOut
from ..services.flows.recommend_flow import load_prefs
from .deps import http_error, load_workspace

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferenceOut)
async def get_preferences(
    workspace_id: Annotated[str, Query()], db: Annotated[AsyncSession, Depends(get_db)]
) -> PreferenceOut:
    await load_workspace(db, workspace_id)
    return PreferenceOut(**await load_prefs(db, workspace_id))


@router.put("", response_model=PreferenceOut)
async def put_preferences(
    payload: PreferenceIn,
    workspace_id: Annotated[str, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PreferenceOut:
    await load_workspace(db, workspace_id)
    if payload.budget is not None and payload.budget < 0:
        raise http_error(AppError("INVALID_PREFERENCE"))
    if payload.commute is not None and payload.commute < 0:
        raise http_error(AppError("INVALID_PREFERENCE"))
    latest = (
        await db.execute(
            select(Preference).where(Preference.workspace_id == workspace_id).order_by(Preference.version.desc())
        )
    ).scalars().first()
    version = (latest.version if latest else 0) + 1
    row = Preference(
        workspace_id=workspace_id,
        version=version,
        budget=payload.budget,
        commute=payload.commute,
        need_bathroom=payload.need_bathroom,
        allow_shared=payload.allow_shared,
        soft=payload.soft.model_dump(),
    )
    db.add(row)
    await db.commit()
    return PreferenceOut(**await load_prefs(db, workspace_id))
