#!/usr/bin/env python3
"""PreToolUse write-guard for the inspire `/apply` and `/inspire` skills.

Confines file-writing tools (Write/Edit/MultiEdit/NotebookEdit) to the active
skill's write scope — but *only while one of the skills is active*. "Active" is
signalled by a marker file each skill creates at the start of its run and
removes at the end; the scope depends on which marker is present:

- ``.inspire-apply.lock`` (`/apply`): writes allowed only inside the docs
  directory (``INSPIRE_DOCS_DIR_PATH``, default ``./docs``) and *never* inside
  the inspiration corpus (``<docs>/inspiration/``).
- ``.inspire-intake.lock`` (`/inspire`): writes allowed *only* inside the
  inspiration corpus — the exact complement.

If both markers are somehow present (an aborted run left one behind), the
freshest wins. When neither is present (ordinary development, or any other
skill), this guard does nothing and exits 0, so it never restricts the host
project's normal editing.

Why a marker instead of detecting the skill directly: Claude Code's PreToolUse
hooks are global to the session and carry no "active skill" field, so a
skill-scoped guard has to gate itself. The trade-off: activation depends on the
skill setting the marker (the guard fails *open* if it doesn't), so this is a
guardrail against a skill over-reaching its own stated scope — the *soft* net
under each stage's hard primary (the path-bounded `write_doc`/`write_note`
tools), not a defence that can stand alone.

Wired via hooks/hooks.json. Reads the hook payload on stdin; exits 0 to allow,
or prints a deny decision (also exit 0 — the decision is the JSON, not the code).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

APPLY_MARKER = ".inspire-apply.lock"
INTAKE_MARKER = ".inspire-intake.lock"
# A marker older than this is treated as stale (a run that aborted without
# cleaning up) and ignored, so a forgotten lock can never permanently constrain a
# repo's writes. Both skills' runs are interactive and short; an hour is ample.
MARKER_TTL_SECONDS = 60 * 60


def _allow() -> NoReturn:
    sys.exit(0)


def _deny(reason: str) -> NoReturn:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def _project_dir(payload: dict[str, Any]) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(root)


def _fresh_marker_mtime(project_dir: Path, name: str) -> float | None:
    """The marker's mtime if it exists and is fresh, else None."""
    try:
        mtime = (project_dir / name).stat().st_mtime
    except OSError:
        return None
    if time.time() - mtime > MARKER_TTL_SECONDS:
        return None  # stale marker from an aborted run
    return mtime


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()  # never let a malformed payload wedge the user's writes

    project_dir = _project_dir(payload)

    # Activation gate: enforce only while a skill's marker is present and fresh.
    # If both are present (an aborted run left one behind), the freshest wins.
    apply_mtime = _fresh_marker_mtime(project_dir, APPLY_MARKER)
    intake_mtime = _fresh_marker_mtime(project_dir, INTAKE_MARKER)
    if apply_mtime is None and intake_mtime is None:
        _allow()  # no marker -> neither skill is running -> don't interfere
    intake_active = (intake_mtime or 0.0) > (apply_mtime or 0.0)

    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        _allow()  # nothing path-shaped to judge

    # Resolve the allowed docs root (default ./docs), relative to the project.
    docs_env = os.environ.get("INSPIRE_DOCS_DIR_PATH", "").strip() or "./docs"
    docs_root = Path(docs_env)
    if not docs_root.is_absolute():
        docs_root = project_dir / docs_root
    docs_root = docs_root.resolve()

    target = Path(file_path)
    if not target.is_absolute():
        target = project_dir / target
    target = target.resolve()  # follows symlinks + normalises '..', so neither can escape

    corpus_root = (docs_root / "inspiration").resolve()
    in_corpus = target == corpus_root or corpus_root in target.parents

    if intake_active:
        # /inspire's scope is the corpus and nothing else.
        if in_corpus:
            _allow()
        _deny(
            f"/inspire is confined to the inspiration corpus ({corpus_root}); refusing to "
            f"write {target}. Notes and the corpus README belong under that directory — "
            "and should be written via the inspire-scribe subagent's write_note tool, not "
            "a raw Write. The project's own docs are /apply's territory."
        )

    # /apply's scope: inside the docs directory, but never the corpus — that is
    # /inspire's output and /apply's read-only source.
    if in_corpus:
        _deny(
            f"/apply must not modify the inspiration corpus ({corpus_root}) — it is /inspire's "
            "output and /apply's read-only source. Promote leads into the project's own docs "
            "elsewhere under the docs directory instead."
        )

    if target == docs_root or docs_root in target.parents:
        _allow()

    _deny(
        f"/apply is confined to the docs directory ({docs_root}); refusing to write {target}. "
        "If this content belongs in the project's docs, target a file under that directory. "
        "If your docs live elsewhere, widen the boundary with INSPIRE_DOCS_DIR_PATH. "
        "Otherwise this edit is outside /apply's scope — leave it as a flagged follow-up "
        "rather than writing it here."
    )


if __name__ == "__main__":
    main()
