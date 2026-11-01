# Security policy

## Supported versions

Fixes are made on the latest release and on `main`.

## Reporting a vulnerability

Do not open a public issue. Use the repository's "Report a vulnerability" button under the Security tab (GitHub private vulnerability reporting). Include the version, the steps to reproduce and the effect.

Expect an acknowledgement within 7 days. A fix and a disclosure date are agreed with the reporter.

## Scope

In scope: the `kb_distillery` package, the web app and the server in `server/`, the publishing code in `publish/` and the Cloudflare worker, and the hooks and scripts in this repository.

Out of scope: the content of a knowledge base, and third-party services the engine calls.

## Secrets

The engine reads API keys from the environment, the OS keychain or `~/.config/kb-distillery/`. Keys are never written to a knowledge base or to this repository. CI runs a secret scan on every pull request. If you find a committed secret, report it as above and revoke it.
