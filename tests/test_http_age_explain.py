"""Behavioral tests; arithmetic expectations do not call product helpers."""
import copy
import datetime
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "http_age_explain.py"
SPEC = importlib.util.spec_from_file_location("subject", ROOT / SCRIPT)
if (ROOT / SCRIPT).exists():
    subject = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(subject)
else:
    subject = None


def date(epoch):
    dt = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=epoch)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def capture(cc="max-age=100", *, request=98, response=100, now=105,
            date_value=90, age="3", cache="shared"):
    headers = [["Date", date(date_value)]]
    if age is not None:
        headers.append(["Age", age])
    if cc is not None:
        headers.append(["Cache-Control", cc])
    return {"request_time": request, "response_time": response,
            "now": now, "cache": cache, "response_headers": headers}


class ArithmeticTests(unittest.TestCase):
    def run_report(self, data):
        self.assertIsNotNone(subject, "implementation module is missing")
        return subject.analyze(data)

    def test_conservative_age_terms(self):
        result = self.run_report(capture())
        self.assertEqual(result["age"], {"date_epoch": 90, "age_value": 3,
            "apparent_age": 10, "response_delay": 2, "corrected_age_value": 5,
            "corrected_initial_age": 10, "resident_time": 5, "current_age": 15})
        self.assertEqual(result["freshness"], {"source": "max-age", "lifetime_seconds": 100,
            "remaining_seconds": 85, "numeric_freshness": "fresh"})
        self.assertTrue(result["selected_threshold_pass"])

    def test_exhaustive_small_time_oracle(self):
        for request, delay, resident, origin, upstream in itertools.product(
                range(3), range(3), range(3), range(7), range(4)):
            response = request + delay
            now = response + resident
            result = self.run_report(capture(request=request, response=response,
                now=now, date_value=origin, age=str(upstream)))
            expected = max(max(response-origin, 0), upstream+delay)+resident
            self.assertEqual(result["age"]["current_age"], expected)

    def test_seeded_times_and_boundary(self):
        rng = random.Random(9111)
        for _ in range(120):
            request = rng.randrange(1_000_000)
            response = request+rng.randrange(200)
            now = response+rng.randrange(200)
            origin = response+rng.randrange(-500, 500)
            upstream = rng.randrange(1000)
            expected = max(response-origin, upstream+response-request, 0)+now-response
            for difference, freshness in [(-1, "stale"), (0, "stale"), (1, "fresh")]:
                lifetime = max(0, expected+difference)
                result = self.run_report(capture(f"max-age={lifetime}", request=request,
                    response=response, now=now, date_value=origin, age=str(upstream)))
                self.assertEqual(result["freshness"]["numeric_freshness"], freshness)
                self.assertEqual(result["freshness"]["remaining_seconds"], lifetime-expected)

    def test_missing_age_and_future_date(self):
        result = self.run_report(capture(request=90, response=100, now=101,
            date_value=200, age=None))
        self.assertEqual(result["age"]["current_age"], 11)

    def test_lifetime_precedence_and_private_smaxage(self):
        for cache, source, lifetime in [("shared", "s-maxage", 10), ("private", "max-age", 30)]:
            data = capture("s-maxage=10, max-age=30", cache=cache)
            data["response_headers"].append(["Expires", date(200)])
            result = self.run_report(data)
            self.assertEqual((result["freshness"]["source"], result["freshness"]["lifetime_seconds"]),
                             (source, lifetime))

    def test_expires_unknown_and_pre_epoch_date(self):
        data = capture(None)
        self.assertEqual(self.run_report(data)["freshness"]["numeric_freshness"], "unknown")
        for expiry, expected in [(200, 110), (80, 0)]:
            item = copy.deepcopy(data)
            item["response_headers"].append(["Expires", date(expiry)])
            self.assertEqual(self.run_report(item)["freshness"]["lifetime_seconds"], expected)
        data = capture(None, date_value=-1)
        data["response_headers"].append(["Expires", date(0)])
        self.assertEqual(self.run_report(data)["freshness"]["lifetime_seconds"], 1)

    def test_smaxage_only_ignored_private(self):
        self.assertEqual(self.run_report(capture("s-maxage=99", cache="private"))["freshness"]["source"], "unknown")

    def test_blockers_are_independent_of_numeric_freshness(self):
        for flag, cache, blockers in [("no-store", "private", ["no-store"]),
                ("no-cache", "shared", ["validation-required"]),
                ("private", "shared", ["shared-private"]), ("private", "private", [])]:
            result = self.run_report(capture("max-age=100,"+flag, cache=cache))
            self.assertEqual(result["freshness"]["numeric_freshness"], "fresh")
            self.assertEqual(result["blockers"], blockers)
            self.assertEqual(result["selected_threshold_pass"], not blockers)

    def test_flags_and_quoted_extensions_repeated_headers(self):
        data = capture('MAX-AGE="00100", x-note="a,b\\\"c", public, must-revalidate')
        data["response_headers"].append(["cAcHe-CoNtRoL", "proxy-revalidate, y-note=ok"])
        data["response_headers"][0][0] = "dAtE"
        result = self.run_report(data)
        self.assertEqual(result["unmodeled_directive_count"], 2)
        self.assertTrue(result["recognized_flags"]["must-revalidate"])
        self.assertTrue(result["recognized_flags"]["proxy-revalidate"])
        self.assertEqual(result["freshness"]["lifetime_seconds"], 100)

    def test_large_age_retains_exact_integer(self):
        limit = 2**63-1
        result = self.run_report(capture(f"max-age={limit}", request=0,
            response=limit-1, now=limit, age=str(limit)))
        self.assertEqual(result["age"]["current_age"], 2*limit)
        self.assertEqual(result["freshness"]["remaining_seconds"], -limit)


class InvalidTests(unittest.TestCase):
    def assert_invalid(self, data):
        self.assertIsNotNone(subject, "implementation module is missing")
        with self.assertRaises(subject.InputError):
            subject.analyze(data)

    def test_shape_and_time_types(self):
        for value in [None, [], True, "private"]:
            self.assert_invalid(value)
        for key in ["request_time", "response_time", "now"]:
            for value in [True, 1.0, "100", -1, 2**63, None]:
                data = capture(); data[key] = value
                self.assert_invalid(data)
        for changes in [{"request_time": 101}, {"now": 99}, {"cache": "other"},
                        {"extra": "secret"}, {"cache": []}]:
            data = capture(); data.update(changes); self.assert_invalid(data)
        data = capture(); del data["cache"]; self.assert_invalid(data)

    def test_invalid_dates_and_duplicates(self):
        for value in ["0", "Thursday, 01-Jan-70 00:01:30 GMT", "Thu, 1 Jan 1970 00:01:30 GMT",
                "Thu, 01 Jan 1970 00:01:30 UTC", "Fri, 01 Jan 1970 00:01:30 GMT",
                "Thu, 32 Jan 1970 00:01:30 GMT", "Thu, 01 Jan 1970 00:01:60 GMT",
                "thu, 01 Jan 1970 00:01:30 GMT", "Thu, 01 Jan 0000 00:00:00 GMT"]:
            data = capture(); data["response_headers"][0][1] = value
            self.assert_invalid(data)
        for field, value in [("DATE", date(90)), ("aGe", "1"), ("Expires", date(200))]:
            data = capture(); data["response_headers"].extend([[field, value], [field, value]])
            self.assert_invalid(data)
        data = capture(); data["response_headers"] = []; self.assert_invalid(data)
        data = capture(); data["response_headers"].append(["Expires", "bad"])
        self.assert_invalid(data)  # strict captured-input profile even when max-age wins

    def test_ages(self):
        for value in ["01", "+1", "-1", "1.0", "", "1,2", "9"*20, "١", "1\n"]:
            data = capture(age=value); self.assert_invalid(data)

    def test_directive_grammar_duplicates_and_qualifiers(self):
        values = ['max-age', 'max-age=-1', 'max-age=1.5', 'max-age="1,2"',
            'max-age="broken', 'max-age=1,MAX-AGE=2', 'x=1,X=2', 'no-store=yes',
            'no-cache="Set-Cookie"', 'private=""', 'max-age=9223372036854775808',
            'x="a"tail', '=1', 'x=', 'x="bad\\"', 'x="a\x7fb"', 'public=1',
            'must-revalidate=1', 'proxy-revalidate=1', 's-maxage=no', 'x=a/b']
        for value in values:
            with self.subTest(value=value): self.assert_invalid(capture(value))
        data = capture("max-age=10"); data["response_headers"].append(["cache-control", "MAX-AGE=10"])
        self.assert_invalid(data)

    def test_header_shape_controls_and_limits(self):
        for headers in [None, {}, [["Date"]], [["Date", 1]], [["bad name", "value"]],
                [["Date", date(90)], ["X", "a\r\nb"]],
                [["Date", date(90)], ["X", "\ud800"]],
                [["Date", date(90)], ["X", "😀"]]]:
            data = capture(); data["response_headers"] = headers; self.assert_invalid(data)
        for header in [["X", "a"*4097], ["x"*129, "a"]]:
            data = capture(); data["response_headers"].append(header); self.assert_invalid(data)
        data = capture(); data["response_headers"] += [["X", "a"]]*129; self.assert_invalid(data)
        self.assert_invalid(capture(",".join(f"x{i}" for i in range(257))))


class CLITests(unittest.TestCase):
    def run_file(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/"private-marker.json"
            file.write_bytes(raw)
            return subprocess.run([sys.executable, SCRIPT, str(file)], cwd=ROOT,
                capture_output=True, timeout=15)

    def test_examples_exit_codes(self):
        for cc, code in [("max-age=100", 0), ("max-age=1", 1),
                         ("max-age=100,no-store", 1), (None, 1), ("max-age=bad", 2)]:
            result = self.run_file(json.dumps(capture(cc)).encode())
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(result.stderr, b"")
            json.loads(result.stdout)

    def test_strict_json_and_bounded_input_neutral_errors(self):
        raws = [b'{"cache":0,"cache":1}', b'{"x":NaN}', b'{"x":Infinity}',
            b'{"x":1.0}', b'{"x":"\\ud800"}', b'\xff', b'['*40+b']'*40,
            b'{"x":'+b'9'*5000+b'}', b' '*65537]
        for raw in raws:
            result = self.run_file(raw)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn(b"private-marker", result.stdout+result.stderr)
            self.assertNotIn(b"Traceback", result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_metadata_privacy_and_input_unchanged(self):
        data = capture('max-age=100, secret-marker="https://private.example,a"')
        data["response_headers"].append(["X-secret-marker", "private-value"])
        before = copy.deepcopy(data)
        result = self.run_file(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        for marker in [b"secret-marker", b"private-value", b"private.example", b"Date", b"Cache-Control"]:
            self.assertNotIn(marker, result.stdout+result.stderr)
        if subject is not None:
            subject.analyze(data)
            self.assertEqual(data, before)

    def test_missing_file_directory_and_cli_argument_errors(self):
        for args in [["not-found-private-marker"], ["."], [], ["--bad-private-marker"]]:
            result = subprocess.run([sys.executable, SCRIPT, *args], cwd=ROOT,
                capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"private-marker", result.stdout+result.stderr)
            self.assertNotIn(b"Traceback", result.stdout+result.stderr)

    def test_actual_closed_pipe_and_help_flush(self):
        # A real OS pipe has no reader before the child starts (not a mocked stream).
        for args in [["--help"], ["-h"], ["examples/fresh.json"]]:
            read_fd, write_fd = os.pipe()
            os.close(read_fd)
            try:
                with subprocess.Popen([sys.executable, SCRIPT, *args], cwd=ROOT,
                        stdout=write_fd, stderr=subprocess.PIPE) as process:
                    _, errors = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 2)
                    self.assertNotEqual(process.returncode, 120)
                    self.assertNotIn(b"Traceback", errors)
                    self.assertNotIn(b"Exception ignored", errors)
            finally:
                os.close(write_fd)
        result = subprocess.run([sys.executable, SCRIPT, "--help"], cwd=ROOT,
            capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"captured response", result.stdout)

    def test_non_regular_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            if hasattr(os, "mkfifo"):
                target = target/"private-marker"
                os.mkfifo(target)
            result = subprocess.run([sys.executable, SCRIPT, str(target)], cwd=ROOT,
                capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"private-marker", result.stdout+result.stderr)

    def test_file_bytes_are_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/"capture.json"
            original = json.dumps(capture()).encode()
            file.write_bytes(original)
            result = subprocess.run([sys.executable, SCRIPT, str(file)], cwd=ROOT,
                capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(file.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
