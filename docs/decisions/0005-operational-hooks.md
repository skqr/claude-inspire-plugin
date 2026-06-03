# 0005 — Add a web-fetch domain policy hook and a session dependency-check hook

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

Two operational gaps remained once the core security model was in place:

1. The web fetcher's SSRF guard ([0003](0003-web-page-support-and-ssrf.md)) blocks by
   *IP* (internal ranges). It has no notion of *which public domains* an operator
   wants to permit — useful for shared or enterprise setups that want "only fetch
   from these sites" or "never fetch from those."
2. The plugin's runtime prerequisites (`uv` for the MCP servers; `python3` for the
   guard/policy hooks) fail late and cryptically — a user discovers `uv` is missing
   only when `/inspire` first errors.

## Decision

Ship two more hooks, both configured by environment variables, both fail-safe:

- **`web_fetch_policy.py` (`PreToolUse` on `get_webpage_content`)** — a *name-based*
  allow/deny policy layered on the IP-based SSRF guard. `INSPIRE_WEB_ALLOWLIST`
  (if set, only these match) and `INSPIRE_WEB_DENYLIST` (these are blocked);
  allowlist wins if both are set; a pattern matches a host that equals it or is a
  subdomain. With neither set, all fetches are allowed (no policy → no behavior
  change).
- **`check_deps.sh` (`SessionStart`)** — verifies `uv` and `python3` are on `PATH`
  and that `INSPIRE_CONTENT_MAX_CHARS` parses as an integer; prints a concise
  warning when something's off, silent otherwise. Written in **POSIX `sh`**, not
  Python, precisely because one thing it checks for is `python3`.

## Consequences

- Operators get a real policy lever over web egress without touching code; the
  default (no env vars) changes nothing.
- Misconfiguration surfaces at session start instead of at first failure.
- Both hooks **fail open**: a missing `python3` makes the policy hook a no-op
  (the dep check will have warned), and the dep check never blocks a session. This
  matches the plugin's stance that *operational* guards warn and degrade, while
  *security* boundaries that must hold are enforced in tool code
  ([0004](0004-apply-write-boundary.md)), not in fail-open hooks.
- The web policy is defense-in-depth, **not** a substitute for the SSRF guard: it
  governs *which public domains*, while the SSRF guard governs *internal-address
  reachability*. Both run.
