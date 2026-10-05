"""Exact JSON comparison and deterministic, value-preserving presentations."""

from dataclasses import dataclass
from decimal import Decimal, DecimalException
import hashlib
import json


class ProbeError(ValueError):
    """An invalid probe input or configuration."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError("duplicate object member")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ProbeError("nonstandard numeric constant")


def _finite_number(text):
    number = Decimal(text)
    # Decimal can return NaN for an unsupported exponent when traps are disabled.
    if not number.is_finite():
        raise ProbeError("number exceeds the supported Decimal range")
    return number


def _check_strings(value, depth=0):
    if depth > 128:
        raise ProbeError("JSON nesting exceeds 128 levels")
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ProbeError("unpaired Unicode surrogate")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_strings(key, depth + 1)
            _check_strings(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_strings(item, depth + 1)


def parse_json(payload):
    """Parse UTF-8 JSON with exact numbers and unambiguous object members."""
    try:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        value = json.loads(text, parse_float=_finite_number, parse_int=_finite_number,
                           parse_constant=_reject_constant,
                           object_pairs_hook=_unique_object)
        _check_strings(value)
        return value
    except ProbeError:
        raise
    except (ValueError, UnicodeError, RecursionError, DecimalException) as exc:
        raise ProbeError("invalid UTF-8 JSON") from exc


def _render_number(value, style):
    """Change a finite Decimal's spelling without rounding or exponent expansion."""
    if style == "original":
        return str(value)
    sign, digits, exponent = value.as_tuple()
    prefix = "-" if sign else ""
    coefficient = "".join(str(digit) for digit in digits)
    if style == "exponent":
        # Keep the stored exponent, including at Decimal's lowest boundary.
        return prefix + coefficient + "e" + str(exponent)

    # Removing trailing zeroes is exact string work. Decimal.normalize() would
    # first round under the caller's active context, so it cannot be used here.
    reduced = coefficient.rstrip("0")
    if not reduced:
        return prefix + "0"
    exponent += len(coefficient) - len(reduced)
    coefficient = reduced
    scientific = coefficient + "e" + str(exponent)
    point = len(coefficient) + exponent
    if exponent >= 0:
        plain_length = point
    elif point > 0:
        plain_length = len(coefficient) + 1
    else:
        plain_length = 2 - point + len(coefficient)
    # Compute the length before allocating zeros: 1e1000000000 stays short.
    if plain_length > len(scientific):
        return prefix + scientific
    if exponent >= 0:
        plain = coefficient + "0" * exponent
    elif point > 0:
        plain = coefficient[:point] + "." + coefficient[point:]
    else:
        plain = "0." + "0" * -point + coefficient
    return prefix + plain


def render_json(value, *, key_order="original", ascii_only=False, pretty=False,
                number_style="original"):
    """Serialize parsed values without converting decimal numbers to floats."""
    if number_style not in {"original", "exponent", "normalized"}:
        raise ProbeError("unsupported number presentation")

    def render(item, level):
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ProbeError("nonfinite number")
            return _render_number(item, number_style)
        if isinstance(item, int):
            return str(item) if number_style == "original" else _render_number(Decimal(item), number_style)
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=ascii_only)
        if isinstance(item, (dict, list)):
            if isinstance(item, dict):
                keys = list(item)
                if key_order == "reversed":
                    keys.reverse()
                elif key_order == "sorted":
                    keys.sort()
                colon = ": " if pretty else ":"
                parts = [render(key, level + 1) + colon + render(item[key], level + 1)
                         for key in keys]
                start, end = "{", "}"
            else:
                parts = [render(child, level + 1) for child in item]
                start, end = "[", "]"
            if not parts:
                return start + end
            if pretty:
                pad = "  " * (level + 1)
                return start + "\n" + pad + (",\n" + pad).join(parts) + "\n" + "  " * level + end
            return start + ",".join(parts) + end
        raise ProbeError("unsupported JSON value type")

    return render(value, 0)


@dataclass(frozen=True)
class Case:
    name: str
    payload: bytes

    @property
    def sha256(self):
        return hashlib.sha256(self.payload).hexdigest()


def make_cases(payload):
    """Return the original and distinct deterministic JSON presentations."""
    value = parse_json(payload)
    compact = render_json(value)
    pretty = render_json(value, pretty=True)
    candidates = [
        ("original", payload),
        ("compact", compact.encode("utf-8")),
        ("reversed-keys", render_json(value, key_order="reversed").encode("utf-8")),
        ("sorted-keys", render_json(value, key_order="sorted").encode("utf-8")),
        ("pretty-lf", (pretty + "\n").encode("utf-8")),
        ("pretty-crlf", (pretty + "\n").replace("\n", "\r\n").encode("utf-8")),
        ("escaped-unicode", render_json(value, ascii_only=True).encode("utf-8")),
        ("escaped-slashes", compact.replace("/", "\\/").encode("utf-8")),
        ("padded-whitespace", (" \t\r\n" + compact + "\r\n\t ").encode("utf-8")),
        ("numbers-exponent", render_json(value, number_style="exponent").encode("utf-8")),
        ("numbers-normalized", render_json(value, number_style="normalized").encode("utf-8")),
    ]
    seen = set()
    cases = []
    for name, body in candidates:
        if body not in seen:
            cases.append(Case(name, body))
            seen.add(body)
    return cases


def _pointer(path, part):
    return path + "/" + str(part).replace("~", "~0").replace("/", "~1")


def _json_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (Decimal, int)):
        return "number"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def first_difference(left, right, path=""):
    """Locate the first semantic difference; object order is insignificant."""
    if _json_type(left) != _json_type(right):
        return {"pointer": path, "kind": "type"}
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return {"pointer": _pointer(path, key), "kind": "member"}
            found = first_difference(left[key], right[key], _pointer(path, key))
            if found is not None:
                return found
    elif isinstance(left, list):
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, _pointer(path, index))
            if found is not None:
                return found
        if len(left) != len(right):
            return {"pointer": _pointer(path, min(len(left), len(right))), "kind": "length"}
    elif left != right:
        return {"pointer": path, "kind": "value"}
    return None
