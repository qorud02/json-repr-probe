"""Run explicit local commands without a shell and compare their JSON results."""

import hashlib
import math
import os
import signal
import subprocess
import tempfile
import time

from .core import Case, ProbeError, first_difference, make_cases, parse_json


def _stop(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def run_case(command, case, *, timeout, max_bytes, cwd=None):
    started = time.monotonic()
    record = {"name": case.name, "input_sha256": case.sha256,
              "input_bytes": len(case.payload)}
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        source.write(case.payload)
        source.seek(0)
        try:
            process = subprocess.Popen(command, stdin=source, stdout=output, stderr=errors,
                                       cwd=cwd, shell=False, start_new_session=(os.name == "posix"))
        except OSError:
            return {**record, "status": "launch-error"}, None
        stopped = None
        while process.poll() is None:
            if os.fstat(output.fileno()).st_size > max_bytes or os.fstat(errors.fileno()).st_size > max_bytes:
                stopped = "output-limit"
                _stop(process)
                break
            if time.monotonic() - started >= timeout:
                stopped = "timeout"
                _stop(process)
                break
            time.sleep(0.01)
        record["exit_code"] = process.returncode
        record["duration_ms"] = round((time.monotonic() - started) * 1000)
        size = os.fstat(output.fileno()).st_size
        stderr_size = os.fstat(errors.fileno()).st_size
        record.update(stdout_bytes=size, stderr_bytes=stderr_size)
        if stopped or size > max_bytes or stderr_size > max_bytes:
            record["status"] = stopped or "output-limit"
            return record, None
        output.seek(0)
        body = output.read(max_bytes + 1)
        record["stdout_sha256"] = hashlib.sha256(body).hexdigest()
        if process.returncode != 0:
            record["status"] = "target-error"
            return record, None
        try:
            value = parse_json(body)
        except ProbeError:
            record["status"] = "invalid-json"
            return record, None
        record["status"] = "passed"
        return record, value


def probe(payload, command, *, timeout=10.0, max_bytes=1048576, cwd=None):
    """Run a baseline control, then test distinct equivalent presentations."""
    if not isinstance(payload, bytes):
        raise ProbeError("input payload must be bytes")
    if (not isinstance(command, (list, tuple)) or not command
            or not isinstance(command[0], str) or not command[0]
            or not all(isinstance(arg, str) for arg in command)):
        raise ProbeError("provide a command after --")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ProbeError("timeout must be a finite positive number")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ProbeError("max bytes must be a positive integer")
    if len(payload) > max_bytes:
        raise ProbeError("input exceeds max bytes")
    cases = make_cases(payload)
    if any(len(case.payload) > max_bytes for case in cases):
        raise ProbeError("a generated presentation exceeds max bytes; raise --max-bytes")
    report = {"schema_version": 1, "status": "passed", "cases": []}
    baseline, expected = run_case(command, cases[0], timeout=timeout, max_bytes=max_bytes, cwd=cwd)
    report["cases"].append(baseline)
    if baseline["status"] != "passed":
        report["status"] = "baseline-failed"
        return report
    control, repeated = run_case(command, Case("baseline-repeat", payload), timeout=timeout, max_bytes=max_bytes, cwd=cwd)
    report["cases"].append(control)
    if control["status"] != "passed":
        report["status"] = "baseline-failed"
        return report
    difference = first_difference(expected, repeated)
    if difference is not None:
        control.update(status="different-output", difference=difference)
        report["status"] = "unstable-baseline"
        return report
    for case in cases[1:]:
        record, actual = run_case(command, case, timeout=timeout, max_bytes=max_bytes, cwd=cwd)
        if record["status"] == "passed":
            difference = first_difference(expected, actual)
            if difference is not None:
                record.update(status="different-output", difference=difference)
        report["cases"].append(record)
        if record["status"] != "passed":
            report["status"] = "failed"
    return report
