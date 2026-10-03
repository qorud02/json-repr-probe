"""Exercise the exact container or installed wheel before publishing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib

parser = argparse.ArgumentParser()
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--container")
mode.add_argument("--python")
parser.add_argument("--console")
args = parser.parse_args()
if args.python and not args.console:
    parser.error("--python requires --console")
root = Path.cwd().resolve()
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
clean_env = {key: value for key, value in os.environ.items()
             if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONOPTIMIZE"}}
checks = []

with tempfile.TemporaryDirectory(prefix="json-package-smoke-") as directory:
    temp = Path(directory)
    if args.container:
        base = ["docker", "run", "--rm", "--platform", "linux/amd64", "--read-only",
                "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m", "--mount",
                "type=bind,source=" + str(root) + ",target=/work,readonly", "--workdir", "/work"]
        prefix = base + [args.container]
        target_python = "python"
        fixture = "/work/examples/input.json"
        example = lambda name: "/work/examples/" + name + ".py"
        counter = "/tmp/probe-counter"
    else:
        prefix = [str(Path(args.console).absolute())]
        target_python = str(Path(args.python).absolute())
        fixture = str(root / "examples/input.json")
        example = lambda name: str(root / "examples" / (name + ".py"))
        counter = str(temp / "counter")

    def run(arguments, expected, label, status=None):
        result = subprocess.run(prefix + arguments, cwd=temp, env=clean_env,
                                capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == expected, (label, expected, result.returncode, result.stdout, result.stderr)
        checks.append(label)
        if status is None:
            return result.stdout.strip()
        report = json.loads(result.stdout)
        assert report["status"] == status, report
        return report

    assert run(["--version"], 0, "console-version") == version
    invocation = ["--input", fixture, "--format", "json", "--"]
    stable = run(invocation + [target_python, "-I", example("stable_cli")], 0, "stable-output", "passed")
    assert len(stable["cases"]) >= 8
    broken = run(invocation + [target_python, "-I", example("order_sensitive_cli")], 1,
                 "changed-output", "failed")
    assert any(case.get("difference", {}).get("pointer") == "/selected" for case in broken["cases"])
    unstable = ("from pathlib import Path; p=Path(" + repr(counter) + "); "
                "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); print(n)")
    run(invocation + [target_python, "-I", "-c", unstable], 1, "unstable-baseline", "unstable-baseline")
    empty = "import sys; assert sys.argv[1:]==['']; print('true')"
    run(invocation + [target_python, "-I", "-c", empty, ""], 0, "empty-argument", "passed")
    run(["--input", fixture], 2, "missing-command")
    selection = ["--input", fixture, "--compare-pointer", "/data", "--format", "json", "--"]
    selected = run(selection + [target_python, "-I", example("metadata_cli")], 0,
                   "selected-metadata", "passed")
    assert selected["comparison_pointer"] == "/data" and len(selected["cases"]) >= 8
    assert selected["cases"][0]["stdout_sha256"] != selected["cases"][1]["stdout_sha256"]
    bug = run(selection + [target_python, "-I", example("metadata_cli"), "--first-key"], 1,
              "selected-ordering-error", "failed")
    assert any(case.get("difference", {}).get("pointer") == "/data/selected" for case in bug["cases"])
    missing = run(["--input", fixture, "--compare-pointer", "/missing", "--format", "json", "--",
                   target_python, "-I", example("metadata_cli")], 1, "missing-selection", "baseline-failed")
    assert missing["cases"][0]["status"] == "missing-pointer"
    run(["--input", fixture, "--compare-pointer", "#/data", "--", target_python,
         "-I", example("metadata_cli")], 2, "invalid-pointer")
    for body, label in (("{\"data\":1,\"outside\":1,\"outside\":2}", "duplicate-outside-selection"),
                        ("{\"data\":1,\"outside\":NaN}", "invalid-number-outside-selection")):
        invalid = run(selection + [target_python, "-I", "-c", "print(" + repr(body) + ")"], 1,
                      label, "baseline-failed")
        assert invalid["cases"][0]["status"] == "invalid-json"
    if args.container:
        identity = subprocess.run(base + ["--entrypoint", "python", args.container, "-P", "-c",
                                           "import os,json_repr_probe; assert os.getuid()==10001; assert json_repr_probe.__file__.startswith('/app/'); print(os.getuid())"],
                                  capture_output=True, text=True, timeout=30)
        assert identity.returncode == 0 and identity.stdout.strip() == "10001", identity
        checks.append("non-root-and-source-independent-import")
    else:
        identity = subprocess.run([target_python, "-I", "-c",
                                   "import json,sys,json_repr_probe; print(json.dumps({'path':json_repr_probe.__file__,'prefix':sys.prefix,'version':json_repr_probe.__version__}))"],
                                  cwd=temp, env=clean_env, capture_output=True, text=True, timeout=30)
        assert identity.returncode == 0, identity.stderr
        imported = json.loads(identity.stdout)
        environment = str(Path(target_python).parents[1])
        assert os.path.commonpath([imported["path"], environment]) == environment, imported
        assert os.path.normcase(imported["prefix"]) == os.path.normcase(environment), imported
        assert imported["version"] == version, imported
        checks.append("isolated-wheel-import-outside-source")
        module = subprocess.run([target_python, "-I", "-m", "json_repr_probe", "--version"],
                                cwd=temp, env=clean_env, capture_output=True, text=True, timeout=30)
        assert module.returncode == 0 and module.stdout.strip() == version, module
        checks.append("module-version")
print(json.dumps({"mode": "container" if args.container else "wheel", "version": version,
                  "checks": checks, "passed": len(checks)}, indent=2))
