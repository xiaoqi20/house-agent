"""房源承诺 × 合同条款核验（流程 B）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError
from ..models import Contract, House, Verification
from ..schemas.verification import VerificationCreate, VerificationOut
from ..services.flows import run_verification
from ..services.flows._common import create_run, launch
from .deps import http_error, load_workspace

router = APIRouter(prefix="/verifications", tags=["verifications"])


@router.post("", response_model=dict, status_code=202)
async def create_verification(
    payload: VerificationCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    await load_workspace(db, payload.workspace_id)
    house = await db.get(House, payload.house_id)
    contract = await db.get(Contract, payload.contract_id)
    if house is None or contract is None:
        raise http_error(AppError("CONTEXT_MISSING", "核验需要一套房源和一份合同"))
    contract.house_id = house.id
    house.contract_id = contract.id
    verification = Verification(
        workspace_id=payload.workspace_id,
        house_id=house.id,
        contract_id=contract.id,
        status="running",
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)

    run = await create_run(
        "verification",
        workspace_id=payload.workspace_id,
        house_id=house.id,
        contract_id=contract.id,
    )
    verification.run_id = run.id
    await db.commit()
    launch(run, lambda ctx: run_verification(ctx, verification.id))
    return {"verification_id": verification.id, "run_id": run.id}


@router.get("/{verification_id}", response_model=VerificationOut)
async def get_verification(
    verification_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> VerificationOut:
    from ..services.convert import verification_out

    verification = await db.get(Verification, verification_id)
    if verification is None:
        raise http_error(AppError("NOT_FOUND", "核验结果不存在"))
    await db.refresh(verification, attribute_names=["items"])
    return verification_out(verification)
