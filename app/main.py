from datetime import date
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.bybit_client import BybitAPIError, check_bybit_relay
from app.pionex_client import PionexAPIError, check_pionex
from app.models import ClosedPnlRecord, TradeCategory
from app.schemas import (
    AnalyticsRecommendationsResponse,
    AnalyticsInsightsResponse,
    BalanceSyncResponse,
    BybitRelayHealthResponse,
    CoinRankingItem,
    DailyAnalyticsItem,
    DirectionAnalyticsItem,
    EquityCurveItem,
    ExchangeSyncResponse,
    HealthResponse,
    MonthlySummaryItem,
    PionexHealthResponse,
    OverviewResponse,
    SyncResponse,
    TradeCategoryResponse,
    TradeCategoryUpdate,
    TradeItem,
    YearlySummaryResponse,
)
from app.services.analytics import (
    analytics_recommendations,
    analytics_insights,
    coin_ranking,
    daily_analytics,
    direction_analytics,
    equity_curve,
    monthly_summary,
    overview,
    resolve_date_range,
    trades_list,
    update_trade_category,
    yearly_summary,
)
from app.services.sync import sync_balance, sync_closed_pnl, sync_closed_pnl_range, sync_pionex_balance, sync_pionex_trades, sync_pionex_trades_range

app = FastAPI(title="Trade Performance", version="0.1.0")
logger = logging.getLogger("trade_performance.api")
logger.setLevel(logging.INFO)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    endpoint = f"{request.method} {request.url.path}"
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("endpoint=%s error=%s", endpoint, type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    logger.info("endpoint=%s status=%s", endpoint, response.status_code)
    return response


@app.exception_handler(BybitAPIError)
async def bybit_error_handler(request: Request, exc: BybitAPIError) -> JSONResponse:
    logger.error(
        "endpoint=%s %s code=%s",
        request.method,
        request.url.path,
        exc.code,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.exception_handler(PionexAPIError)
async def pionex_error_handler(request: Request, exc: PionexAPIError) -> JSONResponse:
    logger.error("endpoint=%s %s code=%s", request.method, request.url.path, exc.code)
    return JSONResponse(status_code=exc.http_status, content={"detail": exc.detail, "code": exc.code})


@app.head("/")
def dashboard_head() -> Response:
    return Response(status_code=200, media_type="text/html")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return Path("app/static/dashboard.html").read_text(encoding="utf-8")


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@app.get(
    "/health/bybit-relay",
    response_model=BybitRelayHealthResponse,
    response_model_exclude_none=True,
)
def health_bybit_relay() -> dict:
    return check_bybit_relay()


@app.get("/health/pionex", response_model=PionexHealthResponse, response_model_exclude_none=True)
def health_pionex() -> dict:
    return check_pionex()


@app.post("/sync/bybit/closed-pnl", response_model=SyncResponse)
def sync_bybit_closed_pnl(
    days: int = Query(default=90, ge=1, le=3650),
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        if date_from or date_to:
            start, end = resolve_date_range(None, date_from, date_to)
            if start is None or end is None:
                raise ValueError("date_from and date_to are required together")
            return sync_closed_pnl_range(db, start, end)
        return sync_closed_pnl(db, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sync/bybit/balance", response_model=BalanceSyncResponse)
def sync_bybit_balance(db: Session = Depends(get_db)):
    try:
        return sync_balance(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sync/pionex/trades", response_model=ExchangeSyncResponse)
def sync_pionex_trade_history(days: int = Query(default=90, ge=1, le=3650), date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db)):
    if date_from or date_to:
        start, end = resolve_date_range(None, date_from, date_to)
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="date_from and date_to are required together")
        return sync_pionex_trades_range(db, start, end)
    return sync_pionex_trades(db, days)


@app.post("/sync/pionex/balance", response_model=BalanceSyncResponse)
def sync_pionex_account_balance(db: Session = Depends(get_db)):
    try:
        return sync_pionex_balance(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_period(period: str | None, date_from: date | None, date_to: date | None) -> None:
    try:
        resolve_date_range(period, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_exchange(exchange: str) -> str:
    if exchange.lower() not in {"all", "bybit", "pionex"}:
        raise HTTPException(status_code=400, detail="exchange must be all, BYBIT or PIONEX")
    return exchange


@app.get("/analytics/overview", response_model=OverviewResponse)
def analytics_overview(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> dict:
    validate_period(period, date_from, date_to)
    return overview(db, period=period, date_from=date_from, date_to=date_to, exchange=validate_exchange(exchange))


@app.get("/analytics/coins", response_model=list[CoinRankingItem])
def analytics_coins(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    validate_period(period, date_from, date_to)
    return coin_ranking(db, period=period, date_from=date_from, date_to=date_to, exchange=validate_exchange(exchange))


@app.get("/analytics/monthly", response_model=list[MonthlySummaryItem])
def analytics_monthly(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    return monthly_summary(db, year, validate_exchange(exchange))


@app.get("/analytics/yearly", response_model=YearlySummaryResponse)
def analytics_yearly(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> dict:
    return yearly_summary(db, year, validate_exchange(exchange))


@app.get("/analytics/equity-curve", response_model=list[EquityCurveItem])
def analytics_equity_curve(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    validate_period(period, date_from, date_to)
    return equity_curve(db, period=period, date_from=date_from, date_to=date_to, exchange=validate_exchange(exchange))


@app.get("/analytics/daily", response_model=list[DailyAnalyticsItem])
def analytics_daily(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    validate_period(period, date_from, date_to)
    return daily_analytics(db, period=period, date_from=date_from, date_to=date_to, exchange=validate_exchange(exchange))


@app.get("/analytics/directions", response_model=list[DirectionAnalyticsItem])
def analytics_directions(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    validate_period(period, date_from, date_to)
    return direction_analytics(db, period=period, date_from=date_from, date_to=date_to, exchange=validate_exchange(exchange))


@app.get("/analytics/insights", response_model=AnalyticsInsightsResponse)
def get_analytics_insights(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> dict:
    validate_period(period, date_from, date_to)
    return analytics_insights(
        db,
        period=period,
        date_from=date_from,
        date_to=date_to,
        exchange=validate_exchange(exchange),
    )


@app.get("/analytics/recommendations", response_model=AnalyticsRecommendationsResponse)
def get_analytics_recommendations(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> dict:
    validate_period(period, date_from, date_to)
    return analytics_recommendations(
        db,
        period=period,
        date_from=date_from,
        date_to=date_to,
        exchange=validate_exchange(exchange),
    )


@app.get("/trades", response_model=list[TradeItem])
def get_trades(
    symbol: str | None = None,
    category: TradeCategory | None = None,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exchange: str = "all",
    db: Session = Depends(get_db),
) -> list[dict]:
    validate_period(period, date_from, date_to)
    return trades_list(
        db,
        symbol=symbol,
        category=category,
        period=period,
        date_from=date_from,
        date_to=date_to,
        exchange=validate_exchange(exchange),
    )


@app.patch("/trades/{trade_id}/category", response_model=TradeCategoryResponse)
def patch_trade_category(
    trade_id: int,
    payload: TradeCategoryUpdate,
    db: Session = Depends(get_db),
):
    exists = db.execute(select(ClosedPnlRecord.id).where(ClosedPnlRecord.id == trade_id)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    return update_trade_category(
        db,
        trade_id=trade_id,
        category=payload.category,
        signal_id=payload.signal_id,
        manual_tag=payload.manual_tag,
        comment=payload.comment,
    )
