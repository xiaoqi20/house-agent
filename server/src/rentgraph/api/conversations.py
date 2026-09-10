"""对话与上下文问答（流程 C）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError
from ..models import Conversation, Message
from ..schemas.chat import ConversationCreate, ConversationOut, MessageCreate, MessageCreated, MessageOut
from ..services.convert import message_out
from ..services.flows import run_answer
from ..services.flows._common import create_run, launch
from .deps import http_error, load_workspace

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ConversationOut:
    await load_workspace(db, payload.workspace_id)
    conversation = Conversation(workspace_id=payload.workspace_id, title=payload.title or "新对话")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationOut(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        title=conversation.title,
        created_at=conversation.created_at,
        message_count=0,
    )


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    workspace_id: Annotated[str, Query()], db: Annotated[AsyncSession, Depends(get_db)]
) -> list[ConversationOut]:
    await load_workspace(db, workspace_id)
    rows = list(
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.workspace_id == workspace_id)
                .order_by(Conversation.created_at.desc())
            )
        ).scalars()
    )
    out: list[ConversationOut] = []
    for row in rows:
        count = (
            await db.execute(select(func.count()).select_from(Message).where(Message.conversation_id == row.id))
        ).scalar_one()
        out.append(
            ConversationOut(
                id=row.id,
                workspace_id=row.workspace_id,
                title=row.title,
                created_at=row.created_at,
                message_count=count,
            )
        )
    return out


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[MessageOut]:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise http_error(AppError("NOT_FOUND", "对话不存在"))
    rows = list(
        (
            await db.execute(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
            )
        ).scalars()
    )
    return [message_out(row) for row in rows]


@router.post("/{conversation_id}/messages", response_model=MessageCreated, status_code=202)
async def post_message(
    conversation_id: str, payload: MessageCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> MessageCreated:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise http_error(AppError("NOT_FOUND", "对话不存在"))
    text = payload.text.strip()
    if not text:
        raise http_error(AppError("INVALID_STATE", "消息内容为空"))

    user_message = Message(conversation_id=conversation.id, role="user", content={"text": text})
    db.add(user_message)
    if conversation.title in ("", "新对话"):
        conversation.title = text[:18]
    await db.commit()
    await db.refresh(user_message)

    run = await create_run(
        "chat",
        workspace_id=conversation.workspace_id,
        house_id=payload.house_id,
        contract_id=payload.contract_id,
    )
    launch(run, lambda ctx: run_answer(ctx, conversation.id, user_message.id, text))
    return MessageCreated(message_id=user_message.id, run_id=run.id)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise http_error(AppError("NOT_FOUND", "对话不存在"))
    await db.delete(conversation)
    await db.commit()
