import json
import logging
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class MwDataResponse(BaseModel): ...


class MetaboliteIdentification(BaseModel):
    study_id: str = ""
    analysis_id: str = ""
    analysis_summary: str = ""
    metabolite_name: str = ""
    refmet_name: str = ""


class StudySummary(BaseModel):
    study_id: str = ""
    submission_date: str = ""
    release_date: str = ""
    version: str = ""
    revision_no: str = ""
    revision_datetime: str = ""
    revision_comment: str = ""
    license: str = ""
    license_url: str = ""
    study_url: str = ""

    @field_validator(
        "revision_comment",
        "revision_datetime",
        "revision_no",
        "version",
        "submission_date",
        "release_date",
        "license",
        "study_url",
    )
    @classmethod
    def field_validator_empty_string(cls, value):
        if value is None or value == "-":
            return ""
        return value

    @field_validator("license_url")
    @classmethod
    def license_url_validator(cls, value):
        if value is None or value == "-":
            return ""
        return value.rstrip("/") + "/"


class CompressedFileItem(BaseModel):
    name: str = ""
    size: int = 0


class StudyFiles(BaseModel):
    study_id: str = ""
    files: list[str] = []
    compressed_file_content: dict[str, list[CompressedFileItem]] = {}


def fetch_all_available_mw_studies() -> list[str]:
    try:
        url = "https://www.metabolomicsworkbench.org/rest/study/study_id/ST/available"
        response = httpx.get(url, timeout=120)
        response.raise_for_status()
        data = get_response_json(response.text)

        studies = list({x.get("study_id") for x in data[0].values()} if data else set())
        studies.sort(reverse=True)
        return studies
    except Exception as ex:
        logger.error(ex)
        return []


def fetch_mw_study_files(
    study_id: str, data_path: None | Path = None
) -> None | StudyFiles:
    try:
        if not data_path:
            data_path: Path = Path(".outputs/mw_dataset")
        data_path.mkdir(parents=True, exist_ok=True)
        study_path = data_path / Path(f"{study_id}_files.json")
        if study_path.exists():
            with study_path.open() as f:
                content = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(
                    f.read()
                )
            return StudyFiles.model_validate(content.get("files", {}))
        else:
            url = f"https://www.metabolomicsworkbench.org/data/study_files.php?STUDY_ID={study_id}"
            response = httpx.get(url, timeout=20)
            response.raise_for_status()
            data_list = get_response_json(response.text)
            if not data_list or not isinstance(data_list, list):
                return None
            data = data_list[0]
            with study_path.open("w") as f:
                json.dump({"files": data}, f, indent=4)
            return StudyFiles.model_validate(data)

    except Exception as ex:
        import traceback

        traceback.print_exc()
        logger.error("%s: %s", study_id, ex)
        return None


def fetch_mw_study_summary(
    study_id: str, data_path: None | Path = None
) -> None | StudySummary:
    try:
        if not data_path:
            data_path: Path = Path(".outputs/mw_dataset")
        data_path.mkdir(parents=True, exist_ok=True)
        study_path = data_path / Path(f"{study_id}_summary.json")
        if study_path.exists():
            with study_path.open() as f:
                content = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(
                    f.read()
                )
            return StudySummary.model_validate(content.get("summary", {}))
        else:
            url = f"https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/summary"
            response = httpx.get(url, timeout=20)
            response.raise_for_status()
            data_list = get_response_json(response.text)
            if not data_list or not isinstance(data_list, list):
                return None
            data = data_list[0]
            with study_path.open("w") as f:
                json.dump({"summary": data}, f, indent=4)
            return StudySummary.model_validate(data)

    except Exception as ex:
        import traceback

        traceback.print_exc()
        logger.error("%s: %s", study_id, ex)
        return None


def fetch_mw_metabolites(
    study_id: str, data_path: None | Path = None
) -> list[MetaboliteIdentification]:
    try:
        if not data_path:
            data_path: Path = Path(".outputs/mw_dataset")
        data_path.mkdir(parents=True, exist_ok=True)
        study_path = data_path / Path(f"{study_id}_metabolites.json")
        if study_path.exists():
            with study_path.open() as f:
                content = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(
                    f.read()
                )
            items = content.get("metabolites", {})
            return [MetaboliteIdentification.model_validate(x) for x in items]
        else:
            url = f"https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/metabolites"
            response = httpx.get(url, timeout=120)
            response.raise_for_status()
            data = get_response_json(response.text)
            if not data or not data[0]:
                return []
            items = data[0]

            # if isinstance(data, dict) and "metabolite_name" in data[0]:
            if not isinstance(data[0], dict):
                with study_path.open("w") as f:
                    json.dump({"metabolites": []}, f, indent=4)
            if "metabolite_name" in data[0]:
                items = [data[0]]
            else:
                items = list(data[0].values())
            with study_path.open("w") as f:
                json.dump({"metabolites": items}, f, indent=4)
            return [MetaboliteIdentification.model_validate(x) for x in items]

    except Exception as ex:
        import traceback

        traceback.print_exc()
        logger.error("%s: %s", study_id, ex)
        return []


def fetch_mw_data(
    study_id: str,
    output_folder_path: str = ".outputs/mw_dataset",
    output_filename: None | str = None,
) -> dict[str, Any]:
    try:
        data_path: Path = Path(output_folder_path)
        data_path.mkdir(parents=True, exist_ok=True)
        output_filename = output_filename or f"{study_id}.json"
        study_path = data_path / Path(output_filename)
        if study_path.exists():
            with study_path.open() as f:
                content = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(
                    f.read()
                )
            return content
        else:
            url = f"https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/mwtab"
            response = httpx.get(url, timeout=60)
            response.raise_for_status()

            result = get_response_json(response.text)
            data = OrderedDict(
                [
                    (
                        x.get("METABOLOMICS WORKBENCH", {}).get(
                            "ANALYSIS_ID", study_id
                        ),
                        x,
                    )
                    for x in result
                ]
            )
            with study_path.open("w") as f:
                json.dump(data, f, indent=4)
        return data

    except Exception as ex:
        logger.error("%s: %s", study_id, ex)

        return None


def group_duplicates(pairs):
    """Groups values of keys that are defined multiple."""
    result = defaultdict(list)
    for k, v in pairs:
        result[k].append(v)
    optimized = {}
    for k, v in result.items():
        if v:
            if len(v) == 1:
                optimized[k] = v[0]
            else:
                optimized[k] = v
    return optimized


def patch_json_text(text):
    # PATCH the response if there are multiple analysis
    error_1_pattern = r"}\s*{"
    updated = re.sub(error_1_pattern, "}, {", text)
    # PATCH if json key value pattern is not valid
    # It fixes this "x":"y":"z" -> "x": "y z"
    error2_pattern = r'\s*"([^"]+)"\s*:\s*"([^"]+)"\s*:"'
    updated = re.sub(error2_pattern, r'"\1": "\2: ', updated)

    error3_pattern = r'"([^"]+)"\s*:\s*}'
    updated = re.sub(error3_pattern, r'"\1":{}}', updated)
    # replace invalid control characters
    updated = re.sub(r"[\t\x00-\x08\x0B-\x0C\x0E-\x1F]", "", updated)
    return f"[{updated}]"


def get_response_json(result: str):
    result = patch_json_text(result)

    return json.loads(result, object_pairs_hook=group_duplicates)
