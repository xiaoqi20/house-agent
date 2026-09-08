from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import get_db
from ..models import Contract, ContractStatus, Risk, RiskLevel
from ..schemas.contract import ContractCreate, ContractOut, ContractTextView, RiskView, RisksSummary
from ..services import ingest
from ..services.analyze import run_analysis
from ..services.storage import storage

router = APIRouter(prefix="/contracts", tags=["contracts"])

Db = Annotated[AsyncSession, Depends(get_db)]
MAX_BYTES = settings.max_upload_mb * 1024 * 1024
UPLOAD_KINDS = {".pdf": "pdf", ".txt": "txt", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}


@router.post("", response_model=ContractOut, status_code=201)
async def create_contract(payload: ContractCreate, db: Db) -> Contract:
    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "合同文本为空")
    contract = Contract(filename=payload.filename, source_type="paste", raw_text=text)
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


@router.post("/upload", response_model=ContractOut, status_code=201)
async def upload_contract(file: UploadFile, db: Db) -> Contract:
    """一期支持 .pdf/.txt（进入分析）与图片（存档，OCR 二期）。文件一律先落 LocalStorage，二期换 OSS。"""
    name = file.filename or "contract"
    ext = Path(name).suffix.lower()
    if ext not in UPLOAD_KINDS:
        raise HTTPException(415, f"一期支持 PDF / TXT / 图片（{', '.join(sorted(UPLOAD_KINDS))}），Word 在二期")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb}MB 限制")

    key = storage.save(name, data)
    kind = UPLOAD_KINDS[ext]
    if kind == "image":
        contract = Contract(
            filename=name,
            source_type="image",
            raw_text="",
            storage_key=key,
            status=ContractStatus.uploaded,
            error="图片已存档。拍照/扫描件识别（OCR）二期上线，当前请上传带文字层的 PDF 或直接粘贴文本。",
        )
    else:
        try:
            text_ = ingest.extract_pdf(data) if kind == "pdf" else ingest.extract_txt(data)
        except ingest.NoTextLayer as exc:
            raise HTTPException(
                422, {"code": "NO_TEXT_LAYER", "message": "未能提取到文字层（疑似扫描件），请改用粘贴文本或等待二期 OCR"}
            ) from exc
        except ingest.TextTooShort as exc:
            raise HTTPException(
                422, {"code": "TEXT_TOO_SHORT", "message": f"正文过短（{exc}），请上传完整合同或直接粘贴文本"}
            ) from exc
        contract = Contract(filename=name, source_type=kind, raw_text=text_, storage_key=key)
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


@router.get("/{contract_id}/file")
async def contract_file(contract_id: int, db: Db):
    """附件下载/预览。LocalStorage 直出文件；二期 OSS 改 302 签名 URL（接口位不变）。"""
    contract = await db.get(Contract, contract_id)
    if contract is None or not contract.storage_key:
        raise HTTPException(404, "文件不存在")
    path = storage.local_path(contract.storage_key)
    if path is None:
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=contract.filename)


@router.get("", response_model=list[ContractOut])
async def list_contracts(db: Db) -> list[Contract]:
    result = await db.execute(select(Contract).order_by(Contract.id.desc()).limit(50))
    return list(result.scalars().all())


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(contract_id: int, db: Db) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(404, "合同不存在")
    return contract


@router.post("/{contract_id}/analyze")
async def analyze_contract(contract_id: int, db: Db) -> EventSourceResponse:
    if await db.get(Contract, contract_id) is None:
        raise HTTPException(404, "合同不存在")
    return EventSourceResponse(run_analysis(db, contract_id))


@router.get("/{contract_id}/text", response_model=ContractTextView)
async def contract_text(contract_id: int, db: Db) -> ContractTextView:
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id).options(selectinload(Contract.clauses), selectinload(Contract.risks))
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise HTTPException(404, "合同不存在")
    order = {"high": 0, "medium": 1, "low": 2}
    risks_by_clause: dict[int, list[Risk]] = {}
    for r in contract.risks:
        risks_by_clause.setdefault(r.clause_id, []).append(r)
    views = []
    for c in sorted(contract.clauses, key=lambda x: (x.clause_no is None, x.clause_no or 0)):
        rs = sorted(risks_by_clause.get(c.id, []), key=lambda r: order[r.level.value])
        views.append(
            {
                "id": c.id,
                "clause_no": c.clause_no,
                "clause_type": c.clause_type,
                "title": c.title,
                "raw_text": c.raw_text,
                "is_risk": bool(rs),
                "risks": [
                    {
                        "id": r.id,
                        "level": r.level.value,
                        "rule_id": r.rule_id,
                        "title": r.title,
                        "reason": r.reason,
                        "suggestion": r.suggestion,
                        "negotiation_script": r.negotiation_script,
                    }
                    for r in rs
                ],
            }
        )
    return ContractTextView(contract_id=contract_id, filename=contract.filename, clauses=views)


@router.get("/{contract_id}/risks", response_model=RisksSummary)
async def contract_risks(contract_id: int, db: Db) -> RisksSummary:
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id).options(selectinload(Contract.risks), selectinload(Contract.clauses))
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise HTTPException(404, "合同不存在")
    clause_no = {c.id: c.clause_no for c in contract.clauses}
    clause_title = {c.id: c.title for c in contract.clauses}
    order = {"high": 0, "medium": 1, "low": 2}
    risks = sorted(contract.risks, key=lambda r: order[r.level.value])
    fields = ("id", "level", "clause_id", "rule_id", "title", "reason", "suggestion", "negotiation_script")
    views = [
        RiskView.model_validate(
            {
                **{f: getattr(r, f) for f in fields},
                "clause_no": clause_no.get(r.clause_id),
                "clause_title": clause_title.get(r.clause_id),
            }
        )
        for r in risks
    ]
    counts = {lv.value: sum(1 for r in risks if r.level.value == lv.value) for lv in RiskLevel}
    return RisksSummary(
        contract_id=contract_id,
        filename=contract.filename,
        health_score=contract.health_score,
        counts=counts,
        risks=views,
    )

