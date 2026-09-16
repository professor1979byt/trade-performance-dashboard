from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import CloseReason, TradeCategory, TradeSource


class HealthResponse(BaseModel):
    status: str
    database: str


class BybitRelayHealthResponse(BaseModel):
    status: str
    proxy_configured: bool
    relay_reachable: bool
    bybit_reachable: bool
    latency_ms: int | None = None
    code: str | None = None


class SyncResponse(BaseModel):
    inserted: int
    skipped: int
    ranges: int


class ExchangeSyncResponse(SyncResponse):
    exchange: str
    updated: int
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    api_positions: int = 0
    source_fills: int = 0
    source_fundings: int = 0
    record_types: dict[str, int] = Field(default_factory=dict)


class PionexHealthResponse(BaseModel):
    status: str
    enabled: bool
    proxy_configured: bool
    relay_reachable: bool
    pionex_reachable: bool
    authenticated: bool
    latency_ms: int | None = None
    code: str | None = None


class BalanceSyncResponse(BaseModel):
    id: int
    total_equity: Decimal
    created_at: datetime


class OverviewResponse(BaseModel):
    total_trades: int
    profitable_trades: int
    losing_trades: int
    winrate: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    liquidation_count: int
    liquidation_net_pnl: Decimal
    liquidation_share_pct: float
    latest_total_equity: Decimal | None
    roi_percent: float | None


class CoinRankingItem(BaseModel):
    symbol: str
    exchange: str
    total_trades: int
    profitable_trades: int
    losing_trades: int
    winrate: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    roi_percent: float | None
    avg_pnl: Decimal
    avg_win: Decimal | None
    avg_loss: Decimal | None
    best_trade: Decimal | None
    worst_trade: Decimal | None


class SummaryResponse(BaseModel):
    total_trades: int
    profitable_trades: int
    losing_trades: int
    winrate: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    roi_percent: float | None


class MonthlySummaryItem(SummaryResponse):
    month: int


class YearlySummaryResponse(SummaryResponse):
    year: int


class EquityCurveItem(BaseModel):
    date: date
    daily_net_pnl: Decimal
    cumulative_net_pnl: Decimal
    estimated_equity: Decimal | None


class DailyAnalyticsItem(BaseModel):
    date: date
    trades: int
    profitable_trades: int
    losing_trades: int
    winrate: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal


class DirectionAnalyticsItem(BaseModel):
    direction: str
    total_trades: int
    profitable_trades: int
    losing_trades: int
    winrate: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    avg_pnl: Decimal
    best_trade: Decimal
    worst_trade: Decimal


class InsightScope(BaseModel):
    period: str
    date_from: date | None
    date_to: date | None
    exchange: str
    total_trades: int


class InsightMetric(BaseModel):
    value: Decimal
    trade_count: int


class InsightCoinGroup(BaseModel):
    exchange: str
    symbol: str
    total_trades: int
    profitable_trades: int
    losing_trades: int
    net_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal


class InsightDirection(BaseModel):
    direction: str
    total_trades: int
    profitable_trades: int
    losing_trades: int
    net_pnl: Decimal
    win_rate_pct: float
    profit_factor: Decimal | None


class InsightExchange(BaseModel):
    exchange: str
    total_trades: int
    profitable_trades: int
    losing_trades: int
    net_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal


class InsightTrade(BaseModel):
    id: int
    exchange: str
    symbol: str
    direction: str | None
    trade_time: datetime
    net_pnl: Decimal


class InsightStreak(BaseModel):
    trade_count: int
    net_pnl: Decimal
    started_at: datetime
    ended_at: datetime
    first_trade_id: int
    last_trade_id: int


class InsightConcentration(BaseModel):
    group_limit: int
    groups: list[InsightCoinGroup]
    gross_amount: Decimal
    total_gross_amount: Decimal
    share_pct: float | None


class InsightLiquidations(BaseModel):
    count: int
    net_pnl: Decimal
    gross_loss: Decimal
    trade_share_pct: float
    loss_share_pct: float | None


class InsightPeriod(BaseModel):
    date: date
    trades: int
    net_pnl: Decimal


class InsightEvidence(BaseModel):
    key: str
    label: str
    value: str
    unit: str
    numerator: str | None = None
    denominator: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class InsightItem(BaseModel):
    id: str
    section: str
    text: str
    secondary_text: str | None = None
    evidence: list[InsightEvidence]


class LossInsightsResponse(BaseModel):
    average_loss: InsightMetric | None
    worst_coin_group: InsightCoinGroup | None
    worst_direction: InsightDirection | None
    worst_exchange: InsightExchange | None
    largest_losing_trades: list[InsightTrade]
    losing_streak: InsightStreak | None
    loss_concentration: InsightConcentration
    liquidations: InsightLiquidations
    worst_day: InsightPeriod | None
    worst_month: InsightPeriod | None


class StrengthInsightsResponse(BaseModel):
    average_win: InsightMetric | None
    win_rate_pct: float
    profit_factor: Decimal | None
    best_coin_group: InsightCoinGroup | None
    best_direction: InsightDirection | None
    best_exchange: InsightExchange | None
    largest_winning_trades: list[InsightTrade]
    winning_streak: InsightStreak | None
    profit_concentration: InsightConcentration
    best_day: InsightPeriod | None
    best_month: InsightPeriod | None


class AnalyticsInsightsResponse(BaseModel):
    scope: InsightScope
    losses: LossInsightsResponse
    strengths: StrengthInsightsResponse
    insights: list[InsightItem]


class RecommendationGroup(BaseModel):
    exchange: str | None = None
    symbol: str | None = None
    direction: str | None = None
    total_trades: int
    win_rate_pct: float
    net_pnl: Decimal
    average_net_pnl: Decimal
    contribution_pct: float | None


class RecommendationLiquidationImpact(BaseModel):
    count: int
    net_pnl: Decimal
    hypothetical_net_pnl: Decimal
    delta_net_pnl: Decimal
    improvement_pct_of_actual: float | None


class RecommendationLossConcentration(BaseModel):
    total_gross_loss: Decimal
    top_1_gross_loss: Decimal
    top_1_share_pct: float | None
    top_3_gross_loss: Decimal
    top_3_share_pct: float | None
    top_5_gross_loss: Decimal
    top_5_share_pct: float | None
    top_3_trade_count: int


class RecommendationFeesImpact(BaseModel):
    total_fees: Decimal
    fees_to_gross_profit_pct: float | None
    fees_to_absolute_gross_pnl_pct: float | None
    average_fee_per_trade: Decimal | None
    hypothetical_net_pnl_without_fees: Decimal
    delta_net_pnl: Decimal


class RecommendationFacts(BaseModel):
    actual_net_pnl: Decimal
    liquidations: RecommendationLiquidationImpact
    directions: list[RecommendationGroup]
    exchanges: list[RecommendationGroup]
    worst_coin_groups: list[RecommendationGroup]
    best_coin_groups: list[RecommendationGroup]
    loss_concentration: RecommendationLossConcentration
    fees: RecommendationFeesImpact


class RecommendationEvidence(BaseModel):
    metric: str
    affected_trade_count: int
    affected_net_pnl: Decimal | None = None
    contribution_pct: float | None = None
    win_rate_pct: float | None = None
    average_net_pnl: Decimal | None = None
    total_fees: Decimal | None = None
    gross_profit: Decimal | None = None
    absolute_gross_pnl: Decimal | None = None
    top_1_loss_share_pct: float | None = None
    top_3_loss_share_pct: float | None = None
    top_5_loss_share_pct: float | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class RecommendationItem(BaseModel):
    id: str
    type: str
    title: str
    summary: str
    interpretation: str
    evidence: RecommendationEvidence
    actual_net_pnl: Decimal
    hypothetical_net_pnl: Decimal | None
    delta_net_pnl: Decimal | None
    improvement_pct_of_actual: float | None
    affected_trade_pct: float | None
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    confidence_label: str
    sample_size: int


class AnalyticsRecommendationsResponse(BaseModel):
    scope: InsightScope
    facts: RecommendationFacts
    recommendations: list[RecommendationItem]


class TradeItem(BaseModel):
    id: int
    exchange: str
    external_trade_id: str | None
    external_order_id: str | None
    external_position_id: str | None
    direction: str | None
    entry_time: datetime | None
    exit_time: datetime | None
    gross_pnl: Decimal | None
    fees: Decimal | None
    funding: Decimal | None
    close_reason: CloseReason
    margin_mode: str | None
    trade_source: TradeSource
    bot_id: str | None
    bot_type: str | None
    account_name: str | None
    symbol: str
    order_id: str
    side: str | None
    qty: Decimal | None
    closed_size: Decimal | None
    avg_entry_price: Decimal | None
    avg_exit_price: Decimal | None
    closed_pnl: Decimal
    total_fee: Decimal
    net_pnl: Decimal
    leverage: Decimal | None
    created_time: datetime
    updated_time: datetime
    category: TradeCategory
    signal_id: str | None
    manual_tag: str | None
    comment: str | None


class TradeCategoryUpdate(BaseModel):
    category: TradeCategory
    signal_id: str | None = None
    manual_tag: str | None = None
    comment: str | None = None


class TradeCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    closed_pnl_record_id: int
    category: TradeCategory
    signal_id: str | None
    manual_tag: str | None
    comment: str | None
    updated_at: datetime
