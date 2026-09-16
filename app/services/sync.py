from datetime import UTC, datetime, timedelta
from decimal import Decimal
from collections import Counter
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bybit_client import BybitReadOnlyClient
from app.models import BalanceSnapshot, CloseReason, ClosedPnlRecord, TradeCategory, TradeCategoryRecord, TradeSource
from app.pionex_client import PionexAdapter, PionexAPIError
from app.utils import decimal_or_none, decimal_or_zero, ms_to_datetime


logger = logging.getLogger("uvicorn.error")


def _record_from_closed_pnl_item(item: dict[str, Any]) -> ClosedPnlRecord:
    open_fee = decimal_or_zero(item.get("openFee"))
    close_fee = decimal_or_zero(item.get("closeFee"))
    closed_pnl = decimal_or_zero(item.get("closedPnl"))
    total_fee = open_fee + close_fee

    return ClosedPnlRecord(
        exchange="BYBIT",
        account_name=None,
        symbol=item["symbol"],
        order_id=item["orderId"],
        side=item.get("side"),
        qty=decimal_or_none(item.get("qty")),
        closed_size=decimal_or_none(item.get("closedSize")),
        avg_entry_price=decimal_or_none(item.get("avgEntryPrice")),
        avg_exit_price=decimal_or_none(item.get("avgExitPrice")),
        closed_pnl=closed_pnl,
        open_fee=open_fee,
        close_fee=close_fee,
        total_fee=total_fee,
        net_pnl=closed_pnl - total_fee,
        leverage=decimal_or_none(item.get("leverage")),
        created_time=ms_to_datetime(item["createdTime"]),
        updated_time=ms_to_datetime(item["updatedTime"]),
        raw_json=item,
        external_trade_id=f"{item['orderId']}:{item['updatedTime']}",
        external_order_id=str(item["orderId"]),
        direction=BybitReadOnlyClient.normalize_closed_pnl_direction(item),
        entry_time=ms_to_datetime(item["createdTime"]),
        exit_time=ms_to_datetime(item["updatedTime"]),
        entry_price=decimal_or_none(item.get("avgEntryPrice")),
        exit_price=decimal_or_none(item.get("avgExitPrice")),
        size=decimal_or_none(item.get("closedSize") or item.get("qty")),
        gross_pnl=closed_pnl,
        fees=total_fee,
        trade_source=TradeSource.UNKNOWN,
        raw_payload=item,
    )


def sync_closed_pnl(db: Session, days: int) -> dict[str, int]:
    end_date = datetime.now(tz=UTC)
    start_date = end_date - timedelta(days=days)
    return sync_closed_pnl_range(db, start_date=start_date, end_date=end_date)


def sync_closed_pnl_range(db: Session, start_date: datetime, end_date: datetime) -> dict[str, int]:
    operation = "sync_closed_pnl"
    client = BybitReadOnlyClient(operation=operation)
    client.check_relay()
    inserted = 0
    skipped = 0
    ranges = max(1, ((end_date - start_date).days + 6) // 7)

    for item in client.iter_closed_pnl(start_date=start_date, end_date=end_date):
        record = _record_from_closed_pnl_item(item)
        exists = db.execute(
            select(ClosedPnlRecord.id).where(
                ClosedPnlRecord.exchange == record.exchange,
                ClosedPnlRecord.order_id == record.order_id,
                ClosedPnlRecord.updated_time == record.updated_time,
            )
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue

        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
                db.add(
                    TradeCategoryRecord(
                        closed_pnl_record_id=record.id,
                        category=TradeCategory.UNKNOWN,
                    )
                )
        except IntegrityError:
            skipped += 1
            continue
        inserted += 1

    db.commit()
    logger.info(
        "operation=%s inserted=%s skipped=%s ranges=%s",
        operation,
        inserted,
        skipped,
        ranges,
    )
    return {"inserted": inserted, "skipped": skipped, "ranges": ranges}


def sync_balance(db: Session) -> BalanceSnapshot:
    operation = "sync_balance"
    client = BybitReadOnlyClient(operation=operation)
    client.check_relay()
    response = client.get_wallet_balance()
    accounts = response.get("result", {}).get("list", [])
    if not accounts:
        raise ValueError("Bybit wallet balance response has no accounts")

    account = accounts[0]
    snapshot = BalanceSnapshot(
        exchange="BYBIT",
        total_equity=decimal_or_zero(account.get("totalEquity")),
        total_wallet_balance=decimal_or_none(account.get("totalWalletBalance")),
        total_available_balance=decimal_or_none(account.get("totalAvailableBalance")),
        total_perp_upl=decimal_or_none(account.get("totalPerpUPL")),
        raw_json=response,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    logger.info("operation=%s snapshot_id=%s status=success", operation, snapshot.id)
    return snapshot


def _weighted_fill_price(rows: list[dict[str, Any]]) -> Decimal | None:
    total_size = sum((abs(decimal_or_zero(row.get("size"))) for row in rows), Decimal("0"))
    if not total_size:
        return None
    total_amount = sum(
        (abs(decimal_or_zero(row.get("size"))) * decimal_or_zero(row.get("price")) for row in rows),
        Decimal("0"),
    )
    return total_amount / total_size


def _record_from_pionex_position(
    item: dict[str, Any], fills: list[dict[str, Any]] | None = None,
    fundings: list[dict[str, Any]] | None = None,
    *, close_reason: CloseReason = CloseReason.NORMAL,
    source_flag: str = "CLOSED",
) -> ClosedPnlRecord:
    position_id = str(item["positionId"])
    created = ms_to_datetime(item.get("createdTime") or item.get("createTime"))
    updated = ms_to_datetime(item.get("updatedTime") or item.get("updateTime"))
    direction = PionexAdapter.normalize_position_direction(item)
    size_long = decimal_or_none(item.get("sizeLong"))
    size_short = decimal_or_none(item.get("sizeShort"))
    closed_sizes = [abs(value) for value in (size_long, size_short) if value is not None and value != 0]
    size = min(closed_sizes) if closed_sizes else None
    amount_long = decimal_or_none(item.get("amountLong"))
    amount_short = decimal_or_none(item.get("amountShort"))
    buy_price = abs(amount_long / size_long) if amount_long is not None and size_long else None
    sell_price = abs(amount_short / size_short) if amount_short is not None and size_short else None

    relevant_fills = fills or []
    liquidation_fills = [
        row for row in relevant_fills if str(row.get("feeType", "")).upper() == "LIQUIDATION"
    ]
    regular_fills = [row for row in relevant_fills if row not in liquidation_fills]
    buy_fills = [row for row in regular_fills if str(row.get("side", "")).upper() == "BUY"]
    sell_fills = [row for row in regular_fills if str(row.get("side", "")).upper() == "SELL"]
    buy_price = buy_price or _weighted_fill_price(buy_fills)
    sell_price = sell_price or _weighted_fill_price(sell_fills)
    entry_price = buy_price if direction == "LONG" else sell_price if direction == "SHORT" else None
    exit_price = sell_price if direction == "LONG" else buy_price if direction == "SHORT" else None
    if close_reason == CloseReason.LIQUIDATION:
        liquidation_side = "SELL" if direction == "LONG" else "BUY"
        liquidation_fill = next(
            (row for row in liquidation_fills if str(row.get("side", "")).upper() == liquidation_side),
            None,
        )
        if liquidation_fill is not None:
            exit_price = decimal_or_none(liquidation_fill.get("price"))

    settled = decimal_or_zero(item.get("amountSettled"))
    gross_pnl = amount_long + amount_short if amount_long is not None and amount_short is not None else -settled
    fees = sum((abs(decimal_or_zero(row.get("fee"))) for row in relevant_fills), Decimal("0"))
    funding = sum((decimal_or_zero(row.get("fundingFee")) for row in (fundings or [])), Decimal("0"))
    raw_payload = dict(item)
    raw_payload["dashboardEnrichment"] = {"fills": relevant_fills, "fundings": fundings or []}
    if close_reason == CloseReason.LIQUIDATION:
        raw_payload["sourceEvidence"] = {
            "endpoint": "/uapi/v1/account/historyPositions", "positionFlag": source_flag,
        }
        raw_payload["sourceEvidence"]["liquidationFillIds"] = [
            row.get("id") for row in liquidation_fills if row.get("id") is not None
        ]
        raw_payload["sourceEvidence"]["liquidationFeeTypes"] = [row.get("feeType") for row in liquidation_fills]
    isolated_mode = str(item.get("isolatedMode", "")).upper()
    margin_mode = "ISOLATED" if isolated_mode.startswith("ISOLATED") else isolated_mode or None
    return ClosedPnlRecord(
        exchange="PIONEX", external_trade_id=position_id, external_position_id=position_id,
        external_order_id=None, account_name=None, symbol=item["symbol"], order_id=position_id,
        side=None, direction=direction, qty=size, closed_size=size, size=size,
        avg_entry_price=entry_price, avg_exit_price=exit_price, entry_price=entry_price, exit_price=exit_price,
        closed_pnl=gross_pnl, gross_pnl=gross_pnl, open_fee=Decimal("0"), close_fee=fees,
        total_fee=fees, fees=fees, funding=funding, net_pnl=gross_pnl - fees + funding,
        leverage=decimal_or_none(item.get("leverage")), margin_mode=margin_mode, close_reason=close_reason,
        created_time=created, updated_time=updated,
        entry_time=created, exit_time=updated, trade_source=TradeSource.UNKNOWN,
        raw_json=raw_payload, raw_payload=raw_payload,
    )


def sync_pionex_trades_range(db: Session, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    client = PionexAdapter("sync_pionex_trades")
    client.check_health()
    inserted = updated = skipped = 0
    skip_reasons: Counter[str] = Counter()
    ranges = max(1, ((end_date - start_date).days + 6) // 7)
    positions: list[tuple[dict[str, Any], str, CloseReason]] = [
        (item, "CLOSED", CloseReason.NORMAL) for item in client.iter_closed_trades(start_date, end_date)
    ]
    positions.extend(
        (item, "TAKEOVER", CloseReason.LIQUIDATION)
        for item in client.iter_taken_over_trades(start_date, end_date)
    )
    fills_by_symbol: dict[str, list[dict[str, Any]]] = {}
    funding_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol in sorted({str(item["symbol"]) for item, _, _ in positions}):
        symbol_positions = [item for item, _, _ in positions if str(item["symbol"]) == symbol]
        enrichment_start = min(
            ms_to_datetime(item.get("createdTime") or item.get("createTime")) for item in symbol_positions
        ) - timedelta(seconds=1)
        enrichment_end = max(
            ms_to_datetime(item.get("updatedTime") or item.get("updateTime")) for item in symbol_positions
        ) + timedelta(seconds=2)
        try:
            fills_by_symbol[symbol] = client.get_fills(symbol, enrichment_start, enrichment_end)
        except PionexAPIError as exc:
            logger.warning("operation=sync_pionex_trades endpoint=fills symbol=%s code=%s", symbol, exc.code)
            fills_by_symbol[symbol] = []
        try:
            funding_by_symbol[symbol] = client.get_funding(enrichment_start, enrichment_end, symbol)
        except PionexAPIError as exc:
            logger.warning("operation=sync_pionex_trades endpoint=funding symbol=%s code=%s", symbol, exc.code)
            funding_by_symbol[symbol] = []

    record_types: Counter[str] = Counter()
    for item, source_flag, close_reason in positions:
        record_types["liquidation_record" if close_reason == CloseReason.LIQUIDATION else "normal_record"] += 1
        position_id = str(item.get("positionId", "")).strip()
        symbol = str(item.get("symbol", "")).strip()
        created_raw = item.get("createdTime") or item.get("createTime")
        updated_raw = item.get("updatedTime") or item.get("updateTime")
        if not position_id:
            skipped += 1
            skip_reasons["unsupported_record"] += 1
            continue
        if not symbol or not symbol.endswith("_USDT_PERP"):
            skipped += 1
            skip_reasons["invalid_symbol"] += 1
            continue
        try:
            created_ms = int(created_raw)
            updated_ms = int(updated_raw)
            if created_ms <= 0 or updated_ms <= 0 or updated_ms < created_ms:
                raise ValueError("invalid position timestamps")
        except (TypeError, ValueError):
            skipped += 1
            skip_reasons["invalid_timestamp"] += 1
            continue
        position_fills = [
            row for row in fills_by_symbol.get(symbol, [])
            if created_ms - 1000 <= int(row.get("timestamp", 0)) <= updated_ms + 1000
        ]
        position_fundings = [
            row for row in funding_by_symbol.get(symbol, [])
            if created_ms <= int(row.get("timestamp", 0)) <= updated_ms
        ]
        try:
            record = _record_from_pionex_position(
                item, position_fills, position_fundings,
                close_reason=close_reason, source_flag=source_flag,
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            skipped += 1
            skip_reasons[
                "missing_liquidation_mapping" if close_reason == CloseReason.LIQUIDATION else "aggregation_failure"
            ] += 1
            logger.warning(
                "operation=sync_pionex_trades position_id=%s reason=aggregation_failure",
                position_id,
            )
            continue
        if record.size is None or record.size == 0:
            skipped += 1
            skip_reasons["zero_size"] += 1
            continue
        if record.direction not in {"LONG", "SHORT"}:
            skipped += 1
            skip_reasons["unknown_direction"] += 1
            continue
        if record.entry_price is None:
            skipped += 1
            skip_reasons["missing_liquidation_mapping" if close_reason == CloseReason.LIQUIDATION else "missing_entry"] += 1
            continue
        if record.exit_price is None:
            skipped += 1
            skip_reasons["missing_liquidation_mapping" if close_reason == CloseReason.LIQUIDATION else "missing_exit"] += 1
            continue
        existing = db.execute(select(ClosedPnlRecord).where(
            ClosedPnlRecord.exchange == "PIONEX",
            ClosedPnlRecord.external_trade_id == record.external_trade_id,
        )).scalar_one_or_none()
        if existing:
            if existing.raw_payload == record.raw_payload:
                skipped += 1
                skip_reasons["duplicate_existing"] += 1
                continue
            for field in (
                "symbol", "side", "direction", "qty", "closed_size", "size", "avg_entry_price",
                "avg_exit_price", "entry_price", "exit_price", "closed_pnl", "gross_pnl", "open_fee",
                "close_fee", "total_fee", "fees", "funding", "net_pnl", "leverage", "created_time",
                "updated_time", "entry_time", "exit_time", "raw_json", "raw_payload", "close_reason", "margin_mode",
            ):
                setattr(existing, field, getattr(record, field))
            updated += 1
            continue
        db.add(record)
        db.flush()
        db.add(TradeCategoryRecord(closed_pnl_record_id=record.id, category=TradeCategory.UNKNOWN))
        inserted += 1
    db.commit()
    result = {
        "exchange": "PIONEX", "inserted": inserted, "updated": updated,
        "skipped": skipped, "ranges": ranges,
        "skip_reasons": dict(skip_reasons),
        "api_positions": len(positions),
        "record_types": dict(record_types),
        "source_fills": sum(len(rows) for rows in fills_by_symbol.values()),
        "source_fundings": sum(len(rows) for rows in funding_by_symbol.values()),
    }
    logger.info(
        "operation=sync_pionex_trades inserted=%s updated=%s skipped=%s skip_reasons=%s api_positions=%s source_fills=%s source_fundings=%s",
        inserted, updated, skipped, dict(skip_reasons), len(positions),
        result["source_fills"], result["source_fundings"],
    )
    return result


def sync_pionex_trades(db: Session, days: int) -> dict[str, Any]:
    end = datetime.now(tz=UTC)
    return sync_pionex_trades_range(db, end - timedelta(days=days), end)


def sync_pionex_balance(db: Session) -> BalanceSnapshot:
    response = PionexAdapter("sync_pionex_balance").get_balance()
    balances = response.get("data", {}).get("balances", [])
    usdt = next((row for row in balances if row.get("coin") == "USDT"), None)
    if usdt is None:
        raise ValueError("Pionex futures balance response has no USDT balance")
    free = decimal_or_zero(usdt.get("free"))
    frozen = decimal_or_zero(usdt.get("frozen"))
    debts = decimal_or_zero(usdt.get("debts"))
    snapshot = BalanceSnapshot(exchange="PIONEX", total_equity=free + frozen - debts,
        total_wallet_balance=free + frozen - debts, total_available_balance=free,
        total_perp_upl=None, raw_json=response)
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def percent(numerator: Decimal, denominator: Decimal | None) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return float((numerator / denominator) * Decimal("100"))
