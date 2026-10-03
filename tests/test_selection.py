import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from json_repr_probe.core import ProbeError
from json_repr_probe.runner import probe as run_probe


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = b'{"z":1,"a":2}'


def target(code):
    return [sys.executable, "-I", "-c", code]


def probe(payload, command, **options):
    # These check output semantics, not launch speed. Windows startup can exceed
    # ten seconds under load; the separate timeout regression retains its limit.
    options.setdefault("timeout", 30)
    return run_probe(payload, command, **options)


COUNTER = ("from pathlib import Path; import json,sys; p=Path('counter'); "
           "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
           "value=json.loads(sys.stdin.buffer.read()); ")


class SelectionRunnerTests(unittest.TestCase):
    def test_changing_metadata_passes_only_with_explicit_selection(self):
        command = target(COUNTER + "print(json.dumps({'request_id':n,'data':sorted(value)}))")
        with tempfile.TemporaryDirectory() as folder:
            whole = probe(FIXTURE, command, cwd=folder)
            selected = probe(FIXTURE, command, cwd=folder, compare_pointer="/data")
        self.assertEqual(whole["status"], "unstable-baseline")
        self.assertNotIn("comparison_pointer", whole)
        self.assertEqual(selected["status"], "passed")
        self.assertEqual(selected["comparison_pointer"], "/data")
        self.assertGreater(len(selected["cases"]), 2)
        self.assertNotEqual(selected["cases"][0]["stdout_sha256"],
                            selected["cases"][1]["stdout_sha256"])

    def test_selected_ordering_bug_reports_absolute_escaped_location(self):
        code = ("import sys,json; value=json.loads(sys.stdin.buffer.read()); "
                "print(json.dumps({'a/b~c':{'selected':next(iter(value))}}))")
        report = probe(FIXTURE, target(code), compare_pointer="/a~1b~0c")
        self.assertEqual(report["status"], "failed", report)
        changed = [case for case in report["cases"]
                   if case["status"] == "different-output"]
        self.assertTrue(changed, report)
        self.assertEqual(changed[0]["difference"],
                         {"pointer": "/a~1b~0c/selected", "kind": "value"})

    def test_nondeterminism_in_selected_value_still_fails_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            report = probe(FIXTURE, target(COUNTER + "print(json.dumps({'data':n}))"),
                           cwd=folder, compare_pointer="/data")
        self.assertEqual(report["status"], "unstable-baseline")
        self.assertEqual(len(report["cases"]), 2)
        self.assertEqual(report["cases"][1]["difference"],
                         {"pointer": "/data", "kind": "value"})

    def test_missing_baseline_selection_is_not_null(self):
        report = probe(b"{}", target("print('{}')"), compare_pointer="/data")
        self.assertEqual(report["status"], "baseline-failed")
        self.assertEqual(len(report["cases"]), 1)
        self.assertEqual(report["cases"][0]["status"], "missing-pointer")
        self.assertEqual(report["cases"][0]["difference"],
                         {"pointer": "/data", "kind": "missing"})
        existing = probe(b"{}", target('print(\'{"data":null}\')'), compare_pointer="/data")
        self.assertEqual(existing["status"], "passed")

    def test_selection_missing_in_repeat_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            code = COUNTER + "print(json.dumps({'data':None} if n == 1 else {}))"
            report = probe(b"{}", target(code), cwd=folder, compare_pointer="/data")
        self.assertEqual(report["status"], "baseline-failed")
        self.assertEqual(report["cases"][1]["status"], "missing-pointer")

    def test_selection_missing_in_variant_fails(self):
        code = ("import sys,json; v=json.loads(sys.stdin.buffer.read()); "
                "print(json.dumps({'data':None} if next(iter(v)) == 'z' else {}))")
        report = probe(FIXTURE, target(code), compare_pointer="/data")
        self.assertEqual(report["status"], "failed")
        missing = [case for case in report["cases"] if case["status"] == "missing-pointer"]
        self.assertTrue(missing)
        self.assertTrue(all(case["difference"]["pointer"] == "/data" for case in missing))

    def test_invalid_pointer_never_launches_target(self):
        with patch("json_repr_probe.runner.run_case") as execute:
            for pointer in ("#/data", "/data~", "/~2", 1):
                with self.subTest(pointer=pointer), self.assertRaises(ProbeError):
                    probe(b"{}", ["target"], compare_pointer=pointer)
            execute.assert_not_called()

    def test_whole_output_is_validated_before_selection(self):
        for body in ('{"data":1,"outside":1,"outside":2}', '{"data":1,"outside":NaN}',
                     '{"data":1} log', '{"data":1,"outside":"\\ud800"}'):
            with self.subTest(body=body):
                report = probe(b"{}", target("print(" + repr(body) + ")"),
                               compare_pointer="/data")
                self.assertEqual(report["cases"][0]["status"], "invalid-json")

    def test_selected_scalar_preserves_boolean_number_distinction(self):
        code = ("import sys,json; v=json.loads(sys.stdin.buffer.read()); "
                "print(json.dumps({'data':True if next(iter(v)) == 'z' else 1}))")
        report = probe(FIXTURE, target(code), compare_pointer="/data")
        changed = [case for case in report["cases"] if case["status"] == "different-output"]
        self.assertTrue(changed)
        self.assertEqual(changed[0]["difference"], {"pointer": "/data", "kind": "type"})

    def test_selection_preserves_precision_and_array_order(self):
        for left, right, pointer in (
                (9007199254740993, 9007199254740992, "/data"),
                ([1, 2], [2, 1], "/data/0")):
            with self.subTest(pointer=pointer):
                code = ("import sys,json; v=json.loads(sys.stdin.buffer.read()); "
                        "print(json.dumps({'data':" + repr(left) +
                        " if next(iter(v)) == 'z' else " + repr(right) + "}))")
                report = probe(FIXTURE, target(code), compare_pointer="/data")
                changed = [case for case in report["cases"] if case["status"] == "different-output"]
                self.assertTrue(changed, report)
                self.assertEqual(changed[0]["difference"]["pointer"], pointer)

    def test_root_selection_matches_default_contract(self):
        command = target("import sys,json; print(json.dumps(json.loads(sys.stdin.buffer.read())))")
        report = probe(b"null", command, compare_pointer="")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["comparison_pointer"], "")

    def test_reports_do_not_record_selected_values(self):
        value = "synthetic-private-output-293"
        command = target("import json; print(json.dumps({'data':'" + value + "'}))")
        report = probe(b"{}", command, compare_pointer="/data")
        self.assertEqual(report["status"], "passed")
        self.assertNotIn(value, json.dumps(report))


class SelectionCliTests(unittest.TestCase):
    def invoke(self, options, command):
        return subprocess.run([sys.executable, "-m", "json_repr_probe",
                               "--input", "examples/input.json", "--timeout", "30", *options,
                               "--", *command], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_metadata_example_passes(self):
        result = self.invoke(["--compare-pointer", "/data", "--format", "json"],
                             [sys.executable, "-m", "examples.metadata_cli"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_broken_metadata_example_fails(self):
        result = self.invoke(["--compare-pointer", "/data"],
                             [sys.executable, "-m", "examples.metadata_cli", "--first-key"])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('at "/data/selected" (value)', result.stdout)

    def test_invalid_pointer_is_configuration_error(self):
        result = self.invoke(["--compare-pointer", "#/data"],
                             target("print('{}')"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("comparison pointer", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_pointer_is_target_failure(self):
        result = self.invoke(["--compare-pointer", "/missing", "--format", "json"],
                             target("print('{}')"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["cases"][0]["status"], "missing-pointer")

    def test_pointer_control_characters_are_escaped(self):
        result = self.invoke(["--compare-pointer", "/\x1b[31m"],
                             target("print('{}')"))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("\x1b", result.stdout)
        self.assertIn("\\u001b", result.stdout)


if __name__ == "__main__":
    unittest.main()
