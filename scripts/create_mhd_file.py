import logging
from pathlib import Path

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
    failed_tasks = {}
    for mw_study_id in study_ids:
        mhd_output_root_path = Path("tests/mhd_dataset")
        mhd_output_root_path.mkdir(exist_ok=True, parents=True)
        try:
            convertor.convert(
                repository_name="Metabolomics Workbench",
                repository_identifier=mw_study_id,
                mhd_identifier=None,
                mhd_output_folder_path=mhd_output_root_path,
            )
            # logger.warning("%s successfull.", mw_study_id)
        except Exception as ex:
            if "has no MS analysis." not in str(
                ex
            ) and "has non-MS analysis" not in str(ex):
                import traceback

                traceback.print_exc()

                failed_tasks[mw_study_id] = ex
                logger.warning("%s failed.", mw_study_id)
                logger.error(ex)
