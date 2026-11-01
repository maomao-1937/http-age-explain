# Validation record

Executed locally on 2026-11-01 with Python 3.11.15, Windows
`Windows-10-10.0.26300-SP0`. Runtime uses only the Python standard library.
Ubuntu and other Python versions were not run by the builder; cross-platform
CI and independent review belong to the release process and are not asserted
here.

## Test-first evidence

The behavioral test file was written before the product module existed. The
focused command below failed with one assertion failure,
`implementation module is missing`, before implementation:

```sh
python -m unittest discover -s tests -p test_http_age_explain.py -k conservative_age_terms -v
```

The wider preimplementation run was also retained: 20 test methods, 39
failures and one error (CLI tests had no executable/report yet). It is not
claimed as a clean assertion-only RED run; the focused core RED is the specific
missing-behavior evidence. The implementation was then written independently.
The first GREEN run passed all 20 original methods in 2.597 seconds.

Final builder command after adding file immutability and nonregular-input
checks:

```sh
python -m unittest discover -s tests -v
```

Result: **22 tests, no skips, OK**, 2.867 seconds in the final saved local run.
Timings are observations, not performance promises. RED/GREEN transcripts live
in the enclosing batch's builder evidence and are intentionally not shipped as
runtime inputs or copied into this repository.

## Meaningful coverage

- 756 small exhaustive combinations of request time, response delay, residence,
  origin Date and upstream Age, checked against an independent arithmetic
  expression. Another 120 seeded time sets each test lifetime below/equal/above
  age (360 boundary checks).
- Future Date, missing Age, pre-epoch Date, exact stale boundary, huge finite
  arithmetic, lifetime precedence, private ignoring s-maxage, Expires clamping,
  unknown lifetime, and blockers independent of numeric freshness.
- Repeated case-insensitive headers, quoted numeric arguments, a comma and
  escaped quote inside an extension, flags, duplicate directives, qualified
  directives, malformed dates/weekday, controls and field/row/directive bounds.
- Strict JSON duplicate/nonfinite/fractional/surrogate rejection, nesting and
  byte caps, unreadable/missing/nonregular inputs, neutral CLI errors, metadata
  privacy, and unchanged caller object/file bytes.
- Real OS stdout pipes whose read ends are closed **before** the child runs,
  for `-h`, `--help`, and a successful report. These return 2 without traceback,
  deferred-shutdown errors, or exit 120. Normal help also flushes and exits 0.

Each CLI subprocess uses the script basename and project root as `cwd`, with
timeouts and owned pipe resources. The nonregular-input test uses a directory
on Windows; on systems with `os.mkfifo`, it additionally exercises a FIFO with
no writer. The FIFO branch was not executed on the builder's Windows host.

## Runnable examples

Every entry in root `checks.json` was invoked with Python as a subprocess and
its exit code compared with the declared value. All **7/7** matched, stderr was
empty, and stdout decoded as JSON:

| Capture | Exit | Observed result |
| --- | --- | --- |
| `examples/fresh.json` | 0 | Age 15; max-age 100; remaining 85 |
| `examples/stale.json` | 1 | Age equals lifetime 15; stale |
| `examples/validation-required.json` | 1 | Numerically fresh; validation blocker |
| `examples/shared-private.json` | 1 | s-maxage 30; shared-private blocker |
| `examples/expires.json` | 0 | Lifetime 30 from Expires; remaining 15 |
| `examples/unknown.json` | 1 | Private ignores s-maxage; unknown; extension count 1 |
| `examples/unsupported-qualified.json` | 2 | Fixed unsupported-qualified-directive code |

These checks demonstrate this declared calculator profile. They do not test
real cache storage, network clocks, servers, browsers, CDN behavior, RFC-wide
conformance, stale reuse, extensions, authentication, 304 flows or races.

## Pre-publication local path regression

Independent specification review found that explicit remote path spellings
reached filesystem metadata access before rejection. Two regression methods
were added. The first produced nine actual failing assertions on URL/UNC/device
spellings under mocked filesystem I/O; no network was contacted. A lexical
guard now rejects those inputs before stat/open. The second confirms that
ordinary named paths, pathlib paths and drive spellings still reach the file
checks. The complete suite then passed **24 tests, no skips**. RED/GREEN logs
are `local-path-red.txt` and `local-path-green.txt` in the batch evidence.
The guard does not prove the backing storage of mounts or symlinks is local.

## 中文验证说明

本地实测 Python 3.11.15、Windows build 26300。先写测试，在模块缺失时观察到
核心断言失败，再实现并获得 GREEN；原始宽测试还包含一个缺失 CLI 输出引发的
错误，已如实保存，不冒充全部为纯断言失败。最终 22 项测试全部通过，无跳过；
7 个示例退出码均符合 checks.json，输出为 JSON，stderr 为空。

已测试真实关闭读取端的 stdout 管道（含 -h/--help）以及输入文件不变。
Windows 使用目录验证非普通文件拒绝，FIFO 分支未在本机执行。尚未声称 Linux
已通过，也没有把离线计算测试当成真实缓存系统或并发行为的验证。
