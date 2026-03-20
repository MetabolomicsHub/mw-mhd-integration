import logging
from pathlib import Path

import jsonschema
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
    return validate_mhd_model(mw_study_id, mhd_file_path, )


if __name__ == "__main__":
    setup_basic_logging_config(logging.INFO)
    study_ids = ["ST001315", "ST002238", "ST004122", "ST004186", "ST001315", "ST000253"]
    mw2mhd_config = Mw2MhdConfiguration()
    for study_id in study_ids:
        convert_mw_study_to_mhd_legacy(study_id)
