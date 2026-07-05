# Security model

`inspire` has **two stages with opposite threat models**. Conflating them is the
mistake the whole design avoids, so reason about each separately.

| | Stage 1 — `/inspire` (intake) | Stage 2 — `/apply` (promotion) |
| --- | --- | --- |
| Reads | **untrusted** third-party content | only vetted internal notes + project files |
| Writes | the corpus (`docs/inspiration/`) — via `write_note`, bounded to it | the project's own docs — via `write_doc`, which excludes the corpus |
| Primary threat | **prompt injection** from the content | **over-reach** (editing too much/broadly) |
| Primary defense | capability isolation (least-privilege readers) + a corpus-bounded write path | a structurally bounded write path |

## Stage 1 — containing untrusted content

A transcript or web page can contain text crafted to look like instructions. The
defense is **capability**, not vigilance ([ADR 0002](../decisions/0002-untrusted-content-isolation.md)):

- **Least-privilege readers.** `inspire-watcher` / `inspire-reader` are allowlisted
  to one content tool + read-only repo access. No `Bash`, `Write`/`Edit`, or general
  web — a successful injection has no shell and no file to mutate.
- **The orchestrator never ingests raw content, and never writes raw either.**
  Subagents return a *finished evaluation*; the `/inspire` skill composes the corpus
  files from those and dispatches `inspire-scribe` — whose only write tool is
  `write_note`, path-bounded to `<docs>/inspiration/` — to write them
  ([ADR 0007](../decisions/0007-inspire-write-boundary.md)). Evaluations are
  *derived from* untrusted content, so bounding the write path means even
  instruction-looking text that survives into one can at most affect the corpus,
  never the project's other files.
- **Pure-read, payload-hardening server.** `inspire-content` only resolves URL→text,
  strips control/escape characters, and caps length.
- **Data-not-instructions framing.** Content is fenced and labelled "data"; the
  server header and the subagent prompts both reinforce it. Injection-looking text is
  *reported*, never obeyed.

### Egress: hard for YouTube, soft for web

This asymmetry is load-bearing — know which guarantee you're relying on
([ADR 0003](../decisions/0003-web-page-support-and-ssrf.md)):

- **YouTube (hard).** `get_youtube_transcript` accepts only a video id, so the
  watcher physically cannot reach anything but YouTube. Nowhere to exfiltrate to.
- **Web (soft).** `get_webpage_content` fetches an arbitrary URL — inherently a
  (low-bandwidth, GET-only) exfiltration channel when paired with repo read access.
  Narrowed two ways, both of which must be preserved:
  1. **SSRF guard** (`_assert_fetchable` / `_host_is_public` + `_GuardedRedirectHandler`):
     `http(s)` only; the initial host **and every redirect hop** must resolve to a
     public IP — loopback, link-local, private, reserved, multicast, and the
     `169.254.169.254` metadata endpoint are refused.
  2. **Prompt rule:** the reader fetches *only the one URL it was handed* and reports
     (never obeys) any page text urging another fetch.
  An operator can further restrict web egress by **domain** via the fetch-policy hook
  (see [hooks-and-config.md](hooks-and-config.md)) — defense-in-depth, not a
  replacement for the SSRF guard.

> **Platform caveat.** Subagent `tools:` restriction of *MCP* tools has been
> incomplete on some Claude Code versions. The no-`Bash`/no-`Write`/no-general-web
> guarantee holds regardless (those are ordinary tools the allowlist does restrict),
> so the worst case is an agent seeing the *other MCP tools* — reads, plus the two
> path-bounded write tools — not gaining egress or an unbounded write.

## Bounding each stage's writes — two symmetric layers

Both skills run in the main thread with the full toolset, so each stage's write
scope is made structural the same way ([ADR 0004](../decisions/0004-apply-write-boundary.md)
for `/apply`, mirrored by [ADR 0007](../decisions/0007-inspire-write-boundary.md)
for `/inspire`):

- **Primary (hard): a path-bounded tool + a restricted subagent.** The skill never
  calls `Write`/`Edit`; it dispatches a write subagent allowlisted to exactly one
  tool on the `inspire-docs` server + read-only repo access — no
  `Write`/`Edit`/`Bash`. The two tools' bounds are exact complements, enforced
  unconditionally in trusted server code:
  - `/inspire` → `inspire-scribe` → `write_note`: **only** inside the corpus
    (`<docs>/inspiration/`).
  - `/apply` → `inspire-applier` → `write_doc`: **only** inside
    `INSPIRE_DOCS_DIR_PATH` (default `./docs`) and **never** the corpus.
  This survives the platform caveat above: ordinary `Write`/`Edit`/`Bash` are
  reliably excluded, so the only write paths are the bounded tools.
- **Backstop (soft): the guard hook.** `guard_docs_write.py` catches any raw
  `Write`/`Edit`/`MultiEdit`/`NotebookEdit` in the main thread while a skill's
  marker is present — `.inspire-intake.lock` confines writes to the corpus only;
  `.inspire-apply.lock` to the docs dir minus the corpus (freshest marker wins if
  both exist). Because hooks are global to the session with no active-skill signal,
  activation is marker-gated and the hook **fails open** if the marker isn't set;
  that's acceptable for a *backstop* under a hard primary.

### `/apply` specifics

`/apply` reads no untrusted content, so its risk is over-reach — and its last line
of defense is procedural: a **propose-first protocol**. Independent of either
mechanism above, it presents an edit brief and applies only per-edit-approved
changes, and never commits/pushes.

## Enforcement summary

| Boundary | Mechanism | Strength |
| --- | --- | --- |
| Reader can't run/exec/exfiltrate | subagent `tools:` allowlist | hard (ordinary tools) |
| YouTube reader reaches only YouTube | tool input is a video id | hard |
| Web reader can't hit internal hosts | SSRF guard in `get_webpage_content` | hard (IP-level) |
| Web reader can't fetch a 2nd URL | reader prompt | soft |
| Web fetch limited to allowed domains | `web_fetch_policy.py` (opt-in) | soft (fails open) |
| `/inspire` writes only the corpus | `write_note` + `inspire-scribe` allowlist | hard |
| `/inspire` raw-write backstop | `guard_docs_write.py` intake mode (marker-gated) | soft (fails open) |
| `/apply` writes only project docs | `write_doc` + `inspire-applier` allowlist | hard |
| `/apply` raw-write backstop | `guard_docs_write.py` apply mode (marker-gated) | soft (fails open) |
| `/apply` won't touch the corpus | both layers exclude `<docs>/inspiration/` | hard (tool) + soft (hook) |
| Neither writer crosses stages | complementary tool bounds; no shared write tool | hard |
