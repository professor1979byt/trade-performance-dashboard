# Screenshot Guide

Capture only real application screens. Do not create illustrative or synthetic dashboard screenshots. Use an anonymized dataset or carefully redact every sensitive field.

## Required captures

| Planned file | What it should prove |
| --- | --- |
| `overview.png` | Dashboard KPI overview, period/exchange scope, and evidence of closed-trade analytics. |
| `intelligence-pnl.png` | Both Intelligence P&L sections: “Where I lose money” and “What works for me.” |
| `result-structure.png` | Structure of Result card(s), affected trade count, and a visible confidence label. |
| `equity-and-breakdown.png` | Equity curve plus at least one daily, direction, coin, monthly, or yearly breakdown. |
| `trades.png` | Trades view with relevant filters and redacted/anonymized trade details. |
| `mobile.png` | Responsive dashboard presentation on a narrow viewport or physical mobile device. |

`architecture.png` is optional and should be added only if a real graphical architecture diagram is later created. The current text diagram in [../architecture.md](../architecture.md) is sufficient.

## Redaction checklist

Before publishing, remove or mask:

- exchange API keys, secrets, tokens, passwords, and environment-variable values;
- account, order, trade, and position identifiers;
- raw API payloads and request/response details;
- IP addresses, proxy addresses, database URLs, hostnames, and deployment configuration;
- sensitive timestamps, balances, PnL values, symbols, or comments when they could identify a real account or strategy.

Keep labels and calculations understandable after redaction. If redaction would make a frame misleading, recapture it with non-sensitive demo data instead.

## Capture notes

- Show the dashboard’s actual Russian UI labels where they appear; the surrounding GitHub documentation may remain in English.
- For the result-structure capture, choose a real visible card and avoid implying that it is a recommendation or forecast.
- For the mobile capture, include enough of the layout to demonstrate responsive cards and controls, not just a scaled desktop screenshot.
- Store image assets in this directory once approved. The README currently lists their planned paths but intentionally does not embed missing images.
