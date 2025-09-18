from pathlib import Path

from mhd_model.convertors.mhd.convertor import BaseMhdConvertor
from mhd_model.shared.model import Revision

from mw2mhd.config import mw2mhd_config
from mw2mhd.v0_1.legacy.builder import MhdLegacyDatasetBuilder


class LegacyProfileV01Convertor(BaseMhdConvertor):
    def __init__(
        self,
        target_mhd_model_schema_uri: str,
        target_mhd_model_profile_uri: str,
    ):
        self.target_mhd_model_schema_uri = target_mhd_model_schema_uri
        self.target_mhd_model_profile_uri = target_mhd_model_profile_uri

    def convert(
        self,
        repository_name: str,
        repository_identifier: str,
        mhd_identifier: None | str,
        mhd_output_folder_path: Path,
        repository_revision: None | Revision = None,
        **kwargs,
    ):
        mhd_dataset_builder = MhdLegacyDatasetBuilder()
        mhd_dataset_builder.build(
            mhd_id=mhd_identifier,
            mhd_output_path=mhd_output_folder_path,
            mw_study_id=repository_identifier,
            target_mhd_model_schema_uri=self.target_mhd_model_schema_uri,
            target_mhd_model_profile_uri=self.target_mhd_model_profile_uri,
            config=mw2mhd_config,
            revision=repository_revision,
            repository_name=repository_name,
            **kwargs,
        )
