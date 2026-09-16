from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def ms_to_datetime(value: Any) -> datetime:
    timestamp_ms = int(value)
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)
