# Security model

`inspire` has **two stages with opposite threat models**. Conflating them is the
mistake the whole design avoids, so reason about each separately.

| | Stage 1 — `/inspire` (intake) | Stage 2 — `/apply` (promotion) |
| --- | --- | --- |
| Reads | **untrusted** third-party content | only vetted internal notes + project files |
| Writes | the corpus (`docs/inspiration/`) | the project's own docs |
| Primary threat | **prompt injection** from the content | **over-reach** (editing too much/broadly) |
| Primary defense | capability isolation (least-privilege readers) | a structurally bounded write path |

## Stage 1 — containing untrusted content

A transcript or web page can contain text crafted to look like instructions. The
defense is **capability**, not vigilance ([ADR 0002](../decisions/0002-untrusted-content-isolation.md)):

- **Least-privilege readers.** `inspire-watcher` / `inspire-reader` are allowlisted
  to one content tool + read-only repo access. No `Bash`, `Write`/`Edit`, or general
  web — a successful injection has no shell and no file to mutate.
- **The orchestrator writes, and never ingests raw content.** Subagents return a
  *finished evaluation*; the `/inspire` skill does the file writing.
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
> so the worst case is a reader seeing *other read MCP tools*, not gaining egress.

## Stage 2 — bounding `/apply`'s writes

`/apply` reads no untrusted content, so its risk is over-reach. The boundary is
enforced in two layers ([ADR 0004](../decisions/0004-apply-write-boundary.md)):

- **Primary (hard): bounded tool + restricted subagent.** `inspire-applier` is
  allowlisted to exactly `write_doc` + read-only repo access — **no
  `Write`/`Edit`/`Bash`**. `write_doc` writes only inside `INSPIRE_DOCS_DIR_PATH`
  (default `./docs`) and refuses the corpus, unconditionally, in trusted server code.
  The applier therefore *cannot* write out of bounds — structural, not a promise.
  This survives the platform caveat above: ordinary `Write`/`Edit`/`Bash` are
  reliably excluded, so the only write path is the bounded tool.
- **Backstop (soft): the guard hook.** `guard_docs_write.py` blocks any raw
  `Write`/`Edit`/`MultiEdit`/`NotebookEdit` outside the docs dir (or into the corpus)
  while `/apply`'s marker is present — catching a stray main-thread write. Because
  hooks are global to the session with no active-skill signal, activation is
  marker-gated and the hook **fails open** if the marker isn't set; that's acceptable
  for a *backstop* under a hard primary.
- **Propose-first protocol.** Independent of either mechanism, `/apply` presents an
  edit brief and applies only per-edit-approved changes, and never commits/pushes.

## Enforcement summary

| Boundary | Mechanism | Strength |
| --- | --- | --- |
| Reader can't run/exec/exfiltrate | subagent `tools:` allowlist | hard (ordinary tools) |
| YouTube reader reaches only YouTube | tool input is a video id | hard |
| Web reader can't hit internal hosts | SSRF guard in `get_webpage_content` | hard (IP-level) |
| Web reader can't fetch a 2nd URL | reader prompt | soft |
| Web fetch limited to allowed domains | `web_fetch_policy.py` (opt-in) | soft (fails open) |
| `/apply` writes only project docs | `write_doc` + `inspire-applier` allowlist | hard |
| `/apply` raw-write backstop | `guard_docs_write.py` (marker-gated) | soft (fails open) |
| `/apply` won't touch the corpus | both layers exclude `<docs>/inspiration/` | hard (tool) + soft (hook) |
