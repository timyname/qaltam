from __future__ import annotations

import asyncio

from backend.app.bot.factory import create_bot, create_dispatcher
from backend.app.db.database import SessionLocal, init_db


async def main() -> None:
    await init_db()
    bot = create_bot()
    dispatcher = create_dispatcher(SessionLocal)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
