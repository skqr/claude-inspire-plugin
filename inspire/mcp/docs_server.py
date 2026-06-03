# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "mcp>=1.2,<2",
#     "python-dotenv>=1.0",
# ]
# ///
"""inspire-docs — a path-bounded MCP write tool for the `/apply` skill.

One tool, ``write_doc``, that writes a file *only* within the project's docs
directory (``INSPIRE_DOCS_DIR_PATH``, default ``./docs``) and *never* inside the
inspiration corpus (``<docs>/inspiration/``, which is `/inspire`'s output and
`/apply`'s read-only source of truth). Any target outside that boundary is
refused here, in this trusted server, unconditionally.

This is the **hard** half of `/apply`'s write boundary: the `inspire-applier`
subagent is allowlisted to exactly this tool plus read-only repo access, so it
has no general Write/Edit/Bash — its only way to change a file is through here,
and here enforces the bound. (The PreToolUse guard hook is the **soft**,
defense-in-depth half, catching stray raw Writes in the main thread.) See
docs/decisions/0004-apply-write-boundary.md.

Launched via an isolated ``uv run`` with cwd set to the host project (see
inspire/.mcp.json), so the project root is the current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("inspire-docs")

# The inspiration corpus is the `inspiration/` subdirectory of the docs root.
CORPUS_SUBDIR = "inspiration"


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _docs_root(project_dir: Path) -> Path:
    raw = os.environ.get("INSPIRE_DOCS_DIR_PATH", "").strip() or "./docs"
    root = Path(raw)
    if not root.is_absolute():
        root = project_dir / root
    return root.resolve()


def _refusal_reason(resolved: Path, docs_root: Path) -> str | None:
    """None if `resolved` is writable by /apply, else a human-readable refusal."""
    corpus = (docs_root / CORPUS_SUBDIR).resolve()
    if resolved == corpus or corpus in resolved.parents:
        return (
            f"{resolved} is inside the inspiration corpus ({corpus}) — that is /inspire's "
            "output and /apply's read-only source, so it is never an edit target."
        )
    if resolved != docs_root and docs_root not in resolved.parents:
        return (
            f"{resolved} is outside the docs directory ({docs_root}). /apply may only write "
            "project docs; widen INSPIRE_DOCS_DIR_PATH if your docs live elsewhere."
        )
    return None


@mcp.tool()
def write_doc(path: str, content: str) -> str:
    """Write a documentation file within the project's docs directory.

    Use this for every file change in the /apply stage. To edit an existing doc,
    Read it, compute the full new text, and pass it here as `content` — this writes
    the whole file. Parent directories are created as needed.

    Args:
        path: Target file, relative to the project root (e.g. "docs/guide.md") or
            absolute. Must resolve inside INSPIRE_DOCS_DIR_PATH (default ./docs) and
            outside the inspiration corpus (<docs>/inspiration/).
        content: The full new contents of the file.

    Returns a one-line confirmation, or a "REFUSED:" line if the path is out of
    bounds (do not try to work around that — the boundary is intentional).
    """
    project_dir = _project_dir()
    docs_root = _docs_root(project_dir)
    target = Path(path)
    resolved = (target if target.is_absolute() else project_dir / target).resolve()

    refusal = _refusal_reason(resolved, docs_root)
    if refusal is not None:
        return f"REFUSED: {refusal}"

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: could not write {resolved}: {type(exc).__name__}: {exc}"
    return f"OK: wrote {len(content)} chars to {resolved}"


def main() -> None:
    """Entry point — runs over stdio, the transport Claude Code speaks to plugin MCP servers."""
    mcp.run()


if __name__ == "__main__":
    main()
