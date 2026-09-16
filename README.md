# Trade Performance Dashboard

> Evidence-based post-trade analytics for real trading history.

Trade Performance Dashboard is a web dashboard for examining the result of closed trades after they happened. It is not a trading bot and not just a PnL tracker: alongside “how much was earned or lost?”, it asks which groups of historical trades made up that result.

## Problem

A total PnL hides structure. A trader can see a profitable or losing period without seeing how directions, instruments, exchanges, fees, liquidations, or a small number of large losses contributed to it. Turning that hidden structure into a trading instruction would be equally misleading when the historical record lacks entry context.

## Solution

The dashboard imports closed-trade history from supported exchanges, normalizes it into a common model, and calculates deterministic post-trade analytics. It presents KPIs, breakdowns, an equity curve, and Intelligence P&L views for the currently selected historical scope.

## What makes it different

The project deliberately separates an observed historical result from a decision claim:

1. **Fact** — for example, the selected history’s LONG trades produced a stated net PnL.
2. **Counterfactual historical scenario** — the same history is recalculated as if a specified group of its closed trades were absent.
3. **Causal or decision interpretation** — a claim about whether a trader should take, avoid, or change a decision.

The current version implements the first two. It does **not** claim the third. Market state, entry thesis, signal, risk plan, exit conditions, and market regime are not available as complete pre-trade context. Historical correlation is therefore not a trading recommendation.

## Key Features

- Closed-trade model for Bybit and Pionex history.
- KPI view: trade count, win rate, gross and net PnL, commissions, profit factor, average win/loss, and liquidation metrics.
- Latest equity snapshot and ROI where an applicable exchange balance snapshot exists.
- Period presets, custom date range, and exchange filters; symbol and category filters in the trades view.
- Intelligence P&L: “Where I lose money” and “What works for me” observations for the selected history.
- Structure of Result: historical scenarios for liquidations, direction, exchange, coin group, loss concentration, and fees when the relevant conditions are present.
- Equity curve plus daily, monthly, yearly, direction, and coin breakdowns.
- Responsive dashboard layout, including mobile-oriented cards and controls.
- HTTP analytics API for the same data used by the dashboard.

## How Intelligence P&L works

For a selected period and exchange scope, the analytics engine aggregates normalized closed trades. It computes the result by dimensions such as direction, exchange, and symbol, then exposes deterministic observations about losses and strengths. The Structure of Result endpoint additionally builds eligible historical scenarios, ordered by their calculated historical difference.

The calculations operate on stored historical trade fields; they do not use a generative model to interpret numbers or create advice.

## Fact vs Counterfactual vs Causality

**Actual historical net PnL** is the recorded net result for the selected scope.

**Hypothetical historical net PnL** is a descriptive recalculation of that same scope without a specified group of closed trades. The displayed difference is the arithmetic change between those two historical totals.

This counterfactual is **not** a forecast, signal, trading recommendation, or proof of causality. For example, a negative historical result for a direction does not mean “do not trade that direction.” It only identifies a group worth examining with information that the current data model does not fully contain.

### Confidence labels

Confidence communicates the affected historical sample size, not statistical significance:

| Confidence | Affected closed trades |
| --- | ---: |
| LOW | 1–4 |
| MEDIUM | 5–19 |
| HIGH | 20+ |

It is a visibility cue about the number of historical trades behind the displayed observation. The application does not calculate statistical significance.

## Dashboard / Screenshots

Screenshots are intentionally not fabricated. The capture plan and anonymization rules are in [docs/screenshots/README.md](docs/screenshots/README.md). Planned assets: `docs/screenshots/overview.png`, `intelligence-pnl.png`, `result-structure.png`, `equity-and-breakdown.png`, `trades.png`, and `mobile.png`.

## Architecture

```text
Bybit / Pionex
       |
       v
Import adapters and sync services
       |
       v
Normalization into closed-trade records
       |
       v
PostgreSQL
       |
       v
Analytics engine
  ├─ KPI and breakdowns
  ├─ Intelligence P&L
  ├─ counterfactual historical scenarios
  └─ equity curve
       |
       v
FastAPI analytics endpoints → web dashboard
```

See [docs/architecture.md](docs/architecture.md) for the compact technical description and the explicitly future-only PFI concept.

## Data Sources

- **Bybit:** closed PnL and account-balance snapshot integration.
- **Pionex:** history-position import, with fills and funding data used as enrichment where available, plus a balance snapshot integration.

The exchange client implementations use read operations for the supported history and balance data; the application contains no exchange order-placement or cancellation flow. Use credentials with the minimum available read-only permissions. Importing history writes normalized records to the application database; it does not execute trades.

## Analytics API

Implemented read endpoints include:

- `GET /health`
- `GET /analytics/overview`
- `GET /analytics/insights`
- `GET /analytics/recommendations`
- `GET /analytics/equity-curve`
- `GET /analytics/daily`
- `GET /analytics/directions`
- `GET /analytics/coins`
- `GET /analytics/monthly`
- `GET /analytics/yearly`
- `GET /trades`

The scope-aware endpoints accept period/date and exchange filtering as implemented by the API; the trade list also supports symbol and category filtering. See the route definitions in `app/main.py` for exact query parameters.

## Mobile UX

The single-page dashboard has a responsive layout: summary metrics, analytics cards, breakdowns, and trades adapt to a compact card-oriented presentation for smaller screens. The planned mobile capture is documented in the screenshot guide.

## Reliability / Tests

The repository contains automated tests for analytics overview, insights, and counterfactual/result-structure calculations in `tests/`. The test suite exercises calculation behavior, filters, confidence thresholds, deterministic ordering, and safeguards against directive trading language. This is test coverage of the analytics layer, not a claim of a production service-level guarantee.

## AI-assisted development

AI/Codex was used as an engineering assistant for work such as analysis of the existing project, development, refactoring, logic review, testing, UI/UX improvements, and documentation preparation. It is not a runtime analyst in the product.

The runtime analytics layer is deliberately deterministic and evidence-based: displayed figures and historical scenarios are calculated from stored trade data rather than delegated to a generative model that could invent a conclusion.

## Limitations

- This is post-trade analytics, not a complete pre-trade decision record.
- Historical association does not establish causality.
- A counterfactual historical scenario is not a forecast or trading signal.
- Confidence labels are sample-size bands, not statistical significance.
- Pionex records can be skipped when a usable explicit direction, size, or entry/exit price cannot be derived from available source data.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for details.

## Roadmap

**Future development only — PFI is not implemented or integrated.** A possible next stage is to connect pre-trade context to the post-trade record:

```text
PFI pre-trade context → actual trade → Trade Performance Dashboard
→ post-trade result analysis → comparison of initial thesis and outcome
```

Potential PFI context includes market regime, funding/open interest, order flow, liquidity, manipulation risk, signal/evidence, and other pre-trade market factors. Only with that context could the project progress toward fuller Decision Intelligence.

## Security & Privacy

Keep credentials outside the repository and use least-privilege exchange access. Do not publish account identifiers, trade identifiers, raw exchange payloads, or infrastructure configuration in screenshots or demos. See [SECURITY.md](SECURITY.md).

## Contest / Demo

The concise contest entry is in [docs/contest.md](docs/contest.md). A 2–3 minute walkthrough script is in [docs/DEMONSTRATION.md](docs/DEMONSTRATION.md). A required demo-video link can be added to the marked placeholder after recording; no video link is claimed here.

## License / reuse

No `LICENSE` file is present in this repository at this revision. No open-source license or reuse permission is asserted by this README.
