"""Validate release metadata before building or authenticating to a registry."""
import os
from pathlib import Path
import re
import tomllib

version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
if os.environ["GITHUB_EVENT_NAME"] == "push":
    ref = os.environ["GITHUB_REF"]
    if not ref.startswith("refs/tags/v"):
        raise SystemExit("Package publishing requires a version tag")
    requested = ref.removeprefix("refs/tags/v")
else:
    if os.environ["GITHUB_REF"] != "refs/heads/main":
        raise SystemExit("Manual package publishing requires main")
    requested = os.environ.get("REQUESTED_VERSION", "")
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", requested) or requested != version:
    raise SystemExit("Requested version must match pyproject.toml")
image = "ghcr.io/" + os.environ["GITHUB_REPOSITORY"].lower()
if image != "ghcr.io/qorud02/json-repr-probe":
    raise SystemExit("Package destination must match the maintained repository")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write("version=" + version + "\nimage=" + image + "\n")
print("Validated package version " + version)
