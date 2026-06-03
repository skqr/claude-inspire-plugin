#!/usr/bin/env python3
"""PreToolUse write-guard for the inspire `/apply` skill.

Confines file-writing tools (Write/Edit/MultiEdit/NotebookEdit) to the docs
directory — ``INSPIRE_DOCS_DIR_PATH``, default ``./docs`` — but *only while
`/apply` is active*. "Active" is signalled by a marker file the apply skill
creates at the start of its run and removes at the end. When the marker is
absent (ordinary development, or any other skill), this guard does nothing and
exits 0, so it never restricts the host project's normal editing.

Why a marker instead of detecting the skill directly: Claude Code's PreToolUse
hooks are global to the session and carry no "active skill" field, so a
skill-scoped guard has to gate itself. The trade-off: activation depends on the
skill setting the marker (the guard fails *open* if it doesn't), so this is a
guardrail against `/apply` over-reaching its own stated scope — not a defence
against an adversary, which `/apply` doesn't face (it reads only vetted internal
notes, never untrusted third-party content).

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

MARKER_NAME = ".inspire-apply.lock"
# A marker older than this is treated as stale (an apply run that aborted without
# cleaning up) and ignored, so a forgotten lock can never permanently constrain a
# repo's writes. apply runs are interactive and short; an hour is ample headroom.
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


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()  # never let a malformed payload wedge the user's writes

    project_dir = _project_dir(payload)

    # Activation gate: enforce only while the apply skill's marker is present and fresh.
    try:
        marker_mtime = (project_dir / MARKER_NAME).stat().st_mtime
    except OSError:
        _allow()  # no marker -> not an apply run -> don't interfere
    if time.time() - marker_mtime > MARKER_TTL_SECONDS:
        _allow()  # stale marker from an aborted run

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

    # The inspiration corpus is /inspire's output and /apply's read-only source —
    # never an /apply edit target, even though it sits inside the docs directory.
    corpus_root = (docs_root / "inspiration").resolve()
    if target == corpus_root or corpus_root in target.parents:
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
