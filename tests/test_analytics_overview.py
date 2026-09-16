from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import TestCase

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.analytics import overview


class OverviewPerformanceMetricsTests(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE closed_pnl_records (
                    id INTEGER PRIMARY KEY,
                    exchange VARCHAR(32) NOT NULL,
                    net_pnl NUMERIC NOT NULL,
                    closed_pnl NUMERIC NOT NULL,
                    total_fee NUMERIC NOT NULL,
                    close_reason VARCHAR(24) NOT NULL,
                    exit_time DATETIME,
                    updated_time DATETIME NOT NULL,
                    created_time DATETIME NOT NULL
                )
            """))
            connection.execute(text("""
                CREATE TABLE balance_snapshots (
                    id INTEGER PRIMARY KEY,
                    exchange VARCHAR(32) NOT NULL,
                    total_equity NUMERIC NOT NULL,
                    created_at DATETIME NOT NULL
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
        close_reason: str = "NORMAL",
        exit_time: datetime | None = None,
    ) -> None:
        trade_time = (exit_time or datetime(2026, 6, 1, tzinfo=UTC)).replace(tzinfo=None)
        timestamp = trade_time.isoformat(sep=" ", timespec="microseconds")
        self.db.execute(
            text("""
                INSERT INTO closed_pnl_records
                    (id, exchange, net_pnl, closed_pnl, total_fee, close_reason, exit_time, updated_time, created_time)
                VALUES
                    (:id, :exchange, :net_pnl, :closed_pnl, :total_fee, :close_reason, :exit_time, :updated_time, :created_time)
            """),
            {
                "id": trade_id,
                "exchange": exchange,
                "net_pnl": net_pnl,
                "closed_pnl": net_pnl,
                "total_fee": "0",
                "close_reason": close_reason,
                "exit_time": timestamp,
                "updated_time": timestamp,
                "created_time": timestamp,
            },
        )
        self.db.commit()

    def test_mixed_wins_losses_and_liquidations(self) -> None:
        self.add_trade(1, "12")
        self.add_trade(2, "-4", exit_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(
            3,
            "-6",
            exchange="PIONEX",
            close_reason="LIQUIDATION",
            exit_time=datetime(2026, 6, 3, tzinfo=UTC),
        )

        result = overview(self.db)

        self.assertEqual(result["gross_profit"], Decimal("12"))
        self.assertEqual(result["gross_loss"], Decimal("10"))
        self.assertEqual(result["profit_factor"], Decimal("1.2"))
        self.assertEqual(result["average_win"], Decimal("12"))
        self.assertEqual(result["average_loss"], Decimal("-5"))
        self.assertEqual(result["liquidation_count"], 1)
        self.assertEqual(result["liquidation_net_pnl"], Decimal("-6"))
        self.assertAlmostEqual(result["liquidation_share_pct"], 100 / 3)

    def test_normal_trades_are_not_liquidations(self) -> None:
        self.add_trade(1, "3")
        self.add_trade(2, "-1")

        result = overview(self.db)

        self.assertEqual(result["liquidation_count"], 0)
        self.assertEqual(result["liquidation_net_pnl"], Decimal("0"))
        self.assertEqual(result["liquidation_share_pct"], 0.0)

    def test_no_losing_trades_has_null_profit_factor_and_average_loss(self) -> None:
        self.add_trade(1, "2")
        self.add_trade(2, "6")

        result = overview(self.db)

        self.assertEqual(result["gross_loss"], Decimal("0"))
        self.assertIsNone(result["profit_factor"])
        self.assertEqual(result["average_win"], Decimal("4"))
        self.assertIsNone(result["average_loss"])

    def test_empty_dataset_has_null_ratio_and_averages(self) -> None:
        result = overview(self.db)

        self.assertEqual(result["gross_profit"], Decimal("0"))
        self.assertEqual(result["gross_loss"], Decimal("0"))
        self.assertIsNone(result["profit_factor"])
        self.assertIsNone(result["average_win"])
        self.assertIsNone(result["average_loss"])
        self.assertEqual(result["liquidation_count"], 0)
        self.assertEqual(result["liquidation_net_pnl"], Decimal("0"))
        self.assertEqual(result["liquidation_share_pct"], 0.0)

    def test_period_and_exchange_filters_apply_to_new_metrics(self) -> None:
        self.add_trade(1, "10", exit_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(
            2,
            "-5",
            exchange="PIONEX",
            close_reason="LIQUIDATION",
            exit_time=datetime(2026, 6, 2, tzinfo=UTC),
        )
        self.add_trade(
            3,
            "-9",
            exchange="PIONEX",
            close_reason="LIQUIDATION",
            exit_time=datetime(2026, 7, 2, tzinfo=UTC),
        )

        result = overview(self.db, period="june_2026", exchange="PIONEX")

        self.assertEqual(result["total_trades"], 1)
        self.assertEqual(result["gross_profit"], Decimal("0"))
        self.assertEqual(result["gross_loss"], Decimal("5"))
        self.assertEqual(result["liquidation_count"], 1)
        self.assertEqual(result["liquidation_net_pnl"], Decimal("-5"))
        self.assertEqual(result["liquidation_share_pct"], 100.0)

        one_day = overview(self.db, date_from=date(2026, 6, 1), date_to=date(2026, 6, 2), exchange="BYBIT")
        self.assertEqual(one_day["total_trades"], 1)
        self.assertEqual(one_day["gross_profit"], Decimal("10"))
        self.assertEqual(one_day["liquidation_count"], 0)
