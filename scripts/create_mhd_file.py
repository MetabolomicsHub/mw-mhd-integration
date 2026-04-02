import json
import logging
import traceback
from pathlib import Path

import jsonschema
from jsonschema import ValidationError
from mhd_model.model.v0_1.dataset.validation.validator import validate_mhd_model

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
    factory = Mw2MhdConvertorFactory()

    convertor = factory.get_convertor(
        target_mhd_model_schema_uri=mw2mhd_config.target_mhd_model_schema_uri,
        target_mhd_model_profile_uri=mw2mhd_config.target_mhd_model_legacy_profile_uri,
    )
    mhd_output_root_path = Path(".outputs/mhd_legacy")
    data_path = Path(".outputs/mw_dataset")
    mhd_output_root_path.mkdir(exist_ok=True, parents=True)
    mhd_output_filename = f"{mw_study_id}.mhd.json"
    try:
        convertor.convert(
            repository_name="Metabolomics Workbench",
            repository_identifier=mw_study_id,
            mhd_identifier=None,
            mhd_output_folder_path=mhd_output_root_path,
            mhd_output_filename=mhd_output_filename,
            data_path=data_path,
        )
    except Exception as ex:
        logger.error("Error converting study %s: %s", mw_study_id, ex)
        traceback.print_exc()
        return False, {
            "conversion_error": [("convertion", ValidationError(message=str(ex)))]
        }

    mhd_file_path = mhd_output_root_path / Path(mhd_output_filename)
    mhd_file_url = (
        f"https://www.metabolomicsworkbench.org/data/mhd.php?MHD_ID={mw_study_id}"
    )
    return validate_mhd_model(
        mw_study_id,
        mhd_file_path,
        mhd_file_url=mhd_file_url,
    )


def write_to_file(errors_file_path, success, errors):
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


if __name__ == "__main__":
    setup_basic_logging_config(logging.INFO)
    # study_ids = ["ST001315", "ST002238", "ST004122", "ST004186", "ST001315", "ST000253"]
    study_ids = [
        x.strip() for x in Path("legacy.txt").read_text().split("\n") if x and x.strip()
    ]
    # study_ids = ["ST002478"]
    study_ids.sort(reverse=True)
    mw2mhd_config = Mw2MhdConfiguration()
    mhd_output_root_path = Path(".outputs/mhd_legacy")
    for study_id in study_ids:
        errors_file_path = mhd_output_root_path / f"{study_id}.mhd.errors.json"
        mhd_output_filename = f"{study_id}.mhd.json"
        mhd_file_path = mhd_output_root_path / Path(mhd_output_filename)
        announcement_file_path = mhd_output_root_path / Path(
            f"{study_id}.announcement.json"
        )
        if (
            not errors_file_path.exists()
            and mhd_file_path.exists()
            and announcement_file_path.exists()
        ):
            logger.info("%s is skipped", study_id)
            continue
        success, errors = convert_mw_study_to_mhd_legacy(study_id)
        if success is None:
            logger.info("%s is skipped", study_id)
            continue
        write_to_file(errors_file_path, success, errors)
