from __future__ import annotations

import argparse
import json
from pathlib import Path

ISSUE_CATEGORIES = (
    "dropped_before_mhd",
    "mapped_to_mhd_only",
    "mapped_to_announcement_only",
    "unmapped_in_converter",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(audit: dict, max_examples: int) -> dict:
    fields = {field["field_id"]: field for field in audit["summary"]["fields"]}

    examples_by_field_and_issue: dict[str, dict[str, list[str]]] = {}
    for study in audit["audits"]:
        study_id = study["study_id"]
        for field in study["fields"]:
            issue = field["classification"]
            if issue not in ISSUE_CATEGORIES:
                continue
            field_examples = examples_by_field_and_issue.setdefault(field["field_id"], {})
            issue_examples = field_examples.setdefault(issue, [])
            if len(issue_examples) < max_examples:
                issue_examples.append(study_id)

    grouped = {
        "dropped_before_mhd": [],
        "missing_from_announcement": [],
        "mapped_to_mhd_only_other": [],
        "mapped_to_announcement_only": [],
        "unmapped_in_converter": [],
    }

    fields_with_issues = []
    for field_id, field in fields.items():
        counts = field["classification_counts"]
        issue_counts = {
            key: counts.get(key, 0)
            for key in ISSUE_CATEGORIES
            if counts.get(key, 0)
        }
        if not issue_counts:
            continue

        issue_entry = {
            "field_id": field_id,
            "category": field["category"],
            "description": field["description"],
            "mhd_expectation": field["mhd_expectation"],
            "announcement_expectation": field["announcement_expectation"],
            "studies_with_source_value": field["studies_with_source_value"],
            "mhd_present_count": field["mhd_present_count"],
            "announcement_present_count": field["announcement_present_count"],
            "issue_counts": issue_counts,
            "example_study_ids": examples_by_field_and_issue.get(field_id, {}),
        }
        fields_with_issues.append(issue_entry)

        if issue_counts.get("dropped_before_mhd"):
            grouped["dropped_before_mhd"].append(issue_entry)
        if issue_counts.get("mapped_to_mhd_only"):
            if field["announcement_expectation"] == "expected":
                grouped["missing_from_announcement"].append(issue_entry)
            else:
                grouped["mapped_to_mhd_only_other"].append(issue_entry)
        if issue_counts.get("mapped_to_announcement_only"):
            grouped["mapped_to_announcement_only"].append(issue_entry)
        if issue_counts.get("unmapped_in_converter"):
            grouped["unmapped_in_converter"].append(issue_entry)

    overview = {
        "study_count": audit["study_count"],
        "field_count": len(audit["summary"]["fields"]),
        "fields_with_any_issue": len(fields_with_issues),
        "issue_field_counts": {
            key: len(value) for key, value in grouped.items()
        },
    }

    return {
        "overview": overview,
        "fields_with_issues": fields_with_issues,
        "issues": grouped,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a compact JSON summary from semantic coverage audit output."
    )
    parser.add_argument(
        "audit_json",
        nargs="?",
        default=".outputs/log_analysis/semantic_coverage.all.json",
        help="Path to the full semantic coverage audit JSON.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=".outputs/log_analysis/semantic_coverage.summary.json",
        help="Where to write the compact summary JSON.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="Maximum example study IDs to keep per field per issue type.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    audit_path = Path(args.audit_json)
    output_path = Path(args.output)

    summary = summarize(load_json(audit_path), max_examples=args.max_examples)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{json.dumps(summary, indent=2)}\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
