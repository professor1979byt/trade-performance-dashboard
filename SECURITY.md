# Security & Privacy

## Credentials

Do not commit exchange credentials, passwords, tokens, database connection strings, proxy addresses, or deployment configuration. The application reads configuration from environment variables; keep local environment files and secret stores outside version control.

For exchange integrations, use the minimum permissions required to read supported account history and balances. Do not grant trading or withdrawal permissions for this dashboard.

## Privacy

Trade history may contain sensitive financial information. Before sharing a demo, screenshot, issue, or exported response, remove or mask account identifiers, order/trade/position identifiers, raw exchange payloads, precise sensitive timestamps, balances where necessary, and any infrastructure details.

## Public demo precautions

Use anonymized or deliberately non-sensitive demo data. Keep administration and synchronization controls protected. Do not expose a database or configuration endpoint publicly, and do not publish credentials in a browser, repository, video, image metadata, or logs.

## Responsible disclosure

If you believe you found a security issue, do not publish sensitive details in a public issue. Contact the project maintainer privately through the repository owner’s preferred private channel and provide a minimal reproducible description without secrets. Allow time for assessment before public disclosure.
