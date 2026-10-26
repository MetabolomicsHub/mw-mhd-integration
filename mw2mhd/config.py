from mhd_model.model.definitions import (
    MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V1_0_MS_PROFILE_NAME,
)
from pydantic import BaseModel


class Mw2MhdConfiguration(BaseModel):
    default_mhd_model_schema_uri: str = MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME
    default_mhd_model_profile_uri: str = MHD_MODEL_V1_0_MS_PROFILE_NAME

    study_http_base_url: str = (
        "https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?StudyID="
    )
    mhd_file_url: str = "https://www.metabolomicsworkbench.org/data/mhd.php?MHD_ID="
    announcement_file_url: str = (
        "https://www.metabolomicsworkbench.org/data/mhd-annoucement.php?MHD_ID="
    )

    default_dataset_license: str = "CC BY-NC-ND"
    dataset_licenses: dict[str, str] = {
        "CC BY-NC-ND": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en/",
        "": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en/",
    }


mw2mhd_config = Mw2MhdConfiguration()
