from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - 取决于驱动
    """SQLite：WAL + busy_timeout。

    默认 journal 模式下写事务会阻塞读，并发请求直接吃 `database is locked` → 500。
    WAL 让读不阻塞写，busy_timeout 让写等 10s 而不是立刻报错。
    ponytail: 只针对 SQLite；PG 由并发控制自己处理，所以这里判一下驱动类型。
    """

    if "sqlite" not in type(dbapi_connection).__module__:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
