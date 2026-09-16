# Contest Entry — Trade Performance Dashboard

**Working title:** Trade Performance Dashboard
**Subtitle:** Evidence-based post-trade analytics for real trading history
**Demo video:** _[add required public demo-video link after recording]_

## Problem

Ordinary PnL tracking answers how much a trader earned or lost. It does not make the structure of that historical result easy to inspect: which trade groups, fees, liquidations, directions, exchanges, or instruments contributed to it.

## Solution

Trade Performance Dashboard imports supported closed-trade history, normalizes it into a common database model, and presents deterministic post-trade analytics in a responsive web dashboard. The product combines KPI, breakdowns, equity curve, and Intelligence P&L views for a selected historical period.

## What is implemented

- Bybit and Pionex history integrations.
- Closed-trade records and PostgreSQL-backed analytics.
- Trade count, win rate, gross/net PnL, fees, profit factor, average win/loss, liquidation metrics, and ROI where an equity snapshot is available.
- Date, period, exchange, symbol, and category filtering in the relevant views.
- Intelligence P&L sections: “Where I lose money” and “What works for me.”
- Structure of Result with historical scenarios and counterfactual calculations.
- Equity curve and monthly, yearly, daily, direction, and coin breakdowns.
- Responsive web dashboard and analytics API.

## Result and differentiation

The dashboard goes beyond a total PnL number by asking: “Which groups of historical closed trades made up this result?” It can show the actual historical net PnL and a hypothetical historical net PnL without a selected group of those already closed trades.

That is descriptive, not prescriptive. A negative result for a group is a fact about the selected history, not a recommendation to stop trading that group. The product explicitly separates fact, counterfactual historical scenario, and causal/decision interpretation. The last of these is not claimed by the current version.

Confidence labels communicate affected sample size: LOW for 1–4 trades, MEDIUM for 5–19, and HIGH for 20+. They are not statistical-significance claims.

## Evidence of a working product

The repository contains the FastAPI application, exchange adapters, normalized trade model, analytics engine, web dashboard, and automated analytics tests. The demonstration script at [DEMONSTRATION.md](DEMONSTRATION.md) walks through implemented dashboard views and the API-backed flow. Five reviewed application captures are embedded in the [project README](../README.md) and listed in [screenshots/README.md](screenshots/README.md). The required public demo-video URL is still a TODO and is not claimed here.

## Role of AI and author contribution

The author built the product’s application flow, integrations, normalization, analytics, dashboard, and supporting tests/documentation. AI/Codex served as an engineering assistant for analysis, development, refactoring, logic review, testing, UI/UX improvement, and documentation work.

There is no claimed runtime LLM analysis. Runtime figures and historical scenarios are deterministic calculations over stored trade data.

## Limitations

This is post-trade analytics. It does not contain complete pre-trade context such as market regime, entry thesis, signal, risk plan, or exit conditions. Historical correlation is not causality, and counterfactual history is not a forecast. See [LIMITATIONS.md](LIMITATIONS.md).

## Further development

**Future only:** PFI could provide pre-trade market context before an actual trade is analyzed by the dashboard. This could later support comparison of the initial thesis with the outcome and more complete Decision Intelligence. PFI is not part of the current implementation.
