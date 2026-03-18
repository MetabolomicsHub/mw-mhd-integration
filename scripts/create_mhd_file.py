import json
import logging
from pathlib import Path

import jsonschema
from mhd_model.convertors.announcement.v0_1.legacy.mhd2announce import (
    create_announcement_file,
)
from mhd_model.model.v0_1.announcement.validation.validator import (
    MhdAnnouncementFileValidator,
)
from mhd_model.model.v0_1.dataset.validation.validator import validate_mhd_file

from mw2mhd.config import (
    Mw2MhdConfiguration,
    mw2mhd_config,
)
from mw2mhd.convertor_factory import (
    Mw2MhdConvertorFactory,
)
from scripts.utils import setup_basic_logging_config

logger = logging.getLogger(__name__)


def convert_mw_study_to_mhd_legacy(
    mw_study_id: str, mw2mhd_config: None | Mw2MhdConfiguration = None
) -> tuple[bool, dict[str, list[jsonschema.ValidationError]]]:
    if not mw2mhd_config:
        mw2mhd_config = Mw2MhdConfiguration()
    all_validation_errors = {}
    success = False
    factory = Mw2MhdConvertorFactory()

    convertor = factory.get_convertor(
        target_mhd_model_schema_uri=mw2mhd_config.target_mhd_model_schema_uri,
        target_mhd_model_profile_uri=mw2mhd_config.target_mhd_model_legacy_profile_uri,
    )
    mhd_output_root_path = Path("tests/mhd_dataset/legacy")
    mhd_output_root_path.mkdir(exist_ok=True, parents=True)
    mhd_output_filename = f"{mw_study_id}.mhd.json"
    convertor.convert(
        repository_name="Metabolomics Workbench",
        repository_identifier=mw_study_id,
        mhd_identifier=None,
        mhd_output_folder_path=mhd_output_root_path,
        mhd_output_filename=mhd_output_filename,
    )
    mhd_file_path = mhd_output_root_path / Path(mhd_output_filename)

    validation_errors = validate_mhd_file(str(mhd_file_path))

    if validation_errors:
        logger.error("MHD model validation errors found for %s", mw_study_id)
        for error in validation_errors:
            logger.error(error)
        all_validation_errors[mhd_output_filename] = validation_errors
    elif not mhd_file_path.exists():
        logger.error("MHD model file not found for %s", mw_study_id)
        all_validation_errors[mhd_output_filename] = [
            f"MHD model file '{mhd_output_filename}' not found"
        ]
    else:
        mhd_announcement_output_root_path = Path("tests/mhd_announcement/legacy")
        mhd_announcement_output_root_path.mkdir(exist_ok=True, parents=True)
        logger.info("MHD model validation successful for %s", mw_study_id)
        announcement_file_name = f"{study_id}.announcement.json"
        announcement_file_path = mhd_announcement_output_root_path / Path(
            announcement_file_name
        )
        mhd_data_json = json.loads(mhd_file_path.read_text())
        mhd_file_url = mw2mhd_config.study_http_base_url + mw_study_id
        create_announcement_file(mhd_data_json, mhd_file_url, announcement_file_path)
        if not announcement_file_path.exists():
            logger.error("MHD announcement file not found for %s", mw_study_id)
            all_validation_errors[mhd_output_filename] = [
                f"MHD announcement file '{mhd_output_filename}' not found"
            ]
        else:
            announcement_file_json = json.loads(announcement_file_path.read_text())
            validator = MhdAnnouncementFileValidator()
            all_errors = validator.validate(announcement_file_json)
            if all_errors:
                logger.error(
                    "MHD announcement file validation errors found for %s", mw_study_id
                )
                for error in all_errors:
                    logger.error(error)
                all_validation_errors[mhd_output_filename] = all_errors
            else:
                success = True
                logger.info(
                    "MHD announcement file validation successful for %s", mw_study_id
                )
    return success, all_validation_errors


if __name__ == "__main__":
    setup_basic_logging_config(logging.INFO)
    study_ids = ["ST001315", "ST002238", "ST004122", "ST004186", "ST001315", "ST000253"]
    mw2mhd_config = Mw2MhdConfiguration()
    for study_id in study_ids:
        convert_mw_study_to_mhd_legacy(study_id)
