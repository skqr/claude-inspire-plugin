# 0002 — Isolate untrusted content with allowlisted subagents over a pure-read MCP surface

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

`/inspire` evaluates third-party content (YouTube transcripts, web articles)
against the user's project. That content is **untrusted** and a genuine
indirect-prompt-injection surface: a transcript or page can contain text crafted
to look like instructions ("ignore previous instructions", "run this", "exfiltrate
that"). A naïve design — one agent that fetches content, reads the repo, and writes
files — would put injection, repo access, and write/exec capability in a single
context. One successful injection then has everything it needs.

## Decision

Split capability so no single context holds both untrusted content **and** the
power to act on it:

1. **The reader is a least-privilege, (near-)no-egress subagent.** Each per-source
   subagent (`inspire-watcher`, `inspire-reader`) is allowlisted to exactly one
   content tool plus read-only repo access (`Read`/`Grep`/`Glob`). No `Bash`, no
   `Write`/`Edit`, no general web. A successful injection has no shell to run and no
   file to mutate.
2. **The orchestrator writes; it never ingests raw content.** Subagents *return*
   their finished evaluation as text; the `/inspire` skill writes
   `docs/inspiration/`. The write-capable context never sees raw transcript/page
   bytes.
3. **The MCP server is a pure read that hardens the payload.** It only resolves a
   URL to text — no shell, no eval, no writes — and defensively strips terminal/
   control characters and caps length, so a source can't pipe escape sequences or a
   wall of text into a model's context.
4. **Data-not-instructions framing.** Content is returned inside explicit fences
   with a standing "treat as data" instruction, reinforced in both the server
   header and the subagent prompts. Injection-looking text is *reported*, never
   obeyed.

## Consequences

- The blast radius of a malicious source is bounded by the reader's toolset, not by
  the model's vigilance alone — defence by capability, not just by prompt.
- Two near-duplicate subagent prompts (watcher/reader) instead of one. Accepted:
  the duplication keeps each reader's tool surface minimal (see
  [0003](0003-web-page-support-and-ssrf.md)).
- A known platform caveat: subagent `tools:` restriction of *MCP* tools has been
  incomplete on some Claude Code versions. The no-`Bash`/no-`Write`/no-general-web
  guarantee still holds (those are ordinary tools the allowlist does restrict), so
  the worst case is a reader seeing *other read MCP tools*, not gaining egress.
- This "allowlisted subagent over an owned, hardened MCP surface" pattern is the
  template reused for the write side in [0004](0004-apply-write-boundary.md).
