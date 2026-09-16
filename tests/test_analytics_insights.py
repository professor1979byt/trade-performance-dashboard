from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import TestCase

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import get_analytics_insights, validate_exchange
from app.schemas import AnalyticsInsightsResponse
from app.services.analytics import analytics_insights, resolve_date_range


class AnalyticsInsightsTests(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE closed_pnl_records (
                    id INTEGER PRIMARY KEY,
                    exchange VARCHAR(32) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    direction VARCHAR(16),
                    net_pnl NUMERIC NOT NULL,
                    close_reason VARCHAR(24) NOT NULL,
                    exit_time DATETIME,
                    updated_time DATETIME NOT NULL,
                    created_time DATETIME NOT NULL
                )
            """))
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def add_trade(
        self,
        trade_id: int,
        net_pnl: str,
        *,
        exchange: str = "BYBIT",
        symbol: str = "BTCUSDT",
        direction: str = "LONG",
        close_reason: str = "NORMAL",
        trade_time: datetime | None = None,
    ) -> None:
        timestamp = (trade_time or datetime(2026, 6, 1, tzinfo=UTC)).replace(tzinfo=None)
        self.db.execute(
            text("""
                INSERT INTO closed_pnl_records
                    (id, exchange, symbol, direction, net_pnl, close_reason, exit_time, updated_time, created_time)
                VALUES
                    (:id, :exchange, :symbol, :direction, :net_pnl, :close_reason, :time, :time, :time)
            """),
            {
                "id": trade_id,
                "exchange": exchange,
                "symbol": symbol,
                "direction": direction,
                "net_pnl": net_pnl,
                "close_reason": close_reason,
                "time": timestamp.isoformat(sep=" ", timespec="microseconds"),
            },
        )
        self.db.commit()

    def result(self, **kwargs) -> dict:
        return analytics_insights(self.db, **kwargs)

    def test_empty_dataset_and_decimal_schema(self) -> None:
        result = self.result()

        self.assertEqual(result["scope"]["total_trades"], 0)
        self.assertIsNone(result["losses"]["average_loss"])
        self.assertIsNone(result["strengths"]["average_win"])
        self.assertIsNone(result["strengths"]["profit_factor"])
        self.assertEqual(result["insights"], [])
        payload = AnalyticsInsightsResponse.model_validate(result).model_dump(mode="json")
        self.assertEqual(payload["losses"]["liquidations"]["net_pnl"], "0")

    def test_mixed_outcomes_and_zero_breaks_streaks(self) -> None:
        self.add_trade(1, "10", trade_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(2, "-3", direction="SHORT", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "0", trade_time=datetime(2026, 6, 3, tzinfo=UTC))
        self.add_trade(4, "-4", direction="SHORT", trade_time=datetime(2026, 6, 4, tzinfo=UTC))
        self.add_trade(5, "-5", direction="SHORT", trade_time=datetime(2026, 6, 5, tzinfo=UTC))

        result = self.result()

        self.assertEqual(result["strengths"]["win_rate_pct"], 20.0)
        self.assertEqual(result["losses"]["average_loss"]["value"], Decimal("-4"))
        self.assertEqual(result["losses"]["losing_streak"]["trade_count"], 2)
        self.assertEqual(result["losses"]["losing_streak"]["net_pnl"], Decimal("-9"))

    def test_liquidation_metrics_and_loss_share(self) -> None:
        self.add_trade(1, "10")
        self.add_trade(2, "-4", close_reason="LIQUIDATION", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-6", close_reason="NORMAL", trade_time=datetime(2026, 6, 3, tzinfo=UTC))

        liquidations = self.result()["losses"]["liquidations"]

        self.assertEqual(liquidations["count"], 1)
        self.assertEqual(liquidations["net_pnl"], Decimal("-4"))
        self.assertEqual(liquidations["gross_loss"], Decimal("4"))
        self.assertAlmostEqual(liquidations["trade_share_pct"], 100 / 3)
        self.assertEqual(liquidations["loss_share_pct"], 40.0)

    def test_no_losses_and_no_wins(self) -> None:
        self.add_trade(1, "2")
        self.add_trade(2, "4", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        no_losses = self.result()
        self.assertIsNone(no_losses["losses"]["average_loss"])
        self.assertIsNone(no_losses["strengths"]["profit_factor"])
        self.assertIsNone(no_losses["losses"]["loss_concentration"]["share_pct"])

        self.db.execute(text("DELETE FROM closed_pnl_records"))
        self.db.commit()
        self.add_trade(3, "-2")
        self.add_trade(4, "-4", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        no_wins = self.result()
        self.assertIsNone(no_wins["strengths"]["average_win"])
        self.assertIsNone(no_wins["strengths"]["profit_concentration"]["share_pct"])

    def test_loss_and_profit_concentration_and_coin_group_ranking(self) -> None:
        self.add_trade(1, "-10", symbol="BTCUSDT")
        self.add_trade(2, "-20", symbol="ETHUSDT", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-5", symbol="SOLUSDT", trade_time=datetime(2026, 6, 3, tzinfo=UTC))
        self.add_trade(4, "30", symbol="BTCUSDT", trade_time=datetime(2026, 6, 4, tzinfo=UTC))
        self.add_trade(5, "8", symbol="ETHUSDT", trade_time=datetime(2026, 6, 5, tzinfo=UTC))
        self.add_trade(6, "4", symbol="SOLUSDT", trade_time=datetime(2026, 6, 6, tzinfo=UTC))
        self.add_trade(7, "-100", exchange="PIONEX", symbol="BTCUSDT", trade_time=datetime(2026, 6, 7, tzinfo=UTC))

        result = self.result()

        self.assertEqual(result["losses"]["worst_coin_group"]["exchange"], "PIONEX")
        self.assertEqual(result["losses"]["worst_coin_group"]["symbol"], "BTCUSDT")
        self.assertEqual(result["losses"]["loss_concentration"]["gross_amount"], Decimal("130"))
        self.assertAlmostEqual(result["losses"]["loss_concentration"]["share_pct"], 130 / 135 * 100)
        self.assertEqual(result["strengths"]["profit_concentration"]["gross_amount"], Decimal("42"))
        self.assertEqual(result["strengths"]["profit_concentration"]["share_pct"], 100.0)

    def test_direction_exchange_comparisons_and_filters(self) -> None:
        self.add_trade(1, "10", exchange="BYBIT", direction="LONG", trade_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(2, "-5", exchange="BYBIT", direction="SHORT", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-9", exchange="PIONEX", direction="LONG", trade_time=datetime(2026, 7, 1, tzinfo=UTC))

        all_result = self.result()
        self.assertEqual(all_result["losses"]["worst_direction"]["direction"], "SHORT")
        self.assertEqual(all_result["losses"]["worst_exchange"]["exchange"], "PIONEX")
        bybit = self.result(exchange="BYBIT", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
        self.assertEqual(bybit["scope"]["total_trades"], 2)
        self.assertIsNone(bybit["losses"]["worst_exchange"])
        self.assertEqual(bybit["scope"]["period"], "custom")
        date_priority = self.result(period="year_2026", date_from=date(2026, 6, 1), date_to=date(2026, 6, 1))
        self.assertEqual(date_priority["scope"]["total_trades"], 1)
        self.assertIsNone(date_priority["losses"]["worst_direction"])

    def test_best_worst_day_month_and_tie_breaking(self) -> None:
        self.add_trade(2, "-5", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(1, "-5", trade_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(3, "10", trade_time=datetime(2026, 7, 1, tzinfo=UTC))

        result = self.result()

        self.assertEqual(result["losses"]["worst_day"]["date"], date(2026, 6, 1))
        self.assertEqual(result["losses"]["worst_month"]["date"], date(2026, 6, 1))
        self.assertEqual(result["strengths"]["best_day"]["date"], date(2026, 7, 1))
        self.assertEqual(result["strengths"]["best_month"]["date"], date(2026, 7, 1))

    def test_invalid_period_exchange_and_insight_allowlist(self) -> None:
        self.add_trade(1, "1")
        with self.assertRaises(ValueError):
            resolve_date_range("not-a-period")
        with self.assertRaises(HTTPException):
            validate_exchange("other")

        with self.assertRaises(HTTPException) as invalid_period:
            get_analytics_insights(period="not-a-period", db=self.db)
        with self.assertRaises(HTTPException) as invalid_exchange:
            get_analytics_insights(exchange="other", db=self.db)
        self.assertEqual(invalid_period.exception.status_code, 400)
        self.assertEqual(invalid_exchange.exception.status_code, 400)

        result = self.result()
        self.assertEqual(set(result), {"scope", "losses", "strengths", "insights"})
        allowed_ids = {
            "loss.liquidation_loss_share", "loss.worst_coin_group", "loss.worst_direction",
            "loss.worst_exchange", "loss.concentration", "loss.losing_streak", "loss.worst_day",
            "strength.best_coin_group", "strength.best_direction", "strength.best_exchange",
            "strength.profit_concentration", "strength.winning_streak", "strength.best_day",
        }
        self.assertTrue(set(item["id"] for item in result["insights"]).issubset(allowed_ids))
