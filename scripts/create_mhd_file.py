import json
import logging
import pathlib

from mhd_model.convertors.announcement.convertor import create_announcement_file
from mhd_model.convertors.sdrf.mhd2sdrf import create_sdrf_files
from mhd_model.domain_utils import get_file_hashes
from mhd_model.validation import (
    MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
    MHD_MODEL_V1_0_MS_PROFILE_NAME,
    validate_announcement_file,
    validate_mhd_model,
)

from mw2mhd.config import MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME, Mw2MhdConfiguration
from mw2mhd.convertor_factory import Mw2MhdConvertorFactory
from mw2mhd.logging_utils import configure_logging
from mw2mhd.v1_0.definitions import REPOSITORY_NAME
from mw2mhd.v1_0.mw_utils import prepare_input_folder

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    configure_logging()
    mw_study_id = "ST005293"
    mw_tab_input_root_folder = pathlib.Path(".inputs")
    mw_tab_input_folder_path = mw_tab_input_root_folder / mw_study_id
    mhd_output_path = ".outputs/mhd"
    mhd_id = "MHD000000"
    config = Mw2MhdConfiguration()
    # builder = MhdDatasetBuilder_v1_0[MhDatasetMsProfile_v1_0]()
    factory = Mw2MhdConvertorFactory()
    prepare_input_folder(
        study_id=mw_study_id, output_folder_path=mw_tab_input_folder_path
    )
    legacy_convertor = factory.get_convertor(
        target_mhd_model_profile_uri=MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
        target_mhd_model_schema_uri=MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    )
    ms_convertor = factory.get_convertor(
        target_mhd_model_profile_uri=MHD_MODEL_V1_0_MS_PROFILE_NAME,
        target_mhd_model_schema_uri=MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    )
    ontology_lookup_db_path = (
        "/Users/ozgury/work/ontology_lookup/.db/ontology_lookup.db"
    )
    legacy_convertor.convert(
        repository_name=REPOSITORY_NAME,
        repository_identifier=mw_study_id,
        mhd_identifier=mhd_id,
        mhd_output_folder_path=mhd_output_path,
        mw_tab_input_folder_path=mw_tab_input_folder_path,
        config=config,
        ontology_lookup_db_path=ontology_lookup_db_path,
    )
    mhd_file_path = f"{mhd_output_path}/{mw_study_id}.mhd.json"
    announcement_file_path = f"{mhd_output_path}/{mw_study_id}.announcement.json"
    file_bytes = pathlib.Path(mhd_file_path).read_bytes()
    mhd_metadata_file_hashes = get_file_hashes(file_bytes)
    mhd_file = json.loads(file_bytes)
    file_bytes = None
    create_announcement_file(
        mhd_file=mhd_file,
        mhd_file_url=f"{config.mhd_file_url}{mw_study_id}",
        mhd_metadata_file_hashes=mhd_metadata_file_hashes,
        announcement_file_path=announcement_file_path,
    )
    sdrf_file_root_path = pathlib.Path(mhd_output_path)

    create_sdrf_files(str(mhd_file_path), sdrf_file_root_path)

    mhd_errors = validate_mhd_model(mhd_file_path=mhd_file_path)

    announcement_errors = validate_announcement_file(
        announcement_file_path=announcement_file_path
    )

    for errors in (mhd_errors, announcement_errors):
        for item in errors or []:
            logger.error(item)
    # raise Exception(errors)
