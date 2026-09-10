"""合同：粘贴 / 上传 → 解析 → 条款抽取 + 风险规则（流程 B 的输入）。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Clause, Contract, uid
from ..schemas.contract import ContractCreate, ContractOut, ContractTextView
from ..services.convert import clause_view, contract_out
from ..services.flows import run_contract_analysis
from ..services.flows._common import create_run, launch
from ..services.storage import storage
from .deps import http_error, load_contract, load_workspace

router = APIRouter(prefix="/contracts", tags=["contracts"])

MIN_TEXT_CHARS = 200
DOC_EXTS = {".pdf", ".txt", ".docx", ".md", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


async def _next_no(db: AsyncSession, workspace_id: str) -> str:
    count = (
        await db.execute(select(func.count()).select_from(Contract).where(Contract.workspace_id == workspace_id))
    ).scalar_one()
    return f"C{count + 1}"


async def _start_analysis(db: AsyncSession, contract: Contract) -> str:
    run = await create_run(
        "contract",
        workspace_id=contract.workspace_id,
        thread_id=contract.id,
        house_id=contract.house_id,
        contract_id=contract.id,
    )
    contract.status = "parsing"
    await db.commit()
    launch(run, lambda ctx: run_contract_analysis(ctx, contract.id))
    return run.id


@router.post("", response_model=dict, status_code=202)
async def create_contract(
    payload: ContractCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    workspace = await load_workspace(db, payload.workspace_id)
    text = (payload.text or "").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise http_error(
            AppError("TEXT_TOO_SHORT", f"合同文本仅 {len(text)} 字，少于 {MIN_TEXT_CHARS} 字", "请粘贴完整合同正文")
        )
    contract = Contract(
        id=uid(),
        workspace_id=workspace.id,
        house_id=payload.house_id,
        no=await _next_no(db, workspace.id),
        name=payload.name or "粘贴的合同文本",
        filename=None,
        source_type="paste",
        size_label=f"{len(text)} 字",
        raw_text=text,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    run_id = await _start_analysis(db, contract)
    return {"contract_id": contract.id, "run_id": run_id}


@router.post("/upload", response_model=dict, status_code=202)
async def upload_contract(
    workspace_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    house_id: Annotated[str | None, Form()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> dict:
    workspace = await load_workspace(db, workspace_id)
    filename = file.filename or "contract.pdf"
    ext = Path(filename).suffix.lower()
    if ext not in DOC_EXTS | IMAGE_EXTS:
        raise http_error(
            AppError(
                "UNSUPPORTED_FORMAT",
                f"暂不支持 {ext or '该'} 格式",
                "支持 PDF / Word(.docx) / 文本 / 图片（图片仅存档，暂不做 OCR）",
            )
        )
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise http_error(AppError("INVALID_STATE", f"文件超过 {settings.max_upload_mb}MB 上限"))
    source_type = "image" if ext in IMAGE_EXTS else ext.lstrip(".")
    key = storage.save(filename, data)
    contract = Contract(
        id=uid(),
        workspace_id=workspace.id,
        house_id=house_id,
        no=await _next_no(db, workspace.id),
        name=filename,
        filename=filename,
        source_type=source_type,
        size_label=_size_label(len(data)),
        storage_key=key,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    run_id = await _start_analysis(db, contract)
    return {"contract_id": contract.id, "run_id": run_id}


@router.get("", response_model=list[ContractOut])
async def list_contracts(workspace_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> list[ContractOut]:
    await load_workspace(db, workspace_id)
    rows = list(
        (
            await db.execute(
                select(Contract).where(Contract.workspace_id == workspace_id).order_by(Contract.created_at.desc())
            )
        ).scalars()
    )
    out: list[ContractOut] = []
    for row in rows:
        await db.refresh(row, attribute_names=["clauses"])
        out.append(contract_out(row))
    return out


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(contract_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> ContractOut:
    contract = await load_contract(db, contract_id)
    await db.refresh(contract, attribute_names=["clauses", "risks"])
    return contract_out(contract)


@router.get("/{contract_id}/text", response_model=ContractTextView)
async def contract_text(contract_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> ContractTextView:
    contract = await load_contract(db, contract_id)
    rows = list(
        (
            await db.execute(select(Clause).where(Clause.contract_id == contract.id).order_by(Clause.clause_no))
        ).scalars()
    )
    for row in rows:
        await db.refresh(row, attribute_names=["risks"])
    return ContractTextView(
        contract_id=contract.id,
        filename=contract.filename,
        clauses=[clause_view(row) for row in rows],
    )


@router.get("/{contract_id}/file")
async def contract_file(contract_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> FileResponse:
    contract = await load_contract(db, contract_id)
    if not contract.storage_key:
        raise http_error(AppError("NOT_FOUND", "该合同是粘贴文本，没有原始文件"))
    path = storage.local_path(contract.storage_key)
    if path is None:
        raise http_error(AppError("NOT_FOUND", "原始文件已被清理"))
    return FileResponse(path, filename=contract.filename or path.name)


@router.post("/{contract_id}/retry", response_model=dict, status_code=202)
async def retry_contract(contract_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    contract = await load_contract(db, contract_id)
    if contract.source_type in IMAGE_EXTS or contract.source_type == "image":
        raise http_error(AppError("OCR_UNSUPPORTED", "图片/扫描件暂不支持 OCR", "请粘贴合同文本或上传文字版 PDF"))
    run_id = await _start_analysis(db, contract)
    return {"contract_id": contract.id, "run_id": run_id}


@router.delete("/{contract_id}", status_code=204)
async def delete_contract(contract_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    contract = await load_contract(db, contract_id)
    await db.delete(contract)
    await db.commit()
