"""Strict RFC 6901 string-form selection of one existing JSON value."""

import re

from .core import ProbeError


class PointerMissing(ProbeError):
    """A syntactically valid pointer does not resolve in this output."""


def pointer_tokens(pointer):
    """Validate a JSON Pointer before any command runs, then decode its tokens."""
    if not isinstance(pointer, str):
        raise ProbeError("comparison pointer must be a string")
    if pointer == "":
        return ()
    if not pointer.startswith("/") or re.search(r"~(?:[^01]|$)", pointer):
        raise ProbeError("comparison pointer must be empty or start with / and use only ~0/~1 escapes")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in pointer):
        raise ProbeError("comparison pointer contains an unpaired Unicode surrogate")
    # Decode ~1 first: ~01 names a literal ~1, rather than a slash.
    return tuple(part.replace("~1", "/").replace("~0", "~")
                 for part in pointer[1:].split("/"))


def resolve_pointer(value, tokens):
    """Resolve decoded tokens; missing values never become a null default."""
    for token in tokens:
        if isinstance(value, dict):
            if token not in value:
                raise PointerMissing("selected object member is missing")
            value = value[token]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise PointerMissing("selected array index does not identify an element")
            # Bound the token before int(): very long indices still fail cleanly.
            if len(token) > len(str(len(value))) or int(token) >= len(value):
                raise PointerMissing("selected array index is out of range")
            value = value[int(token)]
        else:
            raise PointerMissing("selected pointer traverses a scalar")
    return value
