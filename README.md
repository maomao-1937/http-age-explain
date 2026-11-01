# http-age-explain

[![tests](https://github.com/maomao-1937/http-age-explain/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/http-age-explain/actions/workflows/tests.yml)

Explain the conservative HTTP response age calculation and explicit freshness
from one local JSON capture. All times come from the caller. No network,
HTTP requests, dependencies, wall clock, subprocesses, or cache writes are used.
The CLI rejects explicit URL, UNC and device path spellings before filesystem
access. Ordinary named files and drive paths are accepted. This lexical guard
does not establish whether a local mount or symlink uses remote storage.

This is a diagnostic calculator. An exit of `0` means only that numeric freshness
and the selected blockers pass this tool's threshold. It is **never permission
to store or reuse a response**, and is not a complete RFC conformance checker.

## Run from source

Use Python 3.11+; there is no installation step or configuration file.

```sh
python http_age_explain.py examples/fresh.json
python -m unittest discover -s tests -v
```

The first command exits `0`. This is the relevant excerpt of its JSON output
(the actual report also contains flags, counts, and scope information):

```json
{
  "age": {
    "date_epoch": 90,
    "age_value": 3,
    "apparent_age": 10,
    "response_delay": 2,
    "corrected_age_value": 5,
    "corrected_initial_age": 10,
    "resident_time": 5,
    "current_age": 15
  },
  "freshness": {
    "source": "max-age",
    "lifetime_seconds": 100,
    "remaining_seconds": 85,
    "numeric_freshness": "fresh"
  },
  "blockers": [],
  "selected_threshold_pass": true
}
```

## Capture format

```json
{
  "request_time": 98,
  "response_time": 100,
  "now": 105,
  "cache": "shared",
  "response_headers": [
    ["Date", "Thu, 01 Jan 1970 00:01:30 GMT"],
    ["Age", "3"],
    ["Cache-Control", "max-age=100"]
  ]
}
```

The five top-level fields are required; additional fields are rejected. Times
are nonnegative **integer** epoch seconds in one caller-controlled clock domain,
ordered `request_time <= response_time <= now`, each at most `2**63-1`.
Booleans and floating-point numbers are not times. `cache` is `shared` or
`private`. Provide response headers as ordered name/value string pairs, so
repeated fields remain visible. Header names and directive names are insensitive
to ASCII case. Outer header SP/HTAB is removed.

`Date` is required. `Expires` is optional; both use exactly IMF-fixdate with
English case-sensitive names, four-digit years 0001–9999, `GMT`, consistent
weekday, and seconds 00–59. Obsolete HTTP dates, leap seconds, and non-GMT zones
are outside this strict input profile. Pre-epoch dates are supported. Invalid
Expires is rejected even if another lifetime source takes precedence; this tool
rejects malformed captures rather than emulating a cache's recovery behavior.

`Age` is optional (default 0) and uses canonical decimal digits: `0` or a
nonzero digit followed by digits. Repeated Date, Age, or Expires is rejected.
Cache-Control can span repeated headers. A token/quoted-string scanner handles
quoted commas and quoted-pair escapes. `max-age` and `s-maxage` take decimal
seconds, including quoted digits and leading zeros. All delta-seconds spellings
are at most 19 digits and values at most `2**63-1`. Duplicate directives,
including unknown extensions, are rejected. Empty comma-separated list members
are tolerated and counted against the member limit.

Recognized flags are `no-cache`, `no-store`, `private`, `public`,
`must-revalidate`, and `proxy-revalidate`. Qualified `no-cache` or `private` is
explicitly unsupported (exit 2); arguments on the other flags are invalid.
Unrecognized directives are counted in `unmodeled_directive_count` and have
**no modeled semantics**, including registered extensions such as
`stale-while-revalidate`, `stale-if-error`, or `must-understand`. Their presence
does not prove their actual effects have been checked.

## Reading the report

The calculator compares age inferred from Date with upstream Age plus request
delay, takes the larger initial estimate, then adds local residence time. All
terms are exact integer seconds. Future Date values contribute zero apparent
age, but do not remove the delay or upstream Age contribution.

Lifetime selection is shared `s-maxage`, then `max-age`, then the nonnegative
difference between Expires and Date. A private cache ignores `s-maxage`. Without
an explicit source, lifetime, remaining time, and numeric freshness are unknown
(`null`, `null`, `"unknown"`); no heuristic is attempted. Numeric freshness is
`fresh` only when lifetime is **strictly greater** than current age; equality is
`stale`. Remaining seconds are signed and are not clamped at zero.

The selected blockers are `no-store`, `validation-required` for `no-cache`, and
`shared-private` for `private` in a shared cache. A response can be numerically
fresh while blocked. Public and revalidation flags are reported; they do not
override these blockers or grant reuse. Stale is already a threshold failure,
irrespective of whether stale reuse might be permitted elsewhere.

| Exit | Meaning |
| --- | --- |
| 0 | Numeric fresh and no selected blockers; diagnostic threshold only |
| 1 | Numeric stale/unknown or a selected blocker |
| 2 | Invalid/unsupported input, resource bound, CLI/I/O/output error |

Invalid captures return only a fixed code, for example
`{"code":"unsupported-qualified-directive","status":"invalid"}`. No partial
clean report is emitted. Input values, paths, unknown directive names, header
names/values, and URLs are not echoed. The report exposes numeric times, fixed
recognized labels, cache kind, and counts; handle numeric timing evidence as
appropriate for your data. The source file is read without modification.

## Bounds and limitations

One explicitly named regular UTF-8 JSON file, at most 65,536 bytes; 16 nesting
levels; 4,096 tree nodes; at most 128 keys per object; 128 header pairs; header
name length 128 and value length 4,096; total header characters 65,536; 256
Cache-Control members across repeated fields. Header values permit HTAB and
HTTP field bytes 32–255 except DEL; CR/LF, other controls, Unicode beyond the
byte range, duplicate JSON keys, nonfinite/fractional numbers, and Unicode
surrogates are rejected. Reads request at most the byte limit plus one.

Python integers retain accepted large finite Age/delta values and computed
sums exactly, even above `2**31` or `2**63-1`. This diagnostic does **not** map
them to infinity/sentinels. RFC 9111 discusses a sentinel for arithmetic
overflow; Python's sums here do not overflow, and values beyond the input
profile are rejected with exit 2 rather than saturated. Therefore a cache that
uses sentinel/infinity behavior may differ on very large captured values.

Not modeled: request directives, cache keys, Vary matching, method/status,
Authorization/storage eligibility, stale reuse, extension behavior, validators,
304 updates, cache races, backend behavior, eviction, multiple responses, or
clock reliability. No browser/CDN/server behavior is tested. See [RESEARCH.md](RESEARCH.md)
for sources and alternatives, and [TESTING.md](TESTING.md) for actual validation.

Examples in `checks.json` are runnable expected-exit cases: fresh (0), exact
stale boundary (1), validation required (1), shared private (1), Expires (0),
unknown private lifetime with a quoted extension (1), qualified directive (2).

## 中文说明

本工具读取一个本地 JSON，把调用方提供的请求时间、收到响应时间、当前时间
与 Date、Age 逐项展开，解释保守年龄及显式新鲜度。仅需 Python 3.11+ 标准库，
无需安装依赖、配置文件、联网或修改缓存。运行方式与上面的英文示例相同。

五个顶层字段必须齐全且不能添加其他字段。时间必须是 0 到 `2**63-1` 的整数秒，
顺序为请求 ≤ 响应 ≤ 当前；不能用布尔值或小数。Date 必填，严格采用示例中的
GMT 日期格式并验证星期。Age 缺省为 0，不接受前导零；max-age/s-maxage 可用
引号包裹数字并允许前导零。重复关键头、重复指令、畸形日期或引号均拒绝。
带字段参数的 no-cache/private 不在支持范围内，退出码为 2。

初始年龄取“响应时间减 Date 的非负值”与“Age 加请求耗时”的较大者，再加
驻留时间。共享缓存依次选择 s-maxage、max-age、Expires−Date；私有缓存忽略
s-maxage。没有显式寿命时输出 unknown，不猜测启发式寿命。寿命必须严格大于
当前年龄才是 fresh；相等就是 stale，剩余秒数可以为负数。

数值新鲜度和阻断条件分开显示：no-store、no-cache 要求验证、共享缓存遇到
private。退出 0 仅表示这几个诊断条件通过，**不代表响应可被存储或复用**。
退出 1 表示 stale、unknown 或有上述阻断；退出 2 表示输入无效、不支持或
I/O 错误。未知指令只计数，不解释含义，可能影响真实缓存行为。

输出不包含原始路径、头名称/值、扩展指令名或 URL；会包含数字时间、固定标签
及计数。输入文件不改写。上面的 Bounds 一节列出字节、层级、头部和指令上限。
接受的巨大有限 Age 保留精确整数，不转换为无穷哨兵；超出输入上限直接拒绝，
因此不能据此复现某个实际缓存的溢出策略。

工具不判断请求指令、Vary/缓存键、方法/状态码、认证与存储资格、过期复用、
扩展、验证器/304、并发竞争、后端或浏览器行为。实测环境和测试命令见
[TESTING.md](TESTING.md)，资料来源和同类选择见 [RESEARCH.md](RESEARCH.md)。

MIT License, copyright 2026 maomao-1937.
