import json
import logging
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MetaboliteIdentification(BaseModel):
    study_id: str = ""
    analysis_id: str = ""
    analysis_summary: str = ""
    metabolite_name: str = ""
    refmet_name: str = ""


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


def fetch_mw_metabolites(study_id: str) -> list[MetaboliteIdentification]:
    try:
        data_path: Path = Path("tests/mw_dataset")
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
    output_folder_path: str = "tests/mw_dataset",
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
