"""add close reason and margin mode for liquidation provenance

Revision ID: 202608190001
Revises: 202608050001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608190001"
down_revision: Union[str, None] = "202608050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "closed_pnl_records",
        sa.Column("close_reason", sa.String(24), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column("closed_pnl_records", sa.Column("margin_mode", sa.String(32), nullable=True))
    # All existing rows are already closed trade records.  This is metadata
    # only; no PnL, timestamps, or identity fields are changed.
    op.execute("UPDATE closed_pnl_records SET close_reason = 'NORMAL' WHERE close_reason = 'UNKNOWN'")


def downgrade() -> None:
    op.drop_column("closed_pnl_records", "margin_mode")
    op.drop_column("closed_pnl_records", "close_reason")
