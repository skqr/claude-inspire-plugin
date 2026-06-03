"""Offline tests for the inspire plugin's enforcement logic.

Covers the pure, security-relevant pieces — no network, no real YouTube/web
fetches: video-id parsing, the SSRF guard, the path-bounded `write_doc` tool, and
the two PreToolUse hooks (run as subprocesses, exactly as Claude Code invokes them).

Run with:
    uv run --with pytest --with mcp --with python-dotenv pytest -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "inspire" / "hooks"
POLICY_ENV = ("INSPIRE_DOCS_DIR_PATH", "INSPIRE_WEB_ALLOWLIST", "INSPIRE_WEB_DENYLIST")


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


content = _load("inspire_content", "inspire/mcp/server.py")
docs = _load("inspire_docs", "inspire/mcp/docs_server.py")


# --------------------------------------------------------------------------- #
# extract_video_id
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
    ],
)
def test_extract_video_id(url: str) -> None:
    assert content.extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        content.extract_video_id("https://example.com/abc")


# --------------------------------------------------------------------------- #
# SSRF guard
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.1"])
def test_host_is_public_blocks_internal(ip: str) -> None:
    assert content._host_is_public(ip) is False


def test_host_is_public_allows_public_ip() -> None:
    assert content._host_is_public("8.8.8.8") is True


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "http:///nohost"])
def test_assert_fetchable_rejects_scheme_or_host(url: str) -> None:
    with pytest.raises(content.WebFetchError):
        content._assert_fetchable(url)


def test_assert_fetchable_rejects_private() -> None:
    with pytest.raises(content.WebFetchError):
        content._assert_fetchable("http://127.0.0.1/x")


def test_assert_fetchable_allows_public_ip() -> None:
    content._assert_fetchable("https://8.8.8.8/")  # must not raise


# --------------------------------------------------------------------------- #
# write_doc (inspire-docs server)
# --------------------------------------------------------------------------- #
@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "docs" / "inspiration").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    for var in POLICY_ENV:
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_write_doc_inside_docs(project: Path) -> None:
    assert docs.write_doc("docs/guide.md", "# Guide\n").startswith("OK:")
    assert (project / "docs" / "guide.md").read_text() == "# Guide\n"


def test_write_doc_refuses_corpus(project: Path) -> None:
    assert docs.write_doc("docs/inspiration/note.md", "x").startswith("REFUSED:")
    assert not (project / "docs" / "inspiration" / "note.md").exists()


def test_write_doc_refuses_outside(project: Path) -> None:
    assert docs.write_doc("src/app.py", "x").startswith("REFUSED:")
    assert not (project / "src").exists()


def test_write_doc_refuses_traversal(project: Path) -> None:
    assert docs.write_doc("docs/../../etc/passwd", "x").startswith("REFUSED:")


def test_write_doc_custom_docs_dir(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSPIRE_DOCS_DIR_PATH", ".")
    assert docs.write_doc("README.md", "# R\n").startswith("OK:")
    assert (project / "README.md").read_text() == "# R\n"


# --------------------------------------------------------------------------- #
# hooks (subprocess, exactly as Claude Code runs them)
# --------------------------------------------------------------------------- #
def _run_hook(script: str, payload: dict, env: dict) -> bool:
    """Return True if the hook DENIED the call (printed a deny decision)."""
    full = {k: v for k, v in os.environ.items() if k not in POLICY_ENV}
    full.update(env)
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full,
    )
    if not proc.stdout.strip():
        return False
    return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def _write_payload(path: Path) -> dict:
    return {"tool_input": {"file_path": str(path)}}


def test_guard_inert_without_marker(tmp_path: Path) -> None:
    assert not _run_hook(
        "guard_docs_write.py", _write_payload(tmp_path / "src/x.py"),
        {"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


def test_guard_blocks_outside_with_marker(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / ".inspire-apply.lock").touch()
    assert _run_hook(
        "guard_docs_write.py", _write_payload(tmp_path / "src/x.py"),
        {"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


def test_guard_blocks_corpus_with_marker(tmp_path: Path) -> None:
    (tmp_path / "docs/inspiration").mkdir(parents=True)
    (tmp_path / ".inspire-apply.lock").touch()
    assert _run_hook(
        "guard_docs_write.py", _write_payload(tmp_path / "docs/inspiration/n.md"),
        {"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


def test_guard_allows_docs_with_marker(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / ".inspire-apply.lock").touch()
    assert not _run_hook(
        "guard_docs_write.py", _write_payload(tmp_path / "docs/g.md"),
        {"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


@pytest.mark.parametrize(
    "env,url,denied",
    [
        ({}, "https://x.com/y", False),
        ({"INSPIRE_WEB_ALLOWLIST": "example.com"}, "https://docs.example.com/y", False),
        ({"INSPIRE_WEB_ALLOWLIST": "example.com"}, "https://evil.test/y", True),
        ({"INSPIRE_WEB_DENYLIST": "evil.test"}, "https://evil.test/y", True),
        ({"INSPIRE_WEB_DENYLIST": "evil.test"}, "https://example.com/y", False),
    ],
)
def test_web_fetch_policy(env: dict, url: str, denied: bool) -> None:
    assert _run_hook("web_fetch_policy.py", {"tool_input": {"url": url}}, env) is denied
