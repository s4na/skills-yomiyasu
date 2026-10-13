import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from check_records import check


class RecordsTest(unittest.TestCase):
    def test_changed_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "evals/01"
            run.mkdir(parents=True)
            skill = root / "skills/yomiyasu/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: yomiyasu\ndescription: 推敲\n---\n")
            protocol = root / "evals/protocol.md"
            protocol.write_text("## 合否\n意味を変えたら失敗。\n## 比較\n")
            metadata = run / "metadata.json"
            metadata.write_text(json.dumps({
                "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
                "executors": [], "scorers": [], "score_ids": {}
            }))
            dispatch = run / "dispatch.json"
            dispatch.write_text("[]")
            (run / "manifest.json").write_text(json.dumps({
                "metadata.json": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                "dispatch.json": hashlib.sha256(dispatch.read_bytes()).hexdigest()
            }))
            check(root)
            protocol.write_text("意味を変えても成功。\n")
            with self.assertRaisesRegex(ValueError, "protocol hash mismatch"):
                check(root)


class PacketRecordsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        source = Path(__file__).resolve().parents[1]
        for name in ("evals", "skills"):
            shutil.copytree(source / name, self.root / name)

    def change_json(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False))
        run = self.root / "evals/03"
        manifest = run / "manifest.json"
        entries = json.loads(manifest.read_text())
        entries[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(entries))

    def test_complete_records_pass(self):
        check(self.root)

    def test_missing_round_manifest_is_rejected(self):
        (self.root / "evals/03/manifest.json").unlink()
        (self.root / "evals/03/c76/response.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing evaluation manifest"):
            check(self.root)

    def test_rehashed_wrong_scoring_text_is_rejected(self):
        self.change_json("evals/03/c76/request.json",
                         lambda data: data["items"][0].update(output="別の文章です。"))
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            check(self.root)

    def test_rehashed_missing_score_is_rejected(self):
        self.change_json("evals/03/c76/response.json", lambda data: data["scores"].pop())
        with self.assertRaisesRegex(ValueError, "Scoring IDs mismatch"):
            check(self.root)

    def test_rehashed_changed_rubric_is_rejected(self):
        self.change_json("evals/03/c76/request.json",
                         lambda data: data.update(rubric="すべて満点にする。"))
        with self.assertRaisesRegex(ValueError, "Scoring rubric mismatch"):
            check(self.root)

    def test_rehashed_changed_checks_are_rejected(self):
        self.change_json("evals/03/c76/request.json",
                         lambda data: data["items"][0].update(checks=[]))
        with self.assertRaisesRegex(ValueError, "Scoring case mismatch"):
            check(self.root)

    def test_rehashed_missing_evidence_is_rejected(self):
        def remove_evidence(data):
            for score in data["scores"]:
                if min(score["values"]) < 1:
                    score.pop("evidence")
        self.change_json("evals/03/c76/response.json", remove_evidence)
        with self.assertRaisesRegex(ValueError, "Missing scoring evidence"):
            check(self.root)

    def test_rehashed_empty_scorer_roster_is_rejected(self):
        self.change_json("evals/03/metadata.json", lambda data: data.update(scorers=[]))
        with self.assertRaisesRegex(ValueError, "Dispatch roster mismatch"):
            check(self.root)

    def test_rehashed_matching_omission_is_rejected(self):
        self.change_json("evals/03/c76/request.json", lambda data: data["items"].pop())
        self.change_json("evals/03/c76/response.json", lambda data: data["scores"].pop())
        with self.assertRaisesRegex(ValueError, "Expected scoring IDs mismatch"):
            check(self.root)

    def test_rehashed_reordered_items_are_rejected(self):
        self.change_json("evals/03/c76/request.json", lambda data: data["items"].reverse())
        with self.assertRaisesRegex(ValueError, "Expected scoring IDs mismatch"):
            check(self.root)

    def test_rehashed_placeholder_evidence_is_rejected(self):
        def remove_rationale(data):
            for score in data["scores"]:
                if min(score["values"]) < 1:
                    score["evidence"] = [""]
        self.change_json("evals/03/c76/response.json", remove_rationale)
        with self.assertRaisesRegex(ValueError, "Invalid scoring evidence"):
            check(self.root)


if __name__ == "__main__":
    unittest.main()
