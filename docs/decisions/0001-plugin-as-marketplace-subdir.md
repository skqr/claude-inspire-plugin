# 0001 — Ship as a marketplace with the plugin in a subdirectory

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

`inspire` is distributed as a Claude Code plugin. A plugin needs a *marketplace*
to be installed from (`/plugin marketplace add …` then `/plugin install …`). We
own a single GitHub repo and want it to be both the marketplace and the plugin
source, with room to grow (more plugins, or the plugin's own dev tooling and docs)
without the marketplace and plugin manifests colliding at the root.

## Decision

Keep the **marketplace manifest at the repo root** (`.claude-plugin/marketplace.json`)
and nest the **plugin under `inspire/`**, so the marketplace entry points at
`"source": "./inspire"`. The plugin manifest lives at `inspire/.claude-plugin/plugin.json`.

The repo root is therefore free for project-level concerns (this `docs/` tree,
`README.md`, `LICENSE`, lint config) that are *about developing the plugin*, while
everything *shipped to a user's project* lives under `inspire/`.

## Consequences

- Clean separation: "what the user installs" (`inspire/`) vs "how we develop it"
  (root). Adding a second plugin later is just another sibling directory + a
  marketplace entry.
- One extra directory hop in every plugin path — easy to forget when wiring
  `${CLAUDE_PLUGIN_ROOT}`-relative paths. Mitigated by `${CLAUDE_PLUGIN_ROOT}`
  resolving to the `inspire/` directory at runtime, so in-plugin references stay
  relative to it.
- `docs/` at the repo root documents the plugin's design; it is **not** the
  `docs/inspiration/` corpus the plugin writes into a *host* project. Same name,
  different repo — see [0002](0002-untrusted-content-isolation.md).
