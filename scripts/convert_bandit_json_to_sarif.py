#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
SEVERITY_TO_LEVEL = {
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


def _rule_descriptor(result: dict[str, Any]) -> dict[str, Any]:
    rule_id = str(result.get("test_id") or "bandit")
    description = str(result.get("issue_text") or result.get("test_name") or "Bandit security finding")
    descriptor: dict[str, Any] = {
        "id": rule_id,
        "name": str(result.get("test_name") or rule_id),
        "shortDescription": {"text": description},
    }
    more_info = result.get("more_info")
    if more_info:
        descriptor["helpUri"] = str(more_info)
    return descriptor


def _sarif_result(result: dict[str, Any]) -> dict[str, Any]:
    filename = str(result.get("filename") or "")
    line_number = int(result.get("line_number") or 1)
    message = str(result.get("issue_text") or result.get("test_name") or "Bandit security finding")
    severity = str(result.get("issue_severity") or "LOW").upper()
    confidence = str(result.get("issue_confidence") or "LOW").upper()

    sarif_result: dict[str, Any] = {
        "ruleId": str(result.get("test_id") or "bandit"),
        "level": SEVERITY_TO_LEVEL.get(severity, "warning"),
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": filename},
                    "region": {"startLine": max(line_number, 1)},
                }
            }
        ],
        "properties": {
            "issue_confidence": confidence,
            "issue_severity": severity,
            "test_name": str(result.get("test_name") or ""),
        },
    }
    more_info = result.get("more_info")
    if more_info:
        sarif_result["helpUri"] = str(more_info)
    return sarif_result


def convert_bandit_json_to_sarif(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])

    rules_by_id: dict[str, dict[str, Any]] = {}
    sarif_results: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        descriptor = _rule_descriptor(result)
        rules_by_id[descriptor["id"]] = descriptor
        sarif_results.append(_sarif_result(result))

    sarif_payload = {
        "$schema": SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Bandit",
                        "informationUri": "https://bandit.readthedocs.io/",
                        "rules": list(rules_by_id.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sarif_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: convert_bandit_json_to_sarif.py <bandit.json> <bandit.sarif>",
            file=sys.stderr,
        )
        return 2
    convert_bandit_json_to_sarif(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
