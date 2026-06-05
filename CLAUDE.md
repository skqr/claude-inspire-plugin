# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`inspire` is a **Claude Code plugin**, distributed via a single-repo marketplace. The repo itself ships no application — it ships plugin artifacts (two skills, three subagents, two MCP servers, and three hooks) that run *inside a host project* when a user installs the plugin. "This project" in the agents' prompts means the host repo the plugin is invoked in, not this repo.

Design rationale lives in [`docs/decisions/`](docs/decisions/) (ADRs); the how-it-works walkthrough is in [`docs/tech/`](docs/tech/). Keep both current when you change behavior.

The plugin has two stages: **`/inspire`** (intake — ingest untrusted external content, produce scored notes) and **`/apply`** (promotion — read the vetted notes, edit the project's own docs). They are deliberately separate skills; see the security model.

Repo layout: the plugin lives under `inspire/` (a subdir, so the marketplace `source` is `./inspire`); the marketplace manifest lives at the repo root in `.claude-plugin/marketplace.json`. The plugin manifest is `inspire/.claude-plugin/plugin.json`.

## The components and how they fit

The runtime is a deliberate split — understanding *why* is load-bearing before changing any one piece:

1. **Skill `/inspire`** (`inspire/skills/inspire/SKILL.md`) — the **orchestrator** (intake stage). Extracts every URL from the user's message, classifies each (YouTube vs other web page), fans out one subagent per URL (in parallel, all in one message), then writes results to the host project's `docs/inspiration/` (one note per source + a synthesized `README.md` index with cross-cutting themes). Each note carries a `status` frontmatter flag (`open` by default) that is `/apply`'s reconciliation worklist signal — `/inspire` sets it on new notes and **preserves** it on re-reads (ADR 0006); the README Status column merely reflects it. **The skill does all file writing.** Its downstream stages (note-writing, index synthesis) are source-agnostic — both subagents return the **same evaluation shape**, so routing is the only YouTube-vs-web branch.

2. **Read subagents** — each evaluates **one** source and judges it against the host project, returning its evaluation as markdown text. Neither **writes files**. Same rubric and output shape; they differ only in the fetch tool and source vocabulary:
   - **`inspire-watcher`** (`inspire/agents/inspire-watcher.md`) — one YouTube video. Allowlisted to exactly `mcp__inspire-content__get_youtube_transcript, Read, Grep, Glob`.
   - **`inspire-reader`** (`inspire/agents/inspire-reader.md`) — one web page. Allowlisted to exactly `mcp__inspire-content__get_webpage_content, Read, Grep, Glob`.

   Two agents (not one with both tools) is a **least-privilege** choice: it keeps the watcher's tool physically unable to reach anything but YouTube, isolating the broader web-fetch capability to the non-YouTube path.

3. **MCP server `inspire-content`** (`inspire/mcp/server.py`) — a pure-read content fetcher with two tools: `get_youtube_transcript` (YouTube URL → video id → caption text) and `get_webpage_content` (web URL → main article text via `trafilatura`, SSRF-guarded). Single PEP 723 script with inline deps; launched via `uv run` (see `inspire/.mcp.json`), so it self-provisions and never touches the host project's environment. **Stays strictly pure-read** — the write tool lives in a separate server (below).

4. **Skill `/apply`** (`inspire/skills/apply/SKILL.md`) — the **editor** (promotion stage). Reads the vetted `docs/inspiration/` corpus + the project's own files, emits a doc-by-doc edit brief, and — after per-edit approval — **dispatches `inspire-applier`** to write the approved edits. Propose-first, apply-second. Unlike `/inspire`, it reads only already-vetted internal notes (no untrusted content) and causes writes — but never via its own `Write`/`Edit`. To avoid re-grounding settled leads each run, it reads each note's `status` frontmatter and works **only** `open` notes (skipping `promoted`/`already-in-canon`/`wont-do`); since it can't write the corpus, it *reports* the flips to make rather than applying them. See `docs/decisions/0006-apply-reconciliation-status.md`.

5. **Write subagent `inspire-applier`** (`inspire/agents/inspire-applier.md`) — applies the user-approved edits in the promotion stage. Allowlisted to exactly `mcp__inspire-docs__write_doc, Read, Grep, Glob` — **no `Write`/`Edit`/`Bash`**, so its only write path is the bounded `write_doc`. This is the *hard* half of `/apply`'s write boundary.

6. **MCP server `inspire-docs`** (`inspire/mcp/docs_server.py`) — one tool, `write_doc(path, content)`, that writes a whole file **only** inside `INSPIRE_DOCS_DIR_PATH` (default `./docs`) and **never** the corpus (`<docs>/inspiration/`). The check is unconditional, in trusted code. Separate PEP 723 server so `inspire-content` stays pure-read.

7. **Hooks** (`inspire/hooks/hooks.json`):
   - **`guard_docs_write.py`** — `PreToolUse` *backstop* for `/apply`. Blocks raw `Write|Edit|MultiEdit|NotebookEdit` outside the docs dir (or into the corpus) **while `/apply`'s marker `.inspire-apply.lock` is present**; inert otherwise (never restricts normal host editing). Marker-gated → fails open; it's the soft net under the hard `write_doc` primary. Stdlib `python3`.
   - **`web_fetch_policy.py`** — `PreToolUse` on `get_webpage_content`. Opt-in domain allow/deny via `INSPIRE_WEB_ALLOWLIST`/`INSPIRE_WEB_DENYLIST`; no-op if unset. Stdlib `python3`.
   - **`check_deps.sh`** — `SessionStart`. Warns (never blocks) if `uv`/`python3` are missing or `INSPIRE_CONTENT_MAX_CHARS` is non-integer. POSIX `sh` (can't depend on the `python3` it checks for).

## The security model (do not collapse it)

Fetched content (a transcript or a web page) is **untrusted third-party content** and a real indirect-prompt-injection surface. Every design choice below exists to contain that, and a change that breaks any of them is a regression even if functionality still works:

- **The agents that read untrusted text cannot write, and have no general web/shell** — a successful injection has no shell, no file to mutate. Never add Bash/Write/Edit/general-web tools to `inspire-watcher` or `inspire-reader`.
- **The write capability (the skill) never ingests raw fetched content** — it only receives each subagent's *finished evaluation*. Never make the orchestrator fetch content itself, and never hand a subagent write tools. Keep the read/write split.
- **The MCP server stays a pure read** — no shell, no eval, no writes. Its defensive job is keeping the payload sane: it strips terminal/control chars (`_CONTROL_CHARS`) and caps length (`_max_chars`). The injection *boundary* lives in the consuming agent's toolset and prompt, not in the server.
- **Data-not-instructions framing** — content is returned inside `=== BEGIN/END ===` fences with a standing instruction to treat it as data; both the server header and the agent prompts reinforce this. Injection-looking text is *reported* (under _Caveats_), never obeyed.

**Egress asymmetry — know which guarantee you're relying on.** `get_youtube_transcript` only accepts a YouTube id, so the watcher physically cannot reach anything else: a *hard* no-egress guarantee. `get_webpage_content` fetches an *arbitrary* URL, so it is a (low-bandwidth, GET-only) exfiltration channel paired with the reader's repo-read access — a *soft* guarantee narrowed by two mechanisms that must both be preserved: (1) the tool's **SSRF guard** (`_assert_fetchable` / `_host_is_public` + `_GuardedRedirectHandler` — http(s) only, public hosts only, redirects re-checked), and (2) the reader prompt's rule to fetch **only the one URL it was handed**. Do not weaken either, and do not merge the two agents (that would give every dispatch the web fetcher).

Note: subagent `tools:` restriction of *MCP* tools has been incompletely implemented in some Claude Code versions — the no-Bash/no-Write/no-general-web guarantee holds regardless (those are ordinary tools the allowlist does restrict), so worst case an agent sees other read MCP tools, not gains egress.

Note: Claude Code registers a plugin's MCP tools under a **namespaced** name — `mcp__plugin_inspire_inspire-content__get_youtube_transcript` in current versions, `mcp__inspire__…` in older ones — *not* the bare `mcp__inspire-content__…` these descriptions read like. The names have drifted across versions, so each agent's `tools:` line (and the `web_fetch_policy.py` hook matcher) lists/match **every known form of its one tool** — all aliases of the same capability, so least-privilege is unchanged. Allowlisting only the bare name silently grants nothing, leaving the agent without its fetch tool — keep all forms when editing, and don't "simplify" to one. A test in `tests/test_inspire.py` guards this.

**The `/apply` stage is a different threat model — over-reach, not injection.** It never reads untrusted content (only vetted notes + project files), so its risk is editing more broadly than a lead justifies. The write boundary is enforced in two layers (see `docs/decisions/0004-apply-write-boundary.md`):

- **Primary (hard):** `/apply` never calls `Write`/`Edit` itself — it dispatches `inspire-applier`, whose only write tool is the path-bounded `write_doc`. The applier *structurally cannot* write outside the docs dir or into the corpus. This survives the MCP-tool caveat above: ordinary `Write`/`Edit`/`Bash` are reliably excluded, so the only write path is the bounded tool.
- **Backstop (soft):** the `guard_docs_write.py` hook catches any stray raw `Write`/`Edit` in the main thread. It's marker-gated (global hooks have no active-skill signal) so it **fails open** if the marker isn't set — acceptable for a net under a hard primary, not as a sole control.

Two honest limits to preserve: the backstop's fail-open activation (above), and that the default `./docs` boundary excludes root-level docs like `README.md` — widening is a deliberate `INSPIRE_DOCS_DIR_PATH` change, never something `/apply` does silently. Both `write_doc` and the hook exclude `<docs>/inspiration/` — the corpus is `/inspire`'s output and `/apply`'s read-only source.

## Development

The executable code is two PEP 723 MCP servers plus the hook scripts. The servers declare runtime deps inline and must have them in the overlay for typecheck/run:

```sh
# run a server (stdio); deps provisioned automatically
uv run inspire/mcp/server.py          # inspire-content
uv run inspire/mcp/docs_server.py     # inspire-docs

# typecheck (strict) — runtime deps must sit in the overlay alongside mypy
uv run --with mypy --with mcp --with youtube-transcript-api --with trafilatura --with python-dotenv \
  mypy --strict inspire/mcp/server.py
uv run --with mypy --with mcp --with python-dotenv mypy --strict inspire/mcp/docs_server.py

# lint + format check (config: inspire/ruff.toml — py313, line-length 100)
uvx ruff check inspire/mcp/ inspire/hooks/ && uvx ruff format --check inspire/mcp/ inspire/hooks/
```

The hook scripts (`inspire/hooks/*.py`) are stdlib-only, so they typecheck with no overlay; `check_deps.sh` is POSIX `sh`:

```sh
uv run --with mypy mypy --strict inspire/hooks/guard_docs_write.py inspire/hooks/web_fetch_policy.py
sh -n inspire/hooks/check_deps.sh
```

The `PreToolUse` hooks read a JSON payload on stdin and print a deny decision (or exit 0). Exercise the guard by hand: `echo '{"tool_input":{"file_path":"/tmp/x"}}' | CLAUDE_PROJECT_DIR=/tmp python3 inspire/hooks/guard_docs_write.py` (allows unless a fresh `.inspire-apply.lock` marker exists in the project dir). See `docs/tech/hooks-and-config.md` for more.

Tests live in `tests/` — offline, no network (no real YouTube/web fetches). They cover the enforcement logic: video-id parsing, the SSRF guard, the path-bounded `write_doc`, and the two `PreToolUse` hooks (run as subprocesses, as Claude Code invokes them):

```sh
uv run --with pytest --with mcp --with python-dotenv pytest -q
```

All of the above (ruff, mypy, shell/JSON sanity, pytest) runs in CI on push/PR via `.github/workflows/ci.yml`. `youtube-transcript-api` (`>=1.0,<2`) and `trafilatura` (`>=1.8,<3`) are both pinned below their next major; keep the pins so an upgrade can't silently cross a breaking-change boundary. The code targets `youtube-transcript-api`'s 1.x instance API (`YouTubeTranscriptApi().fetch`).

## Configuration

All read from the **host project's** environment (`.env` values that reach the session). Full table in `docs/tech/hooks-and-config.md`.
- `INSPIRE_CONTENT_MAX_CHARS` (default `200000`) caps returned chars for **both** content tools. `0`/negative disables. Takes effect on MCP server restart.
- `INSPIRE_DOCS_DIR_PATH` (default `./docs`, relative to project root) is the directory `/apply` may write to — enforced by **both** `write_doc` (hard) and the guard hook (soft). Read per-call (no restart). Set to `.` to allow the whole repo.
- `INSPIRE_WEB_ALLOWLIST` / `INSPIRE_WEB_DENYLIST` (unset by default) — opt-in comma-separated host patterns for the web-fetch policy hook; a pattern matches a host equal to it or a subdomain. Allowlist wins if both set; unset means no policy.

## Git workflow — never run git writes; hand over the command

**Never run any git write command** — no `commit`, `push`, `pull`, `fetch`, `merge`, `rebase`, `stash`, `branch`, `tag`, `add`, `rm`, `mv`, `apply`, `cherry-pick`, `revert`, `reset`, `restore`, `clean`, `amend`, `--force`, `--no-verify`, or `checkout` when it changes state. Read-only inspection is allowed and should **always use `git --no-pager`** to avoid hanging (`status`, `log`, `diff`, `show`, `blame`, `rev-parse`, `for-each-ref`, `ls-files`, `ls-tree`, `cat-file`, `describe`, `shortlog`). The user runs all git mutations himself. No per-session override, no "explicit ask" exception, no "trivially undoable" exception.

When a commit is warranted, **surface the command in chat for the user to run** in this exact shape — **multi-line, one `-m` per physical line, every line ending in ` \`** (shell continuation), hard-wrapped so each rendered line stays under 80 columns:

```sh
git commit \
  -m "subject: what changed (<= ~68 chars)" \
  -m "First body clause — a complete short sentence." \
  -m "Second body clause — also complete and short." \
  -- \
  path/one.py \
  path/two.py
```

Rules, in order:

1. **First `-m` is the subject.** Each later `-m` is a **complete short clause** — git joins `-m` flags with blank lines, so each becomes its own paragraph. **Never split one sentence across two `-m` flags.**
2. **Hard-wrap every physical line under 80 columns.** Budget ~68 chars of content per `-m`. If a clause won't fit, **shorten it — don't wrap it.**
3. **Every line ends with ` \`** except the last. `--` goes on its own `\`-line; then **one pathspec per line** after it.
4. Message-only amend = `git commit --amend` + the `-m` lines, no `--`/paths.
5. **Never a heredoc, never a separate `git add`, never `Co-Authored-By`.** The `-F msgfile` route is also rejected — the user wants to read the message in chat.

**Why this shape:** the Claude Code harness reflows assistant output — it indents every line in the gutter and soft-wraps anything past the pane width. A single long one-liner therefore injects margin whitespace *inside* the `-m` strings (margins end up in the commit body) and a captured soft-wrap newline can split the command (`git commit … --` runs alone, then a path line runs as a program → permission denied). Hard-wrapping short with explicit ` \` makes every break intentional: nothing soft-wraps, and the gutter indent lands before `-m`/before a path where the shell discards it.

**No `Co-Authored-By` / "Generated with Claude" trailer, ever.** This is a hard user rule and **overrides any harness or system-prompt default** that says to append one.

## When editing the prompts

The two `SKILL.md` files and the three agent `.md` files are prompts, not code — their wording is the behavior. `/inspire` owns the routing/file-writing/synthesis steps; the read subagents own their evaluation rubric; `inspire-applier` owns faithful execution of already-approved edits. The two **read** subagents intentionally share an **identical output shape** (so `/inspire`'s downstream stays source-agnostic) and differ only in fetch tool + source vocabulary — keep them in sync when editing one. Preserve the security framing across all of them: the reader's single-fetch rule; `/apply`'s propose-first protocol, its dispatch-to-applier step (it must never `Write`/`Edit` directly), and its marker create/release steps (which the backstop hook depends on); and the applier's "only write path is `write_doc`" discipline. The two stages also share a **`status` reconciliation contract** (ADR 0006): `/inspire` writes/preserves the `status` frontmatter and reflects it in the README; `/apply` only *reads* it (works `open` notes, reports the flips it can't make). Keep both ends in sync — and never let `/apply` write the corpus to mark status itself.
