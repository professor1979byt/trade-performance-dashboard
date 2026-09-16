from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TradeCategory(StrEnum):
    UNKNOWN = "UNKNOWN"
    SIGNAL_ENTRY = "SIGNAL_ENTRY"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    MIXED_ENTRY = "MIXED_ENTRY"


class TradeSource(StrEnum):
    MANUAL = "MANUAL"
    BOT = "BOT"
    UNKNOWN = "UNKNOWN"


class CloseReason(StrEnum):
    NORMAL = "NORMAL"
    LIQUIDATION = "LIQUIDATION"
    UNKNOWN = "UNKNOWN"


class ClosedPnlRecord(Base):
    __tablename__ = "closed_pnl_records"
    __table_args__ = (
        UniqueConstraint("exchange", "order_id", "updated_time", name="uq_closed_pnl_exchange_order_updated"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(128))
    external_trade_id: Mapped[str | None] = mapped_column(String(192))
    external_order_id: Mapped[str | None] = mapped_column(String(192))
    external_position_id: Mapped[str | None] = mapped_column(String(192))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str | None] = mapped_column(String(16))
    qty: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    closed_size: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    avg_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    avg_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    closed_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    open_fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=Decimal("0"))
    close_fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=Decimal("0"))
    total_fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=Decimal("0"))
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    leverage: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    entry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    size: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fees: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    funding: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    close_reason: Mapped[CloseReason] = mapped_column(String(24), nullable=False, default=CloseReason.UNKNOWN)
    margin_mode: Mapped[str | None] = mapped_column(String(32))
    trade_source: Mapped[TradeSource] = mapped_column(Enum(TradeSource), nullable=False, default=TradeSource.UNKNOWN)
    bot_id: Mapped[str | None] = mapped_column(String(192))
    bot_type: Mapped[str | None] = mapped_column(String(128))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    category: Mapped["TradeCategoryRecord | None"] = relationship(
        back_populates="closed_pnl_record",
        cascade="all, delete-orphan",
        uselist=False,
    )


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    total_wallet_balance: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    total_available_balance: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    total_perp_upl: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class TradeCategoryRecord(Base):
    __tablename__ = "trade_categories"
    __table_args__ = (UniqueConstraint("closed_pnl_record_id", name="uq_trade_categories_record"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    closed_pnl_record_id: Mapped[int] = mapped_column(ForeignKey("closed_pnl_records.id", ondelete="CASCADE"))
    category: Mapped[TradeCategory] = mapped_column(Enum(TradeCategory), nullable=False, default=TradeCategory.UNKNOWN)
    signal_id: Mapped[str | None] = mapped_column(String(128))
    manual_tag: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    closed_pnl_record: Mapped[ClosedPnlRecord] = relationship(back_populates="category")
