# Research and scope decisions

Sources checked on 2026-11-01. Facts below are separated from the product's
design choices; no third-party issue was independently reproduced.

## Primary sources

- [RFC 9111, age calculation](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.3)
  describes upstream Age, transit delay, apparent age and residence. This tool
  chooses the conservative larger initial estimate and implements the published
  mathematics independently, with original code and explanations. No RFC code
  component or prose is copied into this project.
- [RFC 9111, freshness](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2)
  supplies explicit lifetime precedence and the strict freshness comparison.
  [Delta-seconds](https://www.rfc-editor.org/rfc/rfc9111.html#section-1.2.2)
  discusses overflow handling; this bounded calculator retains finite integers
  and does not use an infinity sentinel.
- [CacheControl](https://github.com/psf/cachecontrol) is an existing Python HTTP
  caching library. It is a practical alternative when an application needs an
  actual caching transport, rather than explanations of captured inputs.
- [CacheControl issue #424](https://github.com/psf/cachecontrol/issues/424),
  “Race condition in send()”, was open in the saved source observation. This is
  a reporter's concurrency report, not evidence of a reproduced defect and not
  a problem this arithmetic tool fixes.

## Inference and differentiation

An offline explanation can help a developer distinguish clock-derived age,
upstream Age, transit delay, residence, and explicit lifetime selection. This
is a usefulness hypothesis, not measured demand, usage, or adoption evidence.
The small output is designed for reviewing one capture and avoiding accidental
publication of header metadata. Captured numeric timestamps are still exposed.

Use browser developer tools, a CDN's diagnostics, or an actual caching client
to investigate observed runtime behavior. Those tools see request context,
response status and cache state that this JSON profile deliberately lacks.
Use this project when deterministic caller-controlled arithmetic is the
question. It does not replace cache integration tests or solve concurrency.

## Deliberate profile restrictions

Strict IMF-fixdate, duplicate rejection, required Date, invalid-Expires
rejection, finite input bounds, and unsupported qualified directives are
diagnostic input rules. They do not emulate every recovery or normalization
rule a conforming cache might apply. Unknown extensions are counted and ignored
semantically; registered extensions are not automatically understood.

Numeric freshness and the three selected blockers cannot establish storage or
reuse eligibility. No request policy, method/status, authorization, Vary/key
matching, stale reuse, extension effects, validation/304 handling, clock
reliability, backend or cache concurrency is modeled. This project makes no
full RFC conformance, cache correctness, vulnerability, or security claim.

## 中文摘要

依据 RFC 9111 的年龄、新鲜度与溢出讨论，独立编写计算实现；资料归属通过链接
标明，没有复制 RFC 的代码或原文。现有 CacheControl 适合实际 HTTP 缓存集成，
本工具适合离线核对一个抓取样本的数字。#424 是尚未独立复现的并发问题报告，
本工具不处理该问题。实际需求与采用情况仍需用户反馈验证。
