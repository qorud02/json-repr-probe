from decimal import Decimal
import unittest

from json_repr_probe.core import ProbeError, parse_json
from json_repr_probe.pointer import PointerMissing, pointer_tokens, resolve_pointer


def selected(value, pointer):
    return resolve_pointer(value, pointer_tokens(pointer))


class PointerTests(unittest.TestCase):
    def test_rfc_document_examples(self):
        value = {"foo": ["bar", "baz"], "": 0, "a/b": 1, "c%d": 2,
                 "e^f": 3, "g|h": 4, "i\\j": 5, 'k"l': 6, " ": 7, "m~n": 8}
        examples = {"": value, "/foo": ["bar", "baz"], "/foo/0": "bar",
                    "/": 0, "/a~1b": 1, "/c%d": 2, "/e^f": 3, "/g|h": 4,
                    "/i\\j": 5, '/k"l': 6, "/ ": 7, "/m~0n": 8}
        for pointer, expected in examples.items():
            with self.subTest(pointer=pointer):
                self.assertEqual(selected(value, pointer), expected)

    def test_escape_decoding_order(self):
        self.assertEqual(selected({"~1": 1, "/": 2}, "/~01"), 1)
        self.assertEqual(selected({"~1": 1, "/": 2}, "/~1"), 2)

    def test_nested_empty_and_escaped_names(self):
        self.assertEqual(selected({"": {"a/b~c": [None, {"": False}]}},
                                  "//a~1b~0c/1/"), False)

    def test_numeric_object_names_are_not_array_indices(self):
        value = {"01": "zero-one", "-": "dash", "+1": "plus-one"}
        for key, expected in value.items():
            with self.subTest(key=key):
                self.assertEqual(selected(value, "/" + key), expected)

    def test_array_indices_are_ascii_and_canonical(self):
        self.assertEqual(selected(["first", "second"], "/1"), "second")
        for token in ("01", "+1", "-1", "1.0", "-", "", "١", "１", " 1"):
            with self.subTest(token=token), self.assertRaises(PointerMissing):
                selected(["first", "second"], "/" + token)

    def test_array_index_bounds(self):
        for array, pointer in (([], "/0"), ([1], "/1"), ([1], "/" + "9" * 5000)):
            with self.subTest(length=len(array)), self.assertRaises(PointerMissing):
                selected(array, pointer)

    def test_syntax_is_checked_before_resolution(self):
        for pointer in ("data", "#/data", "#", "/~", "/~2", "/a~x", None, 3):
            with self.subTest(pointer=pointer), self.assertRaises(ProbeError):
                pointer_tokens(pointer)

    def test_unicode_surrogate_rejected(self):
        with self.assertRaises(ProbeError):
            pointer_tokens("/\ud800")

    def test_missing_member_and_scalar_traversal(self):
        for value, pointer in (({}, "/missing"), ({"a": None}, "/a/b"),
                               ({"a": 1}, "/a/b"), ([], "/missing")):
            with self.subTest(pointer=pointer), self.assertRaises(PointerMissing):
                selected(value, pointer)

    def test_null_and_false_are_existing_values(self):
        value = {"a": None, "b": False, "c": [], "d": {}}
        self.assertIsNone(selected(value, "/a"))
        self.assertIs(selected(value, "/b"), False)
        self.assertEqual(selected(value, "/c"), [])
        self.assertEqual(selected(value, "/d"), {})

    def test_exact_numbers_are_preserved(self):
        number = "9007199254740993123456789.123456789"
        self.assertEqual(selected(parse_json('{"data":' + number + '}'), "/data"),
                         Decimal(number))

    def test_unicode_names_do_not_normalize(self):
        value = {"é": 1, "é": 2, "\x00": 3}
        self.assertEqual(selected(value, "/é"), 1)
        self.assertEqual(selected(value, "/é"), 2)
        self.assertEqual(selected(value, "/\x00"), 3)


if __name__ == "__main__":
    unittest.main()
