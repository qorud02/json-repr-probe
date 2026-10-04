"""Independent target: determine whole-number status from the numeric value."""
from decimal import Decimal
import json
import sys

value = json.load(sys.stdin, parse_int=Decimal, parse_float=Decimal)
amount = value["amount"]
result = {"whole": amount == amount.to_integral_value()}
print(json.dumps(result))
