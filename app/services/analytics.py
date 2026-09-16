from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Integer, case, desc, func, select
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot, CloseReason, ClosedPnlRecord, TradeCategory, TradeCategoryRecord
from app.services.sync import percent


PERIOD_ALIASES = {
    "today": "today",
    "7_days": "last_7_days",
    "last_7_days": "last_7_days",
    "30_days": "last_30_days",
    "last_30_days": "last_30_days",
    "current_month": "current_month",
    "previous_month": "previous_month",
    "current_year": "current_year",
    "june_2026": "june_2026",
    "year_2026": "year_2026",
    "all": "all_time",
    "all_time": "all_time",
}


def resolve_date_range(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    today: date | None = None,
) -> tuple[datetime | None, datetime | None]:
    if date_from or date_to:
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
        return start, end

    normalized = PERIOD_ALIASES.get(period or "all_time")
    if normalized is None:
        allowed = ", ".join(sorted(PERIOD_ALIASES))
        raise ValueError(f"Unknown period. Allowed values: {allowed}")
    if normalized == "all_time":
        return None, None

    current = today or datetime.now(tz=UTC).date()
    if normalized == "today":
        start_date, end_date = current, current + timedelta(days=1)
    elif normalized == "last_7_days":
        start_date, end_date = current - timedelta(days=6), current + timedelta(days=1)
    elif normalized == "last_30_days":
        start_date, end_date = current - timedelta(days=29), current + timedelta(days=1)
    elif normalized == "current_month":
        start_date = current.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
    elif normalized == "previous_month":
        end_date = current.replace(day=1)
        start_date = (end_date - timedelta(days=1)).replace(day=1)
    elif normalized == "current_year":
        start_date, end_date = date(current.year, 1, 1), date(current.year + 1, 1, 1)
    elif normalized == "june_2026":
        start_date, end_date = date(2026, 6, 1), date(2026, 7, 1)
    else:
        start_date, end_date = date(2026, 1, 1), date(2027, 1, 1)
    return (
        datetime.combine(start_date, time.min, tzinfo=UTC),
        datetime.combine(end_date, time.min, tzinfo=UTC),
    )


def _date_conditions(start: datetime | None, end: datetime | None, exchange: str = "all") -> list:
    conditions = []
    trade_time = func.coalesce(
        ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time,
    )
    if start is not None:
        conditions.append(trade_time >= start)
    if end is not None:
        conditions.append(trade_time < end)
    if exchange.lower() != "all":
        conditions.append(ClosedPnlRecord.exchange == exchange.upper())
    return conditions


def _latest_equity(db: Session, exchange: str = "all") -> Decimal | None:
    if exchange.lower() == "all":
        return None
    return db.execute(
        select(BalanceSnapshot.total_equity).where(BalanceSnapshot.exchange == exchange.upper()).order_by(desc(BalanceSnapshot.created_at)).limit(1)
    ).scalar_one_or_none()


def overview(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> dict:
    start, end = resolve_date_range(period, date_from, date_to)
    stmt = (
        select(
            func.count(ClosedPnlRecord.id),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, ClosedPnlRecord.net_pnl), else_=0)), 0),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, -ClosedPnlRecord.net_pnl), else_=0)), 0),
            func.avg(case((ClosedPnlRecord.net_pnl > 0, ClosedPnlRecord.net_pnl))),
            func.avg(case((ClosedPnlRecord.net_pnl < 0, ClosedPnlRecord.net_pnl))),
            func.coalesce(func.sum(case((ClosedPnlRecord.close_reason == CloseReason.LIQUIDATION, 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (ClosedPnlRecord.close_reason == CloseReason.LIQUIDATION, ClosedPnlRecord.net_pnl),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .where(*_date_conditions(start, end, exchange))
    )
    row = db.execute(stmt).one()
    (
        total_trades,
        profitable,
        losing,
        gross_pnl,
        total_fees,
        net_pnl,
        gross_profit,
        gross_loss,
        average_win,
        average_loss,
        liquidation_count,
        liquidation_net_pnl,
    ) = row
    latest_equity = _latest_equity(db, exchange)

    return {
        "total_trades": total_trades,
        "profitable_trades": profitable,
        "losing_trades": losing,
        "winrate": float((profitable / total_trades) * 100) if total_trades else 0.0,
        "gross_pnl": gross_pnl,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "average_win": average_win,
        "average_loss": average_loss,
        "liquidation_count": liquidation_count,
        "liquidation_net_pnl": liquidation_net_pnl,
        "liquidation_share_pct": float((liquidation_count / total_trades) * 100) if total_trades else 0.0,
        "latest_total_equity": latest_equity,
        "roi_percent": percent(net_pnl, latest_equity),
    }


def coin_ranking(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> list[dict]:
    start, end = resolve_date_range(period, date_from, date_to)
    latest_equity = _latest_equity(db, exchange)
    rows = db.execute(
        select(
            ClosedPnlRecord.symbol,
            ClosedPnlRecord.exchange,
            func.count(ClosedPnlRecord.id).label("total_trades"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0).label("profitable_trades"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0).label("losing_trades"),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0).label("gross_pnl"),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0).label("total_fees"),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0).label("net_pnl"),
            func.coalesce(func.avg(ClosedPnlRecord.net_pnl), 0).label("avg_pnl"),
            func.avg(case((ClosedPnlRecord.net_pnl > 0, ClosedPnlRecord.net_pnl))).label("avg_win"),
            func.avg(case((ClosedPnlRecord.net_pnl < 0, ClosedPnlRecord.net_pnl))).label("avg_loss"),
            func.max(ClosedPnlRecord.net_pnl).label("best_trade"),
            func.min(ClosedPnlRecord.net_pnl).label("worst_trade"),
        )
        .where(*_date_conditions(start, end, exchange))
        .group_by(ClosedPnlRecord.exchange, ClosedPnlRecord.symbol)
        .order_by(desc("net_pnl"))
    ).all()

    result = []
    for row in rows:
        item = row._mapping
        total_trades = item["total_trades"]
        profitable = item["profitable_trades"]
        net_pnl = item["net_pnl"]
        result.append(
            {
                "symbol": item["symbol"],
                "exchange": item["exchange"],
                "total_trades": total_trades,
                "profitable_trades": profitable,
                "losing_trades": item["losing_trades"],
                "winrate": float((profitable / total_trades) * 100) if total_trades else 0.0,
                "gross_pnl": item["gross_pnl"],
                "total_fees": item["total_fees"],
                "net_pnl": net_pnl,
                "roi_percent": percent(net_pnl, latest_equity),
                "avg_pnl": item["avg_pnl"],
                "avg_win": item["avg_win"],
                "avg_loss": item["avg_loss"],
                "best_trade": item["best_trade"],
                "worst_trade": item["worst_trade"],
            }
        )
    return result


def trades_list(
    db: Session,
    symbol: str | None = None,
    category: TradeCategory | None = None,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> list[dict]:
    start, end = resolve_date_range(period, date_from, date_to)
    stmt = (
        select(ClosedPnlRecord, TradeCategoryRecord)
        .outerjoin(TradeCategoryRecord, TradeCategoryRecord.closed_pnl_record_id == ClosedPnlRecord.id)
        .order_by(desc(func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time)))
    )
    if symbol:
        stmt = stmt.where(ClosedPnlRecord.symbol == symbol.upper())
    if category:
        stmt = stmt.where(TradeCategoryRecord.category == category)
    stmt = stmt.where(*_date_conditions(start, end, exchange))

    rows = db.execute(stmt).all()
    trades = []
    for record, category_record in rows:
        trades.append(
            {
                "id": record.id,
                "exchange": record.exchange,
                "external_trade_id": record.external_trade_id,
                "external_order_id": record.external_order_id,
                "external_position_id": record.external_position_id,
                "direction": record.direction,
                "entry_time": record.entry_time,
                "exit_time": record.exit_time,
                "gross_pnl": record.gross_pnl,
                "fees": record.fees,
                "funding": record.funding,
                "close_reason": record.close_reason,
                "margin_mode": record.margin_mode,
                "trade_source": record.trade_source,
                "bot_id": record.bot_id,
                "bot_type": record.bot_type,
                "account_name": record.account_name,
                "symbol": record.symbol,
                "order_id": record.order_id,
                "side": record.side,
                "qty": record.qty,
                "closed_size": record.closed_size,
                "avg_entry_price": record.avg_entry_price,
                "avg_exit_price": record.avg_exit_price,
                "closed_pnl": record.closed_pnl,
                "total_fee": record.total_fee,
                "net_pnl": record.net_pnl,
                "leverage": record.leverage,
                "created_time": record.created_time,
                "updated_time": record.updated_time,
                "category": category_record.category if category_record else TradeCategory.UNKNOWN,
                "signal_id": category_record.signal_id if category_record else None,
                "manual_tag": category_record.manual_tag if category_record else None,
                "comment": category_record.comment if category_record else None,
            }
        )
    return trades


def _summary_values(row, latest_equity: Decimal | None) -> dict:
    total_trades, profitable, losing, gross_pnl, total_fees, net_pnl = row
    return {
        "total_trades": total_trades,
        "profitable_trades": profitable,
        "losing_trades": losing,
        "winrate": float((profitable / total_trades) * 100) if total_trades else 0.0,
        "gross_pnl": gross_pnl,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "roi_percent": percent(net_pnl, latest_equity),
    }


def monthly_summary(db: Session, year: int, exchange: str = "all") -> list[dict]:
    latest_equity = _latest_equity(db, exchange)
    trade_time = func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time)
    month_expression = func.extract("month", trade_time).cast(Integer)
    rows = db.execute(
        select(
            month_expression.label("month"),
            func.count(ClosedPnlRecord.id),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0),
        )
        .where(
            trade_time >= datetime(year, 1, 1, tzinfo=UTC),
            trade_time < datetime(year + 1, 1, 1, tzinfo=UTC),
            *_date_conditions(None, None, exchange),
        )
        .group_by(month_expression)
        .order_by(month_expression)
    ).all()
    by_month = {row[0]: row[1:] for row in rows}
    result = []
    for month in range(1, 13):
        values = by_month.get(month, (0, 0, 0, Decimal("0"), Decimal("0"), Decimal("0")))
        result.append({"month": month, **_summary_values(values, latest_equity)})
    return result


def yearly_summary(db: Session, year: int, exchange: str = "all") -> dict:
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    row = db.execute(
        select(
            func.count(ClosedPnlRecord.id),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0),
        ).where(*_date_conditions(start, end, exchange))
    ).one()
    return {"year": year, **_summary_values(row, _latest_equity(db, exchange))}


def daily_analytics(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> list[dict]:
    start, end = resolve_date_range(period, date_from, date_to)
    day = func.date(func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time))
    rows = db.execute(
        select(
            day.label("date"),
            func.count(ClosedPnlRecord.id).label("trades"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0).label("profitable"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0).label("losing"),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0).label("gross_pnl"),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0).label("total_fees"),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0).label("net_pnl"),
        )
        .where(*_date_conditions(start, end, exchange))
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        {
            "date": row.date,
            "trades": row.trades,
            "profitable_trades": row.profitable,
            "losing_trades": row.losing,
            "winrate": float((row.profitable / row.trades) * 100) if row.trades else 0.0,
            "gross_pnl": row.gross_pnl,
            "total_fees": row.total_fees,
            "net_pnl": row.net_pnl,
        }
        for row in rows
    ]


def equity_curve(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> list[dict]:
    start, end = resolve_date_range(period, date_from, date_to)
    days = daily_analytics(db, period=period, date_from=date_from, date_to=date_to, exchange=exchange)
    if not days:
        return []

    current_equity = _latest_equity(db, exchange)
    pnl_after_period = Decimal("0")
    if current_equity is not None and end is not None:
        pnl_after_period = db.execute(
            select(func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0)).where(
                func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time) >= end,
                *_date_conditions(None, None, exchange),
            )
        ).scalar_one()

    cumulative = Decimal("0")
    selected_total = sum((item["net_pnl"] for item in days), Decimal("0"))
    result = []
    for item in days:
        cumulative += item["net_pnl"]
        future_selected_pnl = selected_total - cumulative
        estimated_equity = None
        if current_equity is not None:
            estimated_equity = current_equity - pnl_after_period - future_selected_pnl
        result.append(
            {
                "date": item["date"],
                "daily_net_pnl": item["net_pnl"],
                "cumulative_net_pnl": cumulative,
                "estimated_equity": estimated_equity,
            }
        )
    return result


def direction_analytics(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> list[dict]:
    start, end = resolve_date_range(period, date_from, date_to)
    direction = case(
        (func.upper(ClosedPnlRecord.direction) == "LONG", "LONG"),
        (func.upper(ClosedPnlRecord.direction) == "SHORT", "SHORT"),
        else_="UNKNOWN",
    )
    rows = db.execute(
        select(
            direction.label("direction"),
            func.count(ClosedPnlRecord.id).label("total_trades"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl > 0, 1), else_=0)), 0).label("profitable"),
            func.coalesce(func.sum(case((ClosedPnlRecord.net_pnl < 0, 1), else_=0)), 0).label("losing"),
            func.coalesce(func.sum(ClosedPnlRecord.closed_pnl), 0).label("gross_pnl"),
            func.coalesce(func.sum(ClosedPnlRecord.total_fee), 0).label("total_fees"),
            func.coalesce(func.sum(ClosedPnlRecord.net_pnl), 0).label("net_pnl"),
            func.coalesce(func.avg(ClosedPnlRecord.net_pnl), 0).label("avg_pnl"),
            func.coalesce(func.max(ClosedPnlRecord.net_pnl), 0).label("best_trade"),
            func.coalesce(func.min(ClosedPnlRecord.net_pnl), 0).label("worst_trade"),
        )
        .where(*_date_conditions(start, end, exchange))
        .group_by(direction)
        .order_by(direction)
    ).all()
    return [
        {
            "direction": row.direction,
            "total_trades": row.total_trades,
            "profitable_trades": row.profitable,
            "losing_trades": row.losing,
            "winrate": float((row.profitable / row.total_trades) * 100) if row.total_trades else 0.0,
            "gross_pnl": row.gross_pnl,
            "total_fees": row.total_fees,
            "net_pnl": row.net_pnl,
            "avg_pnl": row.avg_pnl,
            "best_trade": row.best_trade,
            "worst_trade": row.worst_trade,
        }
        for row in rows
    ]


def _insight_decimal(value: Decimal | int | float | None = None) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _insight_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _insight_direction(value: str | None) -> str:
    normalized = (value or "").upper()
    return normalized if normalized in {"LONG", "SHORT"} else "UNKNOWN"


def _insight_close_reason(value: CloseReason | str) -> str:
    return value.value if isinstance(value, CloseReason) else str(value)


def _insight_summary(trades: list[dict]) -> dict:
    wins = [trade for trade in trades if trade["net_pnl"] > 0]
    losses = [trade for trade in trades if trade["net_pnl"] < 0]
    gross_profit = sum((trade["net_pnl"] for trade in wins), Decimal("0"))
    gross_loss = sum((-trade["net_pnl"] for trade in losses), Decimal("0"))
    return {
        "total_trades": len(trades),
        "profitable_trades": len(wins),
        "losing_trades": len(losses),
        "net_pnl": sum((trade["net_pnl"] for trade in trades), Decimal("0")),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "average_win": gross_profit / len(wins) if wins else None,
        "average_loss": -gross_loss / len(losses) if losses else None,
        "win_rate_pct": float((len(wins) / len(trades)) * 100) if trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
    }


def _insight_coin_groups(trades: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for trade in trades:
        grouped.setdefault((trade["exchange"], trade["symbol"]), []).append(trade)
    return [
        {"exchange": exchange, "symbol": symbol, **_insight_summary(group_trades)}
        for (exchange, symbol), group_trades in grouped.items()
    ]


def _insight_direction_groups(trades: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for trade in trades:
        direction = trade["direction"]
        if direction in {"LONG", "SHORT"}:
            grouped.setdefault(direction, []).append(trade)
    return [
        {"direction": direction, **_insight_summary(group_trades)}
        for direction, group_trades in grouped.items()
    ]


def _insight_exchange_groups(trades: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for trade in trades:
        grouped.setdefault(trade["exchange"], []).append(trade)
    return [
        {"exchange": exchange, **_insight_summary(group_trades)}
        for exchange, group_trades in grouped.items()
    ]


def _insight_period_groups(trades: list[dict], monthly: bool = False) -> list[dict]:
    grouped: dict[date, list[dict]] = {}
    for trade in trades:
        day = trade["trade_time"].date()
        bucket = day.replace(day=1) if monthly else day
        grouped.setdefault(bucket, []).append(trade)
    return [
        {"date": bucket, "trades": len(group_trades), "net_pnl": _insight_summary(group_trades)["net_pnl"]}
        for bucket, group_trades in grouped.items()
    ]


def _insight_streak(trades: list[dict], outcome: str) -> dict | None:
    longest: list[dict] = []
    current: list[dict] = []
    for trade in sorted(trades, key=lambda item: (item["trade_time"], item["id"])):
        matches = trade["net_pnl"] > 0 if outcome == "win" else trade["net_pnl"] < 0
        if matches:
            current.append(trade)
            continue
        if current:
            if not longest or len(current) > len(longest):
                longest = current
            current = []
    if current and (not longest or len(current) > len(longest)):
        longest = current
    if not longest:
        return None
    return {
        "trade_count": len(longest),
        "net_pnl": sum((trade["net_pnl"] for trade in longest), Decimal("0")),
        "started_at": longest[0]["trade_time"],
        "ended_at": longest[-1]["trade_time"],
        "first_trade_id": longest[0]["id"],
        "last_trade_id": longest[-1]["id"],
    }


def _insight_concentration(groups: list[dict], amount_key: str) -> dict:
    eligible = [group for group in groups if group[amount_key] > 0]
    ordered = sorted(eligible, key=lambda item: (-item[amount_key], item["exchange"], item["symbol"]))
    selected = ordered[:3]
    gross_amount = sum((group[amount_key] for group in selected), Decimal("0"))
    total_gross_amount = sum((group[amount_key] for group in eligible), Decimal("0"))
    return {
        "group_limit": 3,
        "groups": selected,
        "gross_amount": gross_amount,
        "total_gross_amount": total_gross_amount,
        "share_pct": float((gross_amount / total_gross_amount) * 100) if total_gross_amount else None,
    }


def _insight_decimal_text(value: Decimal | int | float) -> str:
    return format(_insight_decimal(value), "f")


def _insight_money(value: Decimal) -> str:
    sign = "−" if value < 0 else "+" if value > 0 else ""
    return f"{sign}{format(abs(value), ',.2f').replace(',', ' ').replace('.', ',')}"


def _insight_evidence(
    key: str,
    label: str,
    value: Decimal | int | float,
    unit: str,
    *,
    numerator: Decimal | int | float | None = None,
    denominator: Decimal | int | float | None = None,
    dimensions: dict[str, str] | None = None,
) -> dict:
    return {
        "key": key,
        "label": label,
        "value": _insight_decimal_text(value),
        "unit": unit,
        "numerator": _insight_decimal_text(numerator) if numerator is not None else None,
        "denominator": _insight_decimal_text(denominator) if denominator is not None else None,
        "dimensions": dimensions or {},
    }


def _insight_item(
    insight_id: str,
    section: str,
    text: str,
    secondary_text: str | None,
    evidence: list[dict],
) -> dict:
    return {
        "id": insight_id,
        "section": section,
        "text": text,
        "secondary_text": secondary_text,
        "evidence": evidence,
    }


def _insight_card_candidates(facts: dict) -> list[dict]:
    losses = facts["losses"]
    strengths = facts["strengths"]
    loss_cards: list[dict] = []
    strength_cards: list[dict] = []

    liquidations = losses["liquidations"]
    if liquidations["count"] and liquidations["loss_share_pct"] is not None:
        loss_cards.append(
            _insight_item(
                "loss.liquidation_loss_share",
                "losses",
                f"Ликвидации составили {liquidations['loss_share_pct']:.2f}% валового убытка.",
                f"{liquidations['count']} сделок; net PnL {_insight_money(liquidations['net_pnl'])}.",
                [
                    _insight_evidence(
                        "liquidation_loss_share_pct",
                        "Доля валового убытка",
                        liquidations["loss_share_pct"],
                        "percent",
                        numerator=liquidations["gross_loss"],
                        denominator=losses["loss_concentration"]["total_gross_amount"],
                    )
                ],
            )
        )

    worst_coin = losses["worst_coin_group"]
    if worst_coin:
        loss_cards.append(
            _insight_item(
                "loss.worst_coin_group",
                "losses",
                f"Наибольший отрицательный net PnL: {worst_coin['symbol']} — {_insight_money(worst_coin['net_pnl'])}.",
                f"{worst_coin['exchange']} · {worst_coin['total_trades']} сделок.",
                [
                    _insight_evidence(
                        "coin_group_net_pnl",
                        "Net PnL",
                        worst_coin["net_pnl"],
                        "pnl",
                        dimensions={"exchange": worst_coin["exchange"], "symbol": worst_coin["symbol"]},
                    )
                ],
            )
        )

    worst_direction = losses["worst_direction"]
    best_direction = strengths["best_direction"]
    if worst_direction and best_direction:
        loss_cards.append(
            _insight_item(
                "loss.worst_direction",
                "losses",
                f"{worst_direction['direction']} дал {_insight_money(worst_direction['net_pnl'])}; {best_direction['direction']} — {_insight_money(best_direction['net_pnl'])}.",
                f"{worst_direction['total_trades']} и {best_direction['total_trades']} сделок соответственно.",
                [
                    _insight_evidence(
                        "direction_net_pnl",
                        "Net PnL худшего направления",
                        worst_direction["net_pnl"],
                        "pnl",
                        dimensions={"direction": worst_direction["direction"]},
                    )
                ],
            )
        )

    worst_exchange = losses["worst_exchange"]
    best_exchange = strengths["best_exchange"]
    if worst_exchange and best_exchange:
        loss_cards.append(
            _insight_item(
                "loss.worst_exchange",
                "losses",
                f"{worst_exchange['exchange']} дал {_insight_money(worst_exchange['net_pnl'])}; {best_exchange['exchange']} — {_insight_money(best_exchange['net_pnl'])}.",
                f"{worst_exchange['total_trades']} и {best_exchange['total_trades']} сделок соответственно.",
                [
                    _insight_evidence(
                        "exchange_net_pnl",
                        "Net PnL худшей биржи",
                        worst_exchange["net_pnl"],
                        "pnl",
                        dimensions={"exchange": worst_exchange["exchange"]},
                    )
                ],
            )
        )

    loss_concentration = losses["loss_concentration"]
    if loss_concentration["share_pct"] is not None:
        symbols = ", ".join(group["symbol"] for group in loss_concentration["groups"])
        loss_cards.append(
            _insight_item(
                "loss.concentration",
                "losses",
                f"Топ-3 coin-группы дали {loss_concentration['share_pct']:.2f}% валового убытка.",
                symbols,
                [
                    _insight_evidence(
                        "loss_concentration_pct",
                        "Концентрация валового убытка",
                        loss_concentration["share_pct"],
                        "percent",
                        numerator=loss_concentration["gross_amount"],
                        denominator=loss_concentration["total_gross_amount"],
                    )
                ],
            )
        )

    losing_streak = losses["losing_streak"]
    if losing_streak and losing_streak["trade_count"] >= 2:
        loss_cards.append(
            _insight_item(
                "loss.losing_streak",
                "losses",
                f"Максимальная серия потерь — {losing_streak['trade_count']} сделок.",
                f"Суммарный PnL {_insight_money(losing_streak['net_pnl'])}.",
                [
                    _insight_evidence("losing_streak_trades", "Сделок в серии", losing_streak["trade_count"], "trades")
                ],
            )
        )

    worst_day = losses["worst_day"]
    if worst_day:
        loss_cards.append(
            _insight_item(
                "loss.worst_day",
                "losses",
                f"Худший день — {worst_day['date'].isoformat()}: {_insight_money(worst_day['net_pnl'])}.",
                f"{worst_day['trades']} сделок.",
                [
                    _insight_evidence("worst_day_net_pnl", "Net PnL дня", worst_day["net_pnl"], "pnl", dimensions={"date": worst_day["date"].isoformat()})
                ],
            )
        )

    best_coin = strengths["best_coin_group"]
    if best_coin:
        strength_cards.append(
            _insight_item(
                "strength.best_coin_group",
                "strengths",
                f"Наибольший положительный net PnL: {best_coin['symbol']} — {_insight_money(best_coin['net_pnl'])}.",
                f"{best_coin['exchange']} · {best_coin['total_trades']} сделок.",
                [
                    _insight_evidence(
                        "coin_group_net_pnl",
                        "Net PnL",
                        best_coin["net_pnl"],
                        "pnl",
                        dimensions={"exchange": best_coin["exchange"], "symbol": best_coin["symbol"]},
                    )
                ],
            )
        )

    if best_direction and worst_direction:
        strength_cards.append(
            _insight_item(
                "strength.best_direction",
                "strengths",
                f"{best_direction['direction']} показывает лучший net PnL: {_insight_money(best_direction['net_pnl'])}.",
                f"{best_direction['total_trades']} сделок; win rate {best_direction['win_rate_pct']:.2f}%.",
                [
                    _insight_evidence(
                        "direction_net_pnl",
                        "Net PnL направления",
                        best_direction["net_pnl"],
                        "pnl",
                        dimensions={"direction": best_direction["direction"]},
                    )
                ],
            )
        )

    if best_exchange and worst_exchange:
        strength_cards.append(
            _insight_item(
                "strength.best_exchange",
                "strengths",
                f"{best_exchange['exchange']} показывает лучший net PnL: {_insight_money(best_exchange['net_pnl'])}.",
                f"{best_exchange['total_trades']} сделок.",
                [
                    _insight_evidence(
                        "exchange_net_pnl",
                        "Net PnL биржи",
                        best_exchange["net_pnl"],
                        "pnl",
                        dimensions={"exchange": best_exchange["exchange"]},
                    )
                ],
            )
        )

    profit_concentration = strengths["profit_concentration"]
    if profit_concentration["share_pct"] is not None:
        symbols = ", ".join(group["symbol"] for group in profit_concentration["groups"])
        strength_cards.append(
            _insight_item(
                "strength.profit_concentration",
                "strengths",
                f"Топ-3 coin-группы дали {profit_concentration['share_pct']:.2f}% валовой прибыли.",
                symbols,
                [
                    _insight_evidence(
                        "profit_concentration_pct",
                        "Концентрация валовой прибыли",
                        profit_concentration["share_pct"],
                        "percent",
                        numerator=profit_concentration["gross_amount"],
                        denominator=profit_concentration["total_gross_amount"],
                    )
                ],
            )
        )

    winning_streak = strengths["winning_streak"]
    if winning_streak and winning_streak["trade_count"] >= 2:
        strength_cards.append(
            _insight_item(
                "strength.winning_streak",
                "strengths",
                f"Максимальная серия побед — {winning_streak['trade_count']} сделок.",
                f"Суммарный PnL {_insight_money(winning_streak['net_pnl'])}.",
                [
                    _insight_evidence("winning_streak_trades", "Сделок в серии", winning_streak["trade_count"], "trades")
                ],
            )
        )

    best_day = strengths["best_day"]
    if best_day:
        strength_cards.append(
            _insight_item(
                "strength.best_day",
                "strengths",
                f"Лучший день — {best_day['date'].isoformat()}: {_insight_money(best_day['net_pnl'])}.",
                f"{best_day['trades']} сделок.",
                [
                    _insight_evidence("best_day_net_pnl", "Net PnL дня", best_day["net_pnl"], "pnl", dimensions={"date": best_day["date"].isoformat()})
                ],
            )
        )

    return [*loss_cards[:5], *strength_cards[:5]]


def analytics_insights(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> dict:
    start, end = resolve_date_range(period, date_from, date_to)
    trade_time = func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time)
    rows = db.execute(
        select(
            ClosedPnlRecord.id,
            ClosedPnlRecord.exchange,
            ClosedPnlRecord.symbol,
            ClosedPnlRecord.direction,
            ClosedPnlRecord.net_pnl,
            ClosedPnlRecord.close_reason,
            trade_time.label("trade_time"),
        ).where(*_date_conditions(start, end, exchange))
    ).mappings().all()
    trades = [
        {
            "id": row["id"],
            "exchange": row["exchange"],
            "symbol": row["symbol"],
            "direction": _insight_direction(row["direction"]),
            "net_pnl": _insight_decimal(row["net_pnl"]),
            "close_reason": _insight_close_reason(row["close_reason"]),
            "trade_time": _insight_datetime(row["trade_time"]),
        }
        for row in rows
    ]
    summary = _insight_summary(trades)
    coin_groups = _insight_coin_groups(trades)
    direction_groups = _insight_direction_groups(trades)
    exchange_groups = _insight_exchange_groups(trades)
    worst_coin = next((group for group in sorted(coin_groups, key=lambda item: (item["net_pnl"], item["exchange"], item["symbol"])) if group["net_pnl"] < 0), None)
    best_coin = next((group for group in sorted(coin_groups, key=lambda item: (-item["net_pnl"], item["exchange"], item["symbol"])) if group["net_pnl"] > 0), None)
    comparable_directions = len(direction_groups) >= 2
    comparable_exchanges = len(exchange_groups) >= 2
    worst_direction = next((group for group in sorted(direction_groups, key=lambda item: (item["net_pnl"], item["direction"])) if group["net_pnl"] < 0), None) if comparable_directions else None
    best_direction = next((group for group in sorted(direction_groups, key=lambda item: (-item["net_pnl"], item["direction"])) if group["net_pnl"] > 0), None) if comparable_directions else None
    worst_exchange = next((group for group in sorted(exchange_groups, key=lambda item: (item["net_pnl"], item["exchange"])) if group["net_pnl"] < 0), None) if comparable_exchanges else None
    best_exchange = next((group for group in sorted(exchange_groups, key=lambda item: (-item["net_pnl"], item["exchange"])) if group["net_pnl"] > 0), None) if comparable_exchanges else None
    losing_trades = sorted((trade for trade in trades if trade["net_pnl"] < 0), key=lambda item: (item["net_pnl"], item["id"]))[:3]
    winning_trades = sorted((trade for trade in trades if trade["net_pnl"] > 0), key=lambda item: (-item["net_pnl"], item["id"]))[:3]
    daily = _insight_period_groups(trades)
    monthly = _insight_period_groups(trades, monthly=True)
    worst_day = next((item for item in sorted(daily, key=lambda item: (item["net_pnl"], item["date"])) if item["net_pnl"] < 0), None)
    best_day = next((item for item in sorted(daily, key=lambda item: (-item["net_pnl"], item["date"])) if item["net_pnl"] > 0), None)
    worst_month = next((item for item in sorted(monthly, key=lambda item: (item["net_pnl"], item["date"])) if item["net_pnl"] < 0), None)
    best_month = next((item for item in sorted(monthly, key=lambda item: (-item["net_pnl"], item["date"])) if item["net_pnl"] > 0), None)
    liquidation_trades = [trade for trade in trades if trade["close_reason"] == CloseReason.LIQUIDATION.value]
    liquidation_net_pnl = sum((trade["net_pnl"] for trade in liquidation_trades), Decimal("0"))
    liquidation_gross_loss = sum((-trade["net_pnl"] for trade in liquidation_trades if trade["net_pnl"] < 0), Decimal("0"))
    loss_concentration = _insight_concentration(coin_groups, "gross_loss")
    profit_concentration = _insight_concentration(coin_groups, "gross_profit")
    normalized_period = "custom" if date_from or date_to else PERIOD_ALIASES[period or "all_time"]
    facts = {
        "scope": {
            "period": normalized_period,
            "date_from": date_from,
            "date_to": date_to,
            "exchange": "ALL" if exchange.lower() == "all" else exchange.upper(),
            "total_trades": summary["total_trades"],
        },
        "losses": {
            "average_loss": {"value": summary["average_loss"], "trade_count": summary["losing_trades"]} if summary["average_loss"] is not None else None,
            "worst_coin_group": worst_coin,
            "worst_direction": worst_direction,
            "worst_exchange": worst_exchange,
            "largest_losing_trades": losing_trades,
            "losing_streak": _insight_streak(trades, "loss"),
            "loss_concentration": loss_concentration,
            "liquidations": {
                "count": len(liquidation_trades),
                "net_pnl": liquidation_net_pnl,
                "gross_loss": liquidation_gross_loss,
                "trade_share_pct": float((len(liquidation_trades) / summary["total_trades"]) * 100) if summary["total_trades"] else 0.0,
                "loss_share_pct": float((liquidation_gross_loss / summary["gross_loss"]) * 100) if summary["gross_loss"] else None,
            },
            "worst_day": worst_day,
            "worst_month": worst_month,
        },
        "strengths": {
            "average_win": {"value": summary["average_win"], "trade_count": summary["profitable_trades"]} if summary["average_win"] is not None else None,
            "win_rate_pct": summary["win_rate_pct"],
            "profit_factor": summary["profit_factor"],
            "best_coin_group": best_coin,
            "best_direction": best_direction,
            "best_exchange": best_exchange,
            "largest_winning_trades": winning_trades,
            "winning_streak": _insight_streak(trades, "win"),
            "profit_concentration": profit_concentration,
            "best_day": best_day,
            "best_month": best_month,
        },
    }
    return {**facts, "insights": _insight_card_candidates(facts)}


# Recommendation confidence is deliberately based only on the observed affected sample.
# It is an evidence-size label, not a statistical-significance claim.
RECOMMENDATION_LOW_MAX_TRADES = 4
RECOMMENDATION_MEDIUM_MAX_TRADES = 19
LOSS_CONCENTRATION_ACTIONABLE_PCT = Decimal("50")
DIRECTION_ACTIONABLE_LOSS_SHARE = Decimal("0.10")
LOW_SAMPLE_DISCLAIMER = (
    "Выборка недостаточна для вывода о качестве торговли этим инструментом/сценарием."
)


def _recommendation_confidence(sample_size: int) -> str:
    if sample_size <= RECOMMENDATION_LOW_MAX_TRADES:
        return "LOW"
    if sample_size <= RECOMMENDATION_MEDIUM_MAX_TRADES:
        return "MEDIUM"
    return "HIGH"


def _recommendation_pct(numerator: Decimal, denominator: Decimal, *, absolute_denominator: bool = False) -> float | None:
    denominator = abs(denominator) if absolute_denominator else denominator
    return float((numerator / denominator) * 100) if denominator else None


def _recommendation_materially_negative(group: dict, gross_loss: Decimal) -> bool:
    return bool(
        group["net_pnl"] < 0
        and gross_loss
        and (-group["net_pnl"] / gross_loss) >= DIRECTION_ACTIONABLE_LOSS_SHARE
    )


def _recommendation_group(
    trades: list[dict],
    actual_net_pnl: Decimal,
    *,
    exchange: str | None = None,
    symbol: str | None = None,
    direction: str | None = None,
) -> dict:
    summary = _insight_summary(trades)
    return {
        "exchange": exchange,
        "symbol": symbol,
        "direction": direction,
        "total_trades": summary["total_trades"],
        "win_rate_pct": summary["win_rate_pct"],
        "net_pnl": summary["net_pnl"],
        "average_net_pnl": summary["net_pnl"] / summary["total_trades"] if summary["total_trades"] else Decimal("0"),
        "contribution_pct": _recommendation_pct(summary["net_pnl"], actual_net_pnl),
    }


def _recommendation_groups(trades: list[dict], actual_net_pnl: Decimal, key: str) -> list[dict]:
    grouped: dict[object, list[dict]] = {}
    for trade in trades:
        if key == "direction":
            value = trade["direction"]
            if value not in {"LONG", "SHORT"}:
                continue
        elif key == "exchange":
            value = trade["exchange"]
        else:
            value = (trade["exchange"], trade["symbol"])
        grouped.setdefault(value, []).append(trade)

    result: list[dict] = []
    for value, group_trades in grouped.items():
        if key == "direction":
            result.append(_recommendation_group(group_trades, actual_net_pnl, direction=value))
        elif key == "exchange":
            result.append(_recommendation_group(group_trades, actual_net_pnl, exchange=value))
        else:
            exchange, symbol = value
            result.append(_recommendation_group(group_trades, actual_net_pnl, exchange=exchange, symbol=symbol))
    return result


def _recommendation_confidence_label(confidence: str) -> str:
    return {"LOW": "Малая выборка", "MEDIUM": "Средняя выборка", "HIGH": "Большая выборка"}[confidence]


def _recommendation_trade_count_text(sample_size: int) -> str:
    last_two = sample_size % 100
    last_one = sample_size % 10
    if last_two not in {11, 12, 13, 14} and last_one == 1:
        word = "сделка"
    elif last_two not in {11, 12, 13, 14} and last_one in {2, 3, 4}:
        word = "сделки"
    else:
        word = "сделок"
    return f"{sample_size} {word}"


def _recommendation_historical_interpretation(
    subject: str,
    sample_size: int,
    actual_net_pnl: Decimal,
    hypothetical_net_pnl: Decimal,
    *,
    observed_label: str | None = None,
    observed_metrics: str | None = None,
) -> str:
    observed = (
        f"{observed_label or f'В выбранной истории {subject}'}: "
        f"{_recommendation_trade_count_text(sample_size)}"
    )
    if observed_metrics:
        observed += f", {observed_metrics}"

    result = (
        f"{observed}. Контрфактический расчёт без {subject}: net PnL "
        f"{_insight_money(hypothetical_net_pnl)} вместо {_insight_money(actual_net_pnl)}; "
        f"историческая разница {_insight_money(hypothetical_net_pnl - actual_net_pnl)}."
    )
    if _recommendation_confidence(sample_size) == "LOW":
        result += f" {LOW_SAMPLE_DISCLAIMER}"
    return result


def _recommendation_item(
    recommendation_id: str,
    recommendation_type: str,
    title: str,
    summary: str,
    interpretation: str,
    evidence: dict,
    actual_net_pnl: Decimal,
    hypothetical_net_pnl: Decimal,
    sample_size: int,
    total_trades: int,
    show_affected_trade_pct: bool = False,
) -> dict:
    delta = hypothetical_net_pnl - actual_net_pnl
    confidence = _recommendation_confidence(sample_size)
    return {
        "id": recommendation_id,
        "type": recommendation_type,
        "title": title,
        "summary": summary,
        "interpretation": interpretation,
        "evidence": evidence,
        "actual_net_pnl": actual_net_pnl,
        "hypothetical_net_pnl": hypothetical_net_pnl,
        "delta_net_pnl": delta,
        "improvement_pct_of_actual": _recommendation_pct(delta, actual_net_pnl, absolute_denominator=True),
        "affected_trade_pct": float((sample_size / total_trades) * 100) if show_affected_trade_pct and total_trades else None,
        "confidence": confidence,
        "confidence_label": _recommendation_confidence_label(confidence),
        "sample_size": sample_size,
    }


def analytics_recommendations(
    db: Session,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
) -> dict:
    """Build deterministic historical counterfactuals for the same scope as analytics insights."""
    start, end = resolve_date_range(period, date_from, date_to)
    trade_time = func.coalesce(ClosedPnlRecord.exit_time, ClosedPnlRecord.updated_time, ClosedPnlRecord.created_time)
    rows = db.execute(
        select(
            ClosedPnlRecord.id,
            ClosedPnlRecord.exchange,
            ClosedPnlRecord.symbol,
            ClosedPnlRecord.direction,
            ClosedPnlRecord.net_pnl,
            ClosedPnlRecord.closed_pnl,
            ClosedPnlRecord.total_fee,
            ClosedPnlRecord.close_reason,
            trade_time.label("trade_time"),
        ).where(*_date_conditions(start, end, exchange))
    ).mappings().all()
    trades = [
        {
            "id": row["id"],
            "exchange": row["exchange"],
            "symbol": row["symbol"],
            "direction": _insight_direction(row["direction"]),
            "net_pnl": _insight_decimal(row["net_pnl"]),
            "gross_pnl": _insight_decimal(row["closed_pnl"]),
            "total_fee": _insight_decimal(row["total_fee"]),
            "close_reason": _insight_close_reason(row["close_reason"]),
            "trade_time": _insight_datetime(row["trade_time"]),
        }
        for row in rows
    ]
    summary = _insight_summary(trades)
    actual_net_pnl = summary["net_pnl"]
    total_fees = sum((trade["total_fee"] for trade in trades), Decimal("0"))
    gross_pnl = sum((trade["gross_pnl"] for trade in trades), Decimal("0"))

    directions = sorted(_recommendation_groups(trades, actual_net_pnl, "direction"), key=lambda item: item["direction"] or "")
    exchanges = sorted(_recommendation_groups(trades, actual_net_pnl, "exchange"), key=lambda item: item["exchange"] or "")
    coin_groups = _recommendation_groups(trades, actual_net_pnl, "coin")
    worst_coin_groups = sorted(
        (group for group in coin_groups if group["net_pnl"] < 0),
        key=lambda item: (item["net_pnl"], item["exchange"] or "", item["symbol"] or ""),
    )[:3]
    best_coin_groups = sorted(
        (group for group in coin_groups if group["net_pnl"] > 0),
        key=lambda item: (-item["net_pnl"], item["exchange"] or "", item["symbol"] or ""),
    )[:3]

    liquidation_trades = [trade for trade in trades if trade["close_reason"] == CloseReason.LIQUIDATION.value]
    liquidation_net_pnl = sum((trade["net_pnl"] for trade in liquidation_trades), Decimal("0"))
    liquidation_hypothetical = actual_net_pnl - liquidation_net_pnl

    losing_trades = sorted((trade for trade in trades if trade["net_pnl"] < 0), key=lambda item: (item["net_pnl"], item["id"]))
    total_gross_loss = sum((-trade["net_pnl"] for trade in losing_trades), Decimal("0"))

    def top_loss(limit: int) -> tuple[Decimal, float | None, int]:
        selected = losing_trades[:limit]
        amount = sum((-trade["net_pnl"] for trade in selected), Decimal("0"))
        return amount, _recommendation_pct(amount, total_gross_loss), len(selected)

    top_1_amount, top_1_share, _ = top_loss(1)
    top_3_amount, top_3_share, top_3_count = top_loss(3)
    top_5_amount, top_5_share, _ = top_loss(5)
    loss_concentration = {
        "total_gross_loss": total_gross_loss,
        "top_1_gross_loss": top_1_amount,
        "top_1_share_pct": top_1_share,
        "top_3_gross_loss": top_3_amount,
        "top_3_share_pct": top_3_share,
        "top_5_gross_loss": top_5_amount,
        "top_5_share_pct": top_5_share,
        "top_3_trade_count": top_3_count,
    }
    fees = {
        "total_fees": total_fees,
        "fees_to_gross_profit_pct": _recommendation_pct(total_fees, summary["gross_profit"]),
        "fees_to_absolute_gross_pnl_pct": _recommendation_pct(total_fees, gross_pnl, absolute_denominator=True),
        "average_fee_per_trade": total_fees / len(trades) if trades else None,
        "hypothetical_net_pnl_without_fees": actual_net_pnl + total_fees,
        "delta_net_pnl": total_fees,
    }

    recommendations: list[dict] = []
    if liquidation_trades and liquidation_net_pnl < 0:
        recommendations.append(
            _recommendation_item(
                "recommendation.liquidation_exclusion",
                "LIQUIDATION_EXCLUSION",
                "Влияние ликвидационных сделок",
                f"На выбранной истории без ликвидационных сделок net PnL был бы {_insight_money(liquidation_hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                _recommendation_historical_interpretation(
                    "ликвидационных сделок",
                    len(liquidation_trades),
                    actual_net_pnl,
                    liquidation_hypothetical,
                    observed_label="Ликвидационные сделки в выбранной истории",
                    observed_metrics=f"net PnL {_insight_money(liquidation_net_pnl)}",
                ),
                {
                    "metric": "liquidation_net_pnl",
                    "affected_trade_count": len(liquidation_trades),
                    "affected_net_pnl": liquidation_net_pnl,
                    "dimensions": {"close_reason": CloseReason.LIQUIDATION.value},
                },
                actual_net_pnl,
                liquidation_hypothetical,
                len(liquidation_trades),
                len(trades),
            )
        )

    if len(directions) >= 2:
        worst_direction = next((item for item in sorted(directions, key=lambda group: (group["net_pnl"], group["direction"] or "")) if item["net_pnl"] < 0), None)
        if worst_direction and _recommendation_materially_negative(worst_direction, summary["gross_loss"]):
            hypothetical = actual_net_pnl - worst_direction["net_pnl"]
            recommendations.append(
                _recommendation_item(
                    f"recommendation.direction_exclusion.{worst_direction['direction'].lower()}",
                    "DIRECTION_EXCLUSION",
                    f"Результаты {worst_direction['direction']}-сделок",
                    f"На выбранной истории без {worst_direction['direction']} net PnL был бы {_insight_money(hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                    _recommendation_historical_interpretation(
                        f"{worst_direction['direction']}-сделок",
                        worst_direction["total_trades"],
                        actual_net_pnl,
                        hypothetical,
                        observed_label=f"Результаты {worst_direction['direction']}-сделок в выбранной истории",
                        observed_metrics=(
                            f"win rate {worst_direction['win_rate_pct']:.2f}%, "
                            f"net PnL {_insight_money(worst_direction['net_pnl'])}, "
                            f"средний net PnL {_insight_money(worst_direction['average_net_pnl'])}"
                        ),
                    ),
                    {
                        "metric": "direction_net_pnl",
                        "affected_trade_count": worst_direction["total_trades"],
                        "affected_net_pnl": worst_direction["net_pnl"],
                        "contribution_pct": worst_direction["contribution_pct"],
                        "win_rate_pct": worst_direction["win_rate_pct"],
                        "average_net_pnl": worst_direction["average_net_pnl"],
                        "dimensions": {"direction": worst_direction["direction"]},
                    },
                    actual_net_pnl,
                    hypothetical,
                    worst_direction["total_trades"],
                    len(trades),
                    True,
                )
            )

    if len(exchanges) >= 2:
        worst_exchange = next((item for item in sorted(exchanges, key=lambda group: (group["net_pnl"], group["exchange"] or "")) if item["net_pnl"] < 0), None)
        if worst_exchange:
            hypothetical = actual_net_pnl - worst_exchange["net_pnl"]
            recommendations.append(
                _recommendation_item(
                    f"recommendation.exchange_exclusion.{worst_exchange['exchange'].lower()}",
                    "EXCHANGE_EXCLUSION",
                    f"Влияние сделок на {worst_exchange['exchange']}",
                    f"На выбранной истории без сделок {worst_exchange['exchange']} net PnL был бы {_insight_money(hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                    _recommendation_historical_interpretation(
                        f"сделок на {worst_exchange['exchange']}",
                        worst_exchange["total_trades"],
                        actual_net_pnl,
                        hypothetical,
                        observed_label=f"Сделки на {worst_exchange['exchange']} в выбранной истории",
                        observed_metrics=(
                            f"win rate {worst_exchange['win_rate_pct']:.2f}%, "
                            f"net PnL {_insight_money(worst_exchange['net_pnl'])}, "
                            f"средний net PnL {_insight_money(worst_exchange['average_net_pnl'])}"
                        ),
                    ),
                    {
                        "metric": "exchange_net_pnl",
                        "affected_trade_count": worst_exchange["total_trades"],
                        "affected_net_pnl": worst_exchange["net_pnl"],
                        "contribution_pct": worst_exchange["contribution_pct"],
                        "win_rate_pct": worst_exchange["win_rate_pct"],
                        "average_net_pnl": worst_exchange["average_net_pnl"],
                        "dimensions": {"exchange": worst_exchange["exchange"]},
                    },
                    actual_net_pnl,
                    hypothetical,
                    worst_exchange["total_trades"],
                    len(trades),
                    True,
                )
            )

    for group in worst_coin_groups:
        hypothetical = actual_net_pnl - group["net_pnl"]
        recommendations.append(
            _recommendation_item(
                f"recommendation.coin_group_exclusion.{group['exchange'].lower()}.{group['symbol'].lower()}",
                "COIN_GROUP_EXCLUSION",
                f"Влияние {group['symbol']} · {group['exchange']}",
                f"На выбранной истории без {group['symbol']} на {group['exchange']} net PnL был бы {_insight_money(hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                _recommendation_historical_interpretation(
                    f"сделок {group['symbol']} на {group['exchange']}",
                    group["total_trades"],
                    actual_net_pnl,
                    hypothetical,
                    observed_label=f"Сделки {group['symbol']} · {group['exchange']} в выбранной истории",
                    observed_metrics=(
                        f"win rate {group['win_rate_pct']:.2f}%, net PnL {_insight_money(group['net_pnl'])}, "
                        f"средний net PnL {_insight_money(group['average_net_pnl'])}"
                    ),
                ),
                {
                    "metric": "coin_group_net_pnl",
                    "affected_trade_count": group["total_trades"],
                    "affected_net_pnl": group["net_pnl"],
                    "contribution_pct": group["contribution_pct"],
                    "win_rate_pct": group["win_rate_pct"],
                    "average_net_pnl": group["average_net_pnl"],
                    "dimensions": {"exchange": group["exchange"], "symbol": group["symbol"]},
                },
                actual_net_pnl,
                hypothetical,
                group["total_trades"],
                len(trades),
                True,
            )
        )

    if top_3_share is not None and top_3_share >= float(LOSS_CONCENTRATION_ACTIONABLE_PCT):
        hypothetical = actual_net_pnl + top_3_amount
        recommendations.append(
            _recommendation_item(
                "recommendation.loss_concentration.top_3",
                "LOSS_CONCENTRATION",
                "Влияние крупнейших убытков",
                f"На выбранной истории без {top_3_count} крупнейших убыточных сделок net PnL был бы {_insight_money(hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                _recommendation_historical_interpretation(
                    f"{top_3_count} крупнейших убыточных сделок",
                    top_3_count,
                    actual_net_pnl,
                    hypothetical,
                    observed_label="Крупнейшие убыточные сделки в выбранной истории",
                    observed_metrics=f"доля валового убытка {top_3_share:.2f}%",
                ),
                {
                    "metric": "top_3_loss_concentration",
                    "affected_trade_count": top_3_count,
                    "affected_net_pnl": -top_3_amount,
                    "top_1_loss_share_pct": top_1_share,
                    "top_3_loss_share_pct": top_3_share,
                    "top_5_loss_share_pct": top_5_share,
                    "dimensions": {"threshold_pct": format(LOSS_CONCENTRATION_ACTIONABLE_PCT, "f")},
                },
                actual_net_pnl,
                hypothetical,
                top_3_count,
                len(trades),
            )
        )

    if total_fees > 0:
        hypothetical = actual_net_pnl + total_fees
        recommendations.append(
            _recommendation_item(
                "recommendation.fees_impact",
                "FEES_IMPACT",
                "Влияние комиссий",
                f"На выбранной истории до учёта комиссий net PnL был бы {_insight_money(hypothetical)} вместо {_insight_money(actual_net_pnl)}.",
                _recommendation_historical_interpretation(
                    "учёта комиссий",
                    len(trades),
                    actual_net_pnl,
                    hypothetical,
                    observed_label="Комиссии по сделкам в выбранной истории",
                    observed_metrics=f"сумма комиссий {_insight_money(total_fees)}",
                ),
                {
                    "metric": "total_fees",
                    "affected_trade_count": len(trades),
                    "total_fees": total_fees,
                    "gross_profit": summary["gross_profit"],
                    "absolute_gross_pnl": abs(gross_pnl),
                    "dimensions": {},
                },
                actual_net_pnl,
                hypothetical,
                len(trades),
                len(trades),
            )
        )

    recommendations.sort(key=lambda item: (-(item["delta_net_pnl"] or Decimal("0")), item["id"]))
    normalized_period = "custom" if date_from or date_to else PERIOD_ALIASES[period or "all_time"]
    return {
        "scope": {
            "period": normalized_period,
            "date_from": date_from,
            "date_to": date_to,
            "exchange": "ALL" if exchange.lower() == "all" else exchange.upper(),
            "total_trades": summary["total_trades"],
        },
        "facts": {
            "actual_net_pnl": actual_net_pnl,
            "liquidations": {
                "count": len(liquidation_trades),
                "net_pnl": liquidation_net_pnl,
                "hypothetical_net_pnl": liquidation_hypothetical,
                "delta_net_pnl": liquidation_hypothetical - actual_net_pnl,
                "improvement_pct_of_actual": _recommendation_pct(liquidation_hypothetical - actual_net_pnl, actual_net_pnl, absolute_denominator=True),
            },
            "directions": directions,
            "exchanges": exchanges,
            "worst_coin_groups": worst_coin_groups,
            "best_coin_groups": best_coin_groups,
            "loss_concentration": loss_concentration,
            "fees": fees,
        },
        "recommendations": recommendations,
    }


def update_trade_category(
    db: Session,
    trade_id: int,
    category: TradeCategory,
    signal_id: str | None,
    manual_tag: str | None,
    comment: str | None,
) -> TradeCategoryRecord:
    record = db.execute(
        select(TradeCategoryRecord).where(TradeCategoryRecord.closed_pnl_record_id == trade_id)
    ).scalar_one_or_none()
    if record is None:
        record = TradeCategoryRecord(closed_pnl_record_id=trade_id)
        db.add(record)

    record.category = category
    record.signal_id = signal_id
    record.manual_tag = manual_tag
    record.comment = comment
    db.commit()
    db.refresh(record)
    return record
