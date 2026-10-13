"""Check stored evidence, not Japanese writing quality (standard library only)."""
import hashlib
import json
from pathlib import Path


def check(root):
    manifests = sorted((root / "evals").glob("*/manifest.json"))
    if not manifests:
        raise ValueError("No evaluation manifest")
    for manifest in manifests:
        entries = json.loads(manifest.read_text())
        for name, expected in entries.items():
            path = manifest.parent / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Evidence hash mismatch: {path}")
            if path.suffix == ".json":
                json.loads(path.read_text())
    skill = root / "skills/yomiyasu/SKILL.md"
    text = skill.read_text()
    if not text.startswith("---\nname: yomiyasu\ndescription: "):
        raise ValueError("Skill metadata missing")
    print(f"Checked {len(manifests)} evaluation manifests and skill metadata")


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[1])
