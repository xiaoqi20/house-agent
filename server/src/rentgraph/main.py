import json
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, contracts, health
from .config import settings
from .db import Base, engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # 轻量迁移（一期够用；正式引入 alembic 后移除此处）
            await conn.execute(text("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS storage_key VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE risks ADD COLUMN IF NOT EXISTS negotiation_script TEXT"))
    except Exception as exc:  # DB 未就绪时不阻塞 /healthz（S1 骨架期容错）
        logger.warning("db_bootstrap_skipped", error=str(exc))
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Path("openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    yield


app = FastAPI(title="RentGraph API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(contracts.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
