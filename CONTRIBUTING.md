# Contributing

Start by running the two example commands in the README and the test suite:

```sh
python -m unittest discover -s tests -v
```

No packages need to be installed for this command. Tests execute real child processes for launch errors, timeouts, capture limits, literal arguments, baseline instability and changed JSON results.

Useful additions include an optional adapter for file-based JSON commands or additional value-preserving presentations. Keep those features explicit: a target's byte-oriented behavior can be intentional. Output selection is implemented with `--compare-pointer`; preserve its missing-value failure behavior and RFC 6901 escapes.

The [numeric presentation guide](docs/numeric-presentations.md) documents exponent and normalized-number cases. Numeric rendering must preserve signed zero, remain exact under restrictive Decimal contexts, and avoid allocating strings proportional to an exponent. Add numeric regressions to `tests/test_numeric_presentations.py`.

Before adding a presentation, demonstrate that every generated payload decodes to the original value. Preserve decimal precision, array order, Unicode string contents and unique object members. Add a positive target that passes and an independent broken target that the new case catches.

Before changing output comparison, add tests for booleans versus numbers, exact decimal values, JSON Pointer escaping and missing fields. Keep report schema changes documented. Reports should carry hashes and locations rather than fixture values or command arguments.

The selection examples cover stable data with changing metadata and an independent order-dependent result. Add selection regressions to `tests/test_pointer.py` or `tests/test_selection.py`. Malformed pointers must fail before a target runs. Valid pointers that do not resolve must fail the case, including on the baseline repeat.

Open a focused issue or pull request with the command you ran, the observed report and a small synthetic fixture. Keep credentials and private input data out of examples and reports.
