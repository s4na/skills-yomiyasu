"""Check stored evidence, not Japanese writing quality (standard library only)."""
import hashlib
import json
from pathlib import Path


def indexed(items, label):
    result = {item["id"]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate IDs: {label}")
    return result


def check_packets(run):
    metadata = json.loads((run / "metadata.json").read_text())
    rubric = (run.parent / "protocol.md").read_text().split("## 合否")[1].split("## 比較")[0]
    cases = {}
    for filename in ("development.json", "holdout.json"):
        path = run / filename
        if path.exists():
            cases.update(indexed(json.loads(path.read_text()), str(path)))
    aliases = metadata.get("aliases", {})
    if not aliases:
        aliases = {**metadata.get("development", {}), **metadata.get("holdout", {})}
    # The first round recorded agent names; later rounds use directory names.
    executors = metadata["executors"]
    scorers = metadata.get("scorers", metadata.get("evaluators", []))
    if "evaluators" in metadata:
        executors = [name[1:] for name in executors]
        scorers = [name[1:] for name in scorers]
    dispatch = json.loads((run / "dispatch.json").read_text())
    expected_agents = {"r" + name for name in executors} | {"s" + name for name in scorers}
    if {item["task_name"] for item in dispatch} != expected_agents or len(dispatch) != len(expected_agents):
        raise ValueError(f"Dispatch roster mismatch: {run}")
    score_ids = metadata["score_ids"]
    if set(score_ids) != set(scorers):
        raise ValueError(f"Scoring inventory mismatch: {run}")
    outputs = {}
    inputs = {}
    for name in executors:
        request = json.loads((run / name / "request.json").read_text())
        response = json.loads((run / name / "response.json").read_text())
        inputs[name] = indexed(request["cases"], name)
        outputs[name] = indexed(response["outputs"], name)
        if inputs[name].keys() != outputs[name].keys():
            raise ValueError(f"Execution IDs mismatch: {run / name}")
    for name in scorers:
        request = json.loads((run / name / "request.json").read_text())
        response = json.loads((run / name / "response.json").read_text())
        if request["rubric"] != rubric:
            raise ValueError(f"Scoring rubric mismatch: {run / name}")
        items = indexed(request["items"], name)
        scores = indexed(response["scores"], name)
        if items.keys() != scores.keys():
            raise ValueError(f"Scoring IDs mismatch: {run / name}")
        if set(items) != set(score_ids[name]) or len(items) != len(score_ids[name]):
            raise ValueError(f"Expected scoring IDs mismatch: {run / name}")
        for key, item in items.items():
            case_id, _, alias = key.rpartition("-")
            if alias in aliases:
                sources = [aliases[alias]]
            else:
                # Preliminary single-condition packets retain the original ID.
                case_id = key
                sources = list(outputs)
            matching = [source for source in sources if case_id in outputs[source]
                        and outputs[source][case_id]["text"] == item["output"]
                        and all(inputs[source][case_id][field] == item[field]
                                for field in ("input", "request"))]
            if not matching:
                raise ValueError(f"Scoring source mismatch: {run / name}: {key}")
            canonical = cases[case_id]
            if any(item[field] != canonical[field] for field in ("input", "request", "checks")):
                raise ValueError(f"Scoring case mismatch: {run / name}: {key}")
            values = scores[key]["values"]
            if len(values) != 6 or any(type(v) not in (int, float) or v not in (0, 0.5, 1) for v in values):
                raise ValueError(f"Invalid scores: {run / name}: {key}")
            if any(value < 1 for value in values) and not scores[key].get("evidence"):
                raise ValueError(f"Missing scoring evidence: {run / name}: {key}")
            evidence = scores[key].get("evidence", [])
            if not isinstance(evidence, list) or any(
                not isinstance(entry, dict)
                or type(entry.get("criterion")) is not int
                or entry["criterion"] not in range(1, 7)
                or any(not isinstance(entry.get(field), str) or not entry[field].strip()
                       for field in ("input", "output", "reason"))
                for entry in evidence
            ):
                raise ValueError(f"Invalid scoring evidence: {run / name}: {key}")
            if {i + 1 for i, value in enumerate(values) if value < 1} - {entry["criterion"] for entry in evidence}:
                raise ValueError(f"Incomplete scoring evidence: {run / name}: {key}")


def check(root):
    rounds = sorted(path for path in (root / "evals").iterdir() if path.is_dir())
    if not rounds:
        raise ValueError("No evaluation manifest")
    # Later rounds share the rubric frozen by the first round.
    metadata = json.loads((root / "evals/01/metadata.json").read_text())
    protocol_hash = hashlib.sha256((root / "evals/protocol.md").read_bytes()).hexdigest()
    if protocol_hash != metadata["protocol_sha256"]:
        raise ValueError("Evaluation protocol hash mismatch")
    for run in rounds:
        manifest = run / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"Missing evaluation manifest: {run}")
        entries = json.loads(manifest.read_text())
        files = {str(path.relative_to(run)) for path in run.rglob("*")
                 if path.is_file() and path.name not in ("manifest.json", "README.md")}
        if set(entries) != files:
            raise ValueError(f"Evidence inventory mismatch: {run}")
        for name, expected in entries.items():
            path = manifest.parent / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Evidence hash mismatch: {path}")
            if path.suffix == ".json":
                json.loads(path.read_text())
        check_packets(run)
    skill = root / "skills/yomiyasu/SKILL.md"
    text = skill.read_text()
    if not text.startswith("---\nname: yomiyasu\ndescription: "):
        raise ValueError("Skill metadata missing")
    print(f"Checked {len(rounds)} evaluation manifests, packet links and skill metadata")


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[1])
