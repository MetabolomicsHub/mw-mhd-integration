from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUMMARY_URL_TEMPLATE = (
    "https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/summary"
)
FILES_URL_TEMPLATE = (
    "https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/files"
)
STUDY_DOWNLOAD_URL_TEMPLATE = (
    "https://www.metabolomicsworkbench.org/studydownload/{filename}"
)
GNPS_USI_URL_TEMPLATE = "https://dashboard.gnps2.org/?usi=mzspec:{study_id}:{name}"

RAW_FILE_EXTENSIONS = {
    ".raw",
    ".mzml",
    ".mzxml",
    ".cdf",
    ".mzdata",
    ".wiff",
    ".d",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")


def _fetch_json(url: str, cache_path: Path) -> dict[str, Any]:
    if cache_path.exists():
        return _read_json(cache_path)

    response = httpx.get(url, timeout=120)
    response.raise_for_status()
    data = response.json()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(cache_path, data)
    return data


def fetch_mw_study_summary(study_id: str, data_path: Path) -> dict[str, Any]:
    return _fetch_json(
        SUMMARY_URL_TEMPLATE.format(study_id=study_id),
        data_path / f"{study_id}_summary.json",
    )


def fetch_mw_study_files(study_id: str, data_path: Path) -> dict[str, Any]:
    return _fetch_json(
        FILES_URL_TEMPLATE.format(study_id=study_id),
        data_path / f"{study_id}_files.json",
    )


def _should_fetch_summary(study_node: dict[str, Any]) -> bool:
    if not study_node.get("license"):
        return True
    if not study_node.get("submission_date"):
        return True
    release_date = study_node.get("public_release_date")
    if not release_date:
        return True
    # The current converter often falls back to using submit date for release date.
    if release_date == study_node.get("submission_date"):
        return True
    return False


def _is_raw_like_file(name: str) -> bool:
    return Path(name).suffix.lower() in RAW_FILE_EXTENSIONS


def _normalize_unique(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    normalized = []
    for item in items:
        key = (item["name"], tuple(item["url_list"]))
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _extract_raw_file_candidates(study_id: str, files_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for filename in files_payload.get("files", []) or []:
        if not isinstance(filename, str):
            continue
        if _is_raw_like_file(filename):
            candidates.append(
                {
                    "name": filename,
                    "extension": Path(filename).suffix,
                    "url_list": [GNPS_USI_URL_TEMPLATE.format(study_id=study_id, name=filename)],
                }
            )

    for archive_name, members in (files_payload.get("compressed_file_content") or {}).items():
        if not isinstance(archive_name, str) or not isinstance(members, list):
            continue
        archive_url = STUDY_DOWNLOAD_URL_TEMPLATE.format(filename=archive_name)
        for member in members:
            member_name = member.get("name") if isinstance(member, dict) else None
            if not isinstance(member_name, str) or not _is_raw_like_file(member_name):
                continue
            candidates.append(
                {
                    "name": member_name,
                    "extension": Path(member_name).suffix,
                    "url_list": [
                        GNPS_USI_URL_TEMPLATE.format(study_id=study_id, name=member_name),
                        archive_url,
                    ],
                }
            )

    return _normalize_unique(candidates)


def _add_raw_file_nodes(
    study_node: dict[str, Any],
    graph: dict[str, Any],
    study_id: str,
    raw_file_candidates: list[dict[str, Any]],
) -> int:
    nodes = graph.setdefault("nodes", [])
    relationships = graph.setdefault("relationships", [])

    existing_names = {
        node.get("name")
        for node in nodes
        if node.get("type") == "raw-data-file" and node.get("name")
    }

    added = 0
    for candidate in raw_file_candidates:
        if candidate["name"] in existing_names:
            continue
        existing_names.add(candidate["name"])
        raw_node_id = f"mhd--raw-data-file--{uuid.uuid4()}"
        nodes.append(
            {
                "id": raw_node_id,
                "type": "raw-data-file",
                "repository_identifier": (
                    f"{study_node.get('repository_identifier', study_id)}:{candidate['name']}"
                ),
                "name": candidate["name"],
                "extension": candidate["extension"],
                "url_list": candidate["url_list"],
            }
        )
        relationships.append(
            {
                "id": f"rel--relationship--{uuid.uuid4()}",
                "type": "relationship",
                "source_ref": study_node["id"],
                "relationship_name": "has-raw-data-file",
                "target_ref": raw_node_id,
                "reverse_relationship_name": "created-in",
            }
        )
        added += 1
    return added


def enrich_mhd_file(mhd_file_path: Path, data_path: Path | None = None) -> dict[str, Any]:
    if data_path is None:
        data_path = Path(".outputs/mw_dataset")

    mhd_data = _read_json(mhd_file_path)
    graph = mhd_data.get("graph", {})
    study_node = next(
        (node for node in graph.get("nodes", []) if node.get("type") == "study"),
        None,
    )
    if not study_node:
        return {"updated": False, "reason": "study_node_not_found"}

    study_id = study_node.get("repository_identifier")
    if not study_id:
        return {"updated": False, "reason": "study_id_not_found"}

    updates = {
        "summary_enriched": False,
        "raw_files_added": 0,
        "updated": False,
    }

    if _should_fetch_summary(study_node):
        try:
            summary = fetch_mw_study_summary(study_id, data_path)
            submission_date = summary.get("submission_date")
            release_date = summary.get("release_date")
            license_url = summary.get("license_url")
            study_url = summary.get("study_url")

            if submission_date and not study_node.get("submission_date"):
                study_node["submission_date"] = f"{submission_date}T00:00:00"
                updates["summary_enriched"] = True
            if release_date and (
                not study_node.get("public_release_date")
                or study_node.get("public_release_date")
                == study_node.get("submission_date")
            ):
                study_node["public_release_date"] = f"{release_date}T00:00:00"
                updates["summary_enriched"] = True
            if license_url and not study_node.get("license"):
                study_node["license"] = license_url
                updates["summary_enriched"] = True
            if study_url and not study_node.get("dataset_url_list"):
                study_node["dataset_url_list"] = [study_url]
                updates["summary_enriched"] = True
        except Exception as ex:
            logger.warning("%s: summary enrichment failed. %s", study_id, ex)

    existing_raw_file_nodes = [
        node for node in graph.get("nodes", []) if node.get("type") == "raw-data-file"
    ]
    if not existing_raw_file_nodes:
        try:
            files_payload = fetch_mw_study_files(study_id, data_path)
            raw_file_candidates = _extract_raw_file_candidates(study_id, files_payload)
            updates["raw_files_added"] = _add_raw_file_nodes(
                study_node, graph, study_id, raw_file_candidates
            )
        except Exception as ex:
            logger.warning("%s: raw file enrichment failed. %s", study_id, ex)

    updates["updated"] = updates["summary_enriched"] or updates["raw_files_added"] > 0
    if updates["updated"]:
        _write_json(mhd_file_path, mhd_data)
    return updates
