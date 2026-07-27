from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _normalize_list(values: list[Any]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        if value is None:
            continue
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_relationship_indexes(
    relationships: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    by_target: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        by_source.setdefault(rel.get("source_ref", ""), []).append(rel)
        by_target.setdefault(rel.get("target_ref", ""), []).append(rel)
    return by_source, by_target


def _cv_term_from_node(
    node: dict[str, Any] | None, fallback_name: str = ""
) -> dict[str, str]:
    node = node or {}
    return {
        "source": node.get("source", "") or "",
        "accession": node.get("accession", "") or "",
        "name": node.get("name", "") or fallback_name,
    }


def _parse_mhd_contacts(
    nodes_by_id: dict[str, dict[str, Any]],
    rels_by_source: dict[str, list[dict[str, Any]]],
    rels_by_target: dict[str, list[dict[str, Any]]],
    study_id: str | None,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    contacts = {"submitters": {}, "principal_investigators": {}}
    if not study_id:
        return contacts

    role_map = {
        "submits": "submitters",
        "principal-investigator-of": "principal_investigators",
    }
    for rel in rels_by_target.get(study_id, []):
        role = role_map.get(rel.get("relationship_name"))
        if not role:
            continue
        person = nodes_by_id.get(rel.get("source_ref"))
        if not person or person.get("type") != "person":
            continue
        full_name = person.get("full_name")
        if not full_name:
            continue
        affiliations = []
        for person_rel in rels_by_source.get(person["id"], []):
            if person_rel.get("relationship_name") != "affiliated-with":
                continue
            organization = nodes_by_id.get(person_rel.get("target_ref"))
            if organization and organization.get("type") == "organization":
                affiliations.append(organization.get("name"))
        contacts[role][full_name] = {
            "email_list": _normalize_list(
                person.get("email_list", person.get("emails", []))
            ),
            "address_list": _normalize_list(
                person.get("address_list", person.get("addresses", []))
            ),
            "phone_list": _normalize_list(
                person.get("phone_list", person.get("phones", []))
            ),
            "affiliation_list": _normalize_list(affiliations),
        }
    return contacts


def _parse_mhd_protocols(
    nodes_by_id: dict[str, dict[str, Any]],
    rels_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    protocols: dict[str, dict[str, Any]] = {}
    for node in nodes_by_id.values():
        if node.get("type") != "protocol":
            continue
        name = node.get("name")
        if not name:
            continue

        protocol_type = nodes_by_id.get(node.get("protocol_type_ref"))
        protocol_entry = {
            "name": name,
            "protocol_type": _cv_term_from_node(protocol_type),
            "description": node.get("description"),
            "protocol_parameters": [],
        }

        for rel in rels_by_source.get(node["id"], []):
            if rel.get("relationship_name") not in {
                "has-protocol-definition",
                "has-parameter-definition",
            }:
                continue
            definition = nodes_by_id.get(rel.get("target_ref"))
            if not definition or definition.get("type") != "parameter-definition":
                continue
            parameter_type = nodes_by_id.get(definition.get("parameter_type_ref"))
            key = _cv_term_from_node(parameter_type, fallback_name=definition.get("name", ""))
            values = []
            for def_rel in rels_by_source.get(definition["id"], []):
                if def_rel.get("relationship_name") != "has-instance":
                    continue
                value_node = nodes_by_id.get(def_rel.get("target_ref"))
                if not value_node:
                    continue
                values.append(_cv_term_from_node(value_node))
            if values:
                protocol_entry["protocol_parameters"].append(
                    {"key": key, "values": values}
                )

        protocols[name] = protocol_entry
    return protocols


def enrich_announcement_file(mhd_model_file_path: Path, announcement_file_path: Path) -> None:
    mhd_data = _load_json(mhd_model_file_path)
    announcement_data = _load_json(announcement_file_path)

    graph = mhd_data.get("graph", {})
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    nodes_by_id = {node["id"]: node for node in nodes if "id" in node}
    rels_by_source, rels_by_target = _build_relationship_indexes(relationships)
    study_id = next(
        (node["id"] for node in nodes if node.get("type") == "study"),
        None,
    )

    contacts = _parse_mhd_contacts(nodes_by_id, rels_by_source, rels_by_target, study_id)
    protocols = _parse_mhd_protocols(nodes_by_id, rels_by_source)

    for group_name in ("submitters", "principal_investigators"):
        enriched_contacts = []
        for item in announcement_data.get(group_name, []) or []:
            if not isinstance(item, dict):
                enriched_contacts.append(item)
                continue
            full_name = item.get("full_name")
            contact = contacts.get(group_name, {}).get(full_name, {})
            merged = dict(item)
            if contact.get("email_list"):
                merged["email_list"] = contact["email_list"]
            if not merged.get("affiliation_list") and contact.get("affiliation_list"):
                merged["affiliation_list"] = contact["affiliation_list"]
            enriched_contacts.append(merged)
        if enriched_contacts:
            announcement_data[group_name] = enriched_contacts

    announcement_protocols = {
        item.get("name"): dict(item)
        for item in (announcement_data.get("protocols", []) or [])
        if isinstance(item, dict) and item.get("name")
    }
    for name, protocol in protocols.items():
        existing = announcement_protocols.get(name, {})
        merged = {
            "name": name,
            "protocol_type": existing.get("protocol_type") or protocol["protocol_type"],
        }
        description = existing.get("description") or protocol.get("description")
        if description:
            merged["description"] = description
        protocol_parameters = existing.get("protocol_parameters") or protocol.get(
            "protocol_parameters"
        )
        if protocol_parameters:
            merged["protocol_parameters"] = protocol_parameters
        if existing.get("relates_assay_names"):
            merged["relates_assay_names"] = existing["relates_assay_names"]
        announcement_protocols[name] = merged

    if announcement_protocols:
        announcement_data["protocols"] = list(announcement_protocols.values())

    announcement_file_path.write_text(
        f"{json.dumps(announcement_data, indent=2)}\n",
        encoding="utf-8",
    )
