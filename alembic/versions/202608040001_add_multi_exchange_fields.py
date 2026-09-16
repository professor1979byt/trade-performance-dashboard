"""add multi-exchange trade fields

Revision ID: 202608040001
Revises: 202606220001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608040001"
down_revision: Union[str, None] = "202606220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    trade_source = postgresql.ENUM("MANUAL", "BOT", "UNKNOWN", name="tradesource")
    trade_source.create(op.get_bind(), checkfirst=True)
    op.add_column("closed_pnl_records", sa.Column("external_trade_id", sa.String(192), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("external_order_id", sa.String(192), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("external_position_id", sa.String(192), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("direction", sa.String(16), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("entry_price", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("exit_price", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("size", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("gross_pnl", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("fees", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("funding", sa.Numeric(38, 18), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("trade_source", trade_source, nullable=False, server_default="UNKNOWN"))
    op.add_column("closed_pnl_records", sa.Column("bot_id", sa.String(192), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("bot_type", sa.String(128), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("closed_pnl_records", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("""
        UPDATE closed_pnl_records SET
            exchange = upper(exchange),
            external_trade_id = order_id || ':' || extract(epoch from updated_time)::text,
            external_order_id = order_id,
            direction = CASE WHEN lower(side) = 'buy' THEN 'LONG' WHEN lower(side) = 'sell' THEN 'SHORT' ELSE 'UNKNOWN' END,
            entry_time = created_time,
            exit_time = updated_time,
            entry_price = avg_entry_price,
            exit_price = avg_exit_price,
            size = coalesce(closed_size, qty),
            gross_pnl = closed_pnl,
            fees = total_fee,
            raw_payload = raw_json
    """)
    op.create_unique_constraint("uq_closed_pnl_exchange_external_trade", "closed_pnl_records", ["exchange", "external_trade_id"])


def downgrade() -> None:
    op.drop_constraint("uq_closed_pnl_exchange_external_trade", "closed_pnl_records", type_="unique")
    op.execute("UPDATE closed_pnl_records SET exchange = lower(exchange)")
    for name in ("updated_at", "raw_payload", "bot_type", "bot_id", "trade_source", "funding", "fees", "gross_pnl", "size", "exit_price", "entry_price", "exit_time", "entry_time", "direction", "external_position_id", "external_order_id", "external_trade_id"):
        op.drop_column("closed_pnl_records", name)
    postgresql.ENUM(name="tradesource").drop(op.get_bind(), checkfirst=True)
