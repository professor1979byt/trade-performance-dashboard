# Limitations

## Scope of analysis

- The dashboard is post-trade analytics over imported closed-trade history. It does not record a complete pre-trade decision context.
- Historical correlation or a group-level result does not prove causality or establish which action would have been correct.
- A hypothetical historical result without a selected group of closed trades is a descriptive counterfactual calculation, not a forecast, signal, or trading recommendation.
- Confidence means affected sample-size band only: LOW for 1–4 trades, MEDIUM for 5–19, and HIGH for 20+. It is not statistical significance.

## Data-source boundaries

- Results depend on the completeness and semantics of data returned by the supported exchange APIs and on successful import.
- For Pionex, the importer skips a history position when it cannot obtain an explicit LONG/SHORT direction, non-zero size, or usable entry/exit prices. Fills and funding are enrichment data and may be unavailable for a source window.
- ROI is only meaningful where a relevant latest equity snapshot is available to the selected exchange scope; otherwise it is not calculated as a usable percentage.

## Deployment boundary

- The repository is not itself a public deployment design. A public demo must protect synchronization controls and keep credentials, account identifiers, raw payloads, and infrastructure configuration private.
- The product does not execute exchange trades, but safe deployment still requires least-privilege credentials and appropriate access controls.

## Future context

PFI pre-trade context and fuller Decision Intelligence are future development only. They are not present in the current version.
