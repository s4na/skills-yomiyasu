import hashlib
import json
from pathlib import Path
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
            protocol.write_text("意味を変えたら失敗。\n")
            metadata = run / "metadata.json"
            metadata.write_text(json.dumps({
                "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest()
            }))
            (run / "manifest.json").write_text(json.dumps({
                "metadata.json": hashlib.sha256(metadata.read_bytes()).hexdigest()
            }))
            check(root)
            protocol.write_text("意味を変えても成功。\n")
            with self.assertRaisesRegex(ValueError, "protocol hash mismatch"):
                check(root)


if __name__ == "__main__":
    unittest.main()
