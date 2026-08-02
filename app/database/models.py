from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.db import Base


# =====================================================
# FAMILIES
# =====================================================

class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    invite_code: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        nullable=False,
        index=True,
    )

    # Nullable while legacy families are mapped to their Telegram chats.
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    users = relationship(
        "User",
        back_populates="family",
        cascade="all, delete-orphan",
    )

    recurring_payments = relationship(
        "RecurringPayment",
        back_populates="family",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<Family(id={self.id}, name='{self.name}')>"
        )


# =====================================================
# USERS
# =====================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    family = relationship(
        "Family",
        back_populates="users",
    )

    transactions = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<User(id={self.id}, "
            f"name='{self.name}', "
            f"telegram_id={self.telegram_id})>"
        )


# =====================================================
# TRANSACTIONS
# =====================================================

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "recurring_payment_id",
            "recurring_period",
            name="uq_transactions_recurring_payment_period",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="📦 Прочее",
    )

    is_recurring: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    recurring_payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_payments.id", ondelete="SET NULL"),
        nullable=True,
    )

    recurring_period: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="transactions",
    )

    recurring_payment = relationship(
        "RecurringPayment",
        back_populates="transactions",
    )

    def __repr__(self):
        return (
            f"<Transaction(id={self.id}, "
            f"title='{self.title}', "
            f"amount={self.amount})>"
        )


# =====================================================
# RECURRING PAYMENTS
# =====================================================

class RecurringPayment(Base):
    __tablename__ = "recurring_payments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="expense",
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="📦 Прочее",
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="📦 Прочее",
    )

    frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="monthly",
    )

    interval_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    day_of_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    month_of_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    payer: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Общий",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    family = relationship(
        "Family",
        back_populates="recurring_payments",
    )

    transactions = relationship(
        "Transaction",
        back_populates="recurring_payment",
    )

    def __repr__(self):
        return (
            f"<RecurringPayment(id={self.id}, "
            f"title='{self.title}', "
            f"amount={self.amount})>"
        )
