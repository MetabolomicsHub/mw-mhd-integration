from types import SimpleNamespace

from mw2mhd.v0_1.legacy.builder import MhdLegacyDatasetBuilder


def raw_file(name: str):
    return SimpleNamespace(id_=name, name=name, repository_identifier=name)


def test_resolve_raw_data_file_prefers_ion_mode_for_basename_match():
    builder = MhdLegacyDatasetBuilder()
    raw_data_files = {
        "Neg_mzML_uploaded/XZ_43.mzML": [
            raw_file("ST004117_NEG_Rawfiles.zip#Neg_mzML_uploaded/XZ_43.mzML")
        ],
        "XZ_43.mzML": [raw_file("ST004117_POS1_Rawfiles.zip#XZ_43.mzML")],
    }

    selected = builder.resolve_raw_data_file(
        mw_study_id="ST004117",
        raw_data_file_name="XZ_43.mzML",
        raw_data_files=raw_data_files,
        ion_mode="POSITIVE",
    )
    assert selected.id_ == "ST004117_POS1_Rawfiles.zip#XZ_43.mzML"

    selected = builder.resolve_raw_data_file(
        mw_study_id="ST004117",
        raw_data_file_name="XZ_43.mzML",
        raw_data_files=raw_data_files,
        ion_mode="NEGATIVE",
    )
    assert selected.id_ == "ST004117_NEG_Rawfiles.zip#Neg_mzML_uploaded/XZ_43.mzML"


def test_resolve_raw_data_file_uses_exact_full_path_match():
    builder = MhdLegacyDatasetBuilder()
    raw_data_files = {
        "mzXMLs_neg/sample.mzXML": [
            raw_file("ST002008_HILIC_QE_HF_Orbitrap_NEG.zip#mzXMLs_neg/sample.mzXML")
        ],
        "mzXMLs_pos/sample.mzXML": [
            raw_file("ST002008_HILIC_QE_HF_Orbitrap_POS.zip#mzXMLs_pos/sample.mzXML")
        ],
    }

    selected = builder.resolve_raw_data_file(
        mw_study_id="ST002008",
        raw_data_file_name="mzXMLs_pos/sample.mzXML",
        raw_data_files=raw_data_files,
        ion_mode="POSITIVE",
    )

    assert (
        selected.id_
        == "ST002008_HILIC_QE_HF_Orbitrap_POS.zip#mzXMLs_pos/sample.mzXML"
    )
