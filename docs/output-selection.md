# Compare one output value

Many commands return a JSON envelope:

```json
{
  "request_id": "changes-on-every-call",
  "data": {
    "message": "hello / 안녕 🧪",
    "count": 4,
    "keys": ["a", "items", "z"]
  }
}
```

When the contract promises that `data` is independent of JSON presentation, select it with `--compare-pointer /data`. The baseline control and every generated case then compare that value. Fields outside the selection still belong to the captured JSON document.

## Start with the example

From a checkout, run:

```sh
python -m json_repr_probe --input examples/input.json --compare-pointer /data -- python -m examples.metadata_cli
```

The probe runs the example for each presentation. Every `data` result matches and the command exits `0`.

Now add `--first-key` after the target name:

```sh
python -m json_repr_probe --input examples/input.json --compare-pointer /data -- python -m examples.metadata_cli --first-key
```

Reordered inputs change the selected result. The report includes `different-output at "/data/selected" (value)` and exits `1`. Omitting `--compare-pointer` from either command compares the entire output and detects the changing request ID on the baseline repeat.

For an installed version with output selection, use `json-repr-probe` instead of `python -m json_repr_probe`. The option was added in version `0.2.0`.

## Add the check to CI

Choose a pointer from the target's documented output contract:

```yaml
- name: Check JSON presentation invariance
  run: python -m json_repr_probe --input tests/fixtures/request.json --compare-pointer /result --format json -- python -m your_package
```

Install the probe or keep its source checkout available in the job. A passing result means the selected value matched across the tested presentations. Keep ordinary expected-result tests for the selected value, and separate tests for any metadata fields that have their own requirements.

## Pointer syntax

The option accepts the string form of [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901). Each `/` begins one path segment:

| Pointer | Selected value |
| --- | --- |
| `/data` | Object member named `data` |
| `/data/items/0` | First element of `data.items` |
| `/a~1b` | Object member named `a/b` |
| `/m~0n` | Object member named `m~n` |
| `/~01` | Object member named `~1` |
| `/` | Object member whose name is the empty string |
| Empty string | Entire output document |

Pass shell quotes when a pointer contains spaces or other shell-sensitive characters. The CLI receives the pointer text directly; URI fragment forms such as `#/data`, percent decoding and wildcard selectors are outside this syntax.

Array indices use ASCII decimal digits without leading zeros: `0`, `1`, `2` and so on. `-` selects no existing array element and fails. In an object, a segment such as `01` or `-` can match that exact member name. Member names compare by Unicode code points without normalization.

## Failure and comparison contract

- Invalid pointer syntax is a configuration error: exit `2`, before launching the target.
- A pointer must resolve in every output, including both baseline runs. An absent member, out-of-range index or traversal through a scalar sets the case status to `missing-pointer` and exits `1`.
- An existing JSON `null`, `false`, empty array or empty object is a value and can be selected.
- Nondeterminism within the selected value still produces `unstable-baseline` and stops after the two baseline invocations.
- Output is parsed and validated in full before selection. Invalid JSON, duplicate members or nonstandard numeric constants elsewhere in the output still fail.
- Array order remains significant; object member order does not. Numbers retain decimal precision. Numeric `1` and `1.0` compare equal; boolean `true` and numeric `1` differ.
- Timeouts, nonzero target exits and input/output byte limits apply to the complete invocation.

Choose the narrowest subtree that covers the result you need to check. This makes fields outside the selection deliberately irrelevant to the presentation comparison; it does not change the target's output.

## Machine-readable reports

Reports keep `schema_version: 1`. Using the option adds `comparison_pointer` with the supplied pointer. Without the option, the field is omitted and the whole-output report retains its existing shape.

Difference pointers always identify a location in the complete stdout document. If `/data` is selected and its `count` changes, the report uses `/data/count`. If the selected scalar itself changes, it uses `/data`. A missing selection has `difference: {"pointer": "/data", "kind": "missing"}`.

Input and stdout hashes, byte counts, durations and exit codes describe the complete invocation. Two stdout hashes may differ while the selected results match. Reports contain locations and hashes rather than output values.

## Python API

```python
from json_repr_probe.runner import probe

report = probe(
    b'{"z": 1, "a": 2}',
    ["python", "-m", "your_package"],
    compare_pointer="/data",
)
assert report["status"] == "passed", report
```

Omit `compare_pointer` or pass `None` for the existing whole-output comparison. Pass `""` to select the root explicitly.
