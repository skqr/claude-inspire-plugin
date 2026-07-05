# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "mcp>=1.2,<2",
#     "python-dotenv>=1.0",
# ]
# ///
"""inspire-docs — the plugin's path-bounded MCP write tools.

Two tools with *complementary* bounds, both enforced here, in trusted server
code, unconditionally:

- ``write_doc`` (the `/apply` stage) writes a file *only* within the project's
  docs directory (``INSPIRE_DOCS_DIR_PATH``, default ``./docs``) and *never*
  inside the inspiration corpus (``<docs>/inspiration/``, which is `/inspire`'s
  output and `/apply`'s read-only source of truth).
- ``write_note`` (the `/inspire` stage) writes *only* inside that corpus —
  the exact complement, so neither stage's writer can reach the other's files.

Each tool is the **hard** half of its stage's write boundary: a dedicated
subagent (`inspire-applier` for ``write_doc``, `inspire-scribe` for
``write_note``) is allowlisted to exactly its one tool plus read-only repo
access, so it has no general Write/Edit/Bash — its only way to change a file is
through here, and here enforces the bound. (The PreToolUse guard hook is the
**soft**, defense-in-depth half, catching stray raw Writes in the main thread.)
See docs/decisions/0004-apply-write-boundary.md and
docs/decisions/0007-inspire-write-boundary.md.

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


def _note_refusal_reason(resolved: Path, docs_root: Path) -> str | None:
    """None if `resolved` is writable by /inspire (inside the corpus), else a refusal."""
    corpus = (docs_root / CORPUS_SUBDIR).resolve()
    if resolved == corpus or corpus in resolved.parents:
        return None
    return (
        f"{resolved} is outside the inspiration corpus ({corpus}). /inspire writes only "
        "corpus notes and the corpus README; the project's own docs are /apply's territory."
    )


def _write_file(resolved: Path, content: str) -> str:
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: could not write {resolved}: {type(exc).__name__}: {exc}"
    return f"OK: wrote {len(content)} chars to {resolved}"


def _resolve_target(path: str, project_dir: Path) -> Path:
    target = Path(path)
    return (target if target.is_absolute() else project_dir / target).resolve()


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
    resolved = _resolve_target(path, project_dir)

    refusal = _refusal_reason(resolved, _docs_root(project_dir))
    if refusal is not None:
        return f"REFUSED: {refusal}"
    return _write_file(resolved, content)


@mcp.tool()
def write_note(path: str, content: str) -> str:
    """Write an inspiration-corpus file (<docs>/inspiration/).

    Use this for every file the /inspire stage produces — the per-source notes and
    the corpus README.md. This writes the whole file; to update an existing note,
    Read it, compute the full new text, and pass it here as `content`. Parent
    directories are created as needed.

    Args:
        path: Target file, relative to the project root (e.g.
            "docs/inspiration/some-source.md") or absolute. Must resolve inside the
            inspiration corpus — the inspiration/ subdirectory of
            INSPIRE_DOCS_DIR_PATH (default ./docs).
        content: The full new contents of the file.

    Returns a one-line confirmation, or a "REFUSED:" line if the path is out of
    bounds (do not try to work around that — the boundary is intentional).
    """
    project_dir = _project_dir()
    resolved = _resolve_target(path, project_dir)

    refusal = _note_refusal_reason(resolved, _docs_root(project_dir))
    if refusal is not None:
        return f"REFUSED: {refusal}"
    return _write_file(resolved, content)


def main() -> None:
    """Entry point — runs over stdio, the transport Claude Code speaks to plugin MCP servers."""
    mcp.run()


if __name__ == "__main__":
    main()
