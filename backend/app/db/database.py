from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.models import account, goal, hypothesis, obligation, profile, receipt, transaction  # noqa: F401

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.app_debug, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if engine.url.get_backend_name() == "sqlite":
            await _ensure_sqlite_compatibility(connection)


async def _ensure_sqlite_compatibility(connection) -> None:
    existing_columns = await _table_columns(connection, "imported_statements")
    if "original_filename" not in existing_columns:
        await connection.execute(text("ALTER TABLE imported_statements ADD COLUMN original_filename VARCHAR(255)"))
    if "telegram_user_id" not in existing_columns:
        await connection.execute(text("ALTER TABLE imported_statements ADD COLUMN telegram_user_id INTEGER"))
    if "raw_content" not in existing_columns:
        await connection.execute(text("ALTER TABLE imported_statements ADD COLUMN raw_content TEXT"))

    account_columns = await _table_columns(connection, "accounts")
    if "telegram_user_id" not in account_columns:
        await connection.execute(text("ALTER TABLE accounts ADD COLUMN telegram_user_id INTEGER"))

    transaction_columns = await _table_columns(connection, "transactions")
    if "telegram_user_id" not in transaction_columns:
        await connection.execute(text("ALTER TABLE transactions ADD COLUMN telegram_user_id INTEGER"))

    await _ensure_sqlite_accounts_table_is_user_safe(connection)


async def _ensure_sqlite_accounts_table_is_user_safe(connection) -> None:
    if not await _sqlite_has_legacy_unique_account_name(connection):
        return

    await connection.execute(text("PRAGMA foreign_keys=OFF"))
    await connection.execute(
        text(
            """
            CREATE TABLE accounts_rebuild (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(16) NOT NULL,
                balance NUMERIC(14, 2) NOT NULL DEFAULT 0
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO accounts_rebuild (id, telegram_user_id, name, type, balance)
            SELECT id, telegram_user_id, name, type, balance
            FROM accounts
            """
        )
    )
    await connection.execute(text("DROP TABLE accounts"))
    await connection.execute(text("ALTER TABLE accounts_rebuild RENAME TO accounts"))
    await connection.execute(text("CREATE INDEX ix_accounts_name ON accounts (name)"))
    await connection.execute(text("CREATE INDEX ix_accounts_telegram_user_id ON accounts (telegram_user_id)"))
    await connection.execute(text("CREATE INDEX ix_accounts_type ON accounts (type)"))
    await connection.execute(text("PRAGMA foreign_keys=ON"))


async def _sqlite_has_legacy_unique_account_name(connection) -> bool:
    indexes = await connection.execute(text("PRAGMA index_list(accounts)"))
    for _, index_name, is_unique, *_ in indexes.fetchall():
        if not is_unique:
            continue
        columns = await connection.execute(text(f"PRAGMA index_info({index_name!r})"))
        indexed_columns = [row[2] for row in columns.fetchall()]
        if indexed_columns == ["name"]:
            return True
    return False


async def _table_columns(connection, table_name: str) -> set[str]:
    result = await connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}
