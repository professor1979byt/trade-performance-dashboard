from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol


class ExchangeAdapter(Protocol):
    exchange: str

    def check_health(self) -> dict[str, Any]: ...

    def iter_closed_trades(self, start_date: datetime, end_date: datetime) -> Iterator[dict[str, Any]]: ...

    def get_balance(self) -> dict[str, Any]: ...


class BybitAdapter:
    """Compatibility wrapper: the proven Bybit client remains unchanged."""

    exchange = "BYBIT"

    def __init__(self, operation: str) -> None:
        from app.bybit_client import BybitReadOnlyClient

        self.client = BybitReadOnlyClient(operation=operation)

    def check_health(self) -> dict[str, Any]:
        return {"latency_ms": self.client.check_relay()}

    def iter_closed_trades(self, start_date: datetime, end_date: datetime):
        return self.client.iter_closed_pnl(start_date, end_date)

    def get_balance(self) -> dict[str, Any]:
        return self.client.get_wallet_balance()
