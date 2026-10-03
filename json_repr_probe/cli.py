import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .core import ProbeError
from .runner import probe


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find JSON presentation dependencies in a local stdin-to-stdout command.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 JSON fixture")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per target invocation (default: 10)")
    parser.add_argument("--max-bytes", type=int, default=1048576, help="size limit for each input/stdout/stderr (default: 1 MiB)")
    parser.add_argument("--cwd", type=Path, help="target working directory; fixture remains relative to the caller")
    parser.add_argument("--compare-pointer", help="compare one output value using an RFC 6901 JSON Pointer (default: whole output)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- executable [arguments]")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    try:
        if args.max_bytes <= 0:
            raise ProbeError("max bytes must be a positive integer")
        with args.input.open("rb") as stream:
            payload = stream.read(args.max_bytes + 1)
        report = probe(payload, command, timeout=args.timeout, max_bytes=args.max_bytes,
                       cwd=args.cwd, compare_pointer=args.compare_pointer)
    except (OSError, ProbeError) as exc:
        message = str(exc) if isinstance(exc, ProbeError) else "cannot read input or access target working directory"
        print("json-repr-probe: " + message, file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print("JSON presentation probe: " + report["status"])
        for case in report["cases"]:
            detail = ""
            if "difference" in case:
                change = case["difference"]
                # JSON quoting keeps terminal control characters inside a pointer inert.
                detail = " at " + json.dumps(change["pointer"], ensure_ascii=True) + " (" + change["kind"] + ")"
            print("  " + case["name"] + ": " + case["status"] + detail)
        print(str(len(report["cases"])) + " invocations; identical payload variants omitted")
    if any(case["status"] == "launch-error" for case in report["cases"]):
        return 2
    return 0 if report["status"] == "passed" else 1
