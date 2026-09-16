"""initial schema

Revision ID: 202606220001
Revises:
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606220001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    trade_category = postgresql.ENUM(
        "UNKNOWN",
        "SIGNAL_ENTRY",
        "MANUAL_ENTRY",
        "MIXED_ENTRY",
        name="tradecategory",
        create_type=False,
    )
    postgresql.ENUM(
        "UNKNOWN",
        "SIGNAL_ENTRY",
        "MANUAL_ENTRY",
        "MIXED_ENTRY",
        name="tradecategory",
    ).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "closed_pnl_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("account_name", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("qty", sa.Numeric(38, 18), nullable=True),
        sa.Column("closed_size", sa.Numeric(38, 18), nullable=True),
        sa.Column("avg_entry_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("avg_exit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("closed_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("open_fee", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("close_fee", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("total_fee", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("net_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("leverage", sa.Numeric(38, 18), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("exchange", "order_id", "updated_time", name="uq_closed_pnl_exchange_order_updated"),
    )
    op.create_index("ix_closed_pnl_records_symbol", "closed_pnl_records", ["symbol"])
    op.create_index("ix_closed_pnl_records_created_time", "closed_pnl_records", ["created_time"])

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("total_equity", sa.Numeric(38, 18), nullable=False),
        sa.Column("total_wallet_balance", sa.Numeric(38, 18), nullable=True),
        sa.Column("total_available_balance", sa.Numeric(38, 18), nullable=True),
        sa.Column("total_perp_upl", sa.Numeric(38, 18), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_balance_snapshots_created_at", "balance_snapshots", ["created_at"])

    op.create_table(
        "trade_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("closed_pnl_record_id", sa.Integer(), nullable=False),
        sa.Column("category", trade_category, nullable=False, server_default="UNKNOWN"),
        sa.Column("signal_id", sa.String(length=128), nullable=True),
        sa.Column("manual_tag", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["closed_pnl_record_id"], ["closed_pnl_records.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("closed_pnl_record_id", name="uq_trade_categories_record"),
    )


def downgrade() -> None:
    op.drop_table("trade_categories")
    op.drop_index("ix_balance_snapshots_created_at", table_name="balance_snapshots")
    op.drop_table("balance_snapshots")
    op.drop_index("ix_closed_pnl_records_created_time", table_name="closed_pnl_records")
    op.drop_index("ix_closed_pnl_records_symbol", table_name="closed_pnl_records")
    op.drop_table("closed_pnl_records")
    postgresql.ENUM(name="tradecategory").drop(op.get_bind(), checkfirst=True)
