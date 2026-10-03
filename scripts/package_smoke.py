"""Check non-root container execution and probe behavior before registry push."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib

image = sys.argv[1]
root = Path.cwd().resolve()
base = ["docker", "run", "--rm", "--platform", "linux/amd64", "--read-only",
        "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m", "--mount", "type=bind,source=" + str(root) + ",target=/work,readonly",
        "--workdir", "/work"]


def run(arguments, expected, status=None):
    result = subprocess.run(base + [image] + arguments, capture_output=True, text=True, timeout=180)
    if result.returncode != expected:
        raise AssertionError((arguments, expected, result.returncode, result.stdout, result.stderr))
    if status is not None:
        report = json.loads(result.stdout)
        assert report["status"] == status, report
        return report
    return result.stdout.strip()


version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
assert run(["--version"], 0) == version
fixture = ["--input", "/work/examples/input.json", "--format", "json", "--"]
stable = run(fixture + ["python", "-m", "examples.stable_cli"], 0, "passed")
assert len(stable["cases"]) >= 8
broken = run(fixture + ["python", "-m", "examples.order_sensitive_cli"], 1, "failed")
assert any(case.get("difference", {}).get("pointer") == "/selected" for case in broken["cases"])
unstable = "from pathlib import Path; p=Path('/tmp/probe-counter'); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); print(n)"
run(fixture + ["python", "-c", unstable], 1, "unstable-baseline")
empty_argument = "import sys; assert sys.argv[1:]==['']; print('true')"
run(fixture + ["python", "-c", empty_argument, ""], 0, "passed")
run(["--input", "/work/examples/input.json"], 2)
identity = subprocess.run(base + ["--entrypoint", "python", image, "-P", "-c", "import os,json_repr_probe; assert os.getuid()==10001; assert json_repr_probe.__file__.startswith('/app/'); print(os.getuid())"], capture_output=True, text=True, timeout=30)
assert identity.returncode == 0 and identity.stdout.strip() == "10001", identity
print("Container smoke passed: version, stdin target, changed output, unstable baseline, empty argv, configuration error and non-root UID")
