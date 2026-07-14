import asyncio

from app.database.db import Base, engine
from app.database.models import Transaction


async def init_db():

    async with engine.begin() as conn:

        # Пока проект в разработке —
        # пересоздаем таблицу автоматически.
        await conn.run_sync(Base.metadata.drop_all)

        await conn.run_sync(Base.metadata.create_all)

    print("✅ Database initialized")


if __name__ == "__main__":
    asyncio.run(init_db())