"""Expose conflicting grades for exactly identical evaluation material.

Run check_records.py first. This report preserves grades; it does not judge text.
"""
import hashlib
import json
from pathlib import Path


def summarize(root):
    groups = {}
    for metadata_path in sorted((root / "evals").glob("*/metadata.json")):
        run = metadata_path.parent
        metadata = json.loads(metadata_path.read_text())
        names = metadata.get("scorers", metadata.get("evaluators", []))
        if "evaluators" in metadata:
            names = [name[1:] for name in names]
        for name in names:
            packet = run / name
            request = json.loads((packet / "request.json").read_text())
            response = json.loads((packet / "response.json").read_text())
            scores = {score["id"]: score for score in response["scores"]}
            for item in request["items"]:
                material = {field: item[field] for field in
                            ("request", "input", "checks", "output")}
                material["rubric"] = request["rubric"]
                canonical = json.dumps(material, ensure_ascii=False, sort_keys=True)
                # Group by the full material, not a hash or candidate label.
                groups.setdefault(canonical, []).append({
                    "packet": str(packet.relative_to(root)),
                    "id": item["id"],
                    "values": scores[item["id"]]["values"],
                })
    results = []
    for material, observations in groups.items():
        decisions = {all(v == 1 for v in row["values"][:4]) for row in observations}
        status = "disputed" if len(decisions) > 1 else "pass" if True in decisions else "fail"
        results.append({
            "material_sha256": hashlib.sha256(material.encode()).hexdigest(),
            "critical_status": status,
            "different_criteria": [i + 1 for i in range(6)
                                   if len({row["values"][i] for row in observations}) > 1],
            "observations": observations,
        })
    results.sort(key=lambda row: row["material_sha256"])
    return {
        "meaning": "Observed grades only. Disputed is not a pass; unanimous pass is not proof of correctness.",
        "counts": {status: sum(row["critical_status"] == status for row in results)
                   for status in ("pass", "fail", "disputed")},
        "groups": results,
    }


if __name__ == "__main__":
    print(json.dumps(summarize(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
