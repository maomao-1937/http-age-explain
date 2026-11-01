#!/usr/bin/env python3
"""Offline age arithmetic for a bounded capture; never a cache reuse decision."""
import argparse
import datetime
import json
import os
import re
import stat
import sys

MAX_BYTES = 65536
MAX_HEADERS = 128
MAX_HEADER_NAME = 128
MAX_HEADER_VALUE = 4096
MAX_DIRECTIVES = 256
MAX_DEPTH = 16
MAX_NODES = 4096
MAX_INTEGER = 2**63 - 1
TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
DECIMAL = re.compile(r"[0-9]+")
CANONICAL = re.compile(r"(?:0|[1-9][0-9]*)")
HTTP_DATE = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun), ([0-9]{2}) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"([0-9]{4}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) GMT")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
WEEKDAYS = "Mon Tue Wed Thu Fri Sat Sun".split()
UTC = datetime.timezone.utc
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=UTC)
FLAGS = ("no-cache", "no-store", "private", "public", "must-revalidate", "proxy-revalidate")
REQUIRED = {"request_time", "response_time", "now", "cache", "response_headers"}


class InputError(ValueError):
    """Carries fixed codes only; exception text never contains captured data."""


def fail(code="invalid-input"):
    raise InputError(code)


def _bounded_tree(value):
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            fail("input-limit")
        if isinstance(item, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                fail("invalid-json")
        elif isinstance(item, dict):
            if len(item) > MAX_HEADERS:
                fail("input-limit")
            pending.extend((part, depth+1) for pair in item.items() for part in pair)
        elif isinstance(item, list):
            if len(item) > MAX_NODES:
                fail("input-limit")
            pending.extend((part, depth+1) for part in item)
        elif item is not None and type(item) not in (int, bool):
            fail("invalid-json")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate-json-key")
        result[key] = value
    return result


def _integer(text):
    if len(text.lstrip("-")) > 19:
        fail("input-limit")
    value = int(text)
    if abs(value) > MAX_INTEGER:
        fail("input-limit")
    return value


def _reject_number(_text):
    fail("invalid-json")


def load_capture(path):
    """Read one regular file once, at most the documented byte limit plus one."""
    try:
        spelling = os.fspath(path)
    except TypeError:
        fail("input-not-local")
    # Reject explicit remote/device locations before stat/open. This is lexical;
    # a local mount or symlink can still be backed by a remote filesystem.
    if (not isinstance(spelling, str) or spelling.replace("\\", "/").startswith("//")
            or "://" in spelling
            or (re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", spelling)
                and not re.match(r"^[A-Za-z]:", spelling))):
        fail("input-not-local")
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            fail("input-not-regular")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                fail("input-not-regular")
            raw = stream.read(MAX_BYTES+1)
    except (OSError, ValueError):
        fail("input-unreadable")
    if len(raw) > MAX_BYTES:
        fail("input-limit")
    # Bound structural depth before the JSON decoder builds nested containers.
    depth = 0
    quoted = False
    escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                fail("input-limit")
        elif byte in (93, 125):
            depth -= 1
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_int=_integer, parse_float=_reject_number, parse_constant=_reject_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        fail("invalid-json")
    _bounded_tree(value)
    return value


def parse_date(value):
    match = HTTP_DATE.fullmatch(value)
    if not match:
        fail("invalid-date")
    weekday, day, month, year, hour, minute, second = match.groups()
    try:
        moment = datetime.datetime(int(year), MONTHS.index(month)+1, int(day),
            int(hour), int(minute), int(second), tzinfo=UTC)
    except ValueError:
        fail("invalid-date")
    if WEEKDAYS[moment.weekday()] != weekday:
        fail("invalid-date")
    delta = moment-EPOCH
    return delta.days*86400+delta.seconds


def parse_delta(value, *, canonical=False):
    grammar = CANONICAL if canonical else DECIMAL
    if not grammar.fullmatch(value) or len(value) > 19:
        fail("invalid-delta-seconds")
    parsed = int(value)
    if parsed > MAX_INTEGER:
        fail("input-limit")
    return parsed


def parse_directives(values):
    """Token/quoted-string scanner; separators inside quotes remain data."""
    result = {}
    members = 0
    for value in values:
        cursor = 0
        size = len(value)
        while cursor < size:
            while cursor < size and value[cursor] in " \t":
                cursor += 1
            if cursor == size:
                break
            if value[cursor] == ",":
                members += 1
                if members > MAX_DIRECTIVES:
                    fail("input-limit")
                cursor += 1
                continue
            match = TOKEN.match(value, cursor)
            if not match:
                fail("invalid-cache-control")
            name = match.group().lower()
            cursor = match.end()
            while cursor < size and value[cursor] in " \t":
                cursor += 1
            argument = None
            if cursor < size and value[cursor] == "=":
                cursor += 1
                while cursor < size and value[cursor] in " \t":
                    cursor += 1
                if cursor < size and value[cursor] == '"':
                    cursor += 1
                    chars = []
                    while cursor < size and value[cursor] != '"':
                        char = value[cursor]
                        if char == "\\":
                            cursor += 1
                            if cursor == size:
                                fail("invalid-cache-control")
                            char = value[cursor]
                        chars.append(char)
                        cursor += 1
                    if cursor == size:
                        fail("invalid-cache-control")
                    argument = "".join(chars)
                    cursor += 1
                else:
                    match = TOKEN.match(value, cursor)
                    if not match:
                        fail("invalid-cache-control")
                    argument = match.group()
                    cursor = match.end()
            while cursor < size and value[cursor] in " \t":
                cursor += 1
            if cursor < size and value[cursor] != ",":
                fail("invalid-cache-control")
            if name in result:
                fail("duplicate-directive")
            members += 1
            if members > MAX_DIRECTIVES:
                fail("input-limit")
            result[name] = argument
            if cursor < size:
                cursor += 1
    for name, argument in result.items():
        if name in ("max-age", "s-maxage"):
            if argument is None:
                fail("invalid-delta-seconds")
            result[name] = parse_delta(argument)
        elif name in FLAGS and argument is not None:
            if name in ("no-cache", "private"):
                fail("unsupported-qualified-directive")
            fail("invalid-cache-control")
    return result


def analyze(data):
    """Return metadata-free numeric evidence; raise InputError on this profile's limits."""
    _bounded_tree(data)
    if type(data) is not dict or set(data) != REQUIRED:
        fail("invalid-shape")
    times = [data[key] for key in ("request_time", "response_time", "now")]
    if any(type(value) is not int or not 0 <= value <= MAX_INTEGER for value in times):
        fail("invalid-time")
    request, response, now = times
    if not request <= response <= now:
        fail("invalid-time-order")
    cache = data["cache"]
    if type(cache) is not str or cache not in ("shared", "private"):
        fail("invalid-cache-kind")
    headers = data["response_headers"]
    if type(headers) is not list or len(headers) > MAX_HEADERS:
        fail("invalid-headers")
    selected = {}
    control = []
    total_bytes = 0
    for pair in headers:
        if type(pair) is not list or len(pair) != 2 or any(type(part) is not str for part in pair):
            fail("invalid-headers")
        name, value = pair
        if not 1 <= len(name) <= MAX_HEADER_NAME or not TOKEN.fullmatch(name):
            fail("invalid-headers")
        if len(value) > MAX_HEADER_VALUE:
            fail("input-limit")
        if any(char != "\t" and not 32 <= ord(char) <= 255 or ord(char) == 127 for char in value):
            fail("invalid-headers")
        total_bytes += len(name)+len(value)
        if total_bytes > MAX_BYTES:
            fail("input-limit")
        name = name.lower()
        value = value.strip(" \t")
        if name in ("date", "age", "expires"):
            if name in selected:
                fail("duplicate-header")
            selected[name] = value
        elif name == "cache-control":
            control.append(value)
    if "date" not in selected:
        fail("date-required")
    origin = parse_date(selected["date"])
    expiry = parse_date(selected["expires"]) if "expires" in selected else None
    upstream = parse_delta(selected["age"], canonical=True) if "age" in selected else 0
    directives = parse_directives(control)
    delay = response-request
    observed = max(0, response-origin)
    transported = upstream+delay
    initial = max(observed, transported)
    resident = now-response
    current = initial+resident
    source = "unknown"
    lifetime = None
    if cache == "shared" and "s-maxage" in directives:
        source, lifetime = "s-maxage", directives["s-maxage"]
    elif "max-age" in directives:
        source, lifetime = "max-age", directives["max-age"]
    elif expiry is not None:
        source, lifetime = "expires", max(0, expiry-origin)
    remaining = None if lifetime is None else lifetime-current
    numeric = "unknown" if lifetime is None else ("fresh" if remaining > 0 else "stale")
    blockers = []
    if "no-store" in directives:
        blockers.append("no-store")
    if "no-cache" in directives:
        blockers.append("validation-required")
    if cache == "shared" and "private" in directives:
        blockers.append("shared-private")
    return {"schema_version": 1, "scope": "numeric-age-and-explicit-freshness-only",
        "diagnostic_only": True, "cache": cache, "header_count": len(headers),
        "age": {"date_epoch": origin, "age_value": upstream, "apparent_age": observed,
            "response_delay": delay, "corrected_age_value": transported,
            "corrected_initial_age": initial, "resident_time": resident, "current_age": current},
        "freshness": {"source": source, "lifetime_seconds": lifetime,
            "remaining_seconds": remaining, "numeric_freshness": numeric},
        "recognized_flags": {flag: flag in directives for flag in FLAGS},
        "unmodeled_directive_count": sum(name not in FLAGS and name not in ("max-age", "s-maxage")
            for name in directives), "blockers": blockers,
        "selected_threshold_pass": numeric == "fresh" and not blockers}


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        fail("invalid-arguments")


def main(argv=None):
    parser = Parser(description="Explain numeric age of a captured response; not a reuse decision.")
    parser.add_argument("capture", help="explicit local JSON capture file")
    try:
        args = parser.parse_args(argv)
        report = analyze(load_capture(args.capture))
        code = 0 if report["selected_threshold_pass"] else 1
    except InputError as error:
        report = {"status": "invalid", "code": str(error)}
        code = 2
    sys.stdout.write(json.dumps(report, sort_keys=True, ensure_ascii=True)+"\n")
    sys.stdout.flush()
    return code


def run():
    try:
        try:
            return main()
        finally:
            # argparse help exits early, so flush it inside the same pipe guard.
            sys.stdout.flush()
    except (BrokenPipeError, OSError):
        # Avoid a second buffered write during interpreter shutdown (exit 120).
        try:
            descriptor = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(descriptor, sys.stdout.fileno())
            finally:
                os.close(descriptor)
        except OSError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
