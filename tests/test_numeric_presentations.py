"""Equivalent number spellings retain exact values without exponent expansion."""
from decimal import Decimal, MAX_EMAX, MIN_ETINY, localcontext
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from json_repr_probe.core import ProbeError, first_difference, make_cases, parse_json, render_json
from json_repr_probe.runner import probe


ROOT = Path(__file__).resolve().parents[1]
NUMERIC_CASES = {"numbers-exponent", "numbers-normalized"}
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")


def numeric_cases(payload):
    return {case.name: case.payload for case in make_cases(payload)
            if case.name in NUMERIC_CASES}


class NumericPresentationTests(unittest.TestCase):
    def assert_equivalent(self, payload):
        expected = parse_json(payload)
        cases = make_cases(payload)
        for case in cases:
            actual = parse_json(case.payload)
            with self.subTest(payload=payload, case=case.name):
                self.assertIsNone(first_difference(expected, actual))
                if isinstance(expected, Decimal):
                    self.assertRegex(case.payload.strip().decode(), NUMBER)
                    self.assertEqual(expected.is_signed(), actual.is_signed())
        self.assertEqual(len(cases), len({case.payload for case in cases}))
        self.assertEqual(cases, make_cases(payload))
        return cases

    def test_number_style_is_explicit_and_validated(self):
        self.assertEqual(render_json(Decimal("1.0")), "1.0")
        self.assertEqual(render_json(Decimal("1.0"), number_style="exponent"), "10e-1")
        self.assertEqual(render_json(Decimal("1.0"), number_style="normalized"), "1")
        self.assertEqual(render_json([True, 1], number_style="exponent"), "[true,1e0]")
        with self.assertRaisesRegex(ProbeError, "number presentation"):
            render_json(Decimal(1), number_style="unsupported")
        for number in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(number=number), self.assertRaises(ProbeError):
                render_json(number, number_style="exponent")

    def test_exponent_style_preserves_complete_decimal_tuple(self):
        for text in ('12.300', '-0.00', '1e400', '1e-400', f'1e{MIN_ETINY}'):
            with self.subTest(text=text):
                number = parse_json(text)
                output = render_json(number, number_style="exponent")
                self.assertEqual(number.as_tuple(), parse_json(output).as_tuple())

    def test_normalized_equal_length_tie_uses_plain_spelling(self):
        self.assertEqual(render_json(Decimal('100'), number_style='normalized'), '100')
        self.assertEqual(render_json(Decimal('1000'), number_style='normalized'), '1e3')
        self.assertEqual(render_json(Decimal('0.01'), number_style='normalized'), '0.01')
        self.assertEqual(render_json(Decimal('0.001'), number_style='normalized'), '1e-3')

    def test_integer_gets_an_explicit_exponent(self):
        self.assertEqual(numeric_cases(b'{"amount":1}')["numbers-exponent"], b'{"amount":1e0}')

    def test_fractional_integer_gets_a_plain_integer(self):
        self.assertEqual(numeric_cases(b'{"amount":1.0}')["numbers-normalized"], b'{"amount":1}')

    def test_exponent_keeps_all_coefficient_digits(self):
        self.assertEqual(numeric_cases(b'12.300')["numbers-exponent"], b'12300e-3')

    def test_normalized_spelling_removes_trailing_zeroes(self):
        self.assertEqual(numeric_cases(b'12.300')["numbers-normalized"], b'12.3')

    def test_signed_zero_is_preserved(self):
        for text in ('0', '-0', '0.0000', '-0.0000', '0e400', '-0e-400'):
            with self.subTest(text=text):
                self.assert_equivalent(text.encode())
        self.assertEqual(numeric_cases(b'-0.000')["numbers-normalized"], b'-0')
        self.assertEqual(numeric_cases(b'-0')["numbers-exponent"], b'-0e0')

    def test_exact_long_numbers_never_use_float(self):
        for text in (
            '90071992547409931234567890123456789',
            '-90071992547409931234567890123456789',
            '0.123456789012345678901234567890123456789',
            '-0.000000000000000000000000000000000000001',
            '12345678901234567890.1234567890123456789000',
            '1e400', '-1e-400', '1000000000000000000000000000000.000',
        ):
            with self.subTest(text=text):
                self.assert_equivalent(text.encode())

    def test_extreme_decimal_exponents_remain_parseable(self):
        for exponent in (MAX_EMAX, MIN_ETINY):
            for coefficient in ('1', '-1', '0', '-0'):
                payload = f'{coefficient}e{exponent}'.encode()
                with self.subTest(payload=payload):
                    cases = self.assert_equivalent(payload)
                    self.assertLess(max(len(case.payload) for case in cases), 100)
        for payload in (
            f'1.00e{MAX_EMAX}'.encode(),
            f'100e{MIN_ETINY}'.encode(),
            f'-0.00e{MAX_EMAX}'.encode(),
        ):
            with self.subTest(payload=payload):
                self.assert_equivalent(payload)

    def test_hostile_decimal_context_does_not_round_or_signal(self):
        payload = b'[12345678901234567890.123456789000, 1e400, -0.00, 1e-400]'
        ordinary = make_cases(payload)
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            self.assertEqual(make_cases(payload), ordinary)
            self.assertFalse(any(context.flags.values()))

    def test_numeric_strings_and_keys_are_not_rewritten(self):
        payload = b'{"1.00e2":["1.00e2", "-0", true, false, null, {"n":1.0}]}'
        self.assert_equivalent(payload)
        cases = numeric_cases(payload)
        self.assertEqual(len(cases), 2)
        for body in cases.values():
            data = json.loads(body)
            self.assertEqual(list(data), ['1.00e2'])
            self.assertEqual(data['1.00e2'][:5], ['1.00e2', '-0', True, False, None])

    def test_inputs_without_numbers_gain_no_extra_invocations(self):
        for payload in (b'null', b'true', b'false', b'"1.0"', b'{}', b'[]', b'{"1e0":[true,"12"]}'):
            with self.subTest(payload=payload):
                self.assertEqual(numeric_cases(payload), {})

    def test_shortest_form_does_not_expand_large_exponents(self):
        for payload in (b'1e100000000', b'1e-100000000', b'-0e100000000'):
            with self.subTest(payload=payload):
                cases = self.assert_equivalent(payload)
                self.assertLess(max(len(case.payload) for case in cases), 80)

    def test_randomized_numbers_preserve_value_and_sign(self):
        rng = random.Random(20261004)
        for _ in range(200):
            digits = str(rng.randint(1, 9)) + ''.join(str(rng.randrange(10)) for _ in range(rng.randrange(0, 80)))
            split = rng.randrange(1, len(digits) + 1)
            mantissa = digits[:split] + ('.' + digits[split:] if split < len(digits) else '')
            sign = '-' if rng.randrange(2) else ''
            exponent = rng.randint(-500, 500)
            payload = f'{sign}{mantissa}e{exponent}'.encode()
            self.assert_equivalent(payload)

    def test_long_coefficient_does_not_use_python_integer_conversion(self):
        payload = ('9' * 5000 + '.000').encode()
        cases = self.assert_equivalent(payload)
        self.assertIn('numbers-exponent', {case.name for case in cases})
        self.assertIn('numbers-normalized', {case.name for case in cases})

    def test_new_numeric_case_over_limit_fails_before_target_runs(self):
        payload = b'[' + b','.join([b'1.' + b'1' * 1000] * 16) + b']'
        # Exponents on long fractional coefficients add more bytes than indentation.
        maximum = max(len(case.payload) for case in make_cases(payload)
                      if case.name not in NUMERIC_CASES)
        with patch('json_repr_probe.runner.run_case', return_value=({'status': 'passed'}, None)) as run:
            with self.assertRaises(ProbeError):
                probe(payload, [sys.executable, '-c', "print('null')"], max_bytes=maximum)
        run.assert_not_called()


class NumericTargetTests(unittest.TestCase):
    def target(self, code):
        return [sys.executable, '-c', code]

    def test_native_integer_type_dependency_is_caught(self):
        command = self.target('import json,sys; value=json.load(sys.stdin); print(json.dumps({"whole":isinstance(value["amount"],int)}))')
        for payload in (b'{"amount":1}', b'{"amount":1.0}'):
            with self.subTest(payload=payload):
                report = probe(payload, command)
                self.assertEqual(report['status'], 'failed')
                changed = [case for case in report['cases'] if case['status'] == 'different-output']
                self.assertTrue(changed)
                self.assertTrue(all(case['name'] in NUMERIC_CASES for case in changed))
                self.assertTrue(all(case['difference'] == {'pointer':'/whole','kind':'value'} for case in changed))

    def test_exact_independent_numeric_target_passes(self):
        command = self.target('from decimal import Decimal; import json,sys; value=json.load(sys.stdin,parse_int=Decimal,parse_float=Decimal); number=value["amount"]; print(json.dumps({"whole":number==number.to_integral_value()}))')
        for payload in (b'{"amount":1}', b'{"amount":1.0}', b'{"amount":1.25}', b'{"amount":9007199254740993}'):
            with self.subTest(payload=payload):
                self.assertEqual(probe(payload, command)['status'], 'passed')

    def test_native_float_roundtrip_exposes_large_integer_rounding(self):
        command = self.target('import json,sys; print(json.dumps(json.load(sys.stdin)))')
        report = probe(b'{"value":9007199254740993}', command)
        self.assertEqual(report['status'], 'failed')
        changed = [case for case in report['cases'] if case['status'] == 'different-output']
        self.assertEqual([case['name'] for case in changed], ['numbers-exponent'])
        self.assertEqual(changed[0]['difference'], {'pointer':'/value','kind':'value'})

    def test_selected_numeric_result_uses_absolute_difference_pointer(self):
        command = self.target('import json,sys; value=json.load(sys.stdin); print(json.dumps({"data":{"whole":isinstance(value["amount"],int)}}))')
        report = probe(b'{"amount":1}', command, compare_pointer='/data')
        self.assertEqual(report['status'], 'failed')
        changed = [case for case in report['cases'] if case['status'] == 'different-output']
        self.assertTrue(changed)
        self.assertTrue(all(case['difference']['pointer'] == '/data/whole' for case in changed))

    def test_documented_examples_have_expected_exit_codes(self):
        for name, expected in (("numeric_value_cli", 0), ("numeric_type_cli", 1)):
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, '-m', 'json_repr_probe', '--input',
                     'examples/numeric-input.json', '--format', 'json', '--',
                     sys.executable, '-m', 'examples.' + name],
                    cwd=ROOT, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'passed' if expected == 0 else 'failed')
                self.assertTrue(any(case['name'] == 'numbers-exponent' for case in report['cases']))

    def test_cli_reports_numeric_change_with_existing_exit_and_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'number.json'
            fixture.write_text('{"amount":1}', encoding='utf-8')
            command = self.target('import json,sys; print(json.dumps({"whole":isinstance(json.load(sys.stdin)["amount"],int)}))')
            result = subprocess.run([sys.executable, '-m', 'json_repr_probe', '--input', str(fixture), '--format', 'json', '--', *command], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('numbers-exponent', [case['name'] for case in report['cases']])
        self.assertNotIn('command', report)


if __name__ == '__main__':
    unittest.main()
