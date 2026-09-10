"""可解释推荐（流程 A 的收口）：三视图排序 + 理由/取舍/风险/待确认/下一步。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError
from ..models import RecommendationRun
from ..schemas.recommendation import RecommendationCreate, RecommendationCreated, RecommendationOut
from ..services.flows import run_recommendation
from ..services.flows._common import create_run, launch
from .deps import http_error, load_workspace

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationCreated, status_code=202)
async def create_recommendation(
    payload: RecommendationCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> RecommendationCreated:
    await load_workspace(db, payload.workspace_id)
    rec = RecommendationRun(workspace_id=payload.workspace_id, view=payload.view)
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    run = await create_run("recommend", workspace_id=payload.workspace_id)
    rec.run_id = run.id
    await db.commit()
    launch(run, lambda ctx: run_recommendation(ctx, rec.id))
    return RecommendationCreated(recommendation_id=rec.id, run_id=run.id)


@router.get("/{recommendation_id}", response_model=RecommendationOut)
async def get_recommendation(
    recommendation_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> RecommendationOut:
    rec = await db.get(RecommendationRun, recommendation_id)
    if rec is None:
        raise http_error(AppError("NOT_FOUND", "推荐结果不存在"))
    from ..services.flows.recommend_flow import _explanation_model, _view_model, build_about

    snapshot = rec.snapshot or {}
    about = build_about((snapshot.get("prefs") or {}), (snapshot.get("houses") or []))
    return RecommendationOut(
        id=rec.id,
        prefs_version=rec.prefs_version,
        view=rec.view,
        created_at=rec.created_at,
        snapshot=rec.snapshot or {},
        views={key: _view_model(value) for key, value in (rec.rankings or {}).items()},
        explanation=_explanation_model(rec.explanation or {}),
        about=about,
    )


@router.get("", response_model=list[RecommendationOut])
async def list_recommendations(
    workspace_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[RecommendationOut]:
    await load_workspace(db, workspace_id)
    rows = list(
        (
            await db.execute(
                select(RecommendationRun)
                .where(RecommendationRun.workspace_id == workspace_id)
                .order_by(RecommendationRun.created_at.desc())
                .limit(20)
            )
        ).scalars()
    )
    return [await get_recommendation(row.id, db) for row in rows]
