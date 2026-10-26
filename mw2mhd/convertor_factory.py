from mhd_model.convertors.mhd.convertor import BaseMhdConvertor, BaseMhdConvertorFactory
from mhd_model.model.definitions import (
    MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
    MHD_MODEL_V0_1_MS_PROFILE_NAME,
    MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
    MHD_MODEL_V1_0_MS_PROFILE_NAME,
)

from mw2mhd.v1_0.legacy_convertor import LegacyProfileV1_0_Convertor
from mw2mhd.v1_0.ms_convertor import MsProfileV1_0_Convertor


class Mw2MhdConvertorFactory(BaseMhdConvertorFactory):
    def get_convertor(
        self,
        target_mhd_model_schema_uri: str,
        target_mhd_model_profile_uri: str,
    ) -> BaseMhdConvertor:
        if target_mhd_model_schema_uri in {
            MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
            MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
        }:
            if target_mhd_model_profile_uri in {
                MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
                MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
            }:
                return LegacyProfileV1_0_Convertor()
            elif target_mhd_model_profile_uri in {
                MHD_MODEL_V0_1_MS_PROFILE_NAME,
                MHD_MODEL_V1_0_MS_PROFILE_NAME,
            }:
                return MsProfileV1_0_Convertor()
            raise NotImplementedError()
        else:
            raise NotImplementedError()
