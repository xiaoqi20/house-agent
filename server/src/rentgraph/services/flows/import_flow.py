"""流程 A：房源导入 → AI 字段提取 → 用户确认。

未经确认的字段只存在 `import_batches.drafts`，`confirm` 之后才写入 `houses`（PRD §6.2）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...db import SessionLocal
from ...errors import AppError
from ...models import House, HouseEvidence, ImportBatch, uid
from ...schemas.house import HouseConfirm
from .. import engine
from ..runs import RunContext
from ..storage import storage


async def run_import_batch(run: RunContext, batch_id: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        batch = await db.get(ImportBatch, batch_id)
        if batch is None:
            raise AppError("NOT_FOUND", "导入批次不存在或已被清理")

        await run.progress("parse", 0, "解析文档", "active")
        if batch.storage_key:
            data = storage.read(batch.storage_key)
            doc = engine.parse_document(batch.filename or "upload.txt", data)
        else:
            doc = engine.parse_text(batch.raw_text or "")
        detail = f"{len(doc.text)} 字" + (f" · {doc.page_count} 页" if doc.page_count else "")
        await run.progress("parse", 0, "解析文档", "done", detail)

        run.check_cancelled()
        await run.progress("extract", 1, "AI 提取房源字段", "active")
        extraction = await engine.extract_listings(doc.text, batch.source)
        drafts = [draft.model_dump() for draft in extraction.drafts]
        if not drafts:
            raise AppError(
            "NO_DRAFTS",
            "未识别到房源信息",
            "请按「房源名 + 租金 + 户型/通勤」的格式粘贴，或使用批量粘贴",
        )
        await run.progress("extract", 1, f"识别 {len(drafts)} 套候选房源", "done")

        batch.drafts = drafts
        batch.house_count = len(drafts)
        batch.status = "ready"
        batch.error = None
        await db.commit()
        return await batch_payload(db, batch, run_id=run.id)


async def batch_payload(db, batch: ImportBatch, *, run_id: str | None = None) -> dict[str, Any]:
    from ...schemas.house import BatchOut, HouseDraft, sanitize_draft

    drafts = [HouseDraft(**sanitize_draft(draft, source=batch.source)) for draft in (batch.drafts or [])]
    duplicates = await _duplicate_names(db, batch)
    for draft in drafts:
        match = duplicates.get(_dup_key(draft.name, draft.rent))
        if match:
            draft.duplicate_of = match
    return BatchOut(
        id=batch.id,
        workspace_id=batch.workspace_id,
        source=batch.source,
        status=batch.status,
        filename=batch.filename,
        link_url=batch.link_url,
        raw_text=batch.raw_text,
        drafts=drafts,
        house_count=batch.house_count,
        error=batch.error,
        run_id=run_id,
    ).model_dump()


async def _duplicate_names(db, batch: ImportBatch) -> dict[str, str]:
    rows = (
        await db.execute(
            select(House).where(House.workspace_id == batch.workspace_id, House.status == "active")
        )
    ).scalars()
    out: dict[str, str] = {}
    for house in rows:
        out[_dup_key(house.name, house.rent)] = house.id
    return out


def _dup_key(name: str, rent: int | None) -> str:
    return f"{(name or '').strip()}|{rent if rent is not None else ''}"


async def confirm_import(db, batch: ImportBatch, houses: list[HouseConfirm]) -> dict[str, Any]:
    """把用户确认后的字段写入本次候选房源。"""

    if not houses:
        raise AppError("NO_DRAFTS", "没有可确认的房源", "请返回上一步重新解析")

    active_count = (
        await db.execute(
            select(func.count()).select_from(House).where(
                House.workspace_id == batch.workspace_id, House.status == "active"
            )
        )
    ).scalar_one()
    if active_count + len(houses) > 10:
        raise AppError(
            "TOO_MANY_HOUSES",
            f"加入后会有 {active_count + len(houses)} 套候选房源，超过 10 套上限",
            "请先移除部分房源，或拆分成本次工作台的两批比较",
        )

    existing = {
        _dup_key(house.name, house.rent): house.no
        for house in (
            await db.execute(
                select(House).where(House.workspace_id == batch.workspace_id, House.status == "active")
            )
        ).scalars()
    }

    seq = active_count
    created: list[House] = []
    duplicate_notes: list[str] = []
    for payload in houses:
        seq += 1
        data = payload.model_dump(exclude={"draft_id"})
        for field in ("visits", "todos", "verify"):
            data[field] = list(data.get(field) or [])
        evidence = data.pop("evidence", {}) or {}
        house = House(
            id=uid(),
            workspace_id=batch.workspace_id,
            batch_id=batch.id,
            no=f"H{seq}",
            status="active",
            **data,
        )
        key = _dup_key(house.name, house.rent)
        if key in existing:
            duplicate_notes.append(f"{house.no} 与 {existing[key]} 疑似重复（同名同租金）")
        db.add(house)
        for field, snippet in evidence.items():
            if snippet:
                db.add(
                    HouseEvidence(
                        house_id=house.id,
                        field=field,
                        snippet=snippet,
                        source=house.source,
                        batch_id=batch.id,
                    )
                )
        created.append(house)

    batch.status = "confirmed"
    await db.commit()
    for house in created:
        await db.refresh(house, attribute_names=["evidence"])

    from ..convert import house_out

    hint = ""
    if batch.house_count and batch.house_count < 3:
        hint = "当前候选房源少于 3 套，比较范围建议 3—10 套；可以继续添加"
    elif duplicate_notes:
        hint = "；".join(duplicate_notes)
    return {
        "houses": [house_out(house).model_dump(mode="json") for house in created],
        "hint": hint,
    }
