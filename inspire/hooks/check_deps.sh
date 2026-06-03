#!/bin/sh
# SessionStart hook: warn (never block) if the inspire plugin's runtime deps are
# missing or its config is malformed, so the user learns at session start rather
# than at first /inspire failure. Stays silent when everything is fine.
#
# Written in POSIX sh (not python) on purpose: one of the things it checks for is
# python3, so it can't depend on it. See docs/decisions/0005-operational-hooks.md.

warn=""

if ! command -v uv >/dev/null 2>&1; then
  warn="${warn}\n- 'uv' is not on PATH: the inspire-content and inspire-docs MCP servers launch via 'uv run' and will fail to start. Install: https://docs.astral.sh/uv/"
fi

if ! command -v python3 >/dev/null 2>&1; then
  warn="${warn}\n- 'python3' is not on PATH: the inspire guard and web-fetch-policy hooks need it and will silently no-op (fail open) without it."
fi

if [ -n "${INSPIRE_CONTENT_MAX_CHARS}" ]; then
  case "${INSPIRE_CONTENT_MAX_CHARS}" in
    *[!0-9-]*)
      warn="${warn}\n- INSPIRE_CONTENT_MAX_CHARS='${INSPIRE_CONTENT_MAX_CHARS}' is not an integer; the server will ignore it and use the default (200000)."
      ;;
  esac
fi

if [ -n "$warn" ]; then
  printf 'inspire plugin — environment check found issue(s):%b\n' "$warn"
fi

exit 0
