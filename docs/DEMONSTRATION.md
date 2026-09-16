# Demonstration Script (2–3 minutes)

Use an anonymized dataset and a local or protected demonstration environment. Do not show credentials, account/order/position IDs, raw payloads, sensitive balances, or infrastructure details.

## 0:00–0:20 — Problem and framing

“A usual PnL tracker tells me how much I earned or lost. Trade Performance Dashboard also shows which groups of historical closed trades made up that result. It is post-trade analytics, not a trading bot or signal service.”

## 0:20–0:40 — Open dashboard and historical data

Open the dashboard overview. Show that the data is closed-trade history from supported exchanges, using only anonymized values. Point out the top KPI row: net PnL, win rate, trade count, profit factor, gross profit/loss, and fees.

## 0:40–0:55 — Change scope

Choose a period or a custom date range, then switch the exchange filter. Explain that the dashboard recalculates the same historical scope across the analytics views. If appropriate, open the trades view and show the symbol/category filters without exposing identifiers.

## 0:55–1:25 — Intelligence P&L

Show the Intelligence P&L sections:

- “Where I lose money” — observed loss-related patterns in the selected history.
- “What works for me” — observed strength-related patterns in the selected history.

Say: “These are deterministic observations about historical records, not generated trade advice.”

## 1:25–1:55 — Structure of Result and counterfactual

Open Structure of Result. Select one visible factor such as liquidations, direction, exchange, coin group, loss concentration, or fees.

Explain: “The card compares actual historical net PnL with a hypothetical calculation for the same history without this group of already closed trades. It is a descriptive counterfactual scenario, not a prediction or a recommendation to stop taking similar trades.”

Point to the affected trade count and confidence label. State: “LOW means 1–4 affected trades, MEDIUM 5–19, and HIGH 20+. This is a sample-size cue, not statistical significance.”

## 1:55–2:15 — Equity and breakdowns

Show the equity curve, then briefly scroll through daily/direction, coin, and monthly or yearly breakdowns. Explain that these views make the historical composition of result inspectable instead of reducing it to one PnL figure.

## 2:15–2:30 — Mobile UX and architecture

Show the responsive mobile layout (device emulation or a prepared capture). Then show the architecture diagram in [architecture.md](architecture.md): exchange history is normalized, stored in PostgreSQL, calculated by a deterministic analytics engine, and served to the dashboard through FastAPI.

## 2:30–2:45 — Honest limitation and future

“The current product does not have the full pre-trade context needed to make causal claims: market regime, thesis, signal, risk, and exit plan. Historical correlation is not causality.”

“Future only: PFI could provide pre-trade context, allowing a later comparison between an initial thesis and the actual outcome. PFI is not implemented today.”

## Final phrase

“Trade Performance Dashboard turns real closed-trade history into evidence-based post-trade analysis—showing what happened, while being explicit about what the data cannot yet prove.”

## Video placeholder

Add the required public demo-video URL to [contest.md](contest.md) only after the recording is available. This document does not claim that a video already exists.
