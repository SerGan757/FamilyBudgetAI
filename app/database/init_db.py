import asyncio

from app.database.db import Base, engine
from app.database import models


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("✅ Таблицы созданы")


if __name__ == "__main__":
    asyncio.run(init())