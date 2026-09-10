"""本次候选房源 CRUD（3—10 套比较范围，PRD §7.1.1）。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..errors import AppError
from ..models import House, HouseEvidence, uid
from ..schemas.house import HouseCreate, HouseOut, HousePatch
from ..services.convert import house_out
from .deps import http_error, load_house, load_workspace

router = APIRouter(prefix="/houses", tags=["houses"])


async def _next_no(db: AsyncSession, workspace_id: str) -> str:
    count = (
        await db.execute(select(func.count()).select_from(House).where(House.workspace_id == workspace_id))
    ).scalar_one()
    return f"H{count + 1}"


@router.get("", response_model=list[HouseOut])
async def list_houses(
    workspace_id: Annotated[str, Query()],
    status: Annotated[Literal["active", "dropped", "all"], Query()] = "active",
    q: Annotated[str | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> list[HouseOut]:
    await load_workspace(db, workspace_id)
    stmt = (
        select(House)
        .where(House.workspace_id == workspace_id)
        .options(selectinload(House.evidence))
        .order_by(House.no)
    )
    if status != "all":
        stmt = stmt.where(House.status == status)
    houses = list((await db.execute(stmt)).scalars())
    if q:
        needle = q.strip().lower()
        houses = [
            house
            for house in houses
            if needle in " ".join(
                [house.name or "", house.region or "", house.address or "", house.layout or "", house.metro or ""]
            ).lower()
        ]
    return [house_out(house) for house in houses]


@router.post("", response_model=HouseOut, status_code=201)
async def create_house(
    payload: HouseCreate, workspace_id: Annotated[str, Query()], db: Annotated[AsyncSession, Depends(get_db)]
) -> HouseOut:
    await load_workspace(db, workspace_id)
    house = House(
        id=uid(),
        workspace_id=workspace_id,
        no=await _next_no(db, workspace_id),
        status="active",
        **payload.model_dump(),
    )
    db.add(house)
    await db.commit()
    await db.refresh(house, attribute_names=["evidence"])
    return house_out(house)


@router.get("/{house_id}", response_model=HouseOut)
async def get_house(house_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> HouseOut:
    house = await load_house(db, house_id)
    await db.refresh(house, attribute_names=["evidence"])
    return house_out(house)


@router.patch("/{house_id}", response_model=HouseOut)
async def patch_house(
    house_id: str, payload: HousePatch, db: Annotated[AsyncSession, Depends(get_db)]
) -> HouseOut:
    house = await load_house(db, house_id)
    changes = payload.model_dump(exclude_unset=True)
    if house.status == "dropped" and changes.get("status") == "active":
        changes["drop_reason"] = ""
    for key, value in changes.items():
        setattr(house, key, value)
    if changes.get("status") == "dropped" and not house.drop_reason:
        house.drop_reason = "用户标记放弃"
    await db.commit()
    await db.refresh(house, attribute_names=["evidence"])
    return house_out(house)


@router.delete("/{house_id}", status_code=204)
async def delete_house(house_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    house = await load_house(db, house_id)
    await db.delete(house)
    await db.commit()


@router.post("/{house_id}/evidence", response_model=HouseOut)
async def add_evidence(
    house_id: str,
    field: str,
    snippet: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HouseOut:
    """补充字段证据（用户手动修正字段后可记录来源，保证可追溯）。"""

    house = await load_house(db, house_id)
    if not field or not snippet:
        raise http_error(AppError("INVALID_STATE", "证据需要字段名与原文片段"))
    db.add(HouseEvidence(house_id=house.id, field=field, snippet=snippet, source=house.source))
    await db.commit()
    await db.refresh(house, attribute_names=["evidence"])
    return house_out(house)
