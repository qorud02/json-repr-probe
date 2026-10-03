# JSON Repr Probe

Find CLI bugs that appear when the same JSON value is written differently.

`json-repr-probe` sends one fixture to your command using different object member orders, whitespace, line endings and Unicode escapes. It compares the command's JSON results and reports the first changed field as a JSON Pointer.

Use it for a CLI whose contract depends on parsed JSON values. Each invocation reads one JSON document from stdin and writes one JSON document to stdout.

## Try it

Python 3.10 or newer. Clone and run; the probe has no runtime dependencies.

```sh
git clone https://github.com/qorud02/json-repr-probe.git
cd json-repr-probe
python -m json_repr_probe --input examples/input.json -- python -m examples.stable_cli
```

On systems where Python is named `python3`, replace both occurrences of `python` with `python3`. The commands also work in Windows PowerShell.

The independent example selects a message, counts array items and sorts the input's keys. All presentations produce the same result; the probe exits **0**.

Now try a deliberately broken command that chooses the first object member:

```sh
python -m json_repr_probe --input examples/input.json -- python -m examples.order_sensitive_cli
```

The result includes:

```text
JSON presentation probe: failed
  original: passed
  baseline-repeat: passed
  compact: passed
  reversed-keys: different-output at "/selected" (value)
  sorted-keys: different-output at "/selected" (value)
```

That command exits **1**. See the captured [passing report](examples/passing-report.json) and [failing report](examples/failing-report.json).

## Test your command

```sh
python -m json_repr_probe --input fixture.json --timeout 5 -- node transform.mjs
python -m json_repr_probe --input fixture.json --format json -- ./your-program
```

Arguments after `--` go directly to the executable. Shell expansion and shell operators are disabled. If your executable is in another directory, pass `--cwd path/to/project`; the input fixture is read relative to your current directory. A script argument after `--` is resolved by the target from its working directory.

For an installed entry point, run `python -m pip install .`, then use `json-repr-probe` in place of `python -m json_repr_probe`. Installation uses setuptools; clone-and-run and tests use the Python standard library.

The original fixture runs twice before the other cases. If those results differ, the report says `unstable-baseline` and stops. This makes a changing timestamp or random result visible before attributing a difference to JSON formatting.

## Compare a result inside an envelope

A command may return stable data together with a new request ID or timing value on each invocation. Use `--compare-pointer /data` to compare the result at `data`. The commands below run the checked-out source:

```sh
python -m json_repr_probe --input examples/input.json --compare-pointer /data -- python -m examples.metadata_cli
```

This example returns a new `request_id` and an unchanged `data` value. Selecting `/data` passes with exit `0`; omitting the option reports `unstable-baseline` at `/request_id`.

Turn on the example's first-member bug:

```sh
python -m json_repr_probe --input examples/input.json --compare-pointer /data -- python -m examples.metadata_cli --first-key
```

It fails with exit `1` at `/data/selected`. A missing `data` field also fails. Selection never substitutes a default value or skips a case.

See the [output selection guide](docs/output-selection.md) for a CI step, escaped field names, array elements and the report contract.

Distinct presentations are generated deterministically:

| Presentation | What changes |
| --- | --- |
| Compact | Structural whitespace |
| Reversed / sorted keys | Object member order, including nested objects |
| Pretty LF / CRLF | Indentation and document line endings |
| Escaped Unicode | UTF-8 characters represented with JSON Unicode escapes |
| Escaped slashes | `/` represented as `\/` in strings |
| Padded whitespace | Legal JSON whitespace before and after the document |

Duplicate byte sequences are omitted. Arrays retain their order. String contents, including normalization forms and embedded line breaks, retain their value. Numbers are parsed and written with decimal precision rather than a conversion to binary floating point.

## Results and CI

| Exit | Meaning |
| --- | --- |
| `0` | All tested results match the stable baseline |
| `1` | A changed result, unstable baseline, timeout, target error or invalid target JSON |
| `2` | Invalid fixture/options, unreadable input or target launch failure |

Object member order is ignored in output comparison. Array order matters. Numeric values such as `1` and `1.0` compare equal; `true` and `1` differ. JSON Pointer uses the standard `~0` and `~1` escapes, with the empty string identifying the root.

Machine-readable reports include case names, input/output hashes, byte counts, exit codes, durations and difference locations. They omit command arguments, stdout/stderr contents and input/output values. Field names can appear in difference pointers. JSON quoting keeps control characters escaped in terminal reports.

Keep target diagnostics on stderr. A log line mixed into stdout fails JSON parsing. The default limits are 10 seconds per invocation and 1 MiB per input, stdout and stderr. Use `--timeout` and `--max-bytes` to adjust them. A generated presentation that exceeds the input limit fails before any target runs. Capture sizes are polled while the target runs and checked again after it exits.

Example CI step:

```yaml
- run: python -m json_repr_probe --input tests/fixtures/request.json -- python -m your_package
```

The repository's [test workflow](.github/workflows/tests.yml) covers Python 3.10, 3.12 and 3.14 on Windows and Linux.

## Choosing a fixture

Use several keys, a nested object, a slash and a non-ASCII string to exercise the available presentations. The included fixture is synthetic. Add fixtures for your actual contract and invoke the probe separately for each one.

The probe measures presentation invariance against your command's own baseline. Validate expected business results with your normal tests. Commands that intentionally report original bytes or member order should have a different test contract. Duplicate object members, nonstandard numeric constants, unpaired Unicode surrogates, invalid UTF-8 and nesting beyond 128 levels are rejected to keep the comparison unambiguous. Numbers must fit Python Decimal's range; `1e400` is supported.

Run a trusted, single-process target in a disposable working directory when it writes files. The probe executes the command for each case with its ordinary local permissions and environment. A timeout kills the process group on POSIX and the direct target process on Windows. Identical results from two baseline runs are a control; they cannot detect every source of nondeterminism.

## Related tools and specification

- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) describes JSON objects as unordered, arrays as ordered, insignificant structural whitespace and equivalent character escapes.
- [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901) defines the JSON Pointer strings used to select an output value and locate differences.
- [jq](https://jqlang.org/manual/) provides filters for extracting and transforming JSON. Output selection here applies directly to every target invocation while retaining full-output parsing, exit-status and capture checks.
- [JSONTestSuite](https://github.com/nst/JSONTestSuite) supplies a corpus for JSON parser acceptance and rejection. This probe checks an application's behavior across equivalent valid representations of one fixture.
- [Hypothesis](https://hypothesis.readthedocs.io/en/latest/) generates test data for property tests. This probe offers a fixed set of presentations and a command boundary you can use without embedding a testing framework in the target.

## Contribute

Run `python -m unittest discover -s tests -v`. The [contributor guide](CONTRIBUTING.md) describes useful changes and regression requirements.

MIT license.

## Container and wheel

The Linux amd64 container packages Python and the probe together. From this repository directory:

```sh
docker run --rm --mount "type=bind,source=${PWD},target=/work,readonly" ghcr.io/qorud02/json-repr-probe:0.1.0 --input /work/examples/input.json -- python -m examples.stable_cli
```

Windows PowerShell uses Docker Desktop with Linux containers and the same command. The stable example exits `0`. Replace `examples.stable_cli` with `examples.order_sensitive_cli` to see a changed `/selected` result and exit `1`.

To check a trusted Python target in your current directory:

```sh
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=16m --mount "type=bind,source=${PWD},target=/work,readonly" ghcr.io/qorud02/json-repr-probe:0.1.0 --input /work/fixture.json -- python /work/transform.py
```

The target receives each JSON presentation on stdin. The image runs as UID `10001` and includes Python 3.12 plus the probe. Use the wheel on your host, or a derived image, for targets needing other runtimes or libraries. Keep target files readable by the container user; the mounted directory is read-only.

Download `json_repr_probe-0.1.0-py3-none-any.whl` and `SHA256SUMS` from the [release](https://github.com/qorud02/json-repr-probe/releases/tag/v0.1.0), then install:

```sh
python -m pip install ./json_repr_probe-0.1.0-py3-none-any.whl
json-repr-probe --version
```

The wheel requires Python 3.10 or newer and has no runtime dependencies. Versioned container tags and release checksums identify the distributed artifacts. The [package workflow](.github/workflows/package.yml) builds and tests a container before pushing it, and produces a checked wheel with a checksum file.
