from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    text,
    UniqueConstraint,
    CheckConstraint,
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
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        nullable=False,
    )

    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(
        String(10), default="ru", server_default="ru", nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Berlin", server_default="Europe/Berlin", nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="EUR", server_default="EUR", nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False,
    )
    plan: Mapped[str] = mapped_column(
        String(20), default="free", server_default="free", nullable=False,
    )
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temporary_screen_ttl: Mapped[int] = mapped_column(
        Integer, default=20, server_default=text("20"), nullable=False,
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

    projects = relationship(
        "Project",
        back_populates="family",
        cascade="all, delete-orphan",
    )

    savings_goals = relationship(
        "SavingsGoal", back_populates="family", cascade="all, delete-orphan",
    )

    category_keyword_overrides = relationship(
        "FamilyCategoryKeywordOverride",
        back_populates="family",
        cascade="all, delete-orphan",
    )
    custom_categories = relationship(
        "FamilyCategory", back_populates="family", cascade="all, delete-orphan",
    )
    document_categories = relationship("DocumentCategory", back_populates="family")
    documents = relationship("Document", back_populates="family")

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

    goal_contributions = relationship(
        "GoalContribution", back_populates="user", cascade="all, delete-orphan",
    )
    created_documents = relationship("Document", back_populates="created_by_user")

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

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    custom_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_categories.id", ondelete="SET NULL"), nullable=True, index=True,
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

    project = relationship(
        "Project",
        back_populates="transactions",
    )
    custom_category = relationship("FamilyCategory", back_populates="transactions")

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


# =====================================================
# PROJECTS
# =====================================================

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("family_id", "tag", name="uq_projects_family_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tag: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        nullable=False,
    )

    family = relationship("Family", back_populates="projects")
    transactions = relationship("Transaction", back_populates="project")

    def __repr__(self):
        return f"<Project(id={self.id}, family_id={self.family_id}, tag='{self.tag}')>"


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        Index(
            "uq_savings_goals_one_active_per_family", "family_id", unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"), nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    family = relationship("Family", back_populates="savings_goals")
    contributions = relationship(
        "GoalContribution", back_populates="goal", cascade="all, delete-orphan",
    )


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        nullable=False, index=True,
    )

    goal = relationship("SavingsGoal", back_populates="contributions")
    user = relationship("User", back_populates="goal_contributions")


class FamilyCategoryKeywordOverride(Base):
    __tablename__ = "family_category_keyword_overrides"
    __table_args__ = (
        CheckConstraint("action IN ('add', 'disable')", name="ck_family_category_keyword_action"),
        UniqueConstraint(
            "family_id", "category_key", "normalized_keyword",
            name="uq_family_category_keyword_override",
        ),
        Index("ix_family_category_keyword_family_category", "family_id", "category_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    category_key: Mapped[str] = mapped_column(String(32), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"), nullable=False,
    )

    family = relationship("Family", back_populates="category_keyword_overrides")


class FamilyCategory(Base):
    __tablename__ = "family_categories"
    __table_args__ = (
        UniqueConstraint("family_id", "normalized_name", name="uq_family_category_name"),
        Index("ix_family_categories_family_active", "family_id", "is_active"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"), nullable=False)
    family = relationship("Family", back_populates="custom_categories")
    keywords = relationship("FamilyCategoryKeyword", back_populates="category", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="custom_category")


class FamilyCategoryKeyword(Base):
    __tablename__ = "family_category_keywords"
    __table_args__ = (UniqueConstraint("family_category_id", "normalized_keyword", name="uq_family_category_keyword"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_category_id: Mapped[int] = mapped_column(ForeignKey("family_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"), nullable=False)
    category = relationship("FamilyCategory", back_populates="keywords")


class DocumentCategory(Base):
    __tablename__ = "document_categories"
    __table_args__ = (
        UniqueConstraint("family_id", "name", name="uq_document_categories_family_name"),
        UniqueConstraint("family_id", "code", name="uq_document_categories_family_code"),
        Index("ix_document_categories_family_active_sort", "family_id", "is_active", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False, default="📁")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
    )

    family = relationship("Family", back_populates="document_categories")
    documents = relationship("Document", back_populates="category")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("access_level IN ('family', 'private')", name="ck_documents_access_level"),
        Index("ix_documents_family_title", "family_id", "title"),
        Index("ix_documents_category_created", "category_id", "created_at"),
        Index(
            "uq_documents_upload_session_key", "upload_session_key", unique=True,
            postgresql_where=text("upload_session_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("document_categories.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    access_level: Mapped[str] = mapped_column(String(10), nullable=False, default="family", server_default="family")
    upload_session_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"))

    family = relationship("Family", back_populates="documents")
    category = relationship("DocumentCategory", back_populates="documents")
    created_by_user = relationship("User", back_populates="created_documents")
    files = relationship("DocumentFile", back_populates="document", cascade="all, delete-orphan", order_by="DocumentFile.sort_order")


class DocumentFile(Base):
    __tablename__ = "document_files"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "sort_order",
            name="uq_document_files_document_sort",
        ),
        Index("ix_document_files_document_sort", "document_id", "sort_order"),
        Index(
            "uq_document_files_document_file_unique",
            "document_id", "telegram_file_unique_id", unique=True,
            postgresql_where=text("telegram_file_unique_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"))

    document = relationship("Document", back_populates="files")


class TemporaryTelegramMessage(Base):
    __tablename__ = "temporary_telegram_messages"
    __table_args__ = (
        UniqueConstraint(
            "chat_id", "message_id",
            name="uq_temporary_telegram_messages_chat_message",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'failed')",
            name="ck_temporary_telegram_messages_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_temporary_telegram_messages_attempts",
        ),
        Index(
            "ix_temporary_telegram_messages_status_delete_after",
            "status", "delete_after",
        ),
        Index("ix_temporary_telegram_messages_locked_until", "locked_until"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delete_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
