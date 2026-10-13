"""Check stored evidence, not Japanese writing quality (standard library only)."""
import hashlib
import json
from pathlib import Path


def indexed(items, label):
    result = {item["id"]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate IDs: {label}")
    return result


def json_digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def condition_digest(request):
    # Freeze the archived execution instructions, excluding the case payload.
    return json_digest({key: value for key, value in request.items() if key != "cases"})


def check_packets(run):
    metadata = json.loads((run / "metadata.json").read_text())
    rubric = (run.parent / "protocol.md").read_text().split("## 合否")[1].split("## 比較")[0]
    cases = {}
    for filename in ("development.json", "holdout.json"):
        path = run / filename
        if path.exists():
            split_cases = indexed(json.loads(path.read_text()), str(path))
            if cases.keys() & split_cases.keys():
                raise ValueError(f"Duplicate case IDs across splits: {run}")
            cases.update(split_cases)
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
    dispatch_conditions = metadata.get("dispatch_condition_sha256", {})
    if set(dispatch_conditions) != expected_agents:
        raise ValueError(f"Dispatch condition inventory mismatch: {run}")
    for item in dispatch:
        if json_digest(item) != dispatch_conditions[item["task_name"]]:
            raise ValueError(f"Dispatch condition mismatch: {run}: {item['task_name']}")
    executor_ids = metadata.get("executor_ids", {})
    if set(executor_ids) != set(executors):
        raise ValueError(f"Execution ID inventory mismatch: {run}")
    score_ids = metadata["score_ids"]
    if set(score_ids) != set(scorers):
        raise ValueError(f"Scoring inventory mismatch: {run}")
    conditions = metadata.get("executor_condition_sha256", {})
    if set(conditions) != set(executors):
        raise ValueError(f"Execution condition inventory mismatch: {run}")
    single_sources = metadata.get("single_condition_sources", {})
    if set(single_sources) - set(scorers) or any(
        source not in executors for source in single_sources.values()
    ):
        raise ValueError(f"Scoring source inventory mismatch: {run}")
    single_cases = metadata.get("single_cases", {})
    if set(single_cases) - set(executors) or set(single_cases.values()) - set(cases):
        raise ValueError(f"Single-case inventory mismatch: {run}")
    authored_drafts = metadata.get("authored_drafts", [])
    raw_json_executors = metadata.get("raw_json_executors", [])
    for label, names in (("Authored draft", authored_drafts), ("Raw JSON", raw_json_executors)):
        if len(names) != len(set(names)) or set(names) - set(executors) or set(names) & set(single_cases):
            raise ValueError(f"{label} inventory mismatch: {run}")
    outputs = {}
    inputs = {}
    for name in executors:
        request = json.loads((run / name / "request.json").read_text())
        if condition_digest(request) != conditions[name]:
            raise ValueError(f"Execution condition mismatch: {run / name}")
        if name in single_cases:
            case_id = single_cases[name]
            case = cases[case_id]
            canonical_request = (f"依頼：\n{case['request']}\n\n原文：\n{case['input']}"
                                 f"\n\n改稿案：\n{case['draft']}")
            if case["user_request"] != canonical_request:
                raise ValueError(f"Single-case canonical request mismatch: {run / name}")
            if request["user_request"] != case["user_request"]:
                raise ValueError(f"Single-case request mismatch: {run / name}")
            inputs[name] = {case_id: {field: case[field] for field in ("id", "input", "request")}}
            outputs[name] = {case_id: {"text": (run / name / "response.txt").read_text()}}
        else:
            response_file = "response.txt" if name in raw_json_executors else "response.json"
            response = json.loads((run / name / response_file).read_text())
            if name in raw_json_executors and (
                not isinstance(response, dict) or set(response) != {"outputs"}
                or not isinstance(response["outputs"], list)
                or any(not isinstance(row, dict) or set(row) != {"id", "text"}
                       or not isinstance(row["text"], str) for row in response["outputs"])
                or [row["id"] for row in response["outputs"]]
                != [case["id"] for case in request["cases"]]
            ):
                raise ValueError(f"Raw JSON output contract mismatch: {run / name}")
            inputs[name] = indexed(request["cases"], name)
            outputs[name] = indexed(response["outputs"], name)
        if list(inputs[name]) != executor_ids[name]:
            raise ValueError(f"Expected execution IDs mismatch: {run / name}")
        if inputs[name].keys() != outputs[name].keys():
            raise ValueError(f"Execution IDs mismatch: {run / name}")
    draft_sources = metadata.get("draft_sources", {})
    if set(draft_sources) - set(inputs):
        raise ValueError(f"Unknown draft consumer: {run}")
    if set(authored_drafts) & set(draft_sources):
        raise ValueError(f"Conflicting draft provenance: {run}")
    for name, cases_by_id in inputs.items():
        source = draft_sources.get(name)
        if source is not None and source not in outputs:
            raise ValueError(f"Unknown draft source: {run / name}")
        for case_id, item in cases_by_id.items():
            if ("draft" in item) != (source is not None or name in authored_drafts):
                raise ValueError(f"Draft source declaration mismatch: {run / name}")
            if name in authored_drafts and (
                case_id not in cases or any(item.get(field) != cases[case_id].get(field)
                                           for field in ("id", "request", "input", "draft"))
            ):
                raise ValueError(f"Authored draft case mismatch: {run / name}: {case_id}")
            if source is not None and (
                case_id not in outputs[source]
                or item["draft"] != outputs[source][case_id]["text"]
                or any(item[field] != inputs[source][case_id][field]
                       for field in ("input", "request"))
            ):
                raise ValueError(f"Draft source mismatch: {run / name}: {case_id}")
    for name in scorers:
        request = json.loads((run / name / "request.json").read_text())
        response = json.loads((run / name / "response.json").read_text())
        if request["rubric"] != rubric:
            raise ValueError(f"Scoring rubric mismatch: {run / name}")
        items = indexed(request["items"], name)
        scores = indexed(response["scores"], name)
        if items.keys() != scores.keys():
            raise ValueError(f"Scoring IDs mismatch: {run / name}")
        if list(items) != score_ids[name]:
            raise ValueError(f"Expected scoring IDs mismatch: {run / name}")
        for key, item in items.items():
            case_id, _, alias = key.rpartition("-")
            if alias in aliases:
                sources = [aliases[alias]]
            else:
                # Preliminary packets retain original IDs and need an explicit source.
                case_id = key
                if name not in single_sources:
                    raise ValueError(f"Missing scoring source binding: {run / name}: {key}")
                sources = [single_sources[name]]
            matching = [source for source in sources if case_id in outputs[source]
                        and outputs[source][case_id]["text"] == item["output"]
                        and all(inputs[source][case_id][field] == item[field]
                                for field in ("input", "request"))]
            if not matching:
                raise ValueError(f"Scoring source mismatch: {run / name}: {key}")
            canonical = cases[case_id]
            if metadata.get("scoring_draft") and (
                "draft" not in item or "draft" not in canonical
                or item["draft"] != canonical["draft"]
            ):
                raise ValueError(f"Scoring draft mismatch: {run / name}: {key}")
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
            if any(entry[field] not in item[field]
                   for entry in evidence for field in ("input", "output")):
                raise ValueError(f"Scoring evidence quote mismatch: {run / name}: {key}")
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
