# Architecture

`inspire` is a Claude Code **plugin** — it ships no application of its own. It
contributes artifacts (skills, subagents, MCP servers, hooks) that run *inside a
host project* when installed. Throughout, "the project" / "this project" means the
**host repo** the plugin is invoked in, not this repo.

It runs as a two-stage learning loop:

```
   URLs                                          docs/inspiration/         project docs
    │                                            (the corpus)              (canon)
    ▼                                                  │                        ▲
┌─────────┐   fan out    ┌──────────────┐   write      │         read           │
│/inspire │ ───────────▶ │  watcher /   │ ──────┐      ▼      ┌────────┐  dispatch│
│ (intake)│   1 per URL  │  reader      │      ┌┴──────────┐ │/apply  │ ─────────┤
└─────────┘              │  subagents   │      │ notes +   │ │(promote)│  approved│
                         └──────┬───────┘      │ index     │ └────┬───┘  edits    │
                                │ MCP (read)   └───────────┘      │ dispatch      │
                                ▼                                 ▼               │
                    ┌────────────────────────┐         ┌───────────────────┐    │
                    │ inspire-content server │         │ inspire-applier   │────┘
                    │ get_youtube_transcript │         │ subagent          │  MCP (write)
                    │ get_webpage_content    │         │   └ write_doc ─────┼─▶ inspire-docs
                    └────────────────────────┘         └───────────────────┘     server
```

## Repository layout

The marketplace manifest is at the repo root; the plugin is nested under `inspire/`
(see [ADR 0001](../decisions/0001-plugin-as-marketplace-subdir.md)).

```
.claude-plugin/marketplace.json     # marketplace → source "./inspire"
inspire/
  .claude-plugin/plugin.json        # plugin manifest
  .mcp.json                         # registers the two MCP servers
  skills/
    inspire/SKILL.md                # /inspire — intake orchestrator
    apply/SKILL.md                  # /apply   — promotion editor
  agents/
    inspire-watcher.md              # reads one YouTube video   (read-only)
    inspire-reader.md               # reads one web page         (read-only)
    inspire-applier.md              # writes approved doc edits  (write_doc only)
  mcp/
    server.py                       # inspire-content  (pure read: transcript + page)
    docs_server.py                  # inspire-docs     (bounded write: write_doc)
  hooks/
    hooks.json                      # PreToolUse ×2 + SessionStart
    guard_docs_write.py             # /apply write backstop
    web_fetch_policy.py             # web-fetch domain policy
    check_deps.sh                   # session dependency check
  ruff.toml                         # lint config (py313, line-length 100)
```

## Stage 1 — `/inspire` (intake)

1. **Collect & classify.** The skill extracts every URL from the user's message and
   routes each: YouTube → `inspire-watcher`, any other `http(s)` page →
   `inspire-reader`. Non-`http(s)` URLs are ignored.
2. **Fan out.** One subagent per URL, dispatched together in a single message so
   they run concurrently. Each subagent:
   - calls its one content tool on the `inspire-content` MCP server,
   - reads enough of the host repo (`Read`/`Grep`/`Glob`) to judge relevance,
   - returns a finished markdown evaluation in a **shared output shape** (TL;DR,
     what it's about, what we can learn, directly applicable, skip, caveats, plus a
     relevance score).
3. **Write the corpus.** The skill — never the subagents — writes one note per
   source to `docs/inspiration/<slug>.md` and maintains
   `docs/inspiration/README.md` (a table + a cross-cutting-themes synthesis).

Because both subagents return the same shape, the skill's note-writing and synthesis
are source-agnostic; routing is the only YouTube-vs-web branch.

### `inspire-content` MCP server

A single PEP 723 script (`mcp/server.py`) launched via `uv run` (deps self-provision;
nothing is installed into the host project). Two tools, both **pure reads** that
return a provenance header + fenced, control-char-stripped, length-capped text:

- `get_youtube_transcript(url, language)` — wraps `youtube-transcript-api`; input is
  constrained to a YouTube id, so it can only ever reach YouTube.
- `get_webpage_content(url)` — fetches the page (SSRF-guarded) and extracts the main
  text with `trafilatura`. Static HTML only.

## Stage 2 — `/apply` (promotion)

1. **Arm the backstop.** The skill creates a marker file (`.inspire-apply.lock`) that
   activates the guard hook for the run.
2. **Scope & verify.** It reads the corpus (prioritising the cross-cutting themes),
   learns the project's doc conventions, and **verifies each lead against the actual
   target file** (the file is ground truth; a stale lead loses).
3. **Propose.** It emits a doc-by-doc edit brief (file / change / why / cost-risk),
   separating keystone edits from dependents, and **stops for approval**.
4. **Apply via subagent.** For approved edits only, it dispatches `inspire-applier`,
   which reads each target, composes the new file, and writes it through
   `write_doc`. The skill itself never calls `Write`/`Edit`.
5. **Report & release.** It relays what landed (and what it deliberately didn't),
   then removes the marker.

### `inspire-docs` MCP server

A second PEP 723 script (`mcp/docs_server.py`). One tool, `write_doc(path, content)`,
that writes a whole file **only** within `INSPIRE_DOCS_DIR_PATH` (default `./docs`)
and **never** inside `<docs>/inspiration/` — the check is unconditional, in trusted
server code. Kept a separate server so `inspire-content` stays strictly pure-read.

## The subagents at a glance

| Subagent | Stage | Tool allowlist | Can write? |
| --- | --- | --- | --- |
| `inspire-watcher` | intake | `get_youtube_transcript`, Read, Grep, Glob | no |
| `inspire-reader` | intake | `get_webpage_content`, Read, Grep, Glob | no |
| `inspire-applier` | promotion | `write_doc`, Read, Grep, Glob | only via `write_doc` (docs dir) |

Each is an *allowlisted subagent over an owned, hardened MCP surface* — the same
pattern on both the read and write sides. See [security.md](security.md).

## Configuration & hooks

Behaviour is tuned by a few environment variables and enforced/assisted by three
hooks — all detailed in [hooks-and-config.md](hooks-and-config.md).
