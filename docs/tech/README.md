# inspire — technical documentation

How the plugin works under the hood, for contributors and the curious.

- **[architecture.md](architecture.md)** — the components, the two stages, and how
  data flows from a dropped URL to a committed doc edit.
- **[security.md](security.md)** — the two threat models (untrusted-content
  injection on intake; over-reach on promotion) and exactly which mechanism enforces
  each boundary.
- **[hooks-and-config.md](hooks-and-config.md)** — every hook and environment
  variable, what it does, and how to verify it.

For the *why* behind these choices, see the [decision records](../decisions/). For
user-facing usage, see the repo [`README.md`](../../README.md).
