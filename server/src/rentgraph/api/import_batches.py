"""房源导入：粘贴 / 批量 / 手动 / 文件上传 → 字段确认 → 加入候选（流程 A）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import ImportBatch, uid
from ..schemas.house import BatchConfirm, BatchConfirmOut, BatchCreate, BatchOut
from ..services import engine
from ..services.flows import confirm_import, run_import_batch
from ..services.flows._common import create_run, launch
from ..services.storage import storage
from .deps import http_error, load_workspace

router = APIRouter(prefix="/import-batches", tags=["imports"])


async def _payload(db: AsyncSession, batch: ImportBatch, run_id: str | None = None) -> BatchOut:
    from ..services.flows.import_flow import batch_payload

    return BatchOut(**await batch_payload(db, batch, run_id=run_id))


@router.post("", response_model=BatchOut, status_code=202)
async def create_batch(
    payload: BatchCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> BatchOut:
    await load_workspace(db, payload.workspace_id)
    text = (payload.text or "").strip()
    if payload.source != "link" and not text:
        raise http_error(AppError("EMPTY_DOCUMENT", "没有收到任何房源文本", "请粘贴房源描述后再解析"))
    if text and len(text) > 200_000:
        raise http_error(AppError("INVALID_STATE", "文本过长（上限 20 万字符）", "请分批导入"))

    batch = ImportBatch(
        id=uid(),
        workspace_id=payload.workspace_id,
        source=payload.source,
        raw_text=text,
        link_url=payload.link_url,
        status="parsing",
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    run = await create_run("import", workspace_id=payload.workspace_id)
    launch(run, lambda ctx: run_import_batch(ctx, batch.id))
    out = await _payload(db, batch, run.id)
    return out


@router.post("/upload", response_model=BatchOut, status_code=202)
async def upload_batch(
    workspace_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchOut:
    await load_workspace(db, workspace_id)
    filename = file.filename or "batch.txt"
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise http_error(AppError("INVALID_STATE", f"文件超过 {settings.max_upload_mb}MB 上限"))

    suffix = engine.SUPPORTED_EXTENSIONS
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    if ext not in suffix:
        raise http_error(
            AppError(
                "UNSUPPORTED_FORMAT",
                f"暂不支持 {ext or '该'} 格式的房源文件",
                "支持 .txt / .csv / .md / .xlsx / .xls / .docx",
            )
        )
    source = {
        ".xlsx": "file-xlsx",
        ".xls": "file-xlsx",
        ".docx": "file-docx",
    }.get(ext, "file-txt")
    key = storage.save(filename, data)
    batch = ImportBatch(
        id=uid(),
        workspace_id=workspace_id,
        source=source,
        filename=filename,
        storage_key=key,
        status="parsing",
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    run = await create_run("import", workspace_id=workspace_id)
    launch(run, lambda ctx: run_import_batch(ctx, batch.id))
    return await _payload(db, batch, run.id)


@router.get("/{batch_id}", response_model=BatchOut)
async def get_batch(batch_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> BatchOut:
    batch = await db.get(ImportBatch, batch_id)
    if batch is None:
        raise http_error(AppError("NOT_FOUND", "导入批次不存在"))
    return await _payload(db, batch)


@router.post("/{batch_id}/confirm", response_model=BatchConfirmOut)
async def confirm_batch(
    batch_id: str, payload: BatchConfirm, db: Annotated[AsyncSession, Depends(get_db)]
) -> BatchConfirmOut:
    batch = await db.get(ImportBatch, batch_id)
    if batch is None:
        raise http_error(AppError("NOT_FOUND", "导入批次不存在"))
    if batch.status == "confirmed":
        raise http_error(AppError("INVALID_STATE", "该批次已确认过，请勿重复加入"))
    result = await confirm_import(db, batch, payload.houses)
    return BatchConfirmOut(**result)


@router.post("/{batch_id}/cancel", response_model=BatchOut)
async def cancel_batch(batch_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> BatchOut:
    batch = await db.get(ImportBatch, batch_id)
    if batch is None:
        raise http_error(AppError("NOT_FOUND", "导入批次不存在"))
    batch.status = "cancelled"
    await db.commit()
    return await _payload(db, batch)
