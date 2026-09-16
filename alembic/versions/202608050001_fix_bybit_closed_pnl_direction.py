"""map Bybit Closed PnL closing side to position direction

Revision ID: 202608050001
Revises: 202608040002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "202608050001"
down_revision: Union[str, None] = "202608040002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bybit Closed PnL reports the closing order side in one-way mode:
    # Sell closes LONG and Buy closes SHORT. Keep this update BYBIT-only.
    op.execute("""
        UPDATE closed_pnl_records
        SET direction = CASE lower(raw_payload->>'side')
            WHEN 'sell' THEN 'LONG'
            WHEN 'buy' THEN 'SHORT'
            ELSE 'UNKNOWN'
        END
        WHERE exchange = 'BYBIT'
          AND direction IS DISTINCT FROM CASE lower(raw_payload->>'side')
              WHEN 'sell' THEN 'LONG'
              WHEN 'buy' THEN 'SHORT'
              ELSE 'UNKNOWN'
          END
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE closed_pnl_records
        SET direction = CASE lower(raw_payload->>'side')
            WHEN 'buy' THEN 'LONG'
            WHEN 'sell' THEN 'SHORT'
            ELSE 'UNKNOWN'
        END
        WHERE exchange = 'BYBIT'
    """)
