# 0006 — Track `/apply` reconciliation with a read-only `status` flag on the corpus

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

`/apply` reads the whole `docs/inspiration/` corpus each run and judges every lead
against the project from scratch. In practice most leads resolve to *"the project
already holds this"* — the corpus is largely confirmatory — so a run spends most of
its effort **re-deriving conclusions it reached last time**. Observed directly: a run
re-grounded four cross-cutting themes only to confirm each was already in canon, and
promoted exactly one genuinely-new lead. That re-grounding is pure churn, and it
grows with the corpus.

We want `/apply` to *skip leads already reconciled* on later runs. Two constraints
shape the mechanism:

1. **`/apply` cannot write the corpus.** Both `write_doc` and the guard hook refuse
   `<docs>/inspiration/` ([0004](0004-apply-write-boundary.md)) — the corpus is
   `/inspire`'s output and `/apply`'s read-only source. So the "done" marker cannot
   be written into the notes *by `/apply`*; it must be something a human or
   `/inspire` writes and `/apply` only reads.
2. **A boolean "applied" would miss the dominant case.** The churn isn't mostly
   leads *`/apply` promoted* — it's leads the project **already held independently**.
   A flag that records only "promoted" marks none of those, and the run re-grounds
   them anyway. The flag has to carry a *disposition*, not a yes/no.

## Decision

Add a **`status` frontmatter field** to each inspiration note, as the source of
truth for `/apply`'s worklist:

```yaml
status: open   # open | promoted | already-in-canon | wont-do
```

- **`open`** (and *absent* `status`, for backward compatibility) — not yet
  reconciled; `/apply` works it.
- **`promoted`** — a prior `/apply` landed this lead in the project's docs.
- **`already-in-canon`** — the project already held it; `/apply` correctly declined
  to manufacture an edit.
- **`wont-do`** — deliberately ruled out of scope.

`/apply` works **only `open` notes** and skips the rest, surfacing the skip count so
it is visible rather than silent. An explicit user request for a named note overrides
the flag.

**Ownership follows the write boundary, unchanged:**

- **`/inspire` writes it.** New notes are born `open`. On a re-read that overwrites an
  existing note, `/inspire` **preserves** the current `status` — unless the source's
  substance materially changed, in which case it resets to `open` for re-evaluation.
- **The user writes it.** Editing one frontmatter line is the whole upkeep cost.
- **`/apply` only reads it.** It never writes the corpus. Instead its final report
  *names the exact flips* (`<note> → already-in-canon`, etc.) so the corpus owner can
  apply them in seconds. This keeps the read/write boundary intact while making the
  manual step trivial.

The README **Sources** table gains a Status column that **reflects** the notes'
frontmatter — a generated view, never a second source of truth. `/inspire`
regenerates it from the notes; it must not diverge.

## Consequences

- The re-grounding churn drops to the still-`open` notes only. The dominant
  "already-in-canon" case is now recorded once and skipped thereafter.
- **The write boundary is untouched.** No new write path, no new tool, and `/apply`
  stays strictly read-only on the corpus — the whole point of the two-stage split
  ([0002](0002-untrusted-content-isolation.md), [0004](0004-apply-write-boundary.md)).
  This is why Design A (read-only flag) was chosen over a `/apply`-written ledger.
- **Upkeep is manual, by design.** Because `/apply` can't write the corpus, flipping a
  note to `promoted`/`already-in-canon` is a human (or `/inspire`) act. `/apply`
  reduces it to pasting the lines it reports, but it is still a step a user can skip —
  in which case the next run simply re-grounds, i.e. today's behavior. The feature
  fails *safe*: a missing/stale flag costs work, never correctness.
- **Staleness is bounded but real.** A `status` set when canon said one thing can go
  stale if canon later regresses. `/apply` trusts the flag (re-checking every settled
  note would defeat the purpose) but treats an explicit user request, or a `/inspire`
  re-read that resets to `open`, as the re-open signals. Same shape as any cached
  judgment.
- **No enforcement code.** This is a prompt-level contract across two `SKILL.md`s plus
  a frontmatter convention — there is nothing in the trusted MCP/hook layer to test.
  The contract lives in the prompts and this ADR; keep them in sync.

## Alternatives considered

- **A `/apply`-written ledger outside the corpus** (e.g. `docs/inspiration-applied.md`
  via `write_doc`). Fully automatic — no manual flip — but adds a written artifact and
  a second place state can drift from the corpus, and the human-facing README still
  needs `/inspire`/manual reconcile anyway. Rejected in favor of keeping `/apply`
  read-only on all corpus state; the manual flip is cheap and boundary-clean.
- **Mark in the corpus directly from `/apply`.** Would require breaking the corpus
  read-only rule ([0004](0004-apply-write-boundary.md)). Rejected outright.
- **A boolean `applied: true`.** Simpler, but marks only promoted leads and misses the
  dominant already-in-canon case, so it wouldn't cut the actual churn. Rejected.
- **Per-theme status in the README.** Matches `/apply`'s unit of work, but themes are
  synthesized and renumbered each run — no stable handle to carry status across
  regeneration. Notes are stable and already carry frontmatter; status lives there and
  the README merely reflects it.
