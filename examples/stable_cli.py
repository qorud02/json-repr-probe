"""Independent example target: select fields without depending on formatting."""
import json
import sys

value = json.loads(sys.stdin.buffer.read())
result = {"message": value["z"], "item_count": len(value["items"]), "keys": sorted(value)}
sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("utf-8"))
