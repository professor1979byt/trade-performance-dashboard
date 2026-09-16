"""normalize balance exchange values

Revision ID: 202608040002
Revises: 202608040001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "202608040002"
down_revision: Union[str, None] = "202608040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE balance_snapshots SET exchange = upper(exchange)")


def downgrade() -> None:
    op.execute("UPDATE balance_snapshots SET exchange = lower(exchange)")
