from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

STUDY_ID_RE = re.compile(r"^ST\d{6}$")

PRESENT = "__present__"

MHD_EXPECTED = "expected"
MHD_UNMAPPED = "unmapped"

ANNOUNCEMENT_EXPECTED = "expected"
ANNOUNCEMENT_UNKNOWN = "unknown"
ANNOUNCEMENT_LIKELY_NOT_EXPECTED = "likely_not_expected"


def is_study_id(value: str) -> bool:
    return bool(STUDY_ID_RE.match(value))


def normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value or value == "-":
        return None
    return value


def normalize_list(values: list[Any]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        item = normalize_scalar(value)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_source_context(study_id: str, source_path: Path) -> dict[str, Any]:
    metabolites_path = source_path.with_name(f"{study_id}_metabolites.json")
    return {
        "study_id": study_id,
        "source_data": load_json(source_path),
        "metabolites_data": load_json(metabolites_path) if metabolites_path.exists() else {},
    }


def select_ms_analyses(source_context: dict[str, Any]) -> list[dict[str, Any]]:
    source_data = source_context["source_data"]
    return [
        payload
        for _analysis_id, payload in sorted(source_data.items())
        if isinstance(payload, dict)
        and "MS" in payload.get("ANALYSIS", {}).get("ANALYSIS_TYPE", "")
    ]


def first_ms_analysis(source_context: dict[str, Any]) -> dict[str, Any]:
    analyses = select_ms_analyses(source_context)
    return analyses[0] if analyses else {}


def collect_source_values(
    source_context: dict[str, Any], section_name: str, field_name: str
) -> list[str]:
    values = []
    for analysis in select_ms_analyses(source_context):
        section = analysis.get(section_name, {})
        if not isinstance(section, dict):
            continue
        values.append(section.get(field_name))
    return normalize_list(values)


def source_first_analysis_values(
    source_context: dict[str, Any], section_name: str, field_name: str
) -> list[str]:
    analysis = first_ms_analysis(source_context)
    section = analysis.get(section_name, {}) if analysis else {}
    if not isinstance(section, dict):
        return []
    return normalize_list([section.get(field_name)])


def source_protocol_present(
    source_context: dict[str, Any],
    section_name: str,
    description_field_name: str | None = None,
    ignore_if_no_description: bool = False,
) -> list[str]:
    for analysis in select_ms_analyses(source_context):
        section = analysis.get(section_name, {})
        if not isinstance(section, dict) or not section:
            continue
        if ignore_if_no_description:
            desc = normalize_scalar(section.get(description_field_name))
            if not desc:
                continue
        return [PRESENT]
    return []


def source_contact_values(
    source_context: dict[str, Any], section_name: str, field_name: str
) -> list[str]:
    analysis = first_ms_analysis(source_context)
    section = analysis.get(section_name, {}) if analysis else {}
    if not isinstance(section, dict):
        return []

    if field_name == "full_name":
        first_name = normalize_scalar(section.get("FIRST_NAME"))
        last_name = normalize_scalar(section.get("LAST_NAME"))
        return normalize_list([" ".join(x for x in (first_name, last_name) if x)])

    mapping = {
        "email": "EMAIL",
        "phone": "PHONE",
        "address": "ADDRESS",
        "affiliation": "INSTITUTE",
    }
    return normalize_list([section.get(mapping[field_name])])


def normalize_doi(value: Any) -> str | None:
    value = normalize_scalar(value)
    if not value:
        return None
    value = value.replace("http://dx.doi.org/", "").replace("https://doi.org/", "")
    return normalize_scalar(value)


def source_project_doi(source_context: dict[str, Any]) -> list[str]:
    analysis = first_ms_analysis(source_context)
    project = analysis.get("PROJECT", {}) if analysis else {}
    if not isinstance(project, dict):
        return []
    return normalize_list([normalize_doi(project.get("DOI"))])


def source_descriptor_names(source_context: dict[str, Any]) -> list[str]:
    analysis = first_ms_analysis(source_context)
    if not analysis:
        return []
    study = analysis.get("STUDY", {})
    project = analysis.get("PROJECT", {})
    values = []
    if isinstance(study, dict):
        values.append(study.get("STUDY_TYPE"))
    if isinstance(project, dict):
        values.append(project.get("PROJECT_TYPE"))
    return normalize_list(values)


def source_publication_titles(source_context: dict[str, Any]) -> list[str]:
    analysis = first_ms_analysis(source_context)
    if not analysis:
        return []
    values = []
    for section_name in ("STUDY", "PROJECT"):
        section = analysis.get(section_name, {})
        if isinstance(section, dict):
            values.append(section.get("PUBLICATIONS"))
    return normalize_list(values)


def source_metadata_file_names(source_context: dict[str, Any]) -> list[str]:
    study_id = source_context["study_id"]
    names = []
    source_data = source_context["source_data"]
    for analysis_id in sorted(source_data):
        payload = source_data.get(analysis_id)
        if not isinstance(payload, dict):
            continue
        names.append(f"{study_id}_{analysis_id}.txt")
    return normalize_list(names)


def source_reported_metabolite_names(source_context: dict[str, Any]) -> list[str]:
    metabolites_data = source_context["metabolites_data"]
    metabolites = metabolites_data.get("metabolites", []) if metabolites_data else []
    values = []
    for item in metabolites:
        if isinstance(item, dict):
            values.append(item.get("metabolite_name"))
    return normalize_list(values)


def source_subject_sample_factor_section(source_context: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = first_ms_analysis(source_context)
    section = analysis.get("SUBJECT_SAMPLE_FACTORS", {}) if analysis else {}
    return section if isinstance(section, list) else []


def source_factor_names(source_context: dict[str, Any]) -> list[str]:
    rows = source_subject_sample_factor_section(source_context)
    if not rows:
        return []

    organism_part_field = source_organism_part_factor_field_name(source_context)
    names = []
    for key in rows[0].get("Factors", {}):
        if key == organism_part_field:
            continue
        names.append(key.replace("_", " ").lower())
    return normalize_list(names)


def source_factor_values(source_context: dict[str, Any]) -> list[str]:
    rows = source_subject_sample_factor_section(source_context)
    organism_part_field = source_organism_part_factor_field_name(source_context)
    values = []
    for row in rows:
        factors = row.get("Factors", {})
        if not isinstance(factors, dict):
            continue
        for key, value in factors.items():
            if key == organism_part_field:
                continue
            values.append(value)
    return normalize_list(values)


def source_organism_values(source_context: dict[str, Any]) -> list[str]:
    return source_first_analysis_values(source_context, "SUBJECT", "SUBJECT_SPECIES")


def source_organism_part_factor_field_name(source_context: dict[str, Any]) -> str | None:
    rows = source_subject_sample_factor_section(source_context)
    if not rows:
        return None
    factors = rows[0].get("Factors", {})
    if not isinstance(factors, dict):
        return None
    for key in factors:
        candidate = key.replace("_", " ").lower()
        if candidate in {"sample source", "tissue"}:
            return key
    return None


def source_organism_part_values(source_context: dict[str, Any]) -> list[str]:
    rows = source_subject_sample_factor_section(source_context)
    organism_part_field = source_organism_part_factor_field_name(source_context)
    values = []
    if organism_part_field:
        for row in rows:
            factors = row.get("Factors", {})
            if isinstance(factors, dict):
                values.append(factors.get(organism_part_field))
        return normalize_list(values)

    analysis = first_ms_analysis(source_context)
    collection = analysis.get("COLLECTION", {}) if analysis else {}
    if not isinstance(collection, dict):
        return []
    return normalize_list([collection.get("SAMPLE_TYPE")])


def source_raw_data_file_names(source_context: dict[str, Any]) -> list[str]:
    values = []
    for row in source_subject_sample_factor_section(source_context):
        sample_data = row.get("Additional sample data", {})
        if not isinstance(sample_data, dict):
            continue
        for key, raw_names in sample_data.items():
            if not key.upper().startswith("RAW_FILE_NAME"):
                continue
            if isinstance(raw_names, str):
                values.append(raw_names)
            elif isinstance(raw_names, list):
                values.extend(raw_names)
    return normalize_list(values)


def build_relationship_indexes(
    relationships: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    by_target: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        by_source.setdefault(rel.get("source_ref", ""), []).append(rel)
        by_target.setdefault(rel.get("target_ref", ""), []).append(rel)
    return by_source, by_target


def parse_definition_instances(
    nodes_by_id: dict[str, dict[str, Any]],
    rels_by_source: dict[str, list[dict[str, Any]]],
    definition_type: str,
    value_types: set[str],
    key_name_getter: Callable[[dict[str, Any], dict[str, dict[str, Any]]], str | None],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for node in nodes_by_id.values():
        if node.get("type") != definition_type:
            continue
        key_name = key_name_getter(node, nodes_by_id)
        if not key_name:
            continue
        key_name = key_name.lower()
        values = []
        for rel in rels_by_source.get(node["id"], []):
            if rel.get("relationship_name") != "has-instance":
                continue
            value_node = nodes_by_id.get(rel.get("target_ref"))
            if not value_node or value_node.get("type") not in value_types:
                continue
            values.append(value_node.get("value", value_node.get("name")))
        result[key_name] = normalize_list(result.get(key_name, []) + values)
    return result


def parse_mhd_context(mhd_data: dict[str, Any]) -> dict[str, Any]:
    graph = mhd_data.get("graph", {})
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    nodes_by_id = {node["id"]: node for node in nodes if "id" in node}
    rels_by_source, rels_by_target = build_relationship_indexes(relationships)

    study_node = next((node for node in nodes if node.get("type") == "study"), {})
    project_node = next((node for node in nodes if node.get("type") == "project"), {})
    study_id = study_node.get("id")

    descriptor_names = []
    for rel in relationships:
        if rel.get("relationship_name") != "described-as":
            continue
        if rel.get("source_ref") not in {study_node.get("id"), project_node.get("id")}:
            continue
        descriptor = nodes_by_id.get(rel.get("target_ref"))
        if descriptor and descriptor.get("type") == "descriptor":
            descriptor_names.append(descriptor.get("name"))

    publication_titles = normalize_list(
        [node.get("title") for node in nodes if node.get("type") == "publication"]
    )

    protocol_ids_by_name: dict[str, list[str]] = {}
    for node in nodes:
        if node.get("type") == "protocol" and normalize_scalar(node.get("name")):
            protocol_ids_by_name.setdefault(node["name"], []).append(node["id"])

    protocol_parameters: dict[str, dict[str, list[str]]] = {}
    protocol_descriptions: dict[str, list[str]] = {}
    for protocol_name, protocol_ids in protocol_ids_by_name.items():
        protocol_parameters[protocol_name] = {}
        descriptions = []
        for protocol_id in protocol_ids:
            protocol_node = nodes_by_id.get(protocol_id, {})
            descriptions.append(protocol_node.get("description"))
            for rel in rels_by_source.get(protocol_id, []):
                if rel.get("relationship_name") not in {
                    "has-parameter-definition",
                    "has-protocol-definition",
                }:
                    continue
                definition = nodes_by_id.get(rel.get("target_ref"))
                if not definition or definition.get("type") != "parameter-definition":
                    continue
                definition_name = normalize_scalar(definition.get("name"))
                if not definition_name:
                    continue
                values = []
                for def_rel in rels_by_source.get(definition["id"], []):
                    if def_rel.get("relationship_name") != "has-instance":
                        continue
                    value_node = nodes_by_id.get(def_rel.get("target_ref"))
                    if not value_node:
                        continue
                    values.append(value_node.get("value", value_node.get("name")))
                protocol_parameters[protocol_name][definition_name] = normalize_list(
                    protocol_parameters[protocol_name].get(definition_name, []) + values
                )
        protocol_descriptions[protocol_name] = normalize_list(descriptions)

    contacts_by_role = {"submitter": [], "principal_investigator": []}
    if study_id:
        relationship_to_role = {
            "submits": "submitter",
            "principal-investigator-of": "principal_investigator",
        }
        for rel in rels_by_target.get(study_id, []):
            role = relationship_to_role.get(rel.get("relationship_name"))
            if not role:
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
            contacts_by_role[role].append(
                {
                    "full_name": normalize_list([person.get("full_name")]),
                    "email": normalize_list(
                        person.get("email_list", person.get("emails", []))
                    ),
                    "phone": normalize_list(
                        person.get("phone_list", person.get("phones", []))
                    ),
                    "address": normalize_list(
                        person.get("address_list", person.get("addresses", []))
                    ),
                    "affiliation": normalize_list(affiliations),
                }
            )

    files_by_type: dict[str, list[str]] = {}
    for node in nodes:
        node_type = node.get("type")
        if node_type in {"metadata-file", "result-file", "raw-data-file"}:
            files_by_type.setdefault(node_type, []).append(node.get("name"))
    for key in list(files_by_type):
        files_by_type[key] = normalize_list(files_by_type[key])

    factor_values_by_name = parse_definition_instances(
        nodes_by_id,
        rels_by_source,
        "factor-definition",
        {"factor-value", "x-mw-factor-value"},
        lambda definition, _nodes_by_id: normalize_scalar(definition.get("name")),
    )

    characteristic_values_by_type = parse_definition_instances(
        nodes_by_id,
        rels_by_source,
        "characteristic-definition",
        {"characteristic-value"},
        lambda definition, nodes_by_id: normalize_scalar(
            nodes_by_id.get(definition.get("characteristic_type_ref"), {}).get("name")
        ),
    )

    metabolite_names = normalize_list(
        [node.get("name") for node in nodes if node.get("type") == "metabolite"]
    )

    return {
        "study_node": study_node,
        "project_node": project_node,
        "descriptor_names": normalize_list(descriptor_names),
        "publication_titles": publication_titles,
        "protocol_ids_by_name": protocol_ids_by_name,
        "protocol_parameters": protocol_parameters,
        "protocol_descriptions": protocol_descriptions,
        "contacts_by_role": contacts_by_role,
        "files_by_type": files_by_type,
        "factor_values_by_name": factor_values_by_name,
        "characteristic_values_by_type": characteristic_values_by_type,
        "metabolite_names": metabolite_names,
    }


def mhd_top_level_values(context: dict[str, Any], node_name: str, field_name: str) -> list[str]:
    return normalize_list([context.get(node_name, {}).get(field_name)])


def mhd_protocol_present(context: dict[str, Any], protocol_name: str) -> list[str]:
    return [PRESENT] if context["protocol_ids_by_name"].get(protocol_name) else []


def mhd_protocol_description(context: dict[str, Any], protocol_name: str) -> list[str]:
    return context["protocol_descriptions"].get(protocol_name, [])


def mhd_protocol_parameter_values(
    context: dict[str, Any], protocol_name: str, parameter_name: str
) -> list[str]:
    return context["protocol_parameters"].get(protocol_name, {}).get(parameter_name, [])


def mhd_contact_values(context: dict[str, Any], role: str, field_name: str) -> list[str]:
    values = []
    for contact in context["contacts_by_role"].get(role, []):
        values.extend(contact.get(field_name, []))
    return normalize_list(values)


def mhd_file_names(context: dict[str, Any], node_type: str) -> list[str]:
    return context["files_by_type"].get(node_type, [])


def mhd_factor_names(context: dict[str, Any]) -> list[str]:
    return normalize_list(list(context["factor_values_by_name"].keys()))


def mhd_factor_values(context: dict[str, Any]) -> list[str]:
    values = []
    for items in context["factor_values_by_name"].values():
        values.extend(items)
    return normalize_list(values)


def mhd_characteristic_values(context: dict[str, Any], characteristic_type_name: str) -> list[str]:
    return context["characteristic_values_by_type"].get(characteristic_type_name.lower(), [])


def mhd_reported_metabolites(context: dict[str, Any]) -> list[str]:
    return context["metabolite_names"]


def mhd_descriptor_names(context: dict[str, Any]) -> list[str]:
    return context["descriptor_names"]


def mhd_publication_titles(context: dict[str, Any]) -> list[str]:
    return context["publication_titles"]


def parse_announcement_context(announcement_data: dict[str, Any]) -> dict[str, Any]:
    contacts_by_role = {"submitter": [], "principal_investigator": []}
    role_map = {
        "submitter": "submitters",
        "principal_investigator": "principal_investigators",
    }
    for role, key in role_map.items():
        for item in announcement_data.get(key, []):
            if not isinstance(item, dict):
                continue
            contacts_by_role[role].append(
                {
                    "full_name": normalize_list([item.get("full_name")]),
                    "email": normalize_list(item.get("email_list", item.get("emails", []))),
                    "phone": normalize_list(item.get("phone_list", item.get("phones", []))),
                    "address": normalize_list(
                        item.get("address_list", item.get("addresses", []))
                    ),
                    "affiliation": normalize_list(item.get("affiliation_list", [])),
                }
            )

    protocol_names = []
    protocol_descriptions: dict[str, list[str]] = {}
    protocol_parameters: dict[str, dict[str, list[str]]] = {}
    for item in announcement_data.get("protocols", []):
        if isinstance(item, dict):
            protocol_name = normalize_scalar(item.get("name"))
            if not protocol_name:
                continue
            protocol_names.append(protocol_name)
            protocol_descriptions[protocol_name] = normalize_list([item.get("description")])
            params_by_name: dict[str, list[str]] = {}
            for kv in item.get("protocol_parameters", []) or []:
                if not isinstance(kv, dict):
                    continue
                key_name = normalize_scalar(kv.get("key", {}).get("name"))
                if not key_name:
                    continue
                values = []
                for value in kv.get("values", []) or []:
                    if not isinstance(value, dict):
                        continue
                    values.append(value.get("name", value.get("value")))
                params_by_name[key_name] = normalize_list(values)
            protocol_parameters[protocol_name] = params_by_name

    factor_values_by_name: dict[str, list[str]] = {}
    for item in announcement_data.get("study_factors", []):
        if not isinstance(item, dict):
            continue
        key_name = normalize_scalar(item.get("key", {}).get("name"))
        if not key_name:
            continue
        values = [value.get("name") for value in item.get("values", []) if isinstance(value, dict)]
        factor_values_by_name[key_name] = normalize_list(values)

    characteristic_values_by_type: dict[str, list[str]] = {}
    for item in announcement_data.get("characteristic_values", []):
        if not isinstance(item, dict):
            continue
        key_name = normalize_scalar(item.get("key", {}).get("name"))
        if not key_name:
            continue
        values = [value.get("name") for value in item.get("values", []) if isinstance(value, dict)]
        characteristic_values_by_type[key_name] = normalize_list(values)

    metadata_file_names = [
        item.get("name")
        for item in announcement_data.get("repository_metadata_file_list", [])
        if isinstance(item, dict)
    ]
    raw_data_file_names = [
        item.get("name")
        for item in announcement_data.get("raw_data_file_list", [])
        if isinstance(item, dict)
    ]
    result_file_names = [
        item.get("name")
        for item in announcement_data.get("result_file_list", [])
        if isinstance(item, dict)
    ]
    reported_metabolite_names = [
        item.get("name")
        for item in announcement_data.get("reported_metabolites", [])
        if isinstance(item, dict)
    ]

    descriptor_names = [
        item.get("name")
        for item in announcement_data.get("descriptors", []) or []
        if isinstance(item, dict)
    ]

    publication_titles = []
    publications = announcement_data.get("publications")
    if isinstance(publications, list):
        for item in publications:
            if isinstance(item, dict):
                publication_titles.append(item.get("title") or item.get("name"))
    elif isinstance(publications, dict):
        publication_titles.append(publications.get("title") or publications.get("name"))

    return {
        "announcement_data": announcement_data,
        "contacts_by_role": contacts_by_role,
        "protocol_names": normalize_list(protocol_names),
        "protocol_descriptions": protocol_descriptions,
        "protocol_parameters": protocol_parameters,
        "factor_values_by_name": factor_values_by_name,
        "characteristic_values_by_type": characteristic_values_by_type,
        "metadata_file_names": normalize_list(metadata_file_names),
        "raw_data_file_names": normalize_list(raw_data_file_names),
        "result_file_names": normalize_list(result_file_names),
        "reported_metabolite_names": normalize_list(reported_metabolite_names),
        "descriptor_names": normalize_list(descriptor_names),
        "publication_titles": normalize_list(publication_titles),
    }


def announcement_top_level_values(context: dict[str, Any], field_name: str) -> list[str]:
    return normalize_list([context["announcement_data"].get(field_name)])


def announcement_protocol_present(
    context: dict[str, Any], protocol_name: str
) -> list[str]:
    return [PRESENT] if protocol_name in context["protocol_names"] else []


def announcement_protocol_description(
    context: dict[str, Any], protocol_name: str
) -> list[str]:
    return context["protocol_descriptions"].get(protocol_name, [])


def announcement_protocol_parameter_values(
    context: dict[str, Any], protocol_name: str, parameter_name: str
) -> list[str]:
    return context["protocol_parameters"].get(protocol_name, {}).get(parameter_name, [])


def announcement_contact_values(
    context: dict[str, Any], role: str, field_name: str
) -> list[str]:
    values = []
    for contact in context["contacts_by_role"].get(role, []):
        values.extend(contact.get(field_name, []))
    return normalize_list(values)


def announcement_factor_names(context: dict[str, Any]) -> list[str]:
    return normalize_list(list(context["factor_values_by_name"].keys()))


def announcement_factor_values(context: dict[str, Any]) -> list[str]:
    values = []
    for items in context["factor_values_by_name"].values():
        values.extend(items)
    return normalize_list(values)


def announcement_characteristic_values(
    context: dict[str, Any], characteristic_type_name: str
) -> list[str]:
    return context["characteristic_values_by_type"].get(characteristic_type_name, [])


def announcement_metadata_file_names(context: dict[str, Any]) -> list[str]:
    return context["metadata_file_names"]


def announcement_raw_data_file_names(context: dict[str, Any]) -> list[str]:
    return context["raw_data_file_names"]


def announcement_result_file_names(context: dict[str, Any]) -> list[str]:
    return context["result_file_names"]


def announcement_reported_metabolites(context: dict[str, Any]) -> list[str]:
    return context["reported_metabolite_names"]


def announcement_descriptor_names(context: dict[str, Any]) -> list[str]:
    return context["descriptor_names"]


def announcement_publication_titles(context: dict[str, Any]) -> list[str]:
    return context["publication_titles"]


def compare_sets(source_values: list[str], target_values: list[str]) -> dict[str, Any]:
    source_set = set(source_values)
    target_set = set(target_values)
    return {
        "source": source_values,
        "target": target_values,
        "matched": sorted(source_set & target_set),
        "missing": sorted(source_set - target_set),
        "unexpected": sorted(target_set - source_set),
    }


def classify_field(
    source_values: list[str],
    mhd_values: list[str],
    announcement_values: list[str],
    mhd_expectation: str,
) -> str:
    if not source_values:
        return "not_in_source"
    has_mhd = bool(mhd_values)
    has_announcement = bool(announcement_values)
    if has_mhd and has_announcement:
        return "mapped_to_both"
    if has_mhd and not has_announcement:
        return "mapped_to_mhd_only"
    if not has_mhd and has_announcement:
        return "mapped_to_announcement_only"
    if mhd_expectation == MHD_UNMAPPED:
        return "unmapped_in_converter"
    return "dropped_before_mhd"


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    category: str
    description: str
    mhd_expectation: str
    announcement_expectation: str
    source_getter: Callable[[dict[str, Any]], list[str]]
    mhd_getter: Callable[[dict[str, Any]], list[str]]
    announcement_getter: Callable[[dict[str, Any]], list[str]]


def contact_field_specs() -> list[FieldSpec]:
    specs = []
    for role, section_name in (
        ("submitter", "STUDY"),
        ("principal_investigator", "PROJECT"),
    ):
        for field_name, announcement_expectation in (
            ("full_name", ANNOUNCEMENT_EXPECTED),
            ("affiliation", ANNOUNCEMENT_EXPECTED),
            ("email", ANNOUNCEMENT_EXPECTED),
            ("phone", ANNOUNCEMENT_LIKELY_NOT_EXPECTED),
            ("address", ANNOUNCEMENT_LIKELY_NOT_EXPECTED),
        ):
            specs.append(
                FieldSpec(
                    field_id=f"{role}.{field_name}",
                    category="contact",
                    description=f"{role.replace('_', ' ')} {field_name.replace('_', ' ')}",
                    mhd_expectation=MHD_EXPECTED,
                    announcement_expectation=announcement_expectation,
                    source_getter=lambda source_context, section_name=section_name, field_name=field_name: source_contact_values(
                        source_context, section_name, field_name
                    ),
                    mhd_getter=lambda mhd_context, role=role, field_name=field_name: mhd_contact_values(
                        mhd_context, role, field_name
                    ),
                    announcement_getter=lambda announcement_context, role=role, field_name=field_name: announcement_contact_values(
                        announcement_context, role, field_name
                    ),
                )
            )
    return specs


def study_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec(
            field_id="study.title",
            category="study",
            description="study title",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=lambda source_context: source_first_analysis_values(
                source_context, "STUDY", "STUDY_TITLE"
            ),
            mhd_getter=lambda mhd_context: mhd_top_level_values(
                mhd_context, "study_node", "title"
            ),
            announcement_getter=lambda announcement_context: announcement_top_level_values(
                announcement_context, "title"
            ),
        ),
        FieldSpec(
            field_id="study.description",
            category="study",
            description="study description",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=lambda source_context: source_first_analysis_values(
                source_context, "STUDY", "STUDY_SUMMARY"
            ),
            mhd_getter=lambda mhd_context: mhd_top_level_values(
                mhd_context, "study_node", "description"
            ),
            announcement_getter=lambda announcement_context: announcement_top_level_values(
                announcement_context, "description"
            ),
        ),
        FieldSpec(
            field_id="project.title",
            category="project",
            description="project title",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=lambda source_context: source_first_analysis_values(
                source_context, "PROJECT", "PROJECT_TITLE"
            ),
            mhd_getter=lambda mhd_context: mhd_top_level_values(
                mhd_context, "project_node", "title"
            ),
            announcement_getter=lambda _announcement_context: [],
        ),
        FieldSpec(
            field_id="project.description",
            category="project",
            description="project description",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=lambda source_context: source_first_analysis_values(
                source_context, "PROJECT", "PROJECT_SUMMARY"
            ),
            mhd_getter=lambda mhd_context: mhd_top_level_values(
                mhd_context, "project_node", "description"
            ),
            announcement_getter=lambda _announcement_context: [],
        ),
        FieldSpec(
            field_id="project.doi",
            category="project",
            description="project doi",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=source_project_doi,
            mhd_getter=lambda mhd_context: mhd_top_level_values(
                mhd_context, "project_node", "doi"
            ),
            announcement_getter=lambda _announcement_context: [],
        ),
        FieldSpec(
            field_id="descriptor.names",
            category="descriptor",
            description="study/project descriptor names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_descriptor_names,
            mhd_getter=mhd_descriptor_names,
            announcement_getter=announcement_descriptor_names,
        ),
        FieldSpec(
            field_id="publication.titles",
            category="publication",
            description="publication titles",
            mhd_expectation=MHD_UNMAPPED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_publication_titles,
            mhd_getter=mhd_publication_titles,
            announcement_getter=announcement_publication_titles,
        ),
    ]


def protocol_field_specs() -> list[FieldSpec]:
    configs = [
        (
            "sample_collection",
            "COLLECTION",
            "sample collection",
            "COLLECTION_SUMMARY",
            False,
            ANNOUNCEMENT_EXPECTED,
            [
                ("description", "COLLECTION_SUMMARY", None, ANNOUNCEMENT_EXPECTED),
            ],
        ),
        (
            "sample_preparation",
            "SAMPLEPREP",
            "sample preparation",
            "SAMPLEPREP_SUMMARY",
            False,
            ANNOUNCEMENT_EXPECTED,
            [
                ("description", "SAMPLEPREP_SUMMARY", None, ANNOUNCEMENT_EXPECTED),
            ],
        ),
        (
            "treatment",
            "TREATMENT",
            "treatment",
            "TREATMENT_SUMMARY",
            True,
            ANNOUNCEMENT_EXPECTED,
            [
                ("description", "TREATMENT_SUMMARY", None, ANNOUNCEMENT_EXPECTED),
            ],
        ),
        (
            "chromatography",
            "CHROMATOGRAPHY",
            "chromatography",
            "CHROMATOGRAPHY_SUMMARY",
            False,
            ANNOUNCEMENT_EXPECTED,
            [
                ("description", "CHROMATOGRAPHY_SUMMARY", None, ANNOUNCEMENT_EXPECTED),
                ("instrument_name", "INSTRUMENT_NAME", "instrument name", ANNOUNCEMENT_EXPECTED),
                ("column_name", "COLUMN_NAME", "column name", ANNOUNCEMENT_EXPECTED),
                ("chromatography_type", "CHROMATOGRAPHY_TYPE", "chromatography type", ANNOUNCEMENT_EXPECTED),
                ("methods_filename", "METHODS_FILENAME", "methods filename", ANNOUNCEMENT_EXPECTED),
                ("methods_id", "METHODS_ID", "methods id", ANNOUNCEMENT_EXPECTED),
            ],
        ),
        (
            "mass_spectrometry",
            "MS",
            "mass spectrometry",
            "MS_COMMENTS",
            False,
            ANNOUNCEMENT_EXPECTED,
            [
                ("description", "MS_COMMENTS", None, ANNOUNCEMENT_EXPECTED),
                ("instrument_name", "INSTRUMENT_NAME", "instrument name", ANNOUNCEMENT_EXPECTED),
                ("instrument_type", "INSTRUMENT_TYPE", "instrument type", ANNOUNCEMENT_EXPECTED),
                ("ms_type", "MS_TYPE", "ms type", ANNOUNCEMENT_EXPECTED),
                ("ion_mode", "ION_MODE", "ion mode", ANNOUNCEMENT_EXPECTED),
            ],
        ),
    ]

    specs = []
    for category, section_name, protocol_name, description_field_name, ignore_if_no_description, presence_expectation, fields in configs:
        specs.append(
            FieldSpec(
                field_id=f"{category}.protocol_present",
                category="protocol",
                description=f"{protocol_name} protocol presence",
                mhd_expectation=MHD_EXPECTED,
                announcement_expectation=presence_expectation,
                source_getter=lambda source_context, section_name=section_name, description_field_name=description_field_name, ignore_if_no_description=ignore_if_no_description: source_protocol_present(
                    source_context,
                    section_name,
                    description_field_name=description_field_name,
                    ignore_if_no_description=ignore_if_no_description,
                ),
                mhd_getter=lambda mhd_context, protocol_name=protocol_name: mhd_protocol_present(
                    mhd_context, protocol_name
                ),
                announcement_getter=lambda announcement_context, protocol_name=protocol_name: announcement_protocol_present(
                    announcement_context, protocol_name
                ),
            )
        )
        for field_id_suffix, source_field_name, parameter_name, announcement_expectation in fields:
            if field_id_suffix == "description":
                specs.append(
                    FieldSpec(
                        field_id=f"{category}.description",
                        category="protocol",
                        description=f"{protocol_name} description",
                        mhd_expectation=MHD_EXPECTED,
                        announcement_expectation=announcement_expectation,
                        source_getter=lambda source_context, section_name=section_name, source_field_name=source_field_name: source_first_analysis_values(
                            source_context, section_name, source_field_name
                        ),
                        mhd_getter=lambda mhd_context, protocol_name=protocol_name: mhd_protocol_description(
                            mhd_context, protocol_name
                        ),
                        announcement_getter=lambda announcement_context, protocol_name=protocol_name: announcement_protocol_description(
                            announcement_context, protocol_name
                        ),
                    )
                )
                continue
            specs.append(
                FieldSpec(
                    field_id=f"{category}.{field_id_suffix}",
                    category="protocol_parameter",
                    description=f"{protocol_name} {parameter_name}",
                    mhd_expectation=MHD_EXPECTED,
                    announcement_expectation=announcement_expectation,
                    source_getter=lambda source_context, section_name=section_name, source_field_name=source_field_name: collect_source_values(
                        source_context, section_name, source_field_name
                    ),
                    mhd_getter=lambda mhd_context, protocol_name=protocol_name, parameter_name=parameter_name: mhd_protocol_parameter_values(
                        mhd_context, protocol_name, parameter_name
                    ),
                    announcement_getter=lambda announcement_context, protocol_name=protocol_name, parameter_name=parameter_name: announcement_protocol_parameter_values(
                        announcement_context, protocol_name, parameter_name
                    ),
                )
            )
    return specs


def file_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec(
            field_id="metadata_file.names",
            category="file",
            description="metadata file names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_metadata_file_names,
            mhd_getter=lambda mhd_context: mhd_file_names(mhd_context, "metadata-file"),
            announcement_getter=announcement_metadata_file_names,
        ),
        FieldSpec(
            field_id="result_file.names",
            category="file",
            description="result file names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=lambda source_context: collect_source_values(
                source_context, "MS", "MS_RESULTS_FILE"
            ),
            mhd_getter=lambda mhd_context: mhd_file_names(mhd_context, "result-file"),
            announcement_getter=announcement_result_file_names,
        ),
        FieldSpec(
            field_id="raw_data_file.names",
            category="file",
            description="raw data file names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_raw_data_file_names,
            mhd_getter=lambda mhd_context: mhd_file_names(mhd_context, "raw-data-file"),
            announcement_getter=announcement_raw_data_file_names,
        ),
    ]


def factor_and_characteristic_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec(
            field_id="factor.names",
            category="study_design",
            description="study factor names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_factor_names,
            mhd_getter=mhd_factor_names,
            announcement_getter=announcement_factor_names,
        ),
        FieldSpec(
            field_id="factor.values",
            category="study_design",
            description="study factor values",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_factor_values,
            mhd_getter=mhd_factor_values,
            announcement_getter=announcement_factor_values,
        ),
        FieldSpec(
            field_id="characteristic.organism.values",
            category="characteristic",
            description="organism characteristic values",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_organism_values,
            mhd_getter=lambda mhd_context: mhd_characteristic_values(
                mhd_context, "organism"
            ),
            announcement_getter=lambda announcement_context: announcement_characteristic_values(
                announcement_context, "Organism"
            ),
        ),
        FieldSpec(
            field_id="characteristic.organism_part.values",
            category="characteristic",
            description="organism part characteristic values",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_organism_part_values,
            mhd_getter=lambda mhd_context: mhd_characteristic_values(
                mhd_context, "organism part"
            ),
            announcement_getter=lambda announcement_context: announcement_characteristic_values(
                announcement_context, "Organism Part"
            ),
        ),
    ]


def metabolite_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec(
            field_id="reported_metabolite.names",
            category="metabolite",
            description="reported metabolite names",
            mhd_expectation=MHD_EXPECTED,
            announcement_expectation=ANNOUNCEMENT_EXPECTED,
            source_getter=source_reported_metabolite_names,
            mhd_getter=mhd_reported_metabolites,
            announcement_getter=announcement_reported_metabolites,
        )
    ]


def unmapped_source_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec(
            field_id="analysis.laboratory_name",
            category="source_only",
            description="analysis laboratory name",
            mhd_expectation=MHD_UNMAPPED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=lambda source_context: collect_source_values(
                source_context, "ANALYSIS", "LABORATORY_NAME"
            ),
            mhd_getter=lambda _mhd_context: [],
            announcement_getter=lambda _announcement_context: [],
        ),
        FieldSpec(
            field_id="analysis.acquisition_parameters_file",
            category="source_only",
            description="acquisition parameters file",
            mhd_expectation=MHD_UNMAPPED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=lambda source_context: collect_source_values(
                source_context, "ANALYSIS", "ACQUISITION_PARAMETERS_FILE"
            ),
            mhd_getter=lambda _mhd_context: [],
            announcement_getter=lambda _announcement_context: [],
        ),
        FieldSpec(
            field_id="analysis.processing_parameters_file",
            category="source_only",
            description="processing parameters file",
            mhd_expectation=MHD_UNMAPPED,
            announcement_expectation=ANNOUNCEMENT_LIKELY_NOT_EXPECTED,
            source_getter=lambda source_context: collect_source_values(
                source_context, "ANALYSIS", "PROCESSING_PARAMETERS_FILE"
            ),
            mhd_getter=lambda _mhd_context: [],
            announcement_getter=lambda _announcement_context: [],
        ),
    ]


FIELD_SPECS = (
    study_field_specs()
    + contact_field_specs()
    + protocol_field_specs()
    + file_field_specs()
    + factor_and_characteristic_field_specs()
    + metabolite_field_specs()
    + unmapped_source_field_specs()
)


def audit_study(
    study_id: str,
    source_path: Path,
    mhd_path: Path,
    announcement_path: Path,
) -> dict[str, Any]:
    source_context = load_source_context(study_id, source_path)
    mhd_context = parse_mhd_context(load_json(mhd_path)) if mhd_path.exists() else {}
    announcement_context = (
        parse_announcement_context(load_json(announcement_path))
        if announcement_path.exists()
        else {}
    )

    fields = []
    for spec in FIELD_SPECS:
        source_values = spec.source_getter(source_context)
        mhd_values = spec.mhd_getter(mhd_context) if mhd_context else []
        announcement_values = (
            spec.announcement_getter(announcement_context) if announcement_context else []
        )
        classification = classify_field(
            source_values,
            mhd_values,
            announcement_values,
            spec.mhd_expectation,
        )
        fields.append(
            {
                "field_id": spec.field_id,
                "category": spec.category,
                "description": spec.description,
                "mhd_expectation": spec.mhd_expectation,
                "announcement_expectation": spec.announcement_expectation,
                "classification": classification,
                "source": source_values,
                "mhd": compare_sets(source_values, mhd_values),
                "announcement": compare_sets(source_values, announcement_values),
            }
        )

    return {
        "study_id": study_id,
        "files": {
            "source": str(source_path),
            "mhd": str(mhd_path),
            "announcement": str(announcement_path),
        },
        "fields": fields,
    }


def summarize_audits(audits: list[dict[str, Any]]) -> dict[str, Any]:
    per_field: dict[str, dict[str, Any]] = {}
    for spec in FIELD_SPECS:
        per_field[spec.field_id] = {
            "field_id": spec.field_id,
            "category": spec.category,
            "description": spec.description,
            "mhd_expectation": spec.mhd_expectation,
            "announcement_expectation": spec.announcement_expectation,
            "studies_with_source_value": 0,
            "mhd_present_count": 0,
            "announcement_present_count": 0,
            "classification_counts": Counter(),
        }

    for audit in audits:
        for field in audit["fields"]:
            entry = per_field[field["field_id"]]
            if field["source"]:
                entry["studies_with_source_value"] += 1
            if field["mhd"]["target"]:
                entry["mhd_present_count"] += 1
            if field["announcement"]["target"]:
                entry["announcement_present_count"] += 1
            entry["classification_counts"][field["classification"]] += 1

    summary_fields = []
    for spec in FIELD_SPECS:
        entry = per_field[spec.field_id]
        summary_fields.append(
            {
                **{
                    key: value
                    for key, value in entry.items()
                    if key != "classification_counts"
                },
                "classification_counts": dict(entry["classification_counts"]),
            }
        )

    return {"fields": summary_fields}


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
            "Audit semantic field coverage from MW source JSON to canonical MHD and "
            "legacy announcement outputs."
        )
    )
    parser.add_argument("--source-dir", default=".outputs/mw_dataset")
    parser.add_argument("--mhd-dir", default=".outputs/mhd_legacy")
    parser.add_argument("--announcement-dir", default=".outputs/mhd_legacy")
    parser.add_argument("--study-id", action="append", dest="study_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--field",
        action="append",
        dest="field_ids",
        help="Limit output to the specified semantic field id. Repeat as needed.",
    )
    parser.add_argument("-o", "--output")
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

    audits = [
        audit_study(
            study_id,
            source_dir / f"{study_id}.json",
            mhd_dir / f"{study_id}.mhd.json",
            announcement_dir / f"{study_id}.announcement.json",
        )
        for study_id in study_ids
    ]

    if args.field_ids:
        wanted = set(args.field_ids)
        audits = [
            {
                **audit,
                "fields": [field for field in audit["fields"] if field["field_id"] in wanted],
            }
            for audit in audits
        ]

    result = {
        "study_count": len(audits),
        "field_ids": args.field_ids or [spec.field_id for spec in FIELD_SPECS],
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
