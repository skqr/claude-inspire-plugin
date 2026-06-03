# 0004 — Bound `/apply`'s writes with a path-restricted tool + restricted subagent (primary) and a guard hook (backstop)

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

`/apply` is the promotion stage: it reads the vetted `docs/inspiration/` corpus and
edits the project's **own** docs. Its threat model is the *opposite* of `/inspire`'s
— it never touches untrusted content, so the risk isn't injection, it's
**over-reach**: editing more files, or more broadly, than a lead justifies, or
mutating the very corpus it reasons from.

The skill originally claimed "writes only to project docs," but that was a
*prose promise* — a skill runs in the main thread with the full toolset, so nothing
mechanically stopped an out-of-bounds `Write`. The first hardening attempt was a
`PreToolUse` guard hook confining writes to a docs directory. But Claude Code hooks
are **global to the session** with **no active-skill signal**, so a skill-scoped
hook must self-gate on a marker the skill toggles — which means activation is
model-managed and the guard **fails open** if the marker isn't set. A guard whose
engagement depends on the model doing a setup step is a weak guarantee for what is
fundamentally a guardrail against the model's own over-reach.

## Decision

Make the boundary **structural**, with the hook demoted to defense-in-depth:

1. **Primary (hard) — a path-bounded write tool + a write-restricted subagent.**
   - A second MCP server, `inspire-docs`, exposes one tool, `write_doc(path,
     content)`, that writes **only** inside `INSPIRE_DOCS_DIR_PATH` (default
     `./docs`) and **refuses** the inspiration corpus (`<docs>/inspiration/`). The
     check runs in trusted server code, unconditionally — no marker, no model
     cooperation.
   - A subagent, `inspire-applier`, is allowlisted to exactly `write_doc` +
     `Read`/`Grep`/`Glob` — **no `Write`/`Edit`/`Bash`**. Its *only* way to change a
     file is `write_doc`. `/apply` proposes and gets approval, then dispatches the
     applier to execute approved edits.
   - This reuses the [0002](0002-untrusted-content-isolation.md) pattern on the
     write side: an allowlisted subagent over an owned, hardened MCP surface.
2. **Backstop (soft) — the existing guard hook.** It still blocks raw
   `Write`/`Edit`/`MultiEdit`/`NotebookEdit` outside the docs dir (or into the
   corpus) while `/apply`'s marker is present, catching any stray main-thread write
   that bypasses the applier. Because it's now a *net under* a hard primary, its
   fail-open activation is acceptable.
3. **Corpus exclusion in both layers.** `<docs>/inspiration/` is `/inspire`'s
   output and `/apply`'s read-only source; neither `write_doc` nor the hook will let
   `/apply` modify it.

## Consequences

- `/apply`'s "only edits project docs" becomes a **hard guarantee** that survives
  the `tools:`-MCP-restriction caveat: ordinary `Write`/`Edit`/`Bash` *are*
  reliably excluded from the applier, so its only write path is the bounded tool.
  Worst case under the caveat, the applier sees other *read* MCP tools — never an
  unbounded write.
- More moving parts: a second MCP server and a third subagent. Accepted as the cost
  of a hard guarantee, consistent with the plugin's existing architecture.
- A write surface now exists in the plugin. Isolated into its **own** server so the
  `inspire-content` server stays strictly pure-read ([0002](0002-untrusted-content-isolation.md)).
- The default `./docs` boundary excludes root-level docs (`README.md`,
  `CONTRIBUTING.md`). Widening is a deliberate `INSPIRE_DOCS_DIR_PATH` change
  (e.g. `.` for the whole repo), never something `/apply` does silently.
- Corpus protection holds even if `INSPIRE_DOCS_DIR_PATH` is customized: if the
  real corpus sits outside a custom docs root, it's already unreachable by the outer
  bound; if inside, the explicit exclusion covers it.

## Alternatives considered

- **Hook only (marker-gated).** Simpler, fewer parts, but fails open on activation —
  rejected as the *primary* control, kept as the backstop.
- **Always-on global hook (no marker).** Would block all out-of-`docs` writes the
  moment the plugin is installed, crippling the host project's normal editing.
  Rejected.
- **Detect the active skill from the transcript.** Fragile and expensive per write;
  no clean skill-boundary signal exists. Rejected.
- **Emit a patch for the user to apply (no write capability at all).** Safest, but
  defeats `/apply`'s value proposition ("apply the approved edits"). Rejected.
