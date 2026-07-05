# 0007 — Bound `/inspire`'s corpus writes symmetrically: `write_note` + scribe subagent (primary) and an intake mode in the guard hook (backstop)

- **Status:** Accepted
- **Date:** 2026-07-05

## Context

[0004](0004-apply-write-boundary.md) made `/apply`'s write scope a hard,
structural guarantee. `/inspire`'s write scope, by contrast, remained a *prose
promise*: the skill ran in the main thread with the full toolset and wrote
`docs/inspiration/` with raw `Write` — nothing mechanically confined those writes
to the corpus. The guard hook couldn't help either: it activated only on
`/apply`'s marker, and its rules point the wrong way for intake (it *denies*
corpus writes, which is exactly where `/inspire` writes).

The asymmetry also mattered for the injection story. The orchestrator never sees
raw fetched content, but the evaluations it writes to disk are *derived from*
untrusted content — a laundered, second-order injection surface sitting in the
one intake context that held an unbounded write capability. Instruction-looking
text that survived a reader's evaluation reached a context that could write
anywhere the session could.

## Decision

Mirror 0004 on the intake side, making the two stages' write bounds exact
complements:

1. **Primary (hard) — a corpus-bounded write tool + a write-restricted subagent.**
   - The `inspire-docs` server gains a second tool, `write_note(path, content)`,
     that writes **only** inside the inspiration corpus (`<docs>/inspiration/`,
     where `<docs>` is `INSPIRE_DOCS_DIR_PATH`) — the exact complement of
     `write_doc`, which refuses the corpus. Same trusted-code, unconditional
     enforcement.
   - A fourth subagent, `inspire-scribe`, is allowlisted to exactly `write_note` +
     `Read`/`Grep`/`Glob` — **no `Write`/`Edit`/`Bash`**. `/inspire` composes every
     file (notes + README) and dispatches the scribe to write them; the skill
     itself never calls `Write`/`Edit`.
2. **Backstop (soft) — an intake mode in the existing guard hook.** `/inspire`
   arms a second marker, `.inspire-intake.lock`; while it is fresh, the hook
   confines raw main-thread `Write`/`Edit`/`MultiEdit`/`NotebookEdit` to the
   corpus **only**. If both markers are somehow present (an aborted run left one
   behind), the freshest wins. As in 0004, the fail-open activation is acceptable
   for a net under a hard primary.
3. **Division of authorship is unchanged.** The orchestrator still owns routing,
   note composition, status preservation (ADR
   [0006](0006-apply-reconciliation-status.md)), and index synthesis; the scribe
   is the hands, writing handed-to-it contents byte-faithfully — the same
   "compose vs. execute" split `/apply` has with `inspire-applier`.

## Consequences

- `/inspire`'s "only writes the corpus" becomes a **hard guarantee** with the same
  strength as `/apply`'s: ordinary `Write`/`Edit`/`Bash` are reliably excluded
  from the scribe, so its only write path is the bounded tool. Injection that
  survives into an evaluation can at most affect the corpus — which was already
  its output — never the project's other files.
- The two bounds are complementary, and must stay that way: `write_doc` never
  writes the corpus, `write_note` writes nowhere else. Granting either write
  subagent the other's tool would collapse the split (a test guards this).
- Under the platform caveat of 0004 (incomplete `tools:` restriction of MCP tools
  on some Claude Code versions), the worst case grows slightly but stays bounded:
  the applier might *see* `write_note` (and the scribe `write_doc`), so on those
  versions cross-stage writes degrade from hard to prompt-held — but both tools
  still confine every write to the docs tree; no agent ever gains an unbounded
  write or egress.
- More moving parts again: a fourth subagent and a second marker. Accepted as the
  cost of symmetry, and cheaper than 0004 was — no new server, since the tool
  joins `inspire-docs` (keeping `inspire-content` strictly pure-read per
  [0002](0002-untrusted-content-isolation.md)).
- `/inspire` now has an arm/release step like `/apply`; a forgotten marker
  auto-expires after an hour, same as before.

## Alternatives considered

- **Hook-only (intake marker, skill keeps raw `Write`).** Fewer parts, but the
  primary control would fail open on activation — the same reason 0004 rejected
  it. Kept as the backstop only.
- **A third MCP server for `write_note`.** Server-level separation doesn't
  strengthen anything under the platform caveat (tool visibility, not server
  reachability, is what leaks), and it adds a process per session. Rejected.
- **Reusing `inspire-applier` with both tools.** Would hand `/apply`'s writer a
  corpus-write capability, breaking 0004's "never writes the corpus" guarantee.
  Rejected.
- **Having the scribe compose the notes itself.** Would move judgment (status
  preservation, faithful relaying, synthesis) into the restricted context and
  bloat its prompt; the applier precedent keeps hands and author separate.
  Rejected.
