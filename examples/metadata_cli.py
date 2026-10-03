"""A JSON command with a stable result and a new request ID on every call."""

import argparse
import json
import sys
from uuid import uuid4


parser = argparse.ArgumentParser()
parser.add_argument("--first-key", action="store_true",
                    help="demonstrate an order-dependent result")
args = parser.parse_args()
value = json.loads(sys.stdin.buffer.read())
data = ({"selected": next(iter(value))} if args.first_key else
        {"message": value["z"], "count": len(value["items"]),
         "keys": sorted(value)})
print(json.dumps({"request_id": str(uuid4()), "data": data}))
