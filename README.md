# inspire — a Claude Code plugin

Drop a batch of links into Claude Code — YouTube videos, web articles, or a mix —
and get each one **evaluated against the project you're working in**: what it's
about, what you can learn from it, and what's directly applicable here —
synthesized into a small durable corpus under `docs/inspiration/`. Then, when you
want to act on it, **`/apply`** promotes the vetted leads into your project's own
docs.

It works in two stages. **Intake** (`/inspire`):

- **A skill, `/inspire`** — the orchestrator. Collects the URLs you drop, routes
  each to the right reader, fans them out, then writes the notes + a synthesized
  index.
- **Two subagents** — `inspire-watcher` evaluates one YouTube video,
  `inspire-reader` evaluates one web page. Both are read-only and minimal-egress
  by design (see _Security_); each returns a finished evaluation in the same shape.
- **An MCP server, `inspire-content`** — a thin, pure-read content fetcher the
  subagents call. Two tools (`get_youtube_transcript`, `get_webpage_content`) in a
  self-contained single Python file with
  [PEP 723](https://peps.python.org/pep-0723/) inline dependencies.

**Promotion** (`/apply`):

- **A skill, `/apply`** — the editor. Reads the vetted corpus and proposes a
  doc-by-doc edit brief, then applies only what you approve, per edit.
- **A subagent, `inspire-applier`**, and a second MCP server, `inspire-docs` — the
  applier executes approved edits through the server's one tool, `write_doc`, which
  is path-bounded to your docs directory. That makes "only edits project docs" a
  structural fact, not a promise (see _Security_).

## Requirements

- Claude Code with plugin support.
- [`uv`](https://docs.astral.sh/uv/) on your `PATH` — the MCP server is launched
  via `uv run`, which provisions its Python deps in an isolated, cached
  environment on first use. Nothing is installed into your project.

## Install

```sh
/plugin marketplace add skqr/claude-inspire-plugin
/plugin install inspire@inspire-marketplace
```

Then, in any repo:

```text
/inspire https://youtu.be/VIDEO_ONE
https://www.youtube.com/watch?v=VIDEO_TWO
https://example.com/some-article
```

URLs can be one-per-line or mixed into a sentence — every YouTube and web URL in
your message is picked up (YouTube links go to `inspire-watcher`, other web pages
to `inspire-reader`). Results land in `docs/inspiration/` (one note per source +
an index with a cross-cutting-themes synthesis).

Then, when you want to turn those leads into changes:

```text
/apply
```

`/apply` reads the `docs/inspiration/` corpus, presents a doc-by-doc edit brief
(which file, what change, why), and applies only the edits you approve — one at a
time. Its writes are confined to your docs directory (`INSPIRE_DOCS_DIR_PATH`,
default `./docs`); you can also point it at a specific note or theme
(`/apply the agentic-engineering note`).

## Security model

Fetched content — a video transcript or a web page's text — is **untrusted
third-party content** and a genuine indirect-prompt-injection surface: captions,
titles, or page body can contain text engineered to hijack a reading agent. This
plugin is built around that:

1. **Least-privilege readers.** Each reader is allowlisted to exactly one content
   tool plus read-only repo access (`Read`/`Grep`/`Glob`). No Bash, no Write/Edit,
   no general web. A successful injection has no shell to run and no file to mutate.
2. **The orchestrator writes files, not the exposed agent.** Readers *return*
   their evaluation as text; the `/inspire` skill writes `docs/inspiration/`. The
   write capability never sits in a context that has ingested raw fetched content.
3. **Data-not-instructions framing.** Content is delivered inside fences with a
   standing instruction to treat it as data; injection-looking text is reported,
   never obeyed.
4. **The MCP server is a pure read.** It only resolves a URL → text. It strips
   terminal/control characters and caps length so a source can't pipe escape
   sequences or a wall of text into a model's context.

**Egress: hard for YouTube, narrowed for web.** `inspire-watcher`'s transcript
tool can only ever reach YouTube (its input is a video id), so it has *nowhere* to
exfiltrate to — a hard guarantee. `inspire-reader`'s `get_webpage_content` fetches
an *arbitrary* URL, which is inherently a (low-bandwidth, GET-only) exfiltration
channel when paired with repo read access. We narrow it two ways: the tool is
**SSRF-guarded** (http(s) only; loopback/link-local/private/reserved hosts —
including the `169.254.169.254` cloud-metadata endpoint — are refused, on the
initial request *and* every redirect hop), and the reader's prompt requires it to
fetch **only the single URL it was handed** and to report (never obey) any page
text urging another fetch. This is a deliberately weaker posture than the YouTube
path — documented here rather than papered over. For an extra layer, you can
restrict fetches by **domain** with `INSPIRE_WEB_ALLOWLIST` / `INSPIRE_WEB_DENYLIST`
(see _Configuration_) — a policy on top of the IP-level SSRF guard, not a substitute.

> **Version caveat (worth verifying on your Claude Code build):** subagent
> *restriction* of MCP tools via `tools:` frontmatter has been incompletely
> implemented in some Claude Code versions (a subagent may inherit MCP tools from
> the host). The no-Bash / no-Write / no-general-web guarantee in (1) holds
> regardless — those are ordinary tools the allowlist does restrict — so the worst
> case is a reader seeing *other read MCP tools* you have configured.

### The `/apply` stage — different risk, different control

`/apply` is the write-capable stage, and it's a **separate skill on purpose**: it
reads only *already-vetted* internal notes plus your own files — never untrusted
third-party content — so its risk isn't injection, it's **over-reach** (editing
more, or more broadly, than a lead justifies). Its write boundary is enforced in two
layers:

1. **Primary (hard) — a bounded write tool.** `/apply` never writes directly; it
   dispatches the `inspire-applier` subagent, whose *only* write tool is `write_doc`
   (on the `inspire-docs` server). `write_doc` writes **only** inside your docs
   directory (`INSPIRE_DOCS_DIR_PATH`, default `./docs`) and **refuses the
   inspiration corpus** — unconditionally, in trusted code, with traversal/symlink
   escapes resolved away. The applier has no general `Write`/`Edit`/`Bash`, so it
   *structurally cannot* write out of bounds.
2. **Backstop (soft) — a guard hook.** A `PreToolUse` hook catches any stray raw
   `Write`/`Edit` in the main thread while `/apply` runs.
3. **Propose-first, per-edit approval.** It presents an edit brief and stops; you
   accept, amend, or reject each edit. It won't commit or push.

Two honest limits, by design rather than oversight: Claude Code hooks are **global
to the session** with no "active skill" signal, so the *backstop* self-gates on a
marker file and fails *open* if it isn't set — fine for a net under a hard primary.
And the default `./docs` boundary excludes root-level docs like `README.md`; widening
it is a deliberate `INSPIRE_DOCS_DIR_PATH` change, never something `/apply` does on
its own. The bounded `write_doc` is the layer you actually rely on.

## Configuration

| Env var (in the host project's `.env`) | Default | Meaning |
| --- | --- | --- |
| `INSPIRE_CONTENT_MAX_CHARS` | `200000` | Max characters returned for any source (transcript or web page; ~3.5h of speech / a very long article). Longer content is truncated and the tool's header says exactly how much was dropped. Set to `0` to disable the cap. Takes effect on MCP server restart. |
| `INSPIRE_DOCS_DIR_PATH` | `./docs` | Directory `/apply` is allowed to write to, enforced by both `write_doc` (hard) and the guard hook (soft); the inspiration corpus (`<docs>/inspiration/`) is excluded. Set it to where your docs live, or to `.` to allow the whole repo (e.g. to edit a root `README.md`). Read per-call — no restart needed. |
| `INSPIRE_WEB_ALLOWLIST` | _(unset)_ | Comma-separated host patterns; if set, the web fetcher may fetch **only** these (a pattern matches a host equal to it or a subdomain). Layered on the SSRF guard. |
| `INSPIRE_WEB_DENYLIST` | _(unset)_ | Comma-separated host patterns the web fetcher refuses. Allowlist wins if both are set; with neither set there's no domain policy. |

## How content is fetched

**Transcripts** wrap [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api)
(MIT, third-party — **not** Google's; it reads the same unofficial caption
endpoints YouTube's web player uses, no API key). Most off-the-shelf
YouTube-transcript MCP servers wrap this same library; this one wraps it behind
its own minimal, hardened surface. It rides YouTube's unofficial endpoints, so it
can be rate-limited or IP-blocked (more aggressively from datacenter IPs).

**Web pages** are fetched directly (SSRF-guarded; see _Security_) and the main
article text is extracted with [`trafilatura`](https://trafilatura.readthedocs.io/)
(Apache-2.0), which strips nav/boilerplate. Only static HTML is supported —
paywalled, login-walled, or JavaScript-rendered pages (and non-HTML like PDFs)
can't be read, by design (no headless browser).

Either way, from a normal machine it generally just works, and failures surface as
a readable `ERROR:` line rather than a crash.

## Development

The executable code is two PEP 723 MCP servers plus a few hook scripts. Run,
typecheck, and lint in an isolated overlay without installing anything globally:

```sh
# run a server (stdio); PEP 723 deps are provisioned automatically
uv run inspire/mcp/server.py          # inspire-content
uv run inspire/mcp/docs_server.py     # inspire-docs

# typecheck — each server's runtime deps must be in the overlay alongside mypy
uv run --with mypy --with mcp --with youtube-transcript-api --with trafilatura --with python-dotenv \
  mypy --strict inspire/mcp/server.py
uv run --with mypy --with mcp --with python-dotenv mypy --strict inspire/mcp/docs_server.py

# the hook scripts are stdlib-only Python (+ one POSIX sh)
uv run --with mypy mypy --strict inspire/hooks/guard_docs_write.py inspire/hooks/web_fetch_policy.py

# lint + format (uses inspire/ruff.toml: py313, line-length 100)
uvx ruff check inspire/mcp/ inspire/hooks/ && uvx ruff format --check inspire/mcp/ inspire/hooks/

# tests (offline; under tests/)
uv run --with pytest --with mcp --with python-dotenv pytest -q
```

All of these run in CI on every push and pull request
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Design rationale lives in
[`docs/decisions/`](docs/decisions/) (ADRs); a how-it-works walkthrough is in
[`docs/tech/`](docs/tech/).

## License

[MIT](LICENSE) © Javi Lorenzana
