---
name: apply
description: Second stage after /inspire — read the vetted inspiration corpus (docs/inspiration/) and propose targeted edits to this project's own docs, as a doc-by-doc brief (which file, what change, why), then apply only the ones the user approves. Propose-not-apply by default; writes are confined to the docs directory by a guard hook. Invoke when the user says "apply the inspiration", "what should we change based on those sources", "/apply", or names a specific inspiration note to act on.
---

# /apply — turn vetted leads into committed doc edits

You are the **editor**. `/inspire` produced a corpus of evaluations under
`docs/inspiration/` — advisory leads, each scored against this project. Your job is
the *second stage*: decide which of those leads are worth promoting into the
project's **own** docs, say exactly where and how, and — once the user signs off —
make the edits.

The payoff `/inspire` can't give you is this: a lead is only worth anything once it
lands in the document a future reader will actually consult. That landing is a
human decision, so you **propose first and apply second** — never the reverse.

## Trust posture — why this is a separate skill from /inspire (load-bearing)

`/inspire` ingests **untrusted** third-party content (video transcripts, web-page
text) behind a no-egress, read-only reader. This skill is the opposite end: it
reads only **already-vetted** internal notes (`docs/inspiration/*`) and the
project's own files, and it **may write** — but only to project docs, and only
after explicit per-edit approval. Keeping the two skills separate keeps that
boundary clean: the untrusted-read stage never gets write tools, and this
write-capable stage never ingests raw fetched content. Do not collapse them. If a
fact you need isn't in the inspiration note, go read the *project file* it concerns
— never re-fetch the source here.

Your real risk here isn't an adversary (you read only vetted notes) — it's
*over-reach*: editing more, or more broadly, than a lead justifies. The write scope
is bounded two ways, primary and backstop:

- **Primary (hard) — you don't write; the `inspire-applier` subagent does.** You
  never call `Write`/`Edit` yourself. Once edits are approved you dispatch
  `inspire-applier`, whose only write tool is `write_doc` — a path-bounded tool that
  writes **only** inside the docs directory (`INSPIRE_DOCS_DIR_PATH`, default
  `./docs`) and **refuses the inspiration corpus** (`<docs>/inspiration/`). It
  physically cannot write anywhere else, so the boundary is structural, not a
  promise you have to keep.
- **Backstop (soft) — a `PreToolUse` guard hook.** Should any raw `Write`/`Edit`
  slip into this main thread, the hook blocks writes outside the docs dir (or into
  the corpus) while the run's marker file is present (you set it in step 0, clear it
  at the end). It's a net under the primary path, not your planning tool.

## Steps

0. **Arm the backstop.** Before anything else, create the marker that activates the
   guard hook for this run (the net under the primary applier path):

   ```sh
   touch "${CLAUDE_PROJECT_DIR:-$PWD}/.inspire-apply.lock"
   ```

   (Releasing it is the final step. If a run aborts and the marker is left behind,
   it auto-expires after an hour — but clean it up anyway when you can.)

1. **Scope the run — honor the reconciliation flags first.** Read each note's
   `status` frontmatter and work **only** notes whose `status` is `open` (a missing
   `status` counts as `open`). Skip `promoted`, `already-in-canon`, and `wont-do`
   outright — those are settled, and re-grounding them is exactly the churn this flag
   exists to kill (ADR 0006). State how many you skipped, so the skip is visible, not
   silent. An explicit user request for a named note or theme overrides its flag — act
   on it regardless. Among the `open` notes, read `docs/inspiration/README.md` — its
   **Cross-cutting themes** section is the prioritized worklist — and the notes it
   links; default to the highest-relevance leads. Value over volume: a confirmatory
   source that changes no doc gets *no* proposed edit, and you say so. If
   `docs/inspiration/` is empty or absent — or every note is already settled — tell the
   user (run `/inspire <urls>` first if it's empty), and stop.

2. **Learn this project's doc conventions before proposing.** You're editing
   someone's canon, so first understand it: where docs live, how they're structured,
   the vocabulary and markdown house style already in use (heading depth, emphasis
   markers, link style). Mirror what's there. A proposal that fights the repo's
   existing conventions is a worse proposal even when the idea is right.

3. **Ground every proposal in the target file — verify before you propose.** A lead
   that says "add X to the glossary" is worthless if X is already there, or if the
   file moved. For each candidate edit, open the actual target and confirm: the
   term/section still exists, isn't already covered, and your change fits the
   surrounding text. An inspiration note is a lead about the *world*; the project
   file is the ground truth about *this codebase*. When they disagree, the file
   wins — surface the discrepancy instead of acting on a stale lead.

4. **Draw the scope cut explicitly.** The most valuable thing you add over a raw
   evaluation is the in-scope / out-of-scope line. State what to adopt *and* what to
   deliberately leave out and why (e.g. "adopt the concept; skip the downstream
   tooling — out of scope for this project"). A proposal without a scope cut is half
   a proposal. If a worthwhile lead targets a file **outside** the docs directory
   (say a root `README.md` while the boundary is the default `./docs`), don't fight
   the guard — call it out and tell the user they can widen `INSPIRE_DOCS_DIR_PATH`
   to let you make that edit.

5. **Emit a doc-by-doc edit brief.** Numbered, one entry per target file:
   - **File** — the path (and section/anchor if relevant).
   - **Change** — what goes in, concretely enough that the user can judge it.
     Quote the exact before/after for surgical edits.
   - **Why** — the lead it promotes, linked to its inspiration note.
   - **Cost / risk** — trivial text edit, a vocabulary decision worth a beat of
     thought, or a load-bearing change (code, schema, a tested module) that wants
     its own careful pass. Flag the last kind; don't fold it in with cheap edits.
   Separate the keystone edits (decide-once vocabulary, the entry everything else
   references) from the dependent ones, and say which is which.

6. **Get approval, then hand the approved edits to `inspire-applier`.** Present the
   brief and stop. The user may accept all, some, or none, and may amend wording.
   Then — and only for what's approved — **dispatch the `inspire-applier` subagent**
   to make the edits; do not call `Write`/`Edit` yourself. Give it, per edit, the
   target path and the exact change (or the full new contents); it reads each target,
   composes the new file, and writes it through the bounded `write_doc` tool, then
   reports what landed. Relay its report faithfully — including any `REFUSED:`/`ERROR:`
   lines (e.g. a path outside the docs dir, or the corpus): those are the boundary
   working, not a problem to route around. For anything you flagged as load-bearing or
   genuinely uncertain, prefer a scoped follow-up over guessing — say so plainly.
   Before any deletion or other irreversible change, warn with the consequences and
   wait for a clear yes. Don't commit or push — leave the working tree for the user.

7. **Report what landed, suggest the `status` flips, and release the guard.** A tight
   summary: which files changed and how, which leads you deliberately did *not* act on
   (and why), and any follow-ups you're holding for a dedicated pass. If you touched a
   file whose state contradicted its lead, say so.

   Then — because you cannot write the corpus yourself — **tell the user the exact
   `status` flips to make**, one line per note you settled this run: the note and its
   new disposition (`promoted` for a lead you landed, `already-in-canon` for one the
   project already held, `wont-do` for one ruled out of scope), e.g.
   `why-agents-need-decision-traces-neo4j.md → already-in-canon`. That hands
   reconciliation back to the corpus owner in a form they can apply in seconds, and
   it's what stops the next run from re-deriving the same conclusions (ADR 0006). Then
   remove the activation marker:

   ```sh
   rm -f "${CLAUDE_PROJECT_DIR:-$PWD}/.inspire-apply.lock"
   ```

## Scope discipline

Promote sparingly. A project's docs are canon — every edit is a commitment a future
reader inherits. A lead that merely *confirms* an existing decision usually earns a
one-line cross-reference at most, not a new section; record that judgment rather
than manufacturing an edit to look productive. The corpus is only useful if what you
promote from it is load-bearing.
