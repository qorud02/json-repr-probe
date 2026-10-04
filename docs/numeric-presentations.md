# Equivalent number spellings

The probe's value-oriented contract treats `1`, `1.0`, and `1e0` as the same
number. Targets can accidentally use a JSON parser's native representation
instead: Python's default decoder returns an `int` for `1` and a `float` for
`1.0` or `1e0`.

## Run the independent examples

From a checkout, check a target that determines whether an amount is a whole
number from its exact decimal value:

```sh
python -m json_repr_probe --input examples/numeric-input.json -- python -m examples.numeric_value_cli
```

It returns exit `0`. The target uses `Decimal` for both numeric parser hooks;
it imports no probe code.

A deliberately broken target checks `isinstance(amount, int)` instead:

```sh
python -m json_repr_probe --input examples/numeric-input.json -- python -m examples.numeric_type_cli
```

It returns exit `1`, with `numbers-exponent: different-output at "/whole" (value)`.
The original input runs twice first and returns the same answer, so this is a
presentation dependency rather than an unstable baseline. The equivalent
exponent form changes the target's answer from `true` to `false`.

A numeric-type distinction can be intentional. Use this probe when a command's
contract depends on numeric values, rather than preserving their spelling,
scale, or the parser's integer/floating-point categories. The new cases run by
default; a previously passing target may now expose one of these dependencies.

## The two presentations

| Case | Example | Method |
| --- | --- | --- |
| `numbers-exponent` | `12.300` → `12300e-3`; `1` → `1e0` | Write the exact coefficient digits and stored exponent |
| `numbers-normalized` | `12.300` → `12.3`; `1.0` → `1` | Remove insignificant coefficient zeros, then choose the shorter plain or coefficient/exponent spelling |

For an equal-length choice, the normalized case uses the plain spelling.
These cases operate on every numeric value, including nested values and a
primitive numeric root. They leave object order, arrays, strings, booleans,
and null unchanged. Numeric-looking strings and member names are never edited.

The sign of zero is retained: `-0.00` can become `-0e-2` or `-0`, but never `0`.
The normalized case deliberately does not retain decimal scale. The original
case and repeated baseline always retain the fixture's original bytes.

All cases remain deterministic and byte-deduplicated. A named case is absent
when an earlier case already has those bytes, and a document without numbers
gains no extra invocations. There are at most two additional target invocations.
Reports keep schema version `1`, existing status names, JSON Pointers, and the
same `0`/`1`/`2` exit meanings. Input values and command arguments remain omitted.

## Precision and resource limits

Number generation uses `Decimal.as_tuple()` and string operations, without
binary floats or context-rounded decimal arithmetic. Long coefficients retain
all digits, including under a caller's restrictive decimal context. The
exponent case retains the stored exponent at the supported Decimal boundaries.

Before allocating a fixed-point spelling, the normalized case calculates its
length. A compact value such as `1e1000000000` stays compact; the renderer never
allocates a billion zeroes. Generated presentations still have to fit
`--max-bytes`, and all input-size checks finish before any target is started.

The target has its own numeric limits. For example, a default Python JSON
round-trip preserves the integer `9007199254740993`, but parses
`9007199254740993e0` through binary floating point and can return
`9007199254740992.0`. The probe reports this as a changed value. A target that
rejects a generated spelling or emits nonfinite JSON fails through the existing
target-error or invalid-JSON checks.

This is a finite set of spelling checks, not exhaustive numeric fuzzing. Select
fixtures that exercise the ranges and precision your command promises.

## References

- [RFC 8259, section 6](https://www.rfc-editor.org/rfc/rfc8259#section-6): JSON's fraction and exponent grammar, plus implementation limits on range and precision
- [Python JSON decoding](https://docs.python.org/3/library/json.html#json.load): `parse_int` and `parse_float` hooks and their defaults
- [Python Decimal tuples](https://docs.python.org/3/library/decimal.html#decimal.Decimal.as_tuple): exact sign, coefficient digits, and exponent
- [Decimal normalization](https://docs.python.org/3/library/decimal.html#decimal.Decimal.normalize): normalization can round under the active context and is not used by this renderer
