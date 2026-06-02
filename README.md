# inspire — a Claude Code plugin

Drop a batch of YouTube URLs into Claude Code and get each video **evaluated
against the project you're working in**: what it's about, what you can learn from
it, and what's directly applicable here — synthesized into a small durable corpus
under `docs/inspiration/`.

It bundles three pieces that work together:

- **A skill, `/inspire`** — the orchestrator. Collects the URLs you drop, fans
  out one subagent per video, then writes the notes + a synthesized index.
- **A subagent, `inspire-watcher`** — evaluates one video. Read-only and
  **no-egress** by design (see _Security_).
- **An MCP server, `youtube-transcript`** — a thin, pure-read transcript fetcher
  the watcher calls. Self-contained single Python file with
  [PEP 723](https://peps.python.org/pep-0723/) inline dependencies.

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
https://www.youtube.com/shorts/VIDEO_THREE
```

URLs can be one-per-line or mixed into a sentence — every YouTube URL in your
message is picked up. Results land in `docs/inspiration/` (one note per video +
an index with a cross-cutting-themes synthesis).

## Security model

A video transcript is **untrusted third-party content** and a genuine
indirect-prompt-injection surface — a video's captions or title can contain text
engineered to hijack a reading agent. This plugin is built around that:

1. **Least-privilege, no-egress watcher.** `inspire-watcher` is allowlisted to
   exactly the transcript tool plus read-only repo access (`Read`/`Grep`/`Glob`).
   No Bash, no Write/Edit, no web. A successful injection has no shell to run, no
   file to mutate, and nowhere to exfiltrate to.
2. **The orchestrator writes files, not the exposed agent.** Watchers *return*
   their evaluation as text; the `/inspire` skill writes `docs/inspiration/`. The
   write capability never sits in a context that has ingested raw transcript text.
3. **Data-not-instructions framing.** The transcript is delivered inside fences
   with a standing instruction to treat it as data; injection-looking text is
   reported, never obeyed.
4. **The MCP server is a pure read.** It only resolves a video id → caption text.
   It strips terminal/control characters and caps length so a video can't pipe
   escape sequences or a wall of text into a model's context.

> **Version caveat (worth verifying on your Claude Code build):** subagent
> *restriction* of MCP tools via `tools:` frontmatter has been incompletely
> implemented in some Claude Code versions (a subagent may inherit MCP tools from
> the host). The no-Bash / no-Write / no-web guarantee in (1) holds regardless —
> those are ordinary tools the allowlist does restrict — so the worst case is the
> watcher seeing *other read MCP tools* you have configured, not gaining egress.

## Configuration

| Env var (in the host project's `.env`) | Default | Meaning |
| --- | --- | --- |
| `YOUTUBE_TRANSCRIPT_MAX_CHARS` | `200000` | Max transcript characters returned (~3.5h of speech). Longer transcripts are truncated and the tool's header says exactly how much was dropped. Set to `0` to disable the cap. Takes effect on MCP server restart. |

## How the transcript is fetched

The MCP server wraps [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api)
(MIT, third-party — **not** Google's; it reads the same unofficial caption
endpoints YouTube's web player uses, no API key). Most off-the-shelf
YouTube-transcript MCP servers wrap this same library; this one wraps it behind
its own minimal, hardened surface. It rides YouTube's unofficial endpoints, so it
can be rate-limited or IP-blocked (more aggressively from datacenter IPs); from a
normal machine it generally just works, and failures surface as a readable
`ERROR:` line rather than a crash.

## Development

The server is a single PEP 723 script. Run, typecheck, and lint it in an isolated
overlay without installing anything globally:

```sh
# run the server (stdio); PEP 723 deps are provisioned automatically
uv run inspire/mcp/server.py

# typecheck — the script's runtime deps must be in the overlay alongside mypy
uv run --with mypy --with mcp --with youtube-transcript-api --with python-dotenv \
  mypy --strict inspire/mcp/server.py

# lint + format (uses inspire/ruff.toml: py313, line-length 100)
uvx ruff check inspire/mcp/ && uvx ruff format --check inspire/mcp/
```

## License

[MIT](LICENSE) © Javi Lorenzana
