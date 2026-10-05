"""Every decoded number must be finite regardless of the caller's Decimal traps."""
from decimal import Decimal, InvalidOperation, MAX_EMAX, MIN_ETINY, localcontext
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from json_repr_probe.core import ProbeError, make_cases, parse_json
from json_repr_probe.runner import probe


OUTSIDE_RANGE = '1e999999999999999999999999999999'


class FiniteNumberTests(unittest.TestCase):
    def test_unrepresentable_exponents_are_rejected_with_or_without_traps(self):
        for number in (OUTSIDE_RANGE, '-' + OUTSIDE_RANGE,
                       '1e-999999999999999999999999999999',
                       '0e999999999999999999999999999999',
                       '-0e-999999999999999999999999999999'):
            for traps_enabled in (True, False):
                with self.subTest(number=number, traps=traps_enabled), localcontext() as context:
                    context.traps[InvalidOperation] = traps_enabled
                    with self.assertRaises(ProbeError):
                        parse_json(number)

    def test_unrepresentable_number_is_rejected_inside_nested_values(self):
        with localcontext() as context:
            context.traps[InvalidOperation] = False
            for payload in ('[' + OUTSIDE_RANGE + ']', '{"outside":{' + '"number":' + OUTSIDE_RANGE + '}}'):
                with self.subTest(payload=payload), self.assertRaises(ProbeError):
                    parse_json(payload)

    def test_supported_boundaries_and_signed_zero_remain_exact(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[InvalidOperation] = False
            for exponent in (MAX_EMAX, MIN_ETINY, 400, -400):
                for coefficient in ('1', '-1', '0', '-0'):
                    text = f'{coefficient}e{exponent}'
                    with self.subTest(text=text):
                        self.assertEqual(parse_json(text).as_tuple(), Decimal(text).as_tuple())
            self.assertEqual(parse_json('12.3000').as_tuple(), Decimal('12.3000').as_tuple())
            self.assertEqual(parse_json('90071992547409931234567890123456789'), Decimal('90071992547409931234567890123456789'))

    def test_existing_nonstandard_constants_still_fail_without_traps(self):
        with localcontext() as context:
            context.traps[InvalidOperation] = False
            for text in ('NaN', 'Infinity', '-Infinity'):
                with self.subTest(text=text), self.assertRaisesRegex(ProbeError, 'nonstandard'):
                    parse_json(text)

    def test_invalid_fixture_fails_before_any_target_runs(self):
        with localcontext() as context, patch('json_repr_probe.runner.run_case') as run:
            context.traps[InvalidOperation] = False
            with self.assertRaises(ProbeError):
                probe(OUTSIDE_RANGE.encode(), [sys.executable, '-c', "print('{}')"])
        run.assert_not_called()

    def test_full_output_is_checked_before_pointer_selection_without_traps(self):
        body = '{"data":1,"outside":' + OUTSIDE_RANGE + '}'
        command = [sys.executable, '-c', 'print(' + repr(body) + ')']
        with localcontext() as context:
            context.traps[InvalidOperation] = False
            report = probe(b'{}', command, compare_pointer='/data')
        self.assertEqual(report['status'], 'baseline-failed')
        self.assertEqual(len(report['cases']), 1)
        self.assertEqual(report['cases'][0]['status'], 'invalid-json')
        self.assertNotIn(OUTSIDE_RANGE, json.dumps(report))

    def test_invalid_number_in_later_variant_cannot_hide_outside_selection(self):
        command = [sys.executable, '-c',
                   "import sys; raw=sys.stdin.buffer.read(); "
                   "number=" + repr(OUTSIDE_RANGE) + " if raw.startswith(b' \\t') else '0'; "
                   "print('{\"data\":1,\"outside\":'+number+'}')"]
        with localcontext() as context:
            context.traps[InvalidOperation] = False
            report = probe(b'{}', command, compare_pointer='/data')
        self.assertEqual(report['status'], 'failed')
        failed = [case for case in report['cases'] if case['status'] != 'passed']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['name'], 'padded-whitespace')
        self.assertEqual(failed[0]['status'], 'invalid-json')

    def test_invalid_number_in_baseline_repeat_cannot_hide_outside_selection(self):
        command = [sys.executable, '-c',
                   "from pathlib import Path; counter=Path('counter'); "
                   "repeated=counter.exists(); counter.write_text('seen'); "
                   "number=" + repr(OUTSIDE_RANGE) + " if repeated else '0'; "
                   "print('{\"data\":1,\"outside\":'+number+'}')"]
        for pointer in (None, '', '/data'):
            with self.subTest(pointer=pointer), tempfile.TemporaryDirectory() as folder:
                with localcontext() as context:
                    context.traps[InvalidOperation] = False
                    report = probe(b'{}', command, cwd=folder, compare_pointer=pointer)
                self.assertEqual(report['status'], 'baseline-failed')
                self.assertEqual(len(report['cases']), 2)
                self.assertEqual(report['cases'][0]['status'], 'passed')
                self.assertEqual(report['cases'][1]['name'], 'baseline-repeat')
                self.assertEqual(report['cases'][1]['status'], 'invalid-json')
                self.assertNotIn(OUTSIDE_RANGE, json.dumps(report))

    def test_invalid_whole_output_is_not_misclassified_as_unstable(self):
        command = [sys.executable, '-c', 'print(' + repr(OUTSIDE_RANGE) + ')']
        with localcontext() as context:
            context.traps[InvalidOperation] = False
            report = probe(b'{}', command)
        self.assertEqual(report['status'], 'baseline-failed')
        self.assertEqual(report['cases'][0]['status'], 'invalid-json')

    def test_presentations_of_supported_numbers_are_context_independent(self):
        payload = b'{"numbers":[-0.00,1e400,1e-400,0.12345678901234567890123456789]}'
        expected = make_cases(payload)
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[InvalidOperation] = False
            self.assertEqual(make_cases(payload), expected)


if __name__ == '__main__':
    unittest.main()
