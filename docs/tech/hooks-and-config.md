# Hooks & configuration

## Environment variables

All are read from the **host project's** environment (or a `.env` whose values reach
the session). None are required; each has a safe default.

| Variable | Default | Read by | Effect |
| --- | --- | --- | --- |
| `INSPIRE_CONTENT_MAX_CHARS` | `200000` | `inspire-content` server | Caps characters returned by **both** content tools. `0`/negative disables the cap. Takes effect on MCP server restart. |
| `INSPIRE_DOCS_DIR_PATH` | `./docs` | `write_doc`, `write_note`, guard hook | Docs root both write bounds derive from: `/apply` may write inside it (minus `<docs>/inspiration/`); `/inspire` may write only `<docs>/inspiration/`. Resolved relative to the project root. Read per-call (no restart). Set to `.` to allow `/apply` the whole repo (e.g. to edit a root `README.md`). |
| `INSPIRE_WEB_ALLOWLIST` | _(unset)_ | web-fetch policy hook | Comma-separated host patterns; if set, **only** these may be fetched. |
| `INSPIRE_WEB_DENYLIST` | _(unset)_ | web-fetch policy hook | Comma-separated host patterns to block. Allowlist wins if both are set. |

Host-pattern matching (allow/deny lists): a pattern matches a host that **equals** it
or is a **subdomain** of it — `example.com` matches `example.com` and
`docs.example.com`, not `notexample.com`.

## Hooks

Declared in `inspire/hooks/hooks.json`. Commands use `${CLAUDE_PLUGIN_ROOT}` so they
resolve regardless of where the plugin is installed.

### 1. `guard_docs_write.py` — `PreToolUse` on `Write|Edit|MultiEdit|NotebookEdit`

The **backstop** for both stages' write boundaries (each hard primary is a
path-bounded MCP tool behind a restricted subagent; see [security.md](security.md)).
Which scope it enforces depends on which marker file is fresh at the project root
(the skills create them at the start of a run and remove them at the end; if both
are somehow present, the freshest wins):

- `.inspire-apply.lock` (`/apply` active): denies a write whose resolved target is
  outside `INSPIRE_DOCS_DIR_PATH` **or** inside the corpus `<docs>/inspiration/`.
- `.inspire-intake.lock` (`/inspire` active): denies any write **outside** the
  corpus — the exact complement.

Paths are fully resolved first, so `../` traversal and symlink escapes can't slip
past. With no marker (normal development, or any other skill) the hook is inert and
exits 0 — it never restricts the host project's ordinary editing. A marker older than
one hour is treated as stale and ignored (so an aborted run can't lock a repo). Needs
`python3` on `PATH`; absent that, it fails open.

### 2. `web_fetch_policy.py` — `PreToolUse` on `get_webpage_content`

A **name-based domain policy** layered on the fetcher's IP-level SSRF guard. Reads
`INSPIRE_WEB_ALLOWLIST` / `INSPIRE_WEB_DENYLIST` (above); with neither set it's a
no-op. Allowlist mode denies anything not matched (including an unparseable host);
denylist mode denies only matches. Fails open on a missing `python3`.

The `hooks.json` matcher is a regex —
`mcp__(plugin_inspire_|inspire__)?inspire-content__get_webpage_content` — because
Claude Code registers a plugin's MCP tools under a **namespaced** name
(`mcp__plugin_inspire_inspire-content__…` in current versions, `mcp__inspire__…`
in older ones), not the bare `mcp__inspire-content__…`. Matching only the bare
name would leave the policy silently inert.

### 3. `check_deps.sh` — `SessionStart`

Warns (never blocks) at session start if `uv` or `python3` is missing from `PATH`, or
if `INSPIRE_CONTENT_MAX_CHARS` isn't an integer. Silent when all is well. Written in
POSIX `sh` on purpose — it can't depend on the `python3` it checks for.

## Verifying a hook by hand

The two `PreToolUse` hooks read a JSON payload on stdin and either exit 0 (allow) or
print a `permissionDecision: "deny"` JSON. To exercise the guard:

```sh
# Outside the docs dir, with /apply "active" → expect a deny JSON
mkdir -p /tmp/proj && touch /tmp/proj/.inspire-apply.lock
echo '{"tool_input":{"file_path":"/tmp/proj/src/x.py"}}' \
  | CLAUDE_PROJECT_DIR=/tmp/proj python3 inspire/hooks/guard_docs_write.py

# No marker → silent (exit 0, allowed)
rm /tmp/proj/.inspire-apply.lock
echo '{"tool_input":{"file_path":"/tmp/proj/src/x.py"}}' \
  | CLAUDE_PROJECT_DIR=/tmp/proj python3 inspire/hooks/guard_docs_write.py

# Intake mode: a plain docs write, with /inspire "active" → expect a deny JSON
touch /tmp/proj/.inspire-intake.lock
echo '{"tool_input":{"file_path":"/tmp/proj/docs/guide.md"}}' \
  | CLAUDE_PROJECT_DIR=/tmp/proj python3 inspire/hooks/guard_docs_write.py
rm /tmp/proj/.inspire-intake.lock
```

The domain policy similarly:

```sh
echo '{"tool_input":{"url":"https://blocked.test/x"}}' \
  | INSPIRE_WEB_DENYLIST=blocked.test python3 inspire/hooks/web_fetch_policy.py
```

## Lint & typecheck

The hook scripts are stdlib-only Python (and one `sh` script), so they check with no
dependency overlay:

```sh
uvx ruff check inspire/hooks/
uv run --with mypy mypy --strict inspire/hooks/guard_docs_write.py inspire/hooks/web_fetch_policy.py
sh -n inspire/hooks/check_deps.sh
```
