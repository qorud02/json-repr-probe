"""Check wheel package bytes, entry point and dependencies against source."""
import hashlib
from email.parser import Parser
from pathlib import Path
import sys
import tomllib
from zipfile import ZipFile

folder = Path(sys.argv[1])
wheels = list(folder.glob("json_repr_probe-*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected exactly one json-repr-probe wheel")
wheel = wheels[0]
version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
with ZipFile(wheel) as archive:
    for source in Path("json_repr_probe").glob("*.py"):
        assert archive.read("json_repr_probe/" + source.name) == source.read_bytes(), source
    metadata = archive.read(next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))).decode()
    headers = Parser().parsestr(metadata)
    assert headers["Name"] == "json-repr-probe" and headers["Version"] == version
    assert not headers.get_all("Requires-Dist"), "Runtime dependencies were added"
    entries = archive.read(next(name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt"))).decode()
    assert "json-repr-probe = json_repr_probe.cli:main" in entries
    license_name = next(name for name in archive.namelist() if name.endswith("/LICENSE"))
    assert archive.read(license_name) == Path("LICENSE").read_bytes()
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
(folder / "SHA256SUMS").write_text(digest + "  " + wheel.name + "\n", encoding="utf-8")
print("Verified wheel " + wheel.name + " SHA256 " + digest)
