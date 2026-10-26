import csv
import logging
from importlib import resources

from mhd_model.domain_utils import get_urn as default_get_urn
from mhd_model.model.v1_0.rules.managed_cv_terms import (
    COMMON_ASSAY_TYPES,
    COMMON_CHARACTERISTIC_DEFINITIONS,
    COMMON_MEASUREMENT_TYPES,
    COMMON_MOLECULAR_ENTITY_IDENTIFIERS,
    COMMON_OMICS_TYPES,
    COMMON_PARAMETER_DEFINITIONS,
    COMMON_PROTOCOLS,
    COMMON_STUDY_FACTOR_DEFINITIONS,
)
from mhd_model.shared.base import CvTerm
from mhd_model.shared.dataset_builder import MhDatasetBuilder
from mhd_model.shared.model import IdentifiableMhdModel
from pydantic import BaseModel, ConfigDict, field_validator

import mw2mhd

logger = logging.getLogger(__name__)


def get_urn(
    dataset_id: str,
    node_class: type[IdentifiableMhdModel],
    identifier: None | str,
    urn_namespace: str = "mhd",
    repository_short_name: None | str = "mw",
) -> str:
    return default_get_urn(
        urn_namespace=urn_namespace,
        dataset_id=dataset_id,
        repository_short_name=repository_short_name,
        node_class=node_class,
        identifier=identifier,
    )


class DatasetBuildContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    study_id: str
    mw_data: None | dict = None
    first_analysis: None | dict = None
    mhd_builder: None | MhDatasetBuilder = None


class MwDataResponse(BaseModel): ...


class MetaboliteIdentification(BaseModel):
    study_id: str = ""
    analysis_id: str = ""
    analysis_summary: str = ""
    metabolite_name: str = ""
    refmet_name: str = ""
    refmet_id: str = ""


class StudySummary(BaseModel):
    study_id: str = ""
    submission_date: str = ""
    release_date: str = ""
    version: str = ""
    revision_no: str = ""
    revision_datetime: str = ""
    revision_comment: str = ""
    license: str = ""
    license_url: str = ""
    study_url: str = ""

    @field_validator(
        "revision_comment",
        "revision_datetime",
        "revision_no",
        "version",
        "submission_date",
        "release_date",
        "license",
        "study_url",
    )
    @classmethod
    def field_validator_empty_string(cls, value):
        if value is None or value == "-":
            return ""
        return value

    @field_validator("license_url")
    @classmethod
    def license_url_validator(cls, value):
        if value is None or value == "-":
            return ""
        return value.rstrip("/") + "/"


class CompressedFileItem(BaseModel):
    name: str = ""
    size: int = 0


class StudyFiles(BaseModel):
    study_id: str = ""
    files: list[str] = []
    compressed_file_content: dict[str, list[CompressedFileItem]] = {}


class CompressedFileItem(BaseModel):
    name: str = ""
    size: int = 0


REPOSITORY_NAME = "Metabolomics Workbench"

LICENSE_MAP: dict[str, str] = {
    "CC BY-NC-ND": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en/",
    "": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en/",
}
## METABOLOMICS WORKBENCH RELATED CONFIGURATION ###
##############################################################################################################
MW_ASSAY_TYPES = {
    "LC-MS": COMMON_ASSAY_TYPES["lc-ms"],
    "GC-MS": COMMON_ASSAY_TYPES["gc-ms"],
    # TODO: Add more assay types if needed
}
MW_MEASUREMENT_TYPES = {
    "targeted": COMMON_MEASUREMENT_TYPES["targeted"],
    "untargeted": COMMON_MEASUREMENT_TYPES["untargeted"],
}

DEFAULT_OMICS_TYPE = COMMON_OMICS_TYPES["metabolomics"]

COMMON_PROTOCOLS_MAP = {
    "sample collection": COMMON_PROTOCOLS["sample collection"],
    "sample preparation": COMMON_PROTOCOLS["sample preparation"],
    "mass spectrometry": COMMON_PROTOCOLS["mass spectrometry"],
    "chromatography": COMMON_PROTOCOLS["chromatography"],
    "treatment": COMMON_PROTOCOLS["treatment"],
    # TODO: Update after adding to managed CV terms
}

MW_PROTOCOLS_MAP = COMMON_PROTOCOLS_MAP.copy()

# Maps each field in a protocol to a CV term (if it is possible)
# TODO: Need to be reviewed and updated
# TODO: If there is any CV term update in MetabolomicsHub model
# This map will be also updated.
COMMON_PROTOCOL_PARAMETER_DEFINITIONS_MAP = {
    "sample collection": {},
    "sample preparation": {},
    "treatment": {},
    "mass spectrometry": {
        "instrument name": COMMON_PARAMETER_DEFINITIONS["mass spectrometry instrument"],
        "instrument type": COMMON_PARAMETER_DEFINITIONS["instrument class"],
        "ms type": COMMON_PARAMETER_DEFINITIONS["ionization type"],
        "ion mode": COMMON_PARAMETER_DEFINITIONS["acquisition polarity"],
    },
    "chromatography": {
        "instrument name": COMMON_PARAMETER_DEFINITIONS["chromatography instrument"],
        "column name": COMMON_PARAMETER_DEFINITIONS["chromatography column"],
        "chromatography type": COMMON_PARAMETER_DEFINITIONS[
            "chromatography separation"
        ],
    },
}
MW_PROTOCOL_PARAMETER_DEFINITIONS_MAP = COMMON_PROTOCOL_PARAMETER_DEFINITIONS_MAP.copy()

MW_PROTOCOL_PARAMETER_DEFINITIONS_MAP.update(
    {
        "sample collection": {
            "storage conditions": CvTerm(
                source="NCIT",
                accession="NCIT:C96145",
                name="Storage Condition",
            ),
        },
        "sample preparation": {},
        "treatment": {},
        "mass spectrometry": {
            "instrument name": COMMON_PARAMETER_DEFINITIONS[
                "mass spectrometry instrument"
            ],
            "instrument type": COMMON_PARAMETER_DEFINITIONS["instrument class"],
            "ms type": COMMON_PARAMETER_DEFINITIONS["ionization type"],
            "ion mode": COMMON_PARAMETER_DEFINITIONS["acquisition polarity"],
        },
        "chromatography": {
            "instrument name": COMMON_PARAMETER_DEFINITIONS[
                "chromatography instrument"
            ],
            "chromatography type": COMMON_PARAMETER_DEFINITIONS[
                "chromatography separation"
            ],
            "column name": COMMON_PARAMETER_DEFINITIONS["chromatography column"],
        },
    }
)
MANAGED_CHARACTERISTICS_MAP = {
    "organism": COMMON_CHARACTERISTIC_DEFINITIONS["organism"],
    "organism part": COMMON_CHARACTERISTIC_DEFINITIONS["organism part"],
    "disease": COMMON_CHARACTERISTIC_DEFINITIONS["disease"],
    "cell type": COMMON_CHARACTERISTIC_DEFINITIONS["cell type"],
}
COMON_STUDY_FACTOR_MAP = {
    "disease": COMMON_STUDY_FACTOR_DEFINITIONS["disease"],
}
MANAGED_STUDY_FACTOR_MAP = COMON_STUDY_FACTOR_MAP.copy()
MANAGED_STUDY_FACTOR_MAP.update(
    {
        "treatment": CvTerm(source="EFO", accession="EFO:0000727", name="treatment"),
    }
)


PUBLIC_MW_STUDY_URL_PREFIX = (
    "https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?Mode=Study&StudyID="
)
PUBLIC_MW_FTP_BASE_URL = "ftp://www.metabolomicsworkbench.org/Studies"

# TODO: Add REFMET to EDAM ontology
COMMON_COMPOUND_IDENTIFIERS_MAP: dict[str, CvTerm] = {
    "chebi": COMMON_MOLECULAR_ENTITY_IDENTIFIERS.get("chebi"),
    "pubchem cid": CvTerm(
        source="EDAM", accession="EDAM:data_1172", name="PubChem CID"
    ),
    "hmdb": CvTerm(
        source="EDAM", accession="EDAM:data_2622", name="Compound ID (HMDB)"
    ),
    "kegg": CvTerm(
        source="EDAM", accession="EDAM:data_2605", name="Compound ID (KEGG)"
    ),
    "refmet": COMMON_MOLECULAR_ENTITY_IDENTIFIERS.get("refmet"),
}

_term_mappings: dict[str, dict[str, CvTerm]] | None = None


def get_cv_terms_mapping() -> dict[str, dict[str, CvTerm]]:
    """loads MW term 2 MS ontology term mappings file

    Returns:
        dict[str, dict[str, CvTerm]]: dictionary of MW term name (lowercase)
        to a CvTerm object grouped by MHD common parameter definition
    """
    global _term_mappings
    if _term_mappings:
        return _term_mappings
    with (
        resources.files(mw2mhd.__name__)
        .joinpath("cv_mapping_table.csv")
        .open("r", encoding="utf-8") as f
    ):
        # MAP TO MHD common parameter/characteristic definition
        custom_definition_mappings = {
            "liquid chromatography instrument": "chromatography instrument",
            "gas chromatography instrument": "chromatography instrument",
            "mass spectrometry instrument": "mass spectrometer",
        }
        # Column names and their index in the cv_mappings.csv file.
        HEADERS = {
            "GROUP": 0,
            "REF_SOURCE": 1,
            "REF_ACCESSION": 2,
            "REF_TERM": 3,
            "ALTERNATIVE_NAMES": 4,
            "TARGET_CV_TERM": 5,
        }

        reader = csv.reader(f)
        term_mappings = {}
        for idx, row in enumerate(reader):
            if idx == 0:
                continue
            target_cv_term = row[HEADERS["TARGET_CV_TERM"]]
            if target_cv_term:
                continue
            accession = row[HEADERS["REF_ACCESSION"]]
            source = row[HEADERS["REF_SOURCE"]]
            term = row[HEADERS["REF_TERM"]]
            cv_names_set: set[str] = set()
            for x in ["ALTERNATIVE_NAMES", "REF_TERM"]:
                cv_names_set.update(
                    {
                        name.strip().lower()
                        for name in row[HEADERS[x]].split(";")
                        if name and name.strip()
                    }
                )
            instance = row[HEADERS["GROUP"]]
            if not cv_names_set or not term or not accession:
                continue
            if not instance:
                logger.warning(
                    "Term mapping file row %s with accession %s and term '%s' "
                    "does not have an instance value. Row will be ignored.",
                    idx + 1,
                    accession,
                    term,
                )
                continue
            definition = custom_definition_mappings.get(instance.lower()) or instance
            if definition not in term_mappings:
                term_mappings[definition] = {}
            for cv_name in cv_names_set:
                term_mappings[definition][cv_name.lower()] = CvTerm(
                    source=source,
                    accession=accession,
                    name=term,
                )
    _term_mappings = term_mappings
    return _term_mappings


def convert_to_cv_term(val: str | dict) -> CvTerm:
    if not val:
        return CvTerm()
    if isinstance(val, str):
        return CvTerm(name=val)
    return CvTerm(
        name=val.get("term") or "",
        source=val.get("termSource") or "",
        accession=val.get("termAccession") or "",
    )


def convert_to_cv_term_with_mapping(group: str, val: str | dict) -> CvTerm:
    if not val:
        return CvTerm()
    mapping = get_cv_terms_mapping().get(group) or {}
    if isinstance(val, str):
        term = mapping.get(val.lower())
        return term if term else CvTerm(name=val)
    term = mapping.get(val.get("term", "").lower())
    return (
        term
        if term
        else CvTerm(
            name=val.get("term") or "",
            source=val.get("termSource") or "",
            accession=val.get("termAccession") or "",
        )
    )
