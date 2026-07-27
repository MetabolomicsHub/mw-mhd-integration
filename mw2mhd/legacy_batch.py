import json
import logging
from pathlib import Path

import jsonschema
from jsonschema import ValidationError
from mhd_model.convertors.announcement.convertor import create_announcement_file
from mhd_model.model.v0_1.dataset.validation.validator import validate_mhd_model

from mw2mhd.announcement_enricher import enrich_announcement_file
from mw2mhd.config import Mw2MhdConfiguration
from mw2mhd.convertor_factory import Mw2MhdConvertorFactory
from mw2mhd.mhd_enricher import enrich_mhd_file

logger = logging.getLogger(__name__)


def ensure_announcement_file(
    mhd_file_path: Path, announcement_file_path: Path
) -> None:
    if not announcement_file_path.exists():
        mhd_data_json = json.loads(mhd_file_path.read_text())
        create_announcement_file(mhd_data_json, None, str(announcement_file_path))
    if announcement_file_path.exists():
        enrich_announcement_file(mhd_file_path, announcement_file_path)


def convert_mw_study_to_mhd_legacy(
    mw_study_id: str,
    mw2mhd_config: None | Mw2MhdConfiguration = None,
    *,
    output_dir: Path = Path(".outputs/mhd_legacy"),
    data_path: Path = Path(".outputs/mw_dataset"),
    verbose: bool = False,
) -> tuple[bool, dict[str, list[jsonschema.ValidationError]]]:
    if not mw2mhd_config:
        mw2mhd_config = Mw2MhdConfiguration()
    factory = Mw2MhdConvertorFactory()

    convertor = factory.get_convertor(
        target_mhd_model_schema_uri=mw2mhd_config.target_mhd_model_schema_uri,
        target_mhd_model_profile_uri=mw2mhd_config.target_mhd_model_legacy_profile_uri,
    )
    output_dir.mkdir(exist_ok=True, parents=True)
    mhd_output_filename = f"{mw_study_id}.mhd.json"
    mhd_file_path = output_dir / Path(mhd_output_filename)
    try:
        convertor.convert(
            repository_name="Metabolomics Workbench",
            repository_identifier=mw_study_id,
            mhd_identifier=None,
            mhd_output_folder_path=output_dir,
            mhd_output_filename=mhd_output_filename,
            data_path=data_path,
        )
        enrich_mhd_file(mhd_file_path, data_path=data_path)
    except Exception as ex:
        if verbose:
            logger.exception("Error converting study %s", mw_study_id)
        else:
            logger.error("Error converting study %s: %s", mw_study_id, ex)
        return False, {
            "conversion_error": [("convertion", ValidationError(message=str(ex)))]
        }

    mhd_file_url = (
        f"https://www.metabolomicsworkbench.org/data/mhd.php?MHD_ID={mw_study_id}"
    )
    success, errors = validate_mhd_model(
        mw_study_id,
        mhd_file_path,
        mhd_file_url=mhd_file_url,
    )
    announcement_file_path = output_dir / f"{mw_study_id}.announcement.json"
    try:
        ensure_announcement_file(mhd_file_path, announcement_file_path)
    except Exception as ex:
        if verbose:
            logger.exception("Error creating announcement file for study %s", mw_study_id)
        else:
            logger.error(
                "Error creating announcement file for study %s: %s", mw_study_id, ex
            )
    return success, errors


def write_to_file(errors_file_path: Path, success: bool, errors: dict) -> None:
    if success and errors_file_path.exists():
        errors_file_path.unlink()
    if not success or errors:
        errors_dict = {}
        for file, val in errors.items():
            for key, error in val:
                if file not in errors_dict:
                    errors_dict[file] = {}
                if key not in errors_dict[file]:
                    errors_dict[file][key] = []
                errors_dict[file][key].append(error.message)

        errors_file_path.write_text(json.dumps({"errors": errors_dict}, indent=2))


def read_study_ids(study_list: Path) -> list[str]:
    study_ids = {
        study_id.strip()
        for study_id in study_list.read_text().split("\n")
        if study_id and study_id.strip()
    }
    return sorted(study_ids, reverse=True)


def convert_legacy_batch(
    *,
    study_list: Path,
    output_dir: Path = Path(".outputs/mhd_legacy"),
    data_path: Path = Path(".outputs/mw_dataset"),
    verbose: bool = False,
) -> None:
    study_ids = read_study_ids(study_list)
    mw2mhd_config = Mw2MhdConfiguration()
    output_dir.mkdir(exist_ok=True, parents=True)
    for study_id in study_ids:
        errors_file_path = output_dir / f"{study_id}.mhd.errors.json"
        mhd_file_path = output_dir / f"{study_id}.mhd.json"
        announcement_file_path = output_dir / f"{study_id}.announcement.json"
        if (
            not errors_file_path.exists()
            and mhd_file_path.exists()
            and announcement_file_path.exists()
        ):
            logger.info("%s is skipped", study_id)
            continue
        success, errors = convert_mw_study_to_mhd_legacy(
            study_id,
            mw2mhd_config=mw2mhd_config,
            output_dir=output_dir,
            data_path=data_path,
            verbose=verbose,
        )
        if success is None:
            logger.info("%s is skipped", study_id)
            continue
        write_to_file(errors_file_path, success, errors)
