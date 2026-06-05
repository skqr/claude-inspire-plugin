#!/usr/bin/env python3
"""PreToolUse domain policy for inspire's web-fetch tool.

Layers a *name-based* allow/deny policy on top of the MCP tool's IP-based SSRF
guard (the SSRF guard stops fetches of internal addresses; this stops fetches of
domains your policy disallows). Configure via the host environment — or a `.env`
whose values are exported into the session:

  INSPIRE_WEB_ALLOWLIST   comma-separated host patterns; if set, ONLY these match
  INSPIRE_WEB_DENYLIST    comma-separated host patterns; these are blocked

The allowlist wins if both are set. A pattern matches a host that equals it or is
a subdomain of it (suffix on a dot boundary): "example.com" matches "example.com"
and "docs.example.com", but not "notexample.com". With neither var set, all
fetches are allowed (no policy). See docs/decisions/0005-operational-hooks.md.

Wired (hooks/hooks.json) to the get_webpage_content tool. The matcher there is a
regex covering every name form Claude Code registers the plugin tool under
(`mcp__plugin_inspire_inspire-content__…`, `mcp__inspire__…`, and the bare name) —
matching only the bare name would let the policy silently never fire.
Reads the PreToolUse payload on stdin; exits 0 to allow, or prints a deny decision.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from typing import NoReturn


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


def _patterns(env_name: str) -> list[str]:
    raw = os.environ.get(env_name, "")
    return [p.strip().lower().lstrip(".") for p in raw.split(",") if p.strip()]


def _host_matches(host: str, patterns: list[str]) -> bool:
    host = host.lower()
    return any(host == p or host.endswith("." + p) for p in patterns)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()  # never let a malformed payload wedge a fetch

    allowlist = _patterns("INSPIRE_WEB_ALLOWLIST")
    denylist = _patterns("INSPIRE_WEB_DENYLIST")
    if not allowlist and not denylist:
        _allow()  # no policy configured

    url = (payload.get("tool_input") or {}).get("url") or ""
    host = urllib.parse.urlparse(url).hostname or ""

    if allowlist:
        if host and _host_matches(host, allowlist):
            _allow()
        _deny(
            f"web-fetch policy: {host or url!r} is not in INSPIRE_WEB_ALLOWLIST "
            f"({', '.join(allowlist)}) — fetch refused."
        )

    if host and _host_matches(host, denylist):
        _deny(
            f"web-fetch policy: {host} is in INSPIRE_WEB_DENYLIST "
            f"({', '.join(denylist)}) — fetch refused."
        )
    _allow()


if __name__ == "__main__":
    main()
