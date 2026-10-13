import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from check_records import check, condition_digest


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
        run = self.root / Path(relative).parts[0] / Path(relative).parts[1]
        manifest = run / "manifest.json"
        entries = json.loads(manifest.read_text())
        entries[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(entries))

    def test_complete_records_pass(self):
        check(self.root)

    def test_invalid_case_set_still_checks_scoring_links(self):
        self.change_json("evals/11/o91x/request.json",
                         lambda data: data["items"][0].update(output="別の本文です。"))
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            check(self.root)

    def test_rehashed_single_case_fields_are_bound_to_user_request(self):
        relative = "evals/09/development.json"
        original = json.loads((self.root / relative).read_text())
        for field in ("request", "input", "draft", "user_request"):
            with self.subTest(field=field):
                self.change_json(relative, lambda data: data[0].update({field: "別の文章です。"}))
                try:
                    with self.assertRaisesRegex(ValueError, "Single-case canonical request mismatch"):
                        check(self.root)
                finally:
                    self.change_json(relative, lambda data: data.__setitem__(slice(None), original))

    def test_rehashed_single_case_raw_request_is_rejected(self):
        relative = "evals/09/a12/request.json"
        self.change_json(relative, lambda data: data.update(user_request="別の依頼です。"))
        altered = json.loads((self.root / relative).read_text())
        # Even refreshing the request-condition inventory must not detach the
        # executed raw request from the canonical case used for scoring.
        self.change_json("evals/09/metadata.json", lambda data:
                         data["executor_condition_sha256"].update(a12=condition_digest(altered)))
        with self.assertRaisesRegex(ValueError, "Single-case request mismatch"):
            check(self.root)

    def test_rehashed_single_case_raw_output_is_rejected(self):
        relative = "evals/09/a12/response.txt"
        path = self.root / relative
        path.write_text("別の本文です。")
        manifest = self.root / "evals/09/manifest.json"
        entries = json.loads(manifest.read_text())
        entries["a12/response.txt"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(entries))
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            check(self.root)

    def test_rehashed_missing_or_changed_scoring_draft_is_rejected(self):
        relative = "evals/09/e91x/request.json"
        original = json.loads((self.root / relative).read_text())
        for missing in (True, False):
            with self.subTest(missing=missing):
                def alter(data):
                    if missing:
                        data["items"][0].pop("draft")
                    else:
                        data["items"][0]["draft"] = "別の改稿です。"
                self.change_json(relative, alter)
                try:
                    with self.assertRaisesRegex(ValueError, "Scoring draft mismatch"):
                        check(self.root)
                finally:
                    self.change_json(relative, lambda data: data.update(original))

    def test_rehashed_wrong_draft_is_rejected(self):
        self.change_json("evals/06/f74/request.json",
                         lambda data: data["cases"][0].update(draft="別の改稿です。"))
        with self.assertRaisesRegex(ValueError, "Draft source mismatch"):
            check(self.root)

    def test_rehashed_authored_batch_fields_are_rejected(self):
        relative = "evals/13/a13y/request.json"
        original = json.loads((self.root / relative).read_text())
        for field in ("id", "request", "input", "draft"):
            with self.subTest(field=field):
                self.change_json(relative, lambda data: data["cases"][0].update({field: "changed"}))
                try:
                    with self.assertRaisesRegex(ValueError, "Raw JSON output contract mismatch|Authored draft case mismatch"):
                        check(self.root)
                finally:
                    self.change_json(relative, lambda data: data.update(original))

    def test_rehashed_authored_draft_declaration_is_required(self):
        self.change_json("evals/13/metadata.json", lambda data: data.update(authored_drafts=[]))
        with self.assertRaisesRegex(ValueError, "Draft source declaration mismatch"):
            check(self.root)

    def test_rehashed_authored_draft_cannot_be_derived(self):
        self.change_json("evals/13/metadata.json", lambda data: data.update(draft_sources={"a13y": "b24y"}))
        with self.assertRaisesRegex(ValueError, "Conflicting draft provenance"):
            check(self.root)

    def test_rehashed_raw_json_output_is_bound_to_scores(self):
        self.change_json("evals/13/a13y/response.txt", lambda data: data["outputs"][0].update(text="changed"))
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            check(self.root)

    def test_rehashed_raw_json_output_order_is_required(self):
        self.change_json("evals/13/a13y/response.txt", lambda data: data["outputs"].reverse())
        with self.assertRaisesRegex(ValueError, "Raw JSON output contract mismatch"):
            check(self.root)

    def test_rehashed_raw_json_output_schema_is_required(self):
        relative = "evals/13/a13y/response.txt"
        original = json.loads((self.root / relative).read_text())
        mutations = (
            lambda data: data.update(extra="unexpected"),
            lambda data: data["outputs"][0].update(extra="unexpected"),
            lambda data: data["outputs"][0].update(text=123),
            lambda data: data.update(outputs={}),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.change_json(relative, mutation)
                try:
                    with self.assertRaisesRegex(ValueError, "Raw JSON output contract mismatch"):
                        check(self.root)
                finally:
                    self.change_json(relative, lambda data: (data.clear(), data.update(original)))

    def test_rehashed_invalid_batch_inventory_is_rejected(self):
        relative = "evals/13/metadata.json"
        original = json.loads((self.root / relative).read_text())
        for field in ("authored_drafts", "raw_json_executors"):
            for names in (["unknown"], ["a13y", "a13y"]):
                with self.subTest(field=field, names=names):
                    self.change_json(relative, lambda data: data.update({field: names}))
                    try:
                        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                            check(self.root)
                    finally:
                        self.change_json(relative, lambda data: data.update(original))

    def test_raw_json_response_cannot_be_replaced_with_derived_json(self):
        self.change_json("evals/13/metadata.json", lambda data: data.update(raw_json_executors=[]))
        with self.assertRaises(FileNotFoundError):
            check(self.root)

    def test_rehashed_missing_draft_source_is_rejected(self):
        self.change_json("evals/06/metadata.json", lambda data: data.update(draft_sources={}))
        with self.assertRaisesRegex(ValueError, "Draft source declaration mismatch"):
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

    def test_rehashed_preliminary_output_from_other_condition_is_rejected(self):
        candidate = json.loads((self.root / "evals/03/df8/response.json").read_text())
        outputs = {item["id"]: item["text"] for item in candidate["outputs"]}
        def replace_output(data):
            for item in data["items"]:
                item["output"] = outputs[item["id"]]
        self.change_json("evals/03/317/request.json", replace_output)
        with self.assertRaisesRegex(ValueError, "Scoring source mismatch"):
            check(self.root)

    def test_rehashed_executor_skill_swap_is_rejected(self):
        baseline = json.loads((self.root / "evals/03/8bc/request.json").read_text())
        self.change_json("evals/03/df8/request.json",
                         lambda data: data.update(skill=baseline["skill"]))
        with self.assertRaisesRegex(ValueError, "Execution condition mismatch"):
            check(self.root)

    def test_rehashed_external_skill_path_change_is_rejected(self):
        self.change_json("evals/01/4f2/request.json",
                         lambda data: data.update(skill_path="/different/SKILL.md"))
        with self.assertRaisesRegex(ValueError, "Execution condition mismatch"):
            check(self.root)

    def test_missing_preliminary_binding_is_rejected(self):
        self.change_json("evals/03/metadata.json",
                         lambda data: data.pop("single_condition_sources"))
        with self.assertRaisesRegex(ValueError, "Missing scoring source binding"):
            check(self.root)

    def test_rehashed_dispatch_conditions_are_rejected(self):
        for field, value in (("fork_turns", "all"), ("model_override", "different-model")):
            with self.subTest(field=field):
                original = (self.root / "evals/03/dispatch.json").read_text()
                self.change_json("evals/03/dispatch.json",
                                 lambda data: data[0].update({field: value}))
                try:
                    with self.assertRaisesRegex(ValueError, "Dispatch condition mismatch"):
                        check(self.root)
                finally:
                    self.change_json("evals/03/dispatch.json",
                                     lambda data: data.__setitem__(slice(None), json.loads(original)))

    def test_rehashed_executor_batch_reordering_is_rejected(self):
        self.change_json("evals/03/df8/request.json", lambda data: data["cases"].reverse())
        self.change_json("evals/03/df8/response.json", lambda data: data["outputs"].reverse())
        with self.assertRaisesRegex(ValueError, "Expected execution IDs mismatch"):
            check(self.root)

    def test_rehashed_cross_split_duplicate_id_is_rejected(self):
        holdout = json.loads((self.root / "evals/03/holdout.json").read_text())
        self.change_json("evals/03/development.json", lambda data: data.append(holdout[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate case IDs across splits"):
            check(self.root)

    def test_rehashed_unquoted_evidence_is_rejected(self):
        relative = "evals/03/c76/response.json"
        original = json.loads((self.root / relative).read_text())
        for field in ("input", "output"):
            with self.subTest(field=field):
                def replace_quote(data):
                    for score in data["scores"]:
                        for entry in score.get("evidence", []):
                            entry[field] = "x"
                self.change_json(relative, replace_quote)
                try:
                    with self.assertRaisesRegex(ValueError, "Scoring evidence quote mismatch"):
                        check(self.root)
                finally:
                    self.change_json(relative, lambda data: data.update(original))

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
