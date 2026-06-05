# Architecture Decision Records

These ADRs capture the *why* behind `inspire`'s design — the load-bearing choices
that aren't obvious from the code alone. Each record is immutable once **Accepted**;
to change a decision, add a new ADR that supersedes it rather than editing history.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-plugin-as-marketplace-subdir.md) | Ship as a marketplace with the plugin in a subdirectory | Accepted |
| [0002](0002-untrusted-content-isolation.md) | Isolate untrusted content with allowlisted subagents over a pure-read MCP surface | Accepted |
| [0003](0003-web-page-support-and-ssrf.md) | Support arbitrary web pages; accept a soft egress guarantee, SSRF-guarded | Accepted |
| [0004](0004-apply-write-boundary.md) | Bound `/apply`'s writes with a path-restricted tool + restricted subagent (primary) and a guard hook (backstop) | Accepted |
| [0005](0005-operational-hooks.md) | Add a web-fetch domain policy hook and a session dependency-check hook | Accepted |
| [0006](0006-apply-reconciliation-status.md) | Track `/apply` reconciliation with a read-only `status` flag on the corpus | Accepted |

For the *how* (components, data flow, configuration), see [`../tech/`](../tech/).
