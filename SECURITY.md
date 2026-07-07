# Security Policy

Orrin is an experimental research prototype, not production software. It can read and write local files, run local tooling, expose a local UI/backend, and optionally call external services when configured.

## Reporting Security Issues

Please do not post secrets, tokens, private logs, or exploitable details in a public issue.

For now, report security concerns by opening a GitHub issue with a high-level description and no sensitive data. If private coordination is needed, say so in the issue and I will follow up.

## Supported Versions

The `main` branch is the only supported line of development. Older branches and experimental branches may be incomplete, stale, or unsafe.

## Security Expectations

- Do not expose Orrin control endpoints publicly without authentication and network controls.
- Treat remote access, tunnels, and Tailscale/Funnel setups as advanced configurations.
- Keep API keys in `.env`, the OS keychain, or another local secret store. Do not commit secrets.
- Do not run Orrin on a machine you do not trust.
- Review generated code or self-extension behavior before relying on it.

## Known Security Limitations

Orrin is not security-hardened. Sandboxing, permissions, remote access, self-modification, and local machine interaction are active areas of caution rather than solved guarantees.
