from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import get_analytics_recommendations
from app.schemas import AnalyticsRecommendationsResponse
from app.services.analytics import analytics_recommendations, resolve_date_range


class AnalyticsRecommendationsTests(TestCase):
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
                    closed_pnl NUMERIC NOT NULL,
                    total_fee NUMERIC NOT NULL,
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
        fee: str = "0",
        exchange: str = "BYBIT",
        symbol: str = "BTCUSDT",
        direction: str = "LONG",
        close_reason: str = "NORMAL",
        trade_time: datetime | None = None,
    ) -> None:
        timestamp = (trade_time or datetime(2026, 6, 1, tzinfo=UTC)).replace(tzinfo=None)
        gross_pnl = Decimal(net_pnl) + Decimal(fee)
        self.db.execute(
            text("""
                INSERT INTO closed_pnl_records
                    (id, exchange, symbol, direction, net_pnl, closed_pnl, total_fee, close_reason, exit_time, updated_time, created_time)
                VALUES
                    (:id, :exchange, :symbol, :direction, :net_pnl, :closed_pnl, :total_fee, :close_reason, :time, :time, :time)
            """),
            {
                "id": trade_id,
                "exchange": exchange,
                "symbol": symbol,
                "direction": direction,
                "net_pnl": net_pnl,
                "closed_pnl": str(gross_pnl),
                "total_fee": fee,
                "close_reason": close_reason,
                "time": timestamp.isoformat(sep=" ", timespec="microseconds"),
            },
        )
        self.db.commit()

    def result(self, **kwargs) -> dict:
        return analytics_recommendations(self.db, **kwargs)

    @staticmethod
    def recommendation(result: dict, recommendation_id: str) -> dict:
        return next(item for item in result["recommendations"] if item["id"] == recommendation_id)

    def test_empty_dataset_zero_pnl_and_decimal_serialization(self) -> None:
        empty = self.result()
        self.assertEqual(empty["scope"]["total_trades"], 0)
        self.assertEqual(empty["facts"]["actual_net_pnl"], Decimal("0"))
        self.assertEqual(empty["recommendations"], [])
        payload = AnalyticsRecommendationsResponse.model_validate(empty).model_dump(mode="json")
        self.assertEqual(payload["facts"]["actual_net_pnl"], "0")
        self.assertIsNone(payload["facts"]["fees"]["average_fee_per_trade"])

        self.add_trade(1, "0", fee="2")
        zero = self.result()
        fees = self.recommendation(zero, "recommendation.fees_impact")
        self.assertIsNone(fees["improvement_pct_of_actual"])
        self.assertIsNone(zero["facts"]["directions"][0]["contribution_pct"])

    def test_liquidation_scenario(self) -> None:
        self.add_trade(1, "10")
        self.add_trade(2, "-40", close_reason="LIQUIDATION", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-5", trade_time=datetime(2026, 6, 3, tzinfo=UTC))

        result = self.result()
        liquidation = result["facts"]["liquidations"]
        recommendation = self.recommendation(result, "recommendation.liquidation_exclusion")

        self.assertEqual(liquidation["count"], 1)
        self.assertEqual(liquidation["net_pnl"], Decimal("-40"))
        self.assertEqual(liquidation["hypothetical_net_pnl"], Decimal("5"))
        self.assertEqual(recommendation["delta_net_pnl"], Decimal("40"))
        self.assertEqual(recommendation["confidence"], "LOW")
        self.assertEqual(recommendation["confidence_label"], "Малая выборка")
        self.assertEqual(recommendation["sample_size"], 1)
        self.assertIn("Контрфактический расчёт", recommendation["interpretation"])
        self.assertIn(
            "Выборка недостаточна для вывода о качестве торговли этим инструментом/сценарием.",
            recommendation["interpretation"],
        )

    def test_direction_exchange_coin_and_scope_filters(self) -> None:
        self.add_trade(1, "10", symbol="BTCUSDT", direction="LONG", trade_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(2, "-6", symbol="ETHUSDT", direction="SHORT", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-4", symbol="ETHUSDT", direction="SHORT", trade_time=datetime(2026, 6, 3, tzinfo=UTC))
        self.add_trade(4, "-20", exchange="PIONEX", symbol="SOLUSDT", direction="UNKNOWN", trade_time=datetime(2026, 7, 1, tzinfo=UTC))

        result = self.result()
        direction = self.recommendation(result, "recommendation.direction_exclusion.short")
        exchange = self.recommendation(result, "recommendation.exchange_exclusion.pionex")
        coin = self.recommendation(result, "recommendation.coin_group_exclusion.pionex.solusdt")

        self.assertEqual(direction["actual_net_pnl"], Decimal("-20"))
        self.assertEqual(direction["hypothetical_net_pnl"], Decimal("-10"))
        self.assertEqual(exchange["hypothetical_net_pnl"], Decimal("0"))
        self.assertEqual(coin["hypothetical_net_pnl"], Decimal("0"))
        self.assertEqual(direction["affected_trade_pct"], 50.0)
        self.assertEqual(exchange["affected_trade_pct"], 25.0)
        self.assertEqual(coin["affected_trade_pct"], 25.0)
        self.assertEqual(direction["confidence_label"], "Малая выборка")
        self.assertEqual(direction["title"], "Результаты SHORT-сделок")
        self.assertIn("Результаты SHORT-сделок в выбранной истории: 2 сделки", direction["interpretation"])
        self.assertIn(
            "Выборка недостаточна для вывода о качестве торговли этим инструментом/сценарием.",
            direction["interpretation"],
        )
        self.assertEqual(result["facts"]["directions"][1]["direction"], "SHORT")

        for item in result["recommendations"]:
            if item["type"] in {"LIQUIDATION_EXCLUSION", "DIRECTION_EXCLUSION", "EXCHANGE_EXCLUSION", "COIN_GROUP_EXCLUSION"}:
                self.assertEqual(item["hypothetical_net_pnl"], item["actual_net_pnl"] - item["evidence"]["affected_net_pnl"])
                self.assertEqual(item["delta_net_pnl"], item["hypothetical_net_pnl"] - item["actual_net_pnl"])

        bybit_june = self.result(exchange="BYBIT", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
        self.assertEqual(bybit_june["scope"]["period"], "custom")
        self.assertEqual(bybit_june["scope"]["total_trades"], 3)
        self.assertFalse(any(item["type"] == "EXCHANGE_EXCLUSION" for item in bybit_june["recommendations"]))
        date_priority = self.result(period="year_2026", date_from=date(2026, 6, 1), date_to=date(2026, 6, 1))
        self.assertEqual(date_priority["scope"]["total_trades"], 1)

    def test_loss_concentration_and_ranking(self) -> None:
        self.add_trade(1, "-50", trade_time=datetime(2026, 6, 1, tzinfo=UTC))
        self.add_trade(2, "-30", symbol="ETHUSDT", trade_time=datetime(2026, 6, 2, tzinfo=UTC))
        self.add_trade(3, "-20", symbol="SOLUSDT", trade_time=datetime(2026, 6, 3, tzinfo=UTC))
        self.add_trade(4, "10", symbol="XRPUSDT", trade_time=datetime(2026, 6, 4, tzinfo=UTC))

        result = self.result()
        concentration = result["facts"]["loss_concentration"]
        recommendation = self.recommendation(result, "recommendation.loss_concentration.top_3")

        self.assertEqual(concentration["top_1_gross_loss"], Decimal("50"))
        self.assertEqual(concentration["top_3_gross_loss"], Decimal("100"))
        self.assertEqual(concentration["top_5_gross_loss"], Decimal("100"))
        self.assertEqual(concentration["top_3_share_pct"], 100.0)
        self.assertEqual(recommendation["hypothetical_net_pnl"], Decimal("10"))
        deltas = [item["delta_net_pnl"] for item in result["recommendations"]]
        self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_fee_impact_and_no_division_by_zero(self) -> None:
        self.add_trade(1, "2", fee="3")
        self.add_trade(2, "-1", fee="1", trade_time=datetime(2026, 6, 2, tzinfo=UTC))

        result = self.result()
        fees = result["facts"]["fees"]
        recommendation = self.recommendation(result, "recommendation.fees_impact")

        self.assertEqual(fees["total_fees"], Decimal("4"))
        self.assertEqual(fees["average_fee_per_trade"], Decimal("2"))
        self.assertEqual(fees["hypothetical_net_pnl_without_fees"], Decimal("5"))
        self.assertEqual(fees["fees_to_gross_profit_pct"], 200.0)
        self.assertEqual(fees["fees_to_absolute_gross_pnl_pct"], 80.0)
        self.assertEqual(recommendation["delta_net_pnl"], Decimal("4"))

    def test_confidence_levels_and_deterministic_ids(self) -> None:
        self.add_trade(1, "-1", symbol="ONE")
        for trade_id in range(2, 7):
            self.add_trade(trade_id, "-1", symbol="FIVE", trade_time=datetime(2026, 6, trade_id, tzinfo=UTC))
        for trade_id in range(7, 27):
            self.add_trade(trade_id, "-1", symbol="TWENTY", trade_time=datetime(2026, 7, 1, tzinfo=UTC))

        first = self.result()
        second = self.result()
        by_id = {item["id"]: item for item in first["recommendations"]}

        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.one"]["confidence"], "LOW")
        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.five"]["confidence"], "MEDIUM")
        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.twenty"]["confidence"], "HIGH")
        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.one"]["confidence_label"], "Малая выборка")
        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.five"]["confidence_label"], "Средняя выборка")
        self.assertEqual(by_id["recommendation.coin_group_exclusion.bybit.twenty"]["confidence_label"], "Большая выборка")
        self.assertEqual([item["id"] for item in first["recommendations"]], [item["id"] for item in second["recommendations"]])

    def test_low_confidence_huge_delta_remains_explicitly_labeled(self) -> None:
        self.add_trade(1, "-1000", symbol="WHALE")
        for trade_id in range(2, 22):
            self.add_trade(trade_id, "1", symbol="SMALL", trade_time=datetime(2026, 7, 1, tzinfo=UTC))

        result = self.result()
        recommendation = self.recommendation(result, "recommendation.coin_group_exclusion.bybit.whale")

        self.assertEqual(result["recommendations"][0]["id"], "recommendation.coin_group_exclusion.bybit.whale")
        self.assertEqual(recommendation["delta_net_pnl"], Decimal("1000"))
        self.assertEqual(recommendation["confidence"], "LOW")
        self.assertEqual(recommendation["confidence_label"], "Малая выборка")
        self.assertEqual(recommendation["affected_trade_pct"], 100 / 21)

    def test_large_short_sample_describes_observed_metrics_without_trade_directive(self) -> None:
        self.add_trade(1, "5", symbol="BTCUSDT", direction="LONG")
        for trade_id in range(2, 22):
            self.add_trade(
                trade_id,
                "-2",
                symbol="ETHUSDT",
                direction="SHORT",
                trade_time=datetime(2026, 6, trade_id - 1, tzinfo=UTC),
            )

        short = self.recommendation(self.result(), "recommendation.direction_exclusion.short")

        self.assertEqual(short["title"], "Результаты SHORT-сделок")
        self.assertIn("20 сделок", short["interpretation"])
        self.assertIn("win rate 0.00%", short["interpretation"])
        self.assertIn("net PnL −40,00", short["interpretation"])
        self.assertIn("средний net PnL −2,00", short["interpretation"])
        self.assertIn("Контрфактический расчёт без SHORT-сделок", short["interpretation"])
        self.assertIn("историческая разница +40,00", short["interpretation"])
        self.assertNotIn("Выборка недостаточна", short["interpretation"])

    def test_cards_and_dashboard_contain_no_directive_trade_recommendations(self) -> None:
        self.add_trade(1, "10", symbol="BTCUSDT", direction="LONG")
        self.add_trade(2, "-40", symbol="ETHUSDT", direction="SHORT", close_reason="LIQUIDATION")
        self.add_trade(3, "-5", exchange="PIONEX", symbol="BILL_USDT_PERP", direction="SHORT")

        result = self.result()
        card_text = " ".join(
            value
            for item in result["recommendations"]
            for value in (item["title"], item["summary"], item["interpretation"])
        ).lower()
        forbidden = ("пересмотреть", "следует", "нужно", "перестать использовать", "исключить")
        for phrase in forbidden:
            self.assertNotIn(phrase, card_text)

        dashboard = (Path(__file__).resolve().parents[1] / "app/static/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Структура результата", dashboard)
        self.assertIn(
            "Что сильнее всего повлияло на итоговый PnL",
            dashboard,
        )
        self.assertIn(
            "Это описание исторического результата, а не оценка качества торгового решения. Для анализа решения необходим контекст до входа: состояние рынка, причина входа и выхода, риск и торговый сигнал.",
            dashboard,
        )
        self.assertIn("function dedupeFactors", dashboard)
        self.assertNotIn("Что изменить", dashboard)
        self.assertNotIn("Загрузка рекомендаций", dashboard)

    def test_invalid_endpoint_filters(self) -> None:
        self.add_trade(1, "1")
        with self.assertRaises(ValueError):
            resolve_date_range("not-a-period")
        with self.assertRaises(HTTPException) as invalid_period:
            get_analytics_recommendations(period="not-a-period", db=self.db)
        with self.assertRaises(HTTPException) as invalid_exchange:
            get_analytics_recommendations(exchange="other", db=self.db)
        self.assertEqual(invalid_period.exception.status_code, 400)
        self.assertEqual(invalid_exchange.exception.status_code, 400)
