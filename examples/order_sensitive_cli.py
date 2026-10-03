"""Deliberately broken example: depend on the first object member."""
import json
import sys

value = json.loads(sys.stdin.buffer.read())
print(json.dumps({"selected": next(iter(value))}))
