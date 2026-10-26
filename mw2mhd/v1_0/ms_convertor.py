from pathlib import Path

from mhd_model.convertors.mhd.convertor import BaseMhdConvertor
from mhd_model.model.v1_0.dataset.profiles.ms.profile import MhDatasetMsProfile_v1_0
from mhd_model.shared.model import Revision
from mhd_model.validation import select_cv_term_helper

from mw2mhd.config import (
    MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V1_0_MS_PROFILE_NAME,
    Mw2MhdConfiguration,
    mw2mhd_config,
)
from mw2mhd.v1_0.builder import MhdDatasetBuilder_v1_0


class MsProfileV1_0_Convertor(BaseMhdConvertor):
    def convert(
        self,
        repository_name: str,
        repository_identifier: str,
        mhd_identifier: None | str,
        mhd_output_folder_path: Path,
        repository_revision: None | Revision = None,
        data_path: None | Path = None,
        ontology_lookup_db_path: None | str = None,
        config: None | Mw2MhdConfiguration = None,
        **kwargs,
    ):
        cv_term_helper = select_cv_term_helper(db_path=ontology_lookup_db_path)
        mhd_dataset_builder = MhdDatasetBuilder_v1_0[MhDatasetMsProfile_v1_0]()
        mhd_dataset_builder.build(
            mhd_id=mhd_identifier,
            mhd_output_path=mhd_output_folder_path,
            mw_study_id=repository_identifier,
            target_mhd_model_schema_uri=MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
            target_mhd_model_profile_uri=MHD_MODEL_V1_0_MS_PROFILE_NAME,
            config=config or mw2mhd_config,
            revision=repository_revision,
            repository_name=repository_name,
            data_path=data_path,
            cv_term_helper=cv_term_helper,
            ontology_lookup_db_path=ontology_lookup_db_path,
            **kwargs,
        )
