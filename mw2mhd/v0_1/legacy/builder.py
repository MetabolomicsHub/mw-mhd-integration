import datetime
import logging
from pathlib import Path
from typing import Any, OrderedDict

import dateutil
from email_validator import validate_email
from mhd_model.model.v0_1.dataset.profiles.base import graph_nodes as mhd_domain
from mhd_model.model.v0_1.dataset.profiles.base.dataset_builder import MhDatasetBuilder
from mhd_model.model.v0_1.dataset.profiles.base.profile import MhDatasetBaseProfile
from mhd_model.model.v0_1.dataset.profiles.legacy.profile import MhDatasetLegacyProfile
from mhd_model.model.v0_1.rules.managed_cv_terms import (
    COMMON_ASSAY_TYPES,
    COMMON_CHARACTERISTIC_DEFINITIONS,
    COMMON_MEASUREMENT_TYPES,
    COMMON_OMICS_TYPES,
    COMMON_PARAMETER_DEFINITIONS,
    COMMON_PROTOCOLS,
    COMMON_STUDY_FACTOR_DEFINITIONS,
)
from mhd_model.shared.model import CvTerm, Revision, UnitCvTerm
from pydantic import HttpUrl

from mw2mhd.config import Mw2MhdConfiguration
from mw2mhd.v0_1.legacy.mw_utils import fetch_mw_data, fetch_mw_metabolites

logger = logging.getLogger(__name__)


## METABOLOMICS WORKBENCH RELATED CONFIGURATION ###
##############################################################################################################
MW_ASSAY_TYPES = {
    "LC-MS": COMMON_ASSAY_TYPES["OBI:0003097S"],
    "GC-MS": COMMON_ASSAY_TYPES["OBI:0003110"],
    # TODO: Add more assay types if needed
}
MW_MEASUREMENT_TYPES = {
    "targeted": COMMON_MEASUREMENT_TYPES["MSIO:0000100"],
    "untargeted": COMMON_MEASUREMENT_TYPES["MSIO:0000101"],
}

DEFAULT_OMICS_TYPE = COMMON_OMICS_TYPES["EDAM:3172"]

COMMON_PROTOCOLS_MAP = {
    "sample collection": COMMON_PROTOCOLS["EFO:0005518"],
    "sample preparation": COMMON_PROTOCOLS["MS:1000831"],
    "mass spectrometry": COMMON_PROTOCOLS["CHMO:0000470"],
    "chromatography": COMMON_PROTOCOLS["CHMO:0001000"],
    "treatment": COMMON_PROTOCOLS["EFO:0003969"],
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
        "instrument name": COMMON_PARAMETER_DEFINITIONS["MSIO:0000171"],
        "instrument type": COMMON_PARAMETER_DEFINITIONS["OBI:0000345"],
        "ms type": COMMON_PARAMETER_DEFINITIONS["CHMO:0000960"],
        "ion mode": COMMON_PARAMETER_DEFINITIONS["MS:1000465"],
    },
    "chromatography": {
        "instrument name": COMMON_PARAMETER_DEFINITIONS["OBI:0000485"],
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
            "instrument name": COMMON_PARAMETER_DEFINITIONS["MSIO:0000171"],
            "instrument type": COMMON_PARAMETER_DEFINITIONS["OBI:0000345"],
            "ms type": COMMON_PARAMETER_DEFINITIONS["CHMO:0000960"],
            "ion mode": COMMON_PARAMETER_DEFINITIONS["MS:1000465"],
        },
        "chromatography": {
            "instrument name": COMMON_PARAMETER_DEFINITIONS["OBI:0000485"],
            "chromatography type": CvTerm(
                source="",
                accession="",
                name="column type",
            ),
            "column name": CvTerm(
                source="",
                accession="",
                name="column name",
            ),
        },
    }
)
MANAGED_CHARACTERISTICS_MAP = {
    "organism": COMMON_CHARACTERISTIC_DEFINITIONS["NCIT:C14250"],
    "organism part": COMMON_CHARACTERISTIC_DEFINITIONS["NCIT:C103199"],
    "disease": COMMON_CHARACTERISTIC_DEFINITIONS["EFO:0000408"],
    "cell type": COMMON_CHARACTERISTIC_DEFINITIONS["EFO:0000324"],
}
COMON_STUDY_FACTOR_MAP = {
    "disease": COMMON_STUDY_FACTOR_DEFINITIONS["EFO:0000408"],
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
    "CHEBI": CvTerm(source="EDAM", accession="EDAM:1174", name="ChEBI ID"),
    "PUBCHEM CID": CvTerm(source="EDAM", accession="EDAM:1172", name="PubChem CID"),
    "HMDB": CvTerm(source="EDAM", accession="EDAM:2622", name="Compound ID (HMDB)"),
    "KEGG": CvTerm(source="EDAM", accession="EDAM:2605", name="Compound ID (KEGG)"),
    "SMILES": CvTerm(source="EDAM", accession="EDAM:1196", name="SMILES"),
    "REFMET": CvTerm(source="", accession="", name="RefMet"),
}


class MhdLegacyDatasetBuilder:
    def build(
        self,
        mhd_id: None | str,
        mhd_output_path: Path,
        mw_study_id: str,
        target_mhd_model_schema_uri: str,
        target_mhd_model_profile_uri: str,
        config: Mw2MhdConfiguration,
        repository_name: str,
        revision: None | Revision = None,
        **kwargs,
    ) -> MhDatasetLegacyProfile:
        #####################################################################################
        # Fetch metadata as json from MW. If it is not valid return error
        # TODO: Fetch other files or connect to a database to use more information
        #####################################################################################

        mwtab: dict[str, Any] = fetch_mw_data(mw_study_id)
        if not mwtab:
            raise ValueError(f"Could not fetch metadata for study {mw_study_id}")

        #####################################################################################
        # Select first analysis to fetch study level data
        #####################################################################################
        # Select all ms analyses
        analysis_list = [
            x
            for x in list(mwtab.keys())
            if "MS" in mwtab[x].get("ANALYSIS", {}).get("ANALYSIS_TYPE", "")
        ]
        analysis_list.sort()
        # Ensure study has MS analyses.
        if not analysis_list:
            raise ValueError(f"{mw_study_id} has no MS analysis.")

        if len(analysis_list) != len(list(mwtab.keys())):
            raise ValueError(f"{mw_study_id} has non-MS analysis.")

        analysis_id = analysis_list[0]
        mw_section: dict[str, Any] = mwtab.get(analysis_id, {}).get(
            "METABOLOMICS WORKBENCH", {}
        )
        # select first analysis to fetch study level metadata
        first_analysis = mwtab.get(analysis_id, {})
        study_section: dict[str, Any] = first_analysis.get("STUDY", {})
        project_section: dict[str, Any] = first_analysis.get("PROJECT", {})
        subject_section: dict[str, Any] = first_analysis.get("SUBJECT", {})

        #####################################################################################
        # Create a dataset builder
        # TODO: fetch revision and revision date information from other source if it exists.
        #####################################################################################

        revision_number = int(mw_section.get("VERSION", 1))
        mhd_builder = MhDatasetBuilder(
            repository_name=repository_name,
            mhd_identifier=None,
            repository_identifier=mw_study_id,
            schema_name=target_mhd_model_schema_uri,
            profile_uri=target_mhd_model_profile_uri,
            repository_revision=revision_number,
            repository_revision_datetime=revision.revision_datetime
            if revision
            else None,
            change_log=[revision] if revision else None,
        )

        #####################################################################################
        # Create data-provider node
        #####################################################################################
        dataset_provider = self.create_data_provider(repository_name)

        #####################################################################################
        # Create study node with basic properties
        # protocols and links will be defined after initial creation.
        #####################################################################################
        mhd_study = self.create_study(
            mhd_builder, study_section, mw_study_id, dataset_provider
        )

        # #####################################################################################
        # Create characteristic definition - organism and value from subject section
        # #####################################################################################
        self.create_organism_characteristic(mhd_builder, subject_section, mhd_study)

        # #####################################################################################
        # Create sample collection protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        analysis_data = mwtab.get(analysis_id, {})
        collection_protocol = self.create_collection_protocol(
            mhd_builder, analysis_data, mhd_study
        )

        # #####################################################################################
        # Create sample collection protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        preparation_protocol = self.create_sample_preparation_protocol(
            mhd_builder, analysis_data, mhd_study
        )

        # #####################################################################################
        # Create treatment protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        treatment_protocol = self.create_treatment_protocol(
            mhd_builder, analysis_data, mhd_study
        )

        #####################################################################################
        # Add metadata files mwTab files and assays with initial values
        # add study level common protocols to each assay
        #####################################################################################
        common_protocols = [
            x for x in (collection_protocol, preparation_protocol, treatment_protocol)
        ]
        # filter if a common filter is None. e.g., filter if treatment protocol is not defined.
        common_protocols = [x for x in common_protocols if x]

        mhd_assays: dict[str, mhd_domain.Assay] = self.create_assays(
            mhd_builder,
            mwtab_data=mwtab,
            mhd_study=mhd_study,
            mw_study_id=mw_study_id,
            common_protocols=common_protocols,
        )

        #####################################################################################
        # Add Submitter
        #####################################################################################
        mhd_submitter, mhd_study_organization = self.create_submitter(
            mhd_builder, study_section, mhd_study
        )

        #####################################################################################
        # Create Principal Investigator and project organization.
        # If PI is also submitter, link submitter as PI
        #####################################################################################
        mhd_pi, mhd_project_organization = self.create_principal_investigator(
            mhd_builder,
            project_section,
            mhd_study,
            mhd_submitter,
            mhd_study_organization,
        )

        mhd_builder.link(
            mhd_pi,
            "principal-investigator-of",
            mhd_study,
            reverse_relationship_name="has-principal-investigator",
        )
        #####################################################################################
        # Create Project and link project and Organization
        #####################################################################################
        mhd_project = self.create_project(mhd_builder, project_section, mhd_study)

        mhd_builder.link(
            mhd_project_organization,
            "manages",
            mhd_project,
            reverse_relationship_name="managed-by",
        )

        # #####################################################################################
        # # Create MS protocols for assays
        # #####################################################################################
        self.create_ms_protocols(mhd_builder, mwtab, mhd_study, mhd_assays)
        # ms_protocols: dict[str, mhd_domain.Protocol] = self.create_ms_protocols(
        #     mhd_builder, mwtab, mhd_study, mhd_assays
        # )
        # #####################################################################################
        # # Create Chromotograpy protocols for assays
        # ####################################################################################
        self.create_chromotography_protocols(mhd_builder, mwtab, mhd_study, mhd_assays)
        # protocols = self.create_chromotography_protocols(
        #     mhd_builder, mwtab, mhd_study, mhd_assays
        # )
        # chromotography_protocols: dict[str, mhd_domain.Protocol] = protocols
        # #####################################################################################
        # # Add study factors, raw-data-files, samples, subjects, factor values.
        # #####################################################################################
        self.process_study_design(
            mhd_builder, mwtab, mhd_study, mhd_assays, mw_study_id
        )

        # #####################################################################################
        # # Add metabolites and metabolite-identifiers
        # #####################################################################################
        self.create_reported_metabolites(mhd_builder, mwtab, mhd_study, mhd_assays)

        #####################################################################################
        # Build and save dataset
        #####################################################################################
        mhd_dataset: MhDatasetBaseProfile = mhd_builder.create_dataset(
            start_item_refs=[mhd_study.id_], dataset_class=MhDatasetLegacyProfile
        )
        filename = mhd_id if mhd_id else mw_study_id
        mhd_dataset.name = f"{filename} MetabolomicsHub Legacy Dataset"
        mhd_output_path.mkdir(parents=True, exist_ok=True)
        output_filename = kwargs.get("mhd_output_filename") or f"{filename}.mhd.json"
        output_path = mhd_output_path / Path(output_filename)
        output_path.open("w").write(
            mhd_dataset.model_dump_json(
                indent=2, by_alias=True, exclude_none=True, serialize_as_any=True
            )
        )
        logger.info(
            "%s study MHD file is created with name: %s", mw_study_id, output_path
        )
        return mhd_dataset

    def process_study_design(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
        mw_study_id: str,
    ):
        """Process study design on SUBJECT_SAMPLE_FACTORS section and create
        subject, sample, factor definition, factor value.
        If raw data file and organism part are defined,  it creates nodes for them as well.

        Args:
            mhd_builder (MhDatasetBuilder): graph builder
            mwtab_data (dict[str, Any]): mwTab content as dictionary
            mhd_study (mhd_domain.Study): study mode
            mhd_assays (dict[str, mhd_domain.Assay]): assays
        """
        analysis_list = list(mwtab_data.keys())

        analysis_data = mwtab_data.get(analysis_list[0], {})

        factors: dict[
            str, tuple[mhd_domain.FactorDefinition, mhd_domain.CvTermObject]
        ] = {}

        # TODO: There is no direct link that shows which study design row is used in which analysis
        # It is not possible to create sample run
        # sample runs will be created only for first analysis
        sample_runs: OrderedDict[str, mhd_domain.SampleRun] = OrderedDict()

        sample_factors_section = analysis_data.get("SUBJECT_SAMPLE_FACTORS", {})
        # iterate on study design and create a sample and subject
        # create factor definitions and factor values

        organism_part_field = None
        # check 'sample source' or tissue column is defined in study design section
        # If it is defined use it organism part value
        if sample_factors_section:
            # try to identify which field is the best candidate for organism part
            sample_factors = sample_factors_section[0].get("Factors", {})
            for k in sample_factors:
                k = k.replace("_", " ")
                if k.lower() == "sample source" or k.lower() == "tissue":
                    organism_part_field = k
                    break

        organism_part_description, default_organism_part_value = (
            self.create_default_organism_part_description(
                mhd_builder, mwtab_data, mhd_study, organism_part_field
            )
        )

        for item in sample_factors_section:
            sample_id = item.get("Sample ID", "").replace("-", "")

            subject_id = item.get("Subject ID", "").replace("-", "")
            subject_id = subject_id or sample_id
            subject = mhd_domain.Subject(
                name=subject_id, repository_identifier=subject_id
            )
            sample = mhd_domain.Sample(name=sample_id, repository_identifier=sample_id)
            sample_run = mhd_domain.SampleRun(
                sample_ref=sample.id_, raw_data_file_refs=[]
            )
            sample_runs[sample.name] = sample_run
            mhd_builder.add(sample_run)
            if mhd_assays[analysis_list[0]].sample_run_refs is None:
                mhd_assays[analysis_list[0]].sample_run_refs = []
            mhd_assays[analysis_list[0]].sample_run_refs.append(sample_run.id_)

            mhd_builder.add(subject)
            mhd_builder.add(sample)
            mhd_builder.link(
                subject,
                "source-of",
                sample,
                reverse_relationship_name="derived-from",
            )

            mhd_builder.link(
                mhd_study,
                "has-sample",
                sample,
                reverse_relationship_name="used-in",
            )
            sample_factors: dict[str, Any] = item.get("Factors", {})
            sample_additional_data = item.get("Additional sample data", {})
            raw_data_files = []
            for field in sample_additional_data:
                if field.upper().startswith("RAW_FILE_NAME"):
                    raw_data_file_names = sample_additional_data[field]
                    if isinstance(raw_data_file_names, str):
                        raw_data_file_names = [raw_data_file_names]
                    if raw_data_file_names:
                        for raw_data_file_name in raw_data_file_names:
                            extension = Path(raw_data_file_name).suffix
                            # TODO: URL may not a valid URL.
                            url = f"https://dashboard.gnps2.org/?usi=mzspec:{mw_study_id}:{raw_data_file_name}"
                            raw_data_file = mhd_domain.RawDataFile(
                                name=raw_data_file_name,
                                extension=extension,
                                url_list=[url],
                            )
                            mhd_builder.add(raw_data_file)
                            sample_run.raw_data_file_refs.append(raw_data_file.id_)
                            mhd_builder.link(
                                mhd_study,
                                "has-raw-data-file",
                                raw_data_file,
                                reverse_relationship_name="created-in",
                            )
                            raw_data_files.append(raw_data_file)

            # map sample source or tissue -> organism part
            # others will be sample factor
            organism_part_field_value = None
            if organism_part_field:
                organism_part_field_value = sample_factors.get(organism_part_field, "")
            if organism_part_field_value:
                # if there are multiple organism part definition, fetch the first
                if isinstance(organism_part_field_value, list):
                    organism_part_field_value = organism_part_field_value[0]
                organism_part_value = self.create_cv_term_object(
                    type_="characteristic-value",
                    accession="",
                    source="",
                    name=organism_part_field_value,
                )
                mhd_builder.add(organism_part_value)
                mhd_builder.link(
                    organism_part_description,
                    "has-instance",
                    organism_part_value,
                    reverse_relationship_name="instance-of",
                )
            else:
                organism_part_value = default_organism_part_value
            if organism_part_value:
                mhd_builder.link(
                    subject,
                    "has-characteristic-value",
                    organism_part_value,
                    reverse_relationship_name="value-of",
                )

            for key in sample_factors:
                name = key.replace("_", " ").lower()
                if not key or key in {organism_part_field}:
                    continue

                if name not in factors:
                    if name in COMMON_STUDY_FACTOR_DEFINITIONS:
                        factor_type = self.create_cv_term_object_from(
                            "factor-type", cv=COMMON_STUDY_FACTOR_DEFINITIONS[name]
                        )
                    elif name in MANAGED_STUDY_FACTOR_MAP:
                        factor_type = self.create_cv_term_object_from(
                            "x-mw-factor-type", cv=MANAGED_STUDY_FACTOR_MAP[name]
                        )
                    else:
                        factor_type = self.create_cv_term_object(
                            type_="x-mw-factor-type",
                            accession="",
                            source="",
                            name=name,
                        )

                    factor_definition = mhd_domain.FactorDefinition(
                        name=name, factor_type_ref=factor_type.id_
                    )
                    mhd_builder.add(factor_type)
                    mhd_builder.add(factor_definition)
                    factors[name] = (factor_definition, factor_type)
                    mhd_builder.link(
                        factor_definition,
                        "has-type",
                        factor_type,
                        reverse_relationship_name="type-of",
                    )
                    mhd_builder.link(
                        mhd_study,
                        "has-factor-definition",
                        factor_definition,
                        reverse_relationship_name="used-in",
                    )
                factor_definition, factor_type = factors[name]
                val = sample_factors[key]
                factor_type_name = (
                    "x-mw-factor-value"
                    if factor_type.type_.startswith("x-mw-")
                    else "factor-value"
                )
                factor_value = self.create_cv_term_value_object(
                    type_=factor_type_name, accession="", source="", name=val
                )
                mhd_builder.add(factor_value)
                mhd_builder.link(
                    factor_definition,
                    "has-instance",
                    factor_value,
                    reverse_relationship_name="instance-of",
                )
                mhd_builder.link(
                    sample,
                    "has-factor-value",
                    factor_value,
                    reverse_relationship_name="value-of",
                )

    def create_default_organism_part_description(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        organism_part_field: None | str,
    ):
        analysis_list = list(mwtab_data.keys())
        analysis_data = mwtab_data.get(analysis_list[0], {})
        collection_section: dict[str, Any] = analysis_data.get("COLLECTION", {})

        characteristic_type = self.create_cv_term_object_from(
            "characteristic-type",
            cv=COMMON_CHARACTERISTIC_DEFINITIONS["NCIT:C103199"],
        )
        mhd_builder.add(characteristic_type)
        definition_name = "organism part"
        characteristic_definition = mhd_domain.CharacteristicDefinition(
            name=definition_name,
            characteristic_type_ref=characteristic_type.id_,
        )
        mhd_builder.add(characteristic_definition)
        mhd_builder.link(
            characteristic_definition,
            "has-type",
            characteristic_type,
            reverse_relationship_name="type-of",
        )
        mhd_builder.link(
            mhd_study,
            "has-characteristic-definition",
            characteristic_definition,
            reverse_relationship_name="used-in",
        )
        default_organism_part_value = None
        organism_part_field_value = collection_section.get("SAMPLE_TYPE", "")
        if not organism_part_field and organism_part_field_value:
            accession = source = ""
            default_organism_part_value = self.create_cv_term_object(
                "characteristic-value",
                accession=accession,
                source=source,
                name=organism_part_field_value,
            )
            mhd_builder.add(default_organism_part_value)
            mhd_builder.link(
                characteristic_definition,
                "has-instance",
                default_organism_part_value,
                reverse_relationship_name="instance-of",
            )

        return characteristic_definition, default_organism_part_value

    def create_reported_metabolites(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        reported_metabolite_names = {}

        metabolites = fetch_mw_metabolites(mhd_study.repository_identifier)
        for item in metabolites:
            name = item.metabolite_name
            analysis = item.analysis_id
            # Skip if analysis id is not defined in study
            if not mhd_assays.get(analysis):
                continue
            refmet_name = item.refmet_name
            if name in reported_metabolite_names:
                reported_metabolite = reported_metabolite_names[name]
            else:
                reported_metabolite = mhd_domain.Metabolite(name=name)
                reported_metabolite_names[name] = reported_metabolite
                mhd_builder.add(reported_metabolite)
                mhd_builder.link(
                    mhd_study,
                    "reports",
                    reported_metabolite,
                    reverse_relationship_name="reported-in",
                )

            mhd_builder.link(
                mhd_assays.get(analysis),
                "reports",
                reported_metabolite,
                reverse_relationship_name="reported-in",
            )

            if refmet_name:
                identifier_type: CvTerm = COMMON_COMPOUND_IDENTIFIERS_MAP["REFMET"]
                identifier = self.create_cv_term_value_object(
                    type_="metabolite-identifier",
                    accession=identifier_type.accession,
                    source=identifier_type.source,
                    name=identifier_type.name,
                    value=refmet_name,
                )

                mhd_builder.add(identifier)
                mhd_builder.link(
                    reported_metabolite,
                    "identified-as",
                    identifier,
                    reverse_relationship_name="reported-identifier-of",
                )

    def create_chromotography_protocols(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        analysis_list = list(mwtab_data.keys())
        analysis_list.sort()
        chromotography_protocols: dict[str, mhd_domain.Protocol] = {}
        for analysis in analysis_list:
            analysis_data = mwtab_data.get(analysis, {})
            chromotography_protocols[analysis], _ = self.create_a_protocol(
                mhd_builder,
                mhd_study,
                analysis_data,
                section_name="CHROMATOGRAPHY",
                description_field_name="CHROMATOGRAPHY_SUMMARY",
                protocol_name="chromatography",
            )
            if chromotography_protocols[analysis]:
                protocol = chromotography_protocols[analysis]
                mhd_assays[analysis].protocol_refs.append(protocol.id_)
                mhd_builder.link(
                    mhd_assays[analysis],
                    "follows",
                    protocol,
                    reverse_relationship_name="used-in",
                )
                excludes = {"CHROMATOGRAPHY_SUMMARY"}
                protocol.parameter_definition_refs = []
                protocol_section: dict[str, Any] = analysis_data.get(
                    "CHROMATOGRAPHY", {}
                )
                self.define_protocol_parameters(
                    mhd_builder, protocol, protocol_section, excludes
                )
        return chromotography_protocols

    def create_ms_protocols(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        analysis_list = list(mwtab_data.keys())
        analysis_list.sort()
        ms_protocols: dict[str, mhd_domain.Protocol] = {}
        for analysis in analysis_list:
            analysis_data = mwtab_data.get(analysis, {})

            ms_protocols[analysis], _ = self.create_a_protocol(
                mhd_builder,
                mhd_study,
                analysis_data,
                section_name="MS",
                description_field_name="MS_COMMENTS",
                protocol_name="mass spectrometry",
            )
            if ms_protocols[analysis]:
                protocol = ms_protocols[analysis]
                mhd_assays[analysis].protocol_refs.append(protocol.id_)
                mhd_builder.link(
                    mhd_assays[analysis],
                    "follows",
                    protocol,
                    reverse_relationship_name="used-in",
                )
                excludes = {"MS_COMMENTS"}
                protocol.parameter_definition_refs = []
                protocol_section: dict[str, Any] = analysis_data.get("MS", {})
                self.define_protocol_parameters(
                    mhd_builder, protocol, protocol_section, excludes
                )
        return ms_protocols

    def create_project(
        self,
        mhd_builder: MhDatasetBuilder,
        project_section: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ) -> mhd_domain.Project:
        project_title = project_section.get("PROJECT_TITLE", "")
        project_description = project_section.get("PROJECT_SUMMARY", "")
        project_doi = (
            project_section.get("DOI", "")
            .replace("http://dx.doi.org/", "")
            .replace("https://doi.org/", "")
        )
        project_doi = project_doi or None

        mhd_project = mhd_domain.Project(
            title=project_title, description=project_description, doi=project_doi
        )
        mhd_builder.add(mhd_project)
        mhd_builder.link(
            mhd_project,
            "has-study",
            mhd_study,
            reverse_relationship_name="part-of",
        )
        # add a project descriptor if PROJECT TYPE is not empty
        project_type = project_section.get("PROJECT_TYPE", None)
        if project_type:
            descriptor_cv = self.create_cv_term_object(
                type_="descriptor", name=project_type, accession="", source=""
            )
            mhd_builder.add(descriptor_cv)
            mhd_builder.link(
                mhd_project,
                "described-as",
                descriptor_cv,
                reverse_relationship_name="describes",
            )

        return mhd_project

    def create_principal_investigator(
        self,
        mhd_builder: MhDatasetBuilder,
        project_section: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_submitter: None | mhd_domain.Person,
        mhd_study_organization: None | mhd_domain.Organization,
    ) -> tuple[mhd_domain.Person, mhd_domain.Organization]:
        pi_first_name = project_section.get("FIRST_NAME", "")
        pi_last_name = project_section.get("LAST_NAME", "")
        pi_full_name = " ".join([x for x in (pi_first_name, pi_last_name) if x])
        mhd_pi = None
        if pi_full_name:
            if mhd_submitter and pi_full_name == mhd_submitter.full_name:
                mhd_pi = mhd_submitter
            else:
                pi_phone = project_section.get("PHONE", "")
                pi_address = project_section.get("ADDRESS", "")
                pi_email = project_section.get("EMAIL", "")
                pi_emails = self.parse_email(mhd_study.repository_identifier, pi_email)
                mhd_pi = mhd_domain.Person(
                    full_name=pi_full_name,
                    emails=pi_emails,
                    addresses=[pi_address],
                    phones=[pi_phone],
                )
                mhd_builder.add(mhd_pi)
            mhd_builder.link(
                mhd_pi,
                "principal-investigator-of",
                mhd_study,
                reverse_relationship_name="has-principal-investigator",
            )

        organization_name = project_section.get("INSTITUTE", "")
        organization_address = project_section.get("ADDRESS", "")
        mhd_project_organization = None
        if mhd_study_organization:
            # if organization of project is same with study organization
            # use same organization node
            if (
                organization_name == mhd_study_organization.name
                or organization_address == mhd_study_organization.address
            ):
                mhd_project_organization = mhd_study_organization
                # select longest organization name
                mhd_project_organization.name = max(
                    mhd_project_organization.name, organization_name
                )

        if not mhd_project_organization:
            mhd_project_organization = mhd_domain.Organization(
                name=organization_name, address=organization_address
            )
            mhd_builder.add(mhd_project_organization)
        if mhd_pi:
            mhd_builder.link(
                mhd_pi,
                "affiliated-with",
                mhd_project_organization,
                reverse_relationship_name="affiliates",
            )
        return mhd_pi, mhd_project_organization

    def parse_email(self, mw_study_id, email: str) -> list[str]:
        if not email or len(email) < 5:
            logger.warning("%s: '%s' email is not valid. %s", mw_study_id, email)
            return []
        email = email.replace(";", ",")
        email = email.replace(" ", "")
        emails = []
        for x in email.split(","):
            try:
                validate_email(x.strip())
                emails.append(x.strip())
            except Exception as ex:
                logger.warning(
                    "%s: '%s' email is not valid. %s", mw_study_id, email, ex
                )

        return emails

    def create_submitter(
        self,
        mhd_builder: MhDatasetBuilder,
        study_section: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ) -> tuple[mhd_domain.Person, mhd_domain.Organization]:
        submitter_first_name = study_section.get("FIRST_NAME", "")
        submitter_last_name = study_section.get("LAST_NAME", "")
        submitter_phone = study_section.get("PHONE", "")
        submitter_address = study_section.get("ADDRESS", "")

        submitter_full_name = " ".join(
            [x for x in (submitter_first_name, submitter_last_name) if x]
        )
        mhd_study_organization = None
        if submitter_full_name:
            submitter_email = study_section.get("EMAIL", None)
            submitter_emails = self.parse_email(
                mhd_study.repository_identifier, submitter_email
            )
            mhd_submitter = mhd_domain.Person(
                full_name=submitter_full_name,
                emails=submitter_emails,
                addresses=[submitter_address],
                phones=[submitter_phone],
            )
            mhd_builder.add(mhd_submitter)
            mhd_builder.link(
                mhd_submitter,
                "submits",
                mhd_study,
                reverse_relationship_name="submitted-by",
            )
            organization_name = study_section.get("INSTITUTE", "")
            organization_address = study_section.get("ADDRESS", "")
            mhd_study_organization = mhd_domain.Organization(
                name=organization_name, address=organization_address
            )
            mhd_builder.add(mhd_study_organization)
            mhd_builder.link(
                mhd_submitter,
                "affiliated-with",
                mhd_study_organization,
                reverse_relationship_name="affiliates",
            )

        return mhd_submitter, mhd_study_organization

    def create_assays(
        self,
        mhd_builder: MhDatasetBuilder,
        mwtab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mw_study_id: str,
        common_protocols: list[mhd_domain.Protocol],
    ):
        mhd_assays: dict[str, mhd_domain.Assay] = {}
        analysis_list = list(mwtab_data.keys())
        analysis_list.sort()

        tsv_file_format = self.create_cv_term_object(
            type_="descriptor", accession="EDAM:3475", source="EDAM", name="TSV"
        )  # TODO: update mwTab is defined in EDAM

        mhd_builder.add(tsv_file_format)
        for analysis in analysis_list:
            file_name = f"{mw_study_id}_{analysis}.txt"
            metadata_http_file_url = (
                "https://www.metabolomicsworkbench.org/data/study_textformat_view.php"
                f"?STUDY_ID={mw_study_id}&ANALYSIS_ID={analysis}"
            )
            extension = ".txt"
            metadata_file = mhd_domain.MetadataFile(
                name=file_name,
                url_list=[HttpUrl(metadata_http_file_url)],
                extension=extension,
                format_ref=tsv_file_format.id_,
            )

            mhd_builder.add(metadata_file)
            mhd_builder.link(
                mhd_study,
                "has-metadata-file",
                metadata_file,
                reverse_relationship_name="describes",
            )

            mhd_assays[analysis] = mhd_domain.Assay(
                name=file_name,
                repository_identifier=analysis,
                metadata_file_ref=metadata_file.id_,
                protocol_refs=[],
            )
            mhd_builder.add(mhd_assays[analysis])
            mhd_builder.link(
                mhd_study,
                "has-assay",
                mhd_assays[analysis],
                reverse_relationship_name="part-of",
            )
            # add study level protocols to assay
            for protocol in common_protocols:
                mhd_assays[analysis].protocol_refs.append(protocol.id_)
                mhd_builder.link(
                    mhd_assays[analysis],
                    "follows",
                    protocol,
                    reverse_relationship_name="used-in",
                )
            result_file_data = (
                mwtab_data[analysis].get("MS", {}).get("MS_RESULTS_FILE", "")
            )
            if result_file_data:
                result_file_name = result_file_data.split()[0]
                result_file_url = f"https://www.metabolomicsworkbench.org/studydownload/{result_file_name}"
                extension = Path(result_file_name).suffix
                result_file = mhd_domain.ResultFile(
                    name=result_file_name,
                    url_list=[HttpUrl(result_file_url)],
                    extension=extension,
                    format_ref=tsv_file_format.id_,
                )
                mhd_builder.add(result_file)
                mhd_builder.link(
                    metadata_file,
                    "references",
                    result_file,
                    reverse_relationship_name="referenced-in",
                )
                mhd_builder.link(
                    mhd_study,
                    "has-result-file",
                    result_file,
                    reverse_relationship_name="created-in",
                )
                mhd_builder.link(
                    mhd_assays[analysis],
                    "has-result-file",
                    result_file,
                    reverse_relationship_name="created-in",
                )

        return mhd_assays

    def create_treatment_protocol(
        self,
        mhd_builder: MhDatasetBuilder,
        analysis_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ):
        treatment_section: dict[str, Any] = analysis_data.get("TREATMENT", {})
        treatment_protocol, _ = self.create_a_protocol(
            mhd_builder,
            mhd_study,
            analysis_data,
            section_name="TREATMENT",
            description_field_name="TREATMENT_SUMMARY",
            protocol_name="treatment",
            ignore_if_no_description=True,
        )
        if treatment_protocol:
            excludes = {
                "TREATMENT_SUMMARY",
                "TREATMENT_PROTOCOL_ID",
                "TREATMENT_PROTOCOL_FILENAME",
                "TREATMENT_PROTOCOL_COMMENTS",
            }
            treatment_protocol.parameter_definition_refs = []
            self.define_protocol_parameters(
                mhd_builder, treatment_protocol, treatment_section, excludes
            )

        return treatment_protocol

    def create_sample_preparation_protocol(
        self,
        mhd_builder: MhDatasetBuilder,
        analysis_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ) -> mhd_domain.Protocol:
        sample_prep_section: dict[str, Any] = analysis_data.get("SAMPLEPREP", {})
        preparation_protocol, _ = self.create_a_protocol(
            mhd_builder,
            mhd_study,
            analysis_data,
            section_name="SAMPLEPREP",
            description_field_name="SAMPLEPREP_SUMMARY",
            protocol_name="sample preparation",
        )
        if preparation_protocol:
            excludes = {
                "SAMPLEPREP_SUMMARY",
                "SAMPLEPREP_PROTOCOL_ID",
                "SAMPLEPREP_PROTOCOL_FILENAME",
                "SAMPLEPREP_PROTOCOL_COMMENTS",
            }
            preparation_protocol.parameter_definition_refs = []
            self.define_protocol_parameters(
                mhd_builder, preparation_protocol, sample_prep_section, excludes
            )

        return preparation_protocol

    def create_collection_protocol(
        self,
        mhd_builder: MhDatasetBuilder,
        analysis_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ) -> mhd_domain.Protocol:
        collection_section: dict[str, Any] = analysis_data.get("COLLECTION", {})
        collection_protocol, _ = self.create_a_protocol(
            mhd_builder,
            mhd_study,
            analysis_data,
            section_name="COLLECTION",
            description_field_name="COLLECTION_SUMMARY",
            protocol_name="sample collection",
        )
        if collection_protocol:
            excludes = {
                "COLLECTION_SUMMARY",
                "SAMPLE_TYPE",
                "COLLECTION_PROTOCOL_ID",
                "COLLECTION_PROTOCOL_FILENAME",
                "COLLECTION_PROTOCOL_COMMENTS",
            }
            collection_protocol.parameter_definition_refs = []
            self.define_protocol_parameters(
                mhd_builder, collection_protocol, collection_section, excludes
            )

        return collection_protocol

    def create_organism_characteristic(
        self,
        mhd_builder: MhDatasetBuilder,
        subject_section: dict[str, Any],
        mhd_study: mhd_domain.Study,
    ) -> None:
        """Create characteristic definition and value from
           SUBJECT_SPECIES and TAXONOMY_ID fields in SUBJECT section

        Args:
            mhd_builder (MhDatasetBuilder): graph builder
            subject_section (dict[str, Any]): SUBJECT section of mwTab as a dictinary
            mhd_study (mhd_domain.Study): study node
        """
        organism_name: str = subject_section.get("SUBJECT_SPECIES", "")
        ncbi_taxon: str = subject_section.get("TAXONOMY_ID", "")
        accession = ""
        source = ""
        if ncbi_taxon and ncbi_taxon.isnumeric():
            accession = f"NCBITaxon:{ncbi_taxon}"
            source = "NCBITAXON"

        if organism_name:
            characteristic_type = self.create_cv_term_object_from(
                "characteristic-type",
                cv=COMMON_CHARACTERISTIC_DEFINITIONS["NCIT:C14250"],
            )
            definition_name = "organism"
            characteristic_definition = mhd_domain.CharacteristicDefinition(
                name=definition_name,
                characteristic_type_ref=characteristic_type.id_,
            )
            characteristic_value = self.create_cv_term_object(
                "characteristic-value",
                accession=accession,
                source=source,
                name=organism_name,
            )

            self.add_characteristic_value(
                mhd_builder,
                mhd_study,
                characteristic_type,
                characteristic_definition,
                characteristic_value,
            )
            return characteristic_type, characteristic_definition, characteristic_value
        return None, None, None

    def create_study(
        self,
        mhd_builder: MhDatasetBuilder,
        study_section: dict[str, Any],
        mw_study_id: str,
        dataset_provider: mhd_domain.CvTermValueObject,
    ) -> mhd_domain.Study:
        """Create a study node, set initial property values and link to data-provider

        Args:
            mhd_builder (MhDatasetBuilder): graph builder
            study_section (dict[str, Any]): STUDY section of mwTab as a dictinary
            mw_study_id (str): Metabolomics Workbench study accession. e.g., ST000001
            dataset_provider (mhd_domain.CvTermValueObject): data-provider node to assign
            repository

        Returns:
            mhd_domain.Study: _description_
        """

        study_title = study_section.get("STUDY_TITLE", "")
        study_description = study_section.get("STUDY_SUMMARY", "")

        # Submittion and release date values are same now!!!
        # TODO: submission and release dates may be fetched from database.
        # TODO: Some studies does not have SUBMIT_DATE. eg., ST004186
        submission_date = self.convert_str_to_datetime(
            study_section.get("SUBMIT_DATE", None)
        )
        release_date = self.convert_str_to_datetime(
            study_section.get("SUBMIT_DATE", None)
        )

        if not submission_date:
            # TODO: !!UPDATE IT
            submission_date = datetime.datetime.now(datetime.timezone.utc)
            release_date = submission_date
        mw_study_repository_url = HttpUrl(f"{PUBLIC_MW_STUDY_URL_PREFIX}{mw_study_id}")

        #####################################################################################
        # license_url is None. Incomment if study has a default licence
        license_url = None
        # license_url = HttpUrl("https://creativecommons.org/publicdomain/zero/1.0/")
        #####################################################################################

        mhd_study = mhd_domain.Study(
            repository_identifier=mw_study_id,
            created_by_ref=dataset_provider.id_,
            mhd_identifier=None,
            title=study_title,
            description=study_description,
            submission_date=submission_date,
            public_release_date=release_date,
            dataset_url_list=[mw_study_repository_url],
            license=license_url,
            protocol_refs=[],
        )
        mhd_builder.add(mhd_study)
        mhd_builder.add_node(dataset_provider)
        mhd_builder.link(
            dataset_provider,
            "provides",
            mhd_study,
            reverse_relationship_name="provided-by",
        )
        # Add a descriptor if STUDY TYPE is not empty
        study_type = study_section.get("STUDY_TYPE", None)
        if study_type:
            descriptor_cv = self.create_cv_term_object(
                type_="descriptor", name=study_type, accession="", source=""
            )
            mhd_builder.add(descriptor_cv)
            mhd_builder.link(
                mhd_study,
                "described-as",
                descriptor_cv,
                reverse_relationship_name="describes",
            )

        return mhd_study

    def create_data_provider(
        self, repository_name: str
    ) -> mhd_domain.CvTermValueObject:
        """Creates a data-provider node with repository name value

        Args:
            repository_name (str): Name of repository

        Returns:
            mhd_domain.CvTermValueObject: data-provider node
        """
        dataset_provider = self.create_cv_term_value_object(
            type_="data-provider",
            source="NCIT",
            accession="NCIT:C189151",
            name="Study Data Repository",
            value=repository_name,
        )

        return dataset_provider

    def add_characteristic_value(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study,
        characteristic_type,
        characteristic_definition,
        characteristic_value,
    ):
        mhd_builder.add(characteristic_type)
        mhd_builder.add(characteristic_definition)
        mhd_builder.add(characteristic_value)
        mhd_builder.link(
            characteristic_definition,
            "has-type",
            characteristic_type,
            reverse_relationship_name="type-of",
        )
        mhd_builder.link(
            characteristic_definition,
            "has-instance",
            characteristic_value,
            reverse_relationship_name="instance-of",
        )
        mhd_builder.link(
            mhd_study,
            "has-characteristic-definition",
            characteristic_definition,
            reverse_relationship_name="used-in",
        )

    def define_protocol_parameters(
        self,
        mhd_builder: MhDatasetBuilder,
        protocol: mhd_domain.Protocol,
        protocol_section: dict[str, Any],
        excludes: list[str],
    ):
        mw_parameter_map = MW_PROTOCOL_PARAMETER_DEFINITIONS_MAP[protocol.name]
        common_parameters_map = COMMON_PROTOCOL_PARAMETER_DEFINITIONS_MAP[protocol.name]
        for field in protocol_section:
            if field and protocol_section.get(field) and field not in excludes:
                # define parameter name from field name.
                # Replace _ to space and make lowercase it
                definition_name = field.replace("_", " ").lower()
                # create common data types.
                # If they are not defined in MHD model, create custom type with prefix x-mw-
                if definition_name in common_parameters_map:
                    parameter_type = self.create_cv_term_object_from(
                        type_="parameter-type",
                        cv=common_parameters_map[definition_name],
                    )
                elif definition_name in mw_parameter_map:
                    parameter_type = self.create_cv_term_object_from(
                        type_="x-mw-parameter-type",
                        cv=mw_parameter_map[definition_name],
                    )
                else:
                    # TODO: this is an example CV term for storage
                    parameter_type = self.create_cv_term_object(
                        type_="x-mw-parameter-type",
                        source="",
                        accession="",
                        name=definition_name,
                    )
                mhd_builder.add(parameter_type)
                definition = mhd_domain.ParameterDefinition(
                    name=definition_name,
                    parameter_type_ref=parameter_type.id_,
                )
                mhd_builder.add(definition)
                # Define parameter value type.
                # If it is type of a definition that has custom type, create custom value with prefix x-mw-
                type_ = (
                    "x-mw-parameter-value"
                    if parameter_type.type_.startswith("x-mw-")
                    else "parameter-value"
                )
                field_value = self.create_cv_term_object(
                    type_=type_,
                    accession="",
                    source="",
                    name=protocol_section.get(field),
                )
                mhd_builder.add(field_value)
                mhd_builder.link(
                    definition,
                    "has-type",
                    parameter_type,
                    reverse_relationship_name="type-of",
                )
                mhd_builder.link(
                    protocol,
                    "has-protocol-definition",
                    definition,
                    reverse_relationship_name="used-in",
                )
                mhd_builder.link(
                    definition,
                    "has-instance",
                    field_value,
                    reverse_relationship_name="instance-of",
                )

    def create_a_protocol(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        analysis_data: dict[str, Any],
        section_name: str,
        description_field_name: str,
        protocol_name: str,
        ignore_if_no_description: bool = False,
    ) -> tuple[mhd_domain.Protocol, mhd_domain.CvTermObject]:
        protocol_section: dict[str, Any] = analysis_data.get(section_name, {})
        protocol_type = None
        protocol = None
        if protocol_section:
            desc = protocol_section.get(description_field_name, "")
            desc = desc if len(desc) > 1 else None
            if ignore_if_no_description and not desc:
                return protocol, protocol_type
            protocol_type = self.create_cv_term_object_from(
                type_="protocol-type", cv=MW_PROTOCOLS_MAP[protocol_name]
            )
            mhd_builder.add(protocol_type)
            protocol = mhd_domain.Protocol(
                name=protocol_name,
                protocol_type_ref=protocol_type.id_,
                description=desc,
            )
            mhd_builder.add(protocol)
            mhd_builder.link(
                mhd_study,
                "has-protocol",
                protocol,
                reverse_relationship_name="used-in",
            )
            mhd_builder.link(
                protocol,
                "has-type",
                protocol_type,
                reverse_relationship_name="type-of",
            )
            mhd_study.protocol_refs.append(protocol.id_)
        return protocol, protocol_type

    def create_cv_term_object(
        self, type_: str, accession: str, source: str, name: str | list
    ) -> mhd_domain.CvTermObject:
        # MW json file may contain multipal values for same field
        # contacanate them
        if name and isinstance(name, list):
            name = ", ".join(name)
        if not source or not accession:
            return mhd_domain.CvTermObject(type_=type_, name=name)

        return mhd_domain.CvTermObject(
            type_=type_, accession=accession, source=source, name=name
        )

    def create_cv_term_object_from(
        self, type_: str, cv: CvTerm
    ) -> mhd_domain.CvTermObject:
        if not cv.source or not cv.accession:
            return mhd_domain.CvTermObject(type_=type_, name=cv.name)

        return mhd_domain.CvTermObject(
            type_=type_, accession=cv.accession, source=cv.source, name=cv.name
        )

    def create_cv_term_value_object(
        self,
        type_: str,
        accession: str = "",
        source: str = "",
        name: str | list = "",
        value: None | str | list = None,
        unit: None | UnitCvTerm = None,
    ) -> mhd_domain.CvTermValueObject:
        # MW json file may contain multipal values for same field
        # contacanate them
        if name and isinstance(name, list):
            name = ", ".join(name)
        if value and isinstance(value, list):
            value = ", ".join(value)
        unit_cv = None
        if unit:
            if not source or not accession:
                unit_cv = UnitCvTerm(name=unit.name) if unit else None

        if not source or not accession:
            return mhd_domain.CvTermValueObject(
                type_=type_, name=name, value=value, unit=unit_cv
            )

        return mhd_domain.CvTermValueObject(
            type_=type_,
            accession=accession,
            source=source,
            name=name,
            value=value,
            unit=unit_cv,
        )

    def convert_str_to_datetime(self, date_str: str) -> datetime.datetime:
        """
        Convert a date string like "September 26, 2024, 4:43 pm" to a datetime object.
        """
        if not date_str:
            return None
        return dateutil.parser.parse(date_str)
