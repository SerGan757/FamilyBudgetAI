from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database.db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )