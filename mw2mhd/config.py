from mhd_model.model.definitions import (
    MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
    MHD_MODEL_V0_1_MS_PROFILE_NAME,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mw2MhdConfiguration(BaseSettings):
    target_mhd_model_schema_uri: str = MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME
    target_mhd_model_ms_profile_uri: str = MHD_MODEL_V0_1_MS_PROFILE_NAME
    target_mhd_model_legacy_profile_uri: str = MHD_MODEL_V0_1_LEGACY_PROFILE_NAME

    public_ftp_base_url: str = (
        "ftp://ftp.ebi.ac.uk/pub/databases/metabolights/studies/public"
    )
    public_http_base_url: str = (
        "http://ftp.ebi.ac.uk/pub/databases/metabolights/studies/public"
    )
    study_http_base_url: str = "https://www.ebi.ac.uk/metabolights"
    default_dataset_licence_url: str = (
        "https://creativecommons.org/publicdomain/zero/1.0/"
    )
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


mw2mhd_config = Mw2MhdConfiguration()
