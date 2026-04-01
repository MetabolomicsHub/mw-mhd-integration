from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

STUDY_ID_RE = re.compile(r"^ST\d{6}$")
CONTACT_FIELDS = ("full_name", "email", "phone", "address", "affiliation")


def is_study_id(value: str) -> bool:
    return bool(STUDY_ID_RE.match(value))


def normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def normalize_list(values: list[Any]) -> list[str]:
    normalized = []
    for value in values:
        item = normalize_scalar(value)
        if item:
            normalized.append(item)
    seen = set()
    deduped = []
    for item in normalized:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def select_first_ms_analysis(source_data: dict[str, Any]) -> dict[str, Any] | None:
    analysis_ids = [
        analysis_id
        for analysis_id, payload in source_data.items()
        if isinstance(payload, dict)
        and "MS" in payload.get("ANALYSIS", {}).get("ANALYSIS_TYPE", "")
    ]
    if not analysis_ids:
        return None
    analysis_ids.sort()
    return source_data[analysis_ids[0]]


def extract_source_contacts(source_data: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    analysis = select_first_ms_analysis(source_data)
    if not analysis:
        return {}

    study = analysis.get("STUDY", {})
    project = analysis.get("PROJECT", {})

    def build_contact(section: dict[str, Any]) -> dict[str, list[str]]:
        first_name = normalize_scalar(section.get("FIRST_NAME"))
        last_name = normalize_scalar(section.get("LAST_NAME"))
        full_name = " ".join(x for x in (first_name, last_name) if x).strip()
        return {
            "full_name": normalize_list([full_name]),
            "email": normalize_list([section.get("EMAIL")]),
            "phone": normalize_list([section.get("PHONE")]),
            "address": normalize_list([section.get("ADDRESS")]),
            "affiliation": normalize_list([section.get("INSTITUTE")]),
        }

    return {
        "submitter": build_contact(study),
        "principal_investigator": build_contact(project),
    }


def build_relationship_indexes(
    relationships: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    by_target: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        by_source.setdefault(rel.get("source_ref", ""), []).append(rel)
        by_target.setdefault(rel.get("target_ref", ""), []).append(rel)
    return by_source, by_target


def extract_mhd_contacts(mhd_data: dict[str, Any]) -> dict[str, list[dict[str, list[str]]]]:
    graph = mhd_data.get("graph", {})
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    nodes_by_id = {node["id"]: node for node in nodes if "id" in node}
    rels_by_source, rels_by_target = build_relationship_indexes(relationships)
    study_id = next(
        (node["id"] for node in nodes if node.get("type") == "study"),
        None,
    )
    if not study_id:
        return {"submitter": [], "principal_investigator": []}

    def contacts_for_relationship(name: str) -> list[dict[str, list[str]]]:
        contacts = []
        for rel in rels_by_target.get(study_id, []):
            if rel.get("relationship_name") != name:
                continue
            person = nodes_by_id.get(rel.get("source_ref"))
            if not person or person.get("type") != "person":
                continue
            affiliations = []
            for person_rel in rels_by_source.get(person["id"], []):
                if person_rel.get("relationship_name") != "affiliated-with":
                    continue
                organization = nodes_by_id.get(person_rel.get("target_ref"))
                if organization and organization.get("type") == "organization":
                    affiliations.append(organization.get("name"))
            contacts.append(
                {
                    "full_name": normalize_list([person.get("full_name")]),
                    "email": normalize_list(person.get("emails", [])),
                    "phone": normalize_list(person.get("phones", [])),
                    "address": normalize_list(person.get("addresses", [])),
                    "affiliation": normalize_list(affiliations),
                }
            )
        return contacts

    return {
        "submitter": contacts_for_relationship("submits"),
        "principal_investigator": contacts_for_relationship("principal-investigator-of"),
    }


def extract_announcement_contacts(
    announcement_data: dict[str, Any],
) -> dict[str, list[dict[str, list[str]]]]:
    role_map = {
        "submitter": "submitters",
        "principal_investigator": "principal_investigators",
    }
    result: dict[str, list[dict[str, list[str]]]] = {}
    for role, key in role_map.items():
        contacts = []
        for item in announcement_data.get(key, []):
            contacts.append(
                {
                    "full_name": normalize_list([item.get("full_name")]),
                    "email": normalize_list(item.get("emails", [])),
                    "phone": normalize_list(item.get("phones", [])),
                    "address": normalize_list(item.get("addresses", [])),
                    "affiliation": normalize_list(item.get("affiliation_list", [])),
                }
            )
        result[role] = contacts
    return result


def collect_target_values(
    contacts: list[dict[str, list[str]]], field_name: str
) -> list[str]:
    values: list[str] = []
    for contact in contacts:
        values.extend(contact.get(field_name, []))
    return normalize_list(values)


def compare_field(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_set = set(expected)
    actual_set = set(actual)
    return {
        "expected": expected,
        "actual": actual,
        "missing_values": sorted(expected_set - actual_set),
        "unexpected_values": sorted(actual_set - expected_set),
        "matched": sorted(expected_set & actual_set),
        "status": (
            "not_applicable"
            if not expected
            else "matched"
            if expected_set <= actual_set
            else "missing"
        ),
    }


def audit_study(
    study_id: str,
    source_path: Path,
    mhd_path: Path,
    announcement_path: Path,
) -> dict[str, Any]:
    source_data = load_json(source_path)
    source_contacts = extract_source_contacts(source_data)
    mhd_contacts = extract_mhd_contacts(load_json(mhd_path)) if mhd_path.exists() else {}
    announcement_contacts = (
        extract_announcement_contacts(load_json(announcement_path))
        if announcement_path.exists()
        else {}
    )

    role_audit: dict[str, Any] = {}
    for role in ("submitter", "principal_investigator"):
        source_role = source_contacts.get(role, {})
        mhd_role = mhd_contacts.get(role, [])
        announcement_role = announcement_contacts.get(role, [])
        field_audit = {}
        for field_name in CONTACT_FIELDS:
            expected = source_role.get(field_name, [])
            field_audit[field_name] = {
                "source": expected,
                "mhd": compare_field(expected, collect_target_values(mhd_role, field_name)),
                "announcement": compare_field(
                    expected, collect_target_values(announcement_role, field_name)
                ),
            }
        role_audit[role] = field_audit

    return {
        "study_id": study_id,
        "files": {
            "source": str(source_path),
            "mhd": str(mhd_path),
            "announcement": str(announcement_path),
        },
        "roles": role_audit,
    }


def summarize_audits(audits: list[dict[str, Any]]) -> dict[str, Any]:
    missing_counter: Counter[str] = Counter()
    expected_counter: Counter[str] = Counter()

    for audit in audits:
        for role, fields in audit.get("roles", {}).items():
            for field_name, targets in fields.items():
                source_values = targets.get("source", [])
                if not source_values:
                    continue
                for target_name in ("mhd", "announcement"):
                    expected_counter[f"{role}.{field_name}.{target_name}"] += 1
                    if targets[target_name]["status"] == "missing":
                        missing_counter[f"{role}.{field_name}.{target_name}"] += 1

    summary = []
    for key in sorted(expected_counter):
        summary.append(
            {
                "field_target": key,
                "studies_with_source_value": expected_counter[key],
                "studies_missing_value": missing_counter.get(key, 0),
            }
        )
    return {"missing_by_field_target": summary}


def resolve_study_ids(
    source_dir: Path,
    mhd_dir: Path,
    announcement_dir: Path,
    explicit_study_ids: list[str] | None,
    limit: int | None,
) -> list[str]:
    if explicit_study_ids:
        return explicit_study_ids

    source_study_ids = {
        path.stem
        for path in source_dir.glob("ST*.json")
        if is_study_id(path.stem) and not path.stem.endswith("_metabolites")
    }
    mhd_study_ids = {
        path.name.removesuffix(".mhd.json")
        for path in mhd_dir.glob("ST*.mhd.json")
        if is_study_id(path.name.removesuffix(".mhd.json"))
    }
    announcement_study_ids = {
        path.name.removesuffix(".announcement.json")
        for path in announcement_dir.glob("ST*.announcement.json")
        if is_study_id(path.name.removesuffix(".announcement.json"))
    }

    study_ids = sorted(source_study_ids & mhd_study_ids & announcement_study_ids)
    if limit is not None:
        return study_ids[:limit]
    return study_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit whether selected source contact fields survive conversion into "
            "legacy MHD and announcement outputs."
        )
    )
    parser.add_argument(
        "--source-dir",
        default=".outputs/mw_dataset",
        help="Directory containing source MW JSON files.",
    )
    parser.add_argument(
        "--mhd-dir",
        default=".outputs/mhd_legacy",
        help="Directory containing converted MHD JSON files.",
    )
    parser.add_argument(
        "--announcement-dir",
        default=".outputs/mhd_legacy",
        help="Directory containing converted announcement JSON files.",
    )
    parser.add_argument(
        "--study-id",
        action="append",
        dest="study_ids",
        help="Study ID to audit. Repeat for multiple studies. Defaults to all source studies.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional max number of studies to audit when --study-id is not provided.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write JSON output to this path instead of stdout.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    mhd_dir = Path(args.mhd_dir)
    announcement_dir = Path(args.announcement_dir)
    study_ids = resolve_study_ids(
        source_dir, mhd_dir, announcement_dir, args.study_ids, args.limit
    )

    audits = []
    for study_id in study_ids:
        source_path = source_dir / f"{study_id}.json"
        if not source_path.exists():
            continue
        audits.append(
            audit_study(
                study_id=study_id,
                source_path=source_path,
                mhd_path=mhd_dir / f"{study_id}.mhd.json",
                announcement_path=announcement_dir / f"{study_id}.announcement.json",
            )
        )

    result = {
        "study_count": len(audits),
        "summary": summarize_audits(audits),
        "audits": audits,
    }

    payload = json.dumps(result, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{payload}\n", encoding="utf-8")
        print(output_path)
        return 0

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
