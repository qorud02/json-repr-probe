import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from json_repr_probe.core import Case, ProbeError
from json_repr_probe.runner import probe, run_case


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / "examples/input.json").read_bytes()


def target(code):
    return [sys.executable, "-c", code]


class RunnerTests(unittest.TestCase):
    def test_stable_command_passes(self):
        command = target("import sys,json; print(json.dumps(json.loads(sys.stdin.buffer.read()),sort_keys=True))")
        # Native float decoding is exact for these binary-representable values.
        payload = b'{"z":"hello /","a":[0,1,-1,1.5,9007199254740992]}'
        report = probe(payload, command, cwd=ROOT)
        self.assertEqual(report["status"], "passed")
        self.assertGreaterEqual(len(report["cases"]), 8)
        self.assertEqual(report["cases"][1]["name"], "baseline-repeat")

    def test_order_sensitive_target_is_caught(self):
        report = probe(FIXTURE, [sys.executable, "-m", "examples.order_sensitive_cli"], cwd=ROOT)
        self.assertEqual(report["status"], "failed")
        changed = {case["name"]: case for case in report["cases"] if case["status"] == "different-output"}
        self.assertIn("reversed-keys", changed)
        self.assertEqual(changed["reversed-keys"]["difference"], {"pointer": "/selected", "kind": "value"})

    def test_raw_input_dependency_is_caught(self):
        report = probe(FIXTURE, target("import sys,json; print(json.dumps({'bytes':len(sys.stdin.buffer.read())}))"))
        self.assertEqual(report["status"], "failed")

    def test_nondeterministic_baseline_is_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            code = "from pathlib import Path; p=Path('counter'); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); print(n)"
            report = probe(b"{}", target(code), cwd=folder)
        self.assertEqual(report["status"], "unstable-baseline")
        self.assertEqual(len(report["cases"]), 2)

    def test_nonzero_baseline(self):
        report = probe(b"{}", target("import sys; print('{}'); sys.exit(7)"))
        self.assertEqual(report["status"], "baseline-failed")
        self.assertEqual(report["cases"][0]["status"], "target-error")
        self.assertEqual(report["cases"][0]["exit_code"], 7)

    def test_nonzero_variant(self):
        code = "import sys; b=sys.stdin.buffer.read(); print('{}'); sys.exit(8 if b.startswith(b' \\t') else 0)"
        report = probe(b"{}", target(code))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["cases"][-1]["status"], "target-error")

    def test_invalid_stdout(self):
        for code in ("print('log before {}')", "print('{\"a\":1,\"a\":2}')", "print('NaN')", "print('{} {}')"):
            with self.subTest(code=code):
                report = probe(b"{}", target(code))
                self.assertEqual(report["cases"][0]["status"], "invalid-json")

    def test_timeout(self):
        result, value = run_case(target("import time; time.sleep(10)"), Case("slow", b"{}"), timeout=0.15, max_bytes=1024)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNone(value)
        self.assertLess(result["duration_ms"], 3000)

    def test_output_limit_for_stdout_and_stderr(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                result, _ = run_case(target("import sys; sys." + stream + ".write('x'*2048)"), Case("large", b"{}"), timeout=3, max_bytes=1024)
                self.assertEqual(result["status"], "output-limit")

    def test_missing_executable(self):
        report = probe(b"{}", ["json-repr-probe-nonexistent-executable-719335"])
        self.assertEqual(report["cases"][0]["status"], "launch-error")

    def test_no_shell_expansion(self):
        argument = "$(not-a-command); `not-a-command` & %PATH%"
        command = target("import sys,json; print(json.dumps(sys.argv[1]))") + [argument]
        result, value = run_case(command, Case("literal", b"{}"), timeout=3, max_bytes=1024)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(value, argument)

    def test_report_omits_values_and_command(self):
        secret = "synthetic-sensitive-value-735"
        report = probe(b"{}", target("import json; print(json.dumps('" + secret + "'))"))
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn("command", report)

    def test_invalid_configuration(self):
        for options in ({"timeout": 0}, {"timeout": float("nan")}, {"timeout": float("inf")}, {"max_bytes": 0}, {"max_bytes": True}):
            with self.subTest(options=options), self.assertRaises(ProbeError):
                probe(b"{}", target("print('{}')"), **options)

    def test_input_limit_and_generated_limit(self):
        for data in (b" " * 1025, ('"' + "안" * 300 + '"').encode()):
            with self.subTest(data=len(data)), self.assertRaises(ProbeError):
                probe(data, target("print('{}')"), max_bytes=1024)

    def test_missing_command(self):
        with self.assertRaises(ProbeError):
            probe(b"{}", [])

    def test_api_requires_bytes_and_explicit_argument_list(self):
        for data, command in (("{}", ["python"]), (b"{}", "python")):
            with self.subTest(data=data, command=command), self.assertRaises(ProbeError):
                probe(data, command)

    def test_empty_argument_is_passed_to_target(self):
        command = target("import sys,json; print(json.dumps(sys.argv[1:]))") + [""]
        with tempfile.TemporaryDirectory() as folder:
            result, value = run_case(command, Case("empty-argument", b"{}"), timeout=30, max_bytes=1024, cwd=folder)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(value, [""])
            self.assertEqual(probe(b"{}", command, timeout=30, cwd=folder)["status"], "passed")

    def test_command_requires_nonempty_executable_and_string_arguments(self):
        for command in (("",), (None,), ("python", 1), ("python", None)):
            with self.subTest(command=command), self.assertRaises(ProbeError):
                probe(b"{}", command)


class CliTests(unittest.TestCase):
    def invoke(self, args):
        return subprocess.run([sys.executable, "-m", "json_repr_probe", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_passing_example(self):
        result = self.invoke(["--input", "examples/input.json", "--format", "json", "--", sys.executable, "-m", "examples.stable_cli"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_failing_example(self):
        result = self.invoke(["--input", "examples/input.json", "--", sys.executable, "-m", "examples.order_sensitive_cli"])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('at "/selected" (value)', result.stdout)

    def test_missing_input(self):
        result = self.invoke(["--input", "nonexistent-719335.json", "--", sys.executable, "-c", "print('{}')"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read input", result.stderr)

    def test_missing_command(self):
        result = self.invoke(["--input", "examples/input.json"])
        self.assertEqual(result.returncode, 2)

    def test_missing_executable(self):
        result = self.invoke(["--input", "examples/input.json", "--", "nonexistent-executable-719335"])
        self.assertEqual(result.returncode, 2)

    def test_terminal_control_chars_in_pointer_are_escaped(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / "input.json"
            fixture.write_text('{"z":1,"a":2}', encoding="utf-8")
            code = "import sys,json; v=json.loads(sys.stdin.buffer.read()); print(json.dumps({'\\x1b[31m':next(iter(v))}))"
            result = self.invoke(["--input", str(fixture), "--", *target(code)])
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("\x1b", result.stdout)
        self.assertIn("\\u001b", result.stdout)


if __name__ == "__main__":
    unittest.main()
