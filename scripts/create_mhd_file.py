import logging
from pathlib import Path

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

if __name__ == "__main__":
    setup_basic_logging_config(logging.WARNING)
    # Download all public studies
    # study_ids = fetch_all_available_mw_studies()
    # study_ids = [x for x in study_ids if int(x.replace("ST", "")) <= 167]

    # run only selected studies
    study_ids = ["ST001315", "ST002238", "ST004122", "ST004186", "ST001315", "ST000253"]

    config = Mw2MhdConfiguration()

    factory = Mw2MhdConvertorFactory()

    convertor = factory.get_convertor(
        target_mhd_model_schema_uri=mw2mhd_config.target_mhd_model_schema_uri,
        target_mhd_model_profile_uri=mw2mhd_config.target_mhd_model_legacy_profile_uri,
    )
    for idx, mw_study_id in enumerate(study_ids):
        # cache_root_path = "tests/gnps_dataset"
        mhd_output_root_path = Path("tests/mhd_dataset/legacy")
        mhd_output_root_path.mkdir(exist_ok=True, parents=True)
        mhd_output_filename = f"{mw_study_id}.mhd.json"
        convertor.convert(
            repository_name="Metabolomics Workbench",
            repository_identifier=mw_study_id,
            mhd_identifier=None,
            mhd_output_folder_path=mhd_output_root_path,
            mhd_output_filename=mhd_output_filename,
            # cache_root_path=cache_root_path,
        )
        file_path = mhd_output_root_path / Path(mhd_output_filename)

        validation_errors = validate_mhd_file(str(file_path))

        if validation_errors:
            logger.error("MHD model validation errors found for %s", mw_study_id)
            for error in validation_errors:
                logger.error(error)
        else:
            logger.info("MHD model validation successful for %s", mw_study_id)
