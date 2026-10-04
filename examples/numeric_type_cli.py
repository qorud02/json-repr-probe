"""Deliberately broken target: confuse a parser's native type with numeric value."""
import json
import sys

value = json.load(sys.stdin)
# This reports False for 1.0 or 1e0, even though both represent a whole number.
print(json.dumps({"whole": isinstance(value["amount"], int)}))
