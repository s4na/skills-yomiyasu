"""Small synthetic packets, never modifications of archived evaluation records."""
import json
from pathlib import Path
import tempfile
import unittest

from check_records import condition_digest, json_digest
from compare_scores import compare


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "evals" / "test"
        self.run.mkdir(parents=True)
        (self.run.parent / "protocol.md").write_text("## 合否rubric## 比較")
        case = {"id": "case-1", "input": "input", "request": "request",
                "draft": "draft", "checks": ["check"]}
        self.write("development.json", [case])
        metadata = {"executors": ["old", "new"], "scorers": ["j1", "j2"],
                    "aliases": {"A": "old", "B": "new"},
                    "executor_ids": {"old": ["case-1"], "new": ["case-1"]},
                    "executor_condition_sha256": {}, "dispatch_condition_sha256": {},
                    "authored_drafts": ["old", "new"], "scoring_draft": True,
                    "score_ids": {}}
        for source in ("old", "new"):
            request = {"instructions": source, "cases": [case]}
            self.write(f"{source}/request.json", request)
            self.write(f"{source}/response.json", {"outputs": [{"id": "case-1", "text": "output"}]})
            metadata["executor_condition_sha256"][source] = condition_digest(request)
        for judge in metadata["scorers"]:
            items = [{**case, "id": "case-1-" + alias, "output": "output"} for alias in ("A", "B")]
            self.write(f"{judge}/request.json", {"rubric": "rubric", "items": items})
            self.write(f"{judge}/response.json", {"scores": [{"id": item["id"], "values": [1] * 6,
                        "evidence": [{"criterion": i, "input": "input", "output": "output",
                                      "reason": "Synthetic test only"} for i in range(1, 7)]}
                       for item in items]})
            metadata["score_ids"][judge] = [item["id"] for item in items]
        dispatch = [{"task_name": name} for name in ("rold", "rnew", "sj1", "sj2")]
        metadata["dispatch_condition_sha256"] = {item["task_name"]: json_digest(item) for item in dispatch}
        self.write("dispatch.json", dispatch)
        self.write("metadata.json", metadata)

    def write(self, path, value):
        path = self.run / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def read(self, path):
        return json.loads((self.run / path).read_text())

    def score(self, judge, alias, criterion, value):
        path = f"{judge}/response.json"
        response = self.read(path)
        next(row for row in response["scores"] if row["id"] == "case-1-" + alias)["values"][criterion - 1] = value
        self.write(path, response)

    def result(self):
        return compare(self.run, "old", "new")

    def test_published_comparisons_are_reproducible(self):
        repo = Path(__file__).resolve().parents[1]
        for filename, baseline, candidate in (
                ('development.json', 'a13y', 'b24y'),
                ('holdout.json', 'e57y', 'f68y')):
            with self.subTest(filename=filename):
                stored = json.loads((repo / 'reports/14' / filename).read_text())
                self.assertEqual(compare(repo / 'evals/13', baseline, candidate), stored)

    def test_stable_and_unanimous_improvement(self):
        self.assertEqual(self.result()["counts"], {"stable": 6, "improved": 0, "regressed": 0, "mixed": 0})
        for judge in ("j1", "j2"):
            self.score(judge, "A", 6, 0.5)
        result = self.result()
        self.assertTrue(result["candidate_eligible"])
        self.assertEqual(result["critical_all_pass"], {"baseline": True, "candidate": True})
        self.assertEqual(result["counts"]["improved"], 1)
        self.assertEqual(result["cases"][0]["criteria"][5]["observations"], [
            {"judge": judge, "baseline": 0.5, "candidate": 1} for judge in ("j1", "j2")])

    def test_candidate_critical_failure(self):
        self.score("j1", "B", 1, 0.5)
        self.assertFalse(self.result()["candidate_eligible"])

    def test_noncritical_regression_even_with_one_judge(self):
        for criterion in (5, 6):
            with self.subTest(criterion=criterion):
                self.score("j1", "B", criterion, 0.5)
                result = self.result()
                self.assertFalse(result["candidate_eligible"])
                self.assertEqual(result["cases"][0]["criteria"][criterion - 1]["status"], "mixed")
                self.score("j2", "B", criterion, 0.5)
                self.assertEqual(self.result()["cases"][0]["criteria"][criterion - 1]["status"], "regressed")

    def test_mixed_is_not_improvement(self):
        self.score("j1", "A", 6, 0.5)
        self.assertEqual(self.result()["counts"]["improved"], 0)
        self.assertEqual(self.result()["counts"]["mixed"], 1)

    def test_missing_side_is_refused(self):
        for filename, key in (("request.json", "items"), ("response.json", "scores")):
            data = self.read("j2/" + filename)
            data[key].pop()
            self.write("j2/" + filename, data)
        metadata = self.read("metadata.json")
        metadata["score_ids"]["j2"].pop()
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "Incomplete comparison coverage"):
            self.result()

    def test_invalid_set_and_same_condition(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            compare(self.run, "old", "old")
        metadata = self.read("metadata.json")
        metadata["status"] = "invalid_case_set"
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "invalid_case_set"):
            self.result()

    def test_input_difference(self):
        data = self.read("j2/request.json")
        data["items"][1]["input"] = "different"
        self.write("j2/request.json", data)
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            self.result()

    def test_unaliased_single_condition_judge_is_not_silently_omitted(self):
        item = self.read('j1/request.json')['items'][0]
        item['id'] = 'case-1'
        score = self.read('j1/response.json')['scores'][0]
        score['id'] = 'case-1'
        self.write('j3/request.json', {'rubric': 'rubric', 'items': [item]})
        self.write('j3/response.json', {'scores': [score]})
        metadata = self.read('metadata.json')
        metadata['scorers'].append('j3')
        metadata['single_condition_sources'] = {'j3': 'old'}
        metadata['score_ids']['j3'] = ['case-1']
        entry = {'task_name': 'sj3'}
        dispatch = self.read('dispatch.json') + [entry]
        self.write('dispatch.json', dispatch)
        metadata['dispatch_condition_sha256']['sj3'] = json_digest(entry)
        self.write('metadata.json', metadata)
        with self.assertRaisesRegex(ValueError, 'Incomplete comparison coverage: j3'):
            self.result()

    def test_empty_bound_judge_is_not_silently_omitted(self):
        self.test_unaliased_single_condition_judge_is_not_silently_omitted()
        self.write('j3/request.json', {'rubric': 'rubric', 'items': []})
        self.write('j3/response.json', {'scores': []})
        metadata = self.read('metadata.json')
        metadata['score_ids']['j3'] = []
        self.write('metadata.json', metadata)
        with self.assertRaisesRegex(ValueError, 'Incomplete comparison coverage: j3'):
            self.result()

    def test_legacy_single_condition_judge_requires_complete_pair(self):
        repo = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, 'Incomplete comparison coverage: 317'):
            compare(repo / 'evals/03', '8bc', 'df8')

    def test_case_sets_must_match(self):
        metadata = self.read("metadata.json")
        metadata["executor_ids"]["new"] = ["different-case"]
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "same nonempty case sequence"):
            self.result()

    def test_same_cases_in_reverse_order_are_refused(self):
        metadata = self.read("metadata.json")
        metadata["executor_ids"]["old"] = ["case-1", "case-2"]
        metadata["executor_ids"]["new"] = ["case-2", "case-1"]
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "same nonempty case sequence"):
            self.result()

    def test_at_least_two_related_judges(self):
        for filename, key in (("request.json", "items"), ("response.json", "scores")):
            data = self.read("j2/" + filename)
            data[key] = []
            self.write("j2/" + filename, data)
        metadata = self.read("metadata.json")
        metadata["score_ids"]["j2"] = []
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.result()

    def test_identical_execution_conditions_are_refused(self):
        metadata = self.read("metadata.json")
        metadata["executor_condition_sha256"]["new"] = metadata["executor_condition_sha256"]["old"]
        self.write("metadata.json", metadata)
        with self.assertRaisesRegex(ValueError, "identical execution conditions"):
            self.result()


if __name__ == "__main__":
    unittest.main()
