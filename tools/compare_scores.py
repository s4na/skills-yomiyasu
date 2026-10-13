"""Compare all archived judges for two executor directories; never decide adoption.

Run check_records.py first for manifest and repository-wide verification.
"""
import argparse
import json
from pathlib import Path

from check_records import check_packets, indexed


def compare(run, baseline, candidate):
    run = Path(run)
    metadata = json.loads((run / "metadata.json").read_text())
    if metadata.get("status") == "invalid_case_set":
        raise ValueError("Cannot compare an invalid_case_set")
    sources = (baseline, candidate)
    if baseline == candidate:
        raise ValueError("Baseline and candidate must differ")
    if any(source not in metadata["executors"] for source in sources):
        raise ValueError("Select executor directory names from metadata.executors")
    if (metadata["executor_condition_sha256"][baseline]
            == metadata["executor_condition_sha256"][candidate]):
        raise ValueError("Baseline and candidate have identical execution conditions")
    case_ids = metadata["executor_ids"][baseline]
    if not case_ids or case_ids != metadata["executor_ids"][candidate]:
        raise ValueError("Baseline and candidate must have the same nonempty case sequence (including order)")
    check_packets(run)
    execution_materials = []
    for source in sources:
        request = json.loads((run / source / "request.json").read_text())
        if source in metadata.get("single_cases", {}):
            material = {metadata["single_cases"][source]: request["user_request"]}
        else:
            material = {item["id"]: {field: item[field] for field in
                        ("request", "input", "draft", "checks") if field in item}
                        for item in request["cases"]}
        execution_materials.append(material)
    if execution_materials[0] != execution_materials[1]:
        raise ValueError("Execution case material differs between conditions")
    judges = {}
    materials = {}
    expected = {(source, case_id) for source in sources for case_id in case_ids}
    for judge in metadata["scorers"]:
        request = json.loads((run / judge / "request.json").read_text())
        response = json.loads((run / judge / "response.json").read_text())
        scores = indexed(response["scores"], judge)
        observations = {}
        for item in request["items"]:
            case_id, _, alias = item["id"].rpartition("-")
            if alias in metadata["aliases"]:
                source = metadata["aliases"][alias]
            else:
                source = metadata.get("single_condition_sources", {}).get(judge)
                case_id = item["id"]
            if source not in sources:
                continue
            key = (source, case_id)
            if key in observations:
                raise ValueError(f"Duplicate comparison observation: {judge}: {key}")
            observations[key] = scores[item["id"]]["values"]
            material = {field: item[field] for field in ("request", "input", "checks")}
            if "draft" in item:
                material["draft"] = item["draft"]
            material["rubric"] = request["rubric"]
            if case_id in materials and materials[case_id] != material:
                raise ValueError(f"Comparison material differs: {judge}: {case_id}")
            materials[case_id] = material
        if observations or metadata.get("single_condition_sources", {}).get(judge) in sources:
            if set(observations) != expected:
                raise ValueError(f"Incomplete comparison coverage: {judge}")
            judges[judge] = observations
    if len(judges) < 2:
        raise ValueError("Comparison requires at least two complete judges")

    cases = []
    for case_id in case_ids:
        criteria = []
        for index in range(6):
            observations = [{
                "judge": judge,
                "baseline": values[baseline, case_id][index],
                "candidate": values[candidate, case_id][index],
            } for judge, values in judges.items()]
            deltas = [row["candidate"] - row["baseline"] for row in observations]
            if all(delta > 0 for delta in deltas):
                status = "improved"
            elif all(delta == 0 for delta in deltas):
                status = "stable"
            elif all(delta < 0 for delta in deltas):
                status = "regressed"
            else:
                status = "mixed"
            criteria.append({"criterion": index + 1, "status": status,
                             "any_regression": any(delta < 0 for delta in deltas),
                             "observations": observations})
        cases.append({"case_id": case_id, "criteria": criteria})
    criteria = [criterion for case in cases for criterion in case["criteria"]]
    critical_pass = {
        label: all(row[label] == 1 for criterion in criteria
                   if criterion["criterion"] <= 4 for row in criterion["observations"])
        for label in ("baseline", "candidate")
    }
    noncritical_regressions = sum(criterion["any_regression"] for criterion in criteria
                                 if criterion["criterion"] in (5, 6))
    return {
        "meaning": ("Archived grades only; eligible means candidate critical scores are all 1 "
                    "and no judge lowered criterion 5 or 6. Human adoption review is still required."),
        "baseline": baseline, "candidate": candidate, "judges": list(judges),
        "critical_all_pass": critical_pass,
        "candidate_eligible": critical_pass["candidate"] and not noncritical_regressions,
        "counts": {status: sum(row["status"] == status for row in criteria)
                   for status in ("improved", "stable", "regressed", "mixed")},
        "any_regression_count": sum(row["any_regression"] for row in criteria),
        "noncritical_any_regression_count": noncritical_regressions,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="evaluation directory, e.g. evals/13")
    parser.add_argument("--baseline", required=True, help="baseline executor directory name")
    parser.add_argument("--candidate", required=True, help="candidate executor directory name")
    args = parser.parse_args()
    try:
        result = compare(args.run, args.baseline, args.candidate)
    except (ValueError, KeyError, OSError, TypeError, IndexError) as error:
        parser.exit(2, f"Comparison refused: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
