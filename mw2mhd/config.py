from mhd_model.model.definitions import (
    MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
    MHD_MODEL_V0_1_MS_PROFILE_NAME,
)
from pydantic import BaseModel


class Mw2MhdConfiguration(BaseModel):
    target_mhd_model_schema_uri: str = MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME
    target_mhd_model_ms_profile_uri: str = MHD_MODEL_V0_1_MS_PROFILE_NAME
    target_mhd_model_legacy_profile_uri: str = MHD_MODEL_V0_1_LEGACY_PROFILE_NAME

    study_http_base_url: str = (
        "https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?StudyID="
    )
    default_dataset_licence_url: str = (
        "https://www.metabolomicsworkbench.org/about/termsofuse.php"
    )
    # model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


mw2mhd_config = Mw2MhdConfiguration()
