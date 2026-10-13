import json
from pathlib import Path
import tempfile
import unittest

from summarize_scores import summarize


class ScoreSummaryTest(unittest.TestCase):
    def test_invalid_case_set_is_explicitly_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "evals/11"
            packet = run / "judge"
            packet.mkdir(parents=True)
            (run / "metadata.json").write_text(json.dumps({
                "scorers": ["judge"], "status": "invalid_case_set",
                "exclusion_reason": "Independent audit found contradictory checks.",
            }))
            (packet / "request.json").write_text(json.dumps({
                "rubric": "fixed", "items": [dict(id="case", request="r", input="i", checks=[], output="o")]
            }))
            (packet / "response.json").write_text(json.dumps({
                "scores": [dict(id="case", values=[1] * 6)]
            }))
            report = summarize(root)
            self.assertEqual(report["counts"], {"pass": 0, "fail": 0, "disputed": 0})
            self.assertEqual(report["groups"], [])
            self.assertEqual(report["excluded_rounds"], [{
                "round": "evals/11", "reason": "Independent audit found contradictory checks."
            }])

    def test_optional_draft_presence_and_content_separate_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "evals/01"
            packet = run / "abc"
            packet.mkdir(parents=True)
            (run / "metadata.json").write_text(json.dumps({"scorers": ["abc"]}))
            items = [dict(id=str(n), request="r", input="i", checks=[], output="o")
                     for n in range(4)]
            items[1]["draft"] = ""
            items[2]["draft"] = "first"
            items[3]["draft"] = "second"
            scores = [dict(id=item["id"], values=[1] * 6) for item in items]
            (packet / "request.json").write_text(json.dumps(dict(rubric="fixed", items=items)))
            (packet / "response.json").write_text(json.dumps(dict(scores=scores)))
            report = summarize(root)
            self.assertEqual(report["counts"], {"pass": 4, "fail": 0, "disputed": 0})

    def test_real_identical_output_is_disputed(self):
        report = summarize(Path(__file__).resolve().parents[1])
        matches = [group for group in report["groups"]
                   if any(row["packet"] == "evals/05/e98" and row["id"] == "4db-02-Z"
                          for row in group["observations"])]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["critical_status"], "disputed")
        self.assertIn(2, matches[0]["different_criteria"])
        self.assertTrue(any(row["packet"] == "evals/05/88f" and row["id"] == "4db-02-X"
                            for row in matches[0]["observations"]))

    def test_material_boundaries_and_noncritical_disagreement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "evals/01"
            packet = run / "abc"
            packet.mkdir(parents=True)
            (run / "metadata.json").write_text(json.dumps({"scorers": ["abc"]}))
            items, scores = [], []
            for n, (output, checks, values) in enumerate([
                ("a", ["x"], [1] * 6),
                ("a", ["x"], [1, 1, 1, 1, .5, 1]),
                ("a", ["y"], [0, 1, 1, 1, 1, 1]),
                ("b", ["x"], [0, 1, 1, 1, 1, 1]),
            ]):
                items.append(dict(id=str(n), request="r", input="i", checks=checks, output=output))
                scores.append(dict(id=str(n), values=values))
            (packet / "request.json").write_text(json.dumps(dict(rubric="fixed", items=items)))
            (packet / "response.json").write_text(json.dumps(dict(scores=scores)))
            report = summarize(root)
            self.assertEqual(report["counts"], {"pass": 1, "fail": 2, "disputed": 0})
            passing = next(group for group in report["groups"] if group["critical_status"] == "pass")
            self.assertEqual(passing["different_criteria"], [5])


if __name__ == "__main__":
    unittest.main()
