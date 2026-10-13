import json
from pathlib import Path
import unittest


class InterfaceTest(unittest.TestCase):
    root = Path(__file__).resolve().parents[1] / 'evals/06/interface'

    def test_distributed_skill_matches_executed_fixture(self):
        repo = Path(__file__).resolve().parents[1]
        fixture = repo / 'evals/11/interface/r24x/request.json'
        if not fixture.exists():
            fixture = repo / 'evals/07/interface/de86/request.json'
        if not fixture.exists():
            fixture = repo / 'evals/06/interface/cd75/request.json'
        request = json.loads(fixture.read_text())
        self.assertEqual((repo / 'skills/yomiyasu-verify/SKILL.md').read_text(), request['skill'])

    def test_single_input_extension_preserves_batch_contract(self):
        root = Path(__file__).resolve().parents[1] / 'evals/09/interface'
        for name in ('u91x', 'v02x'):
            cases = json.loads((root / name / 'request.json').read_text())['cases']
            result = json.loads((root / name / 'response.txt').read_text())
            self.assertEqual(set(result), {'outputs'})
            self.assertEqual([row['id'] for row in result['outputs']], [case['id'] for case in cases])
            for case, row in zip(cases, result['outputs']):
                self.assertEqual(set(row), {'id', 'text'})
                if case['id'] == 'm-5':
                    self.assertEqual(json.loads(row['text']), json.loads(case['input']))
                else:
                    self.assertEqual(row['text'], case['input'])

    def test_final_contract_includes_single_element_arrays(self):
        repo = Path(__file__).resolve().parents[1]
        for name in ('q13x', 'r24x'):
            root = repo / 'evals/11/interface' / name
            packet = json.loads((root / 'request.json').read_text())
            self.assertEqual(packet['skill'], (repo / 'skills/yomiyasu-verify/SKILL.md').read_text())
            result = json.loads((root / 'response.txt').read_text())
            self.assertEqual(set(result), {'outputs'})
            self.assertEqual([row['id'] for row in result['outputs']], [case['id'] for case in packet['cases']])
            for case, row in zip(packet['cases'], result['outputs']):
                self.assertEqual(set(row), {'id', 'text'})
                if case['id'] == 'm-5':
                    self.assertEqual(json.loads(row['text']), json.loads(case['input']))
                else:
                    self.assertEqual(row['text'], case['input'])

    def test_previous_response_has_no_json_mapping(self):
        with self.assertRaises(json.JSONDecodeError):
            json.loads((self.root / 'bc64/response.txt').read_text())

    def test_fixed_response_maps_every_case_and_preserves_content(self):
        cases = json.loads((self.root / 'cd75/request.json').read_text())['cases']
        result = json.loads((self.root / 'cd75/response.txt').read_text())
        self.assertEqual(set(result), {'outputs'})
        self.assertEqual([row['id'] for row in result['outputs']], [row['id'] for row in cases])
        for case, row in zip(cases, result['outputs']):
            self.assertEqual(set(row), {'id', 'text'})
            if case['id'] == 'm-5':
                self.assertEqual(json.loads(row['text']), json.loads(case['input']))
            else:
                self.assertEqual(row['text'], case['input'])


if __name__ == '__main__':
    unittest.main()
