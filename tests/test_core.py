from decimal import Decimal
import json
import unittest

from json_repr_probe.core import ProbeError, first_difference, make_cases, parse_json, render_json


class ExactJsonTests(unittest.TestCase):
    def test_large_integer_preserved(self):
        number = "90071992547409931234567890123456789"
        self.assertEqual(render_json(parse_json(number)), number)

    def test_decimal_precision_preserved(self):
        number = "0.12345678901234567890123456789"
        self.assertEqual(render_json(parse_json(number)), number)

    def test_extreme_exponent_preserved(self):
        self.assertEqual(parse_json(render_json(parse_json("1e400"))), Decimal("1e400"))

    def test_decimal_range_error_is_reported_cleanly(self):
        with self.assertRaises(ProbeError):
            parse_json("1e999999999999999999999999999999")

    def test_duplicate_members_rejected(self):
        with self.assertRaisesRegex(ProbeError, "duplicate"):
            parse_json('{"a": 1, "a": 2}')

    def test_escaped_duplicate_members_rejected(self):
        with self.assertRaisesRegex(ProbeError, "duplicate"):
            parse_json('{"a": 1, "\\u0061": 2}')

    def test_nonstandard_constants_rejected(self):
        for text in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(text=text), self.assertRaises(ProbeError):
                parse_json(text)

    def test_invalid_utf8_rejected(self):
        with self.assertRaises(ProbeError):
            parse_json(b'"\xff"')

    def test_unpaired_surrogates_rejected_in_keys_and_values(self):
        for text in ('"\\ud800"', '{"\\udfff": 1}'):
            with self.subTest(text=text), self.assertRaisesRegex(ProbeError, "surrogate"):
                parse_json(text)

    def test_valid_surrogate_pair(self):
        self.assertEqual(parse_json('"\\ud83e\\uddea"'), "🧪")

    def test_deep_nesting_rejected_cleanly(self):
        with self.assertRaises(ProbeError):
            parse_json("[" * 140 + "0" + "]" * 140)

    def test_trailing_document_rejected(self):
        with self.assertRaises(ProbeError):
            parse_json("{} {}")

    def test_all_presentations_preserve_value(self):
        payload = '{"z":"안녕 / 🧪 \\n","a":{"y":2,"x":1},"list":[true,null,1e400,0.123456789012345678901]}\n'.encode()
        expected = parse_json(payload)
        cases = make_cases(payload)
        self.assertGreaterEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case.name):
                self.assertIsNone(first_difference(expected, parse_json(case.payload)))

    def test_variants_deterministic_and_deduplicated(self):
        first = make_cases(b'{"z":1,"a":2}')
        self.assertEqual(first, make_cases(b'{"z":1,"a":2}'))
        self.assertEqual(len(first), len({case.payload for case in first}))

    def test_nested_key_order_reversed_array_order_preserved(self):
        value = parse_json('{"z": [{"y": 2, "x": 1}, "last"], "a": 3}')
        text = render_json(value, key_order="reversed")
        self.assertEqual(list(json.loads(text)), ["a", "z"])
        self.assertEqual(list(json.loads(text)["z"][0]), ["x", "y"])
        self.assertEqual(json.loads(text)["z"][1], "last")

    def test_crlf_variant_leaves_string_escape_intact(self):
        cases = {case.name: case.payload for case in make_cases(b'{"a":"line\\nnext"}')}
        self.assertIn(b"\r\n", cases["pretty-crlf"])
        self.assertEqual(parse_json(cases["pretty-crlf"])["a"], "line\nnext")

    def test_primitive_json_inputs(self):
        for text in ("null", "true", "1", '"hello"', "[]", "{}"):
            with self.subTest(text=text):
                for case in make_cases(text.encode()):
                    self.assertIsNone(first_difference(parse_json(text), parse_json(case.payload)))

    def test_unicode_normalization_is_preserved(self):
        self.assertIsNotNone(first_difference(parse_json('"é"'), parse_json('"é"')))


class ComparisonTests(unittest.TestCase):
    def test_object_key_order_ignored(self):
        self.assertIsNone(first_difference(parse_json('{"a":1,"b":2}'), parse_json('{"b":2,"a":1}')))

    def test_decimal_lexical_forms_equal(self):
        self.assertIsNone(first_difference(parse_json("1"), parse_json("1.0e0")))

    def test_boolean_is_not_numeric_one(self):
        self.assertEqual(first_difference(True, Decimal(1)), {"pointer": "", "kind": "type"})

    def test_array_order_is_significant(self):
        self.assertEqual(first_difference([1, 2], [2, 1]), {"pointer": "/0", "kind": "value"})

    def test_pointer_escape(self):
        self.assertEqual(first_difference({"a/b~c": 1}, {"a/b~c": 2}),
                         {"pointer": "/a~1b~0c", "kind": "value"})

    def test_member_missing(self):
        self.assertEqual(first_difference({"a": None}, {}), {"pointer": "/a", "kind": "member"})

    def test_array_length(self):
        self.assertEqual(first_difference([0], [0, 1]), {"pointer": "/1", "kind": "length"})

    def test_empty_key_pointer(self):
        self.assertEqual(first_difference({"": 1}, {"": 2}), {"pointer": "/", "kind": "value"})

    def test_precision_difference_detected(self):
        self.assertIsNotNone(first_difference(parse_json("9007199254740993"), parse_json("9007199254740992")))


if __name__ == "__main__":
    unittest.main()
