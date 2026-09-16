# Architecture

Trade Performance Dashboard separates exchange-history collection from deterministic post-trade analytics.

```text
Bybit / Pionex
      ↓
Import adapters and sync services
      ↓
Normalization into closed-trade records
      ↓
PostgreSQL
      ↓
Analytics engine
 ├─ KPI
 ├─ breakdowns
 ├─ Intelligence P&L
 ├─ counterfactual historical scenarios
 └─ equity curve
      ↓
FastAPI endpoints
      ↓
Web dashboard
```

## Implemented flow

1. The Bybit and Pionex adapters retrieve supported account-history and balance data through read operations.
2. Sync services map source fields into the `closed_pnl_records` model. Pionex history positions can be enriched with fills and funding data when available.
3. PostgreSQL stores normalized closed-trade records and balance snapshots.
4. The analytics service applies a common period/date and exchange scope, then calculates overview KPIs, breakdowns, insights, historical scenarios, and cumulative net-PnL/equity-curve data.
5. FastAPI exposes the results to the single-page web dashboard.

The dashboard can update a local trade category/comment through its API. This is user annotation of stored application data, not an exchange trading action.

## Counterfactual calculation

For an eligible historical group, the engine calculates:

```text
actual historical net PnL
− net PnL of the selected historical group
= hypothetical historical net PnL without that group
```

This is deterministic arithmetic on the selected closed-trade history. It is not a forecast, causal model, or trading instruction.

## Source-specific boundary

Pionex import only persists a record when the source data yields an explicit LONG/SHORT direction, non-zero size, and usable entry and exit prices. Records that do not meet those conditions are skipped and reported by the sync result. This keeps the analytics model from silently guessing missing directional context.

## Future only: PFI context

```text
PFI pre-trade context
      ↓
Actual trade
      ↓
Trade Performance Dashboard post-trade analysis
      ↓
Compare initial thesis with actual outcome
```

PFI is a future concept, not an implemented integration. Potential context could include market regime, funding/open interest, order flow, liquidity, manipulation risk, signal/evidence, and other pre-trade factors. That context would be necessary before making fuller Decision Intelligence claims.
