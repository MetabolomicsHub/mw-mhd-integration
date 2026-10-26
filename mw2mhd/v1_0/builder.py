import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Generic, TypeVar, get_args

import dateutil
from bs4 import BeautifulSoup
from email_validator import validate_email
from mhd_model.model.definitions import (
    MHD_MODEL_PROFILE_SCHEMA_MAP,
    MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
    MHD_MODEL_V0_1_MS_PROFILE_NAME,
    MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
    MHD_MODEL_V1_0_MS_PROFILE_NAME,
)
from mhd_model.model.v1_0.dataset.profiles.base import graph_nodes as mhd_domain
from mhd_model.model.v1_0.dataset.profiles.base import relationships
from mhd_model.model.v1_0.dataset.profiles.base.profile import (
    MhDatasetBaseProfile_v1_0,
)
from mhd_model.model.v1_0.rules.managed_cv_terms import (
    COMMON_CHARACTERISTIC_DEFINITIONS,
    COMMON_MISSING_DATA_TERMS,
    COMMON_PROTOCOLS,
    COMMON_TECHNOLOGY_TYPES,
    MISSING_PUBLICATION_REASON,
)
from mhd_model.shared.base import CvTerm, KeyValue, UnitCvTerm
from mhd_model.shared.dataset_builder import MhDatasetBuilder
from mhd_model.shared.model import BaseMhDatasetProfile
from mhd_model.shared.validation.cv_term_helper import BaseCvTermHelper
from mhd_model.validation import select_cv_term_helper

from mw2mhd.config import Mw2MhdConfiguration
from mw2mhd.v1_0 import definitions
from mw2mhd.v1_0.definitions import convert_to_cv_term_with_mapping, get_urn

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=MhDatasetBaseProfile_v1_0)


class MhdDatasetBuilder_v1_0(Generic[T]):
    def build(
        self,
        mw_study_id: str,
        mhd_id: None | str,
        mw_tab_input_folder_path: str | Path,
        mhd_output_path: Path,
        config: Mw2MhdConfiguration,
        cv_term_helper: None | BaseCvTermHelper = None,
        ontology_lookup_db_path: None | str = None,
        target_mhd_model_schema_uri: None | str = None,
        target_mhd_model_profile_uri: None | str = None,
        **kwargs,
    ) -> T:
        #####################################################################################
        # Load json files in input folder
        #####################################################################################
        if isinstance(mw_tab_input_folder_path, str):
            mw_tab_input_folder_path = Path(mw_tab_input_folder_path)
        if not mw_tab_input_folder_path or not mw_tab_input_folder_path.exists():
            raise TypeError("MW Tab study folder is required")
        mw_data: dict = {"analysis": {}}
        for file in mw_tab_input_folder_path.glob(f"{mw_study_id}*.json"):
            json_data: dict[str, Any] = json.loads(file.read_bytes())
            if file.name.startswith(f"{mw_study_id}_AN"):
                analysis_id = json_data.get("METABOLOMICS WORKBENCH", {}).get(
                    "ANALYSIS_ID"
                )
                mw_data["analysis"][analysis_id] = json_data
            elif file.name.startswith(f"{mw_study_id}_files"):
                mw_data["files"] = json_data.get("files", {})
            elif file.name.startswith(f"{mw_study_id}_metabolites"):
                mw_data["metabolites"] = json_data
            elif file.name.startswith(f"{mw_study_id}_summary"):
                mw_data["summary"] = json_data.get("summary", {})
            else:
                logger.warning("%s is not an expected file.", file)

        if "metabolites" not in mw_data:
            mw_data["metabolites"] = {}
        if "files" not in mw_data:
            mw_data["files"] = {}
        if "summary" not in mw_data:
            mw_data["summary"] = {}

        mwtab_analysis_data: dict = mw_data["analysis"]
        if not mwtab_analysis_data:
            raise ValueError(
                f"Could not loaded MW Tab Json files for study {mw_study_id}"
            )

        #####################################################################################
        # Select ontology term selection service (local vs OLS)
        #####################################################################################
        if not cv_term_helper:
            cv_term_helper = select_cv_term_helper(db_path=ontology_lookup_db_path)

        repository_name = definitions.REPOSITORY_NAME
        #####################################################################################
        # Select MS studies and fail if there is non-MS analysis
        #####################################################################################
        technology_types = set()
        analysis_list = []
        ms_technology = COMMON_TECHNOLOGY_TYPES.get("mass spectrometry assay")
        for k, v in mwtab_analysis_data.items():
            if isinstance(v, dict):
                technology_type = v.get("ANALYSIS", {}).get("ANALYSIS_TYPE")
                term = definitions.convert_to_cv_term_with_mapping(
                    "technology type", technology_type
                )
                technology_types.add(term)
                if term.get_as_string() == ms_technology.get_as_string():
                    analysis_list.append(k)

        analysis_list.sort()

        # Ensure study has MS analyses.
        if not technology_types:
            raise ValueError(f"{mw_study_id} has no MS analysis")

        if analysis_list and len(technology_types) > 1:
            technologies = ", ".join([str(x) for x in technology_types])
            message = f"{mw_study_id} has non-MS analyses that will be skipped. {technologies}"
            logger.error(message)
            raise ValueError(message)

        analysis_id = analysis_list[0]

        #####################################################################################
        # Select first analysis to fetch study level data
        #####################################################################################
        first_analysis: dict = mwtab_analysis_data.get(analysis_id, {})
        study_section: dict[str, Any] = first_analysis.get("STUDY", {})
        project_section: dict[str, Any] = first_analysis.get("PROJECT", {})
        subject_section: dict[str, Any] = first_analysis.get("SUBJECT", {})
        mw_section: dict[str, Any] = first_analysis.get("METABOLOMICS WORKBENCH", {})

        #####################################################################################
        # Create a dataset builder
        dataset = self.create_dataset(
            mw_study_id,
            mhd_id,
            repository_name,
            mw_section,
            study_section,
            target_mhd_model_profile_uri=target_mhd_model_profile_uri,
            target_mhd_model_schema_uri=target_mhd_model_schema_uri,
        )

        mhd_builder = MhDatasetBuilder[T](
            dataset=dataset, cv_term_helper=cv_term_helper
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
            mhd_builder,
            study_section,
            mw_section,
            mw_study_id,
            dataset_provider,
            mhd_id,
        )

        # #####################################################################################
        # Create characteristic definition - organism, organism part, disease, cell line, cell type
        # #####################################################################################
        characteristic_definitions: dict[
            str,
            dict[str, tuple],
        ] = self.create_subject_characteristics(mhd_builder, subject_section, mhd_study)

        # #####################################################################################
        # Create sample collection protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        # analysis_data = first_analysis
        collection_protocol, collection_run_config = self.create_collection_protocol(
            mhd_builder, first_analysis, mhd_study
        )

        # #####################################################################################
        # Create sample collection protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        preparation_protocol, preparation_run_config = (
            self.create_sample_preparation_protocol(
                mhd_builder, first_analysis, mhd_study
            )
        )

        # #####################################################################################
        # Create treatment protocol and parameter definitions
        # use first analysis data to define it
        # #####################################################################################
        treatment_protocol, treatment_run_config = self.create_treatment_protocol(
            mhd_builder, first_analysis, mhd_study
        )

        #####################################################################################
        # Add metadata files mwTab files and assays with initial values
        # add study level common protocols to each assay
        #####################################################################################
        common_protocols = [
            x
            for x in (collection_protocol, preparation_protocol, treatment_protocol)
            if x
        ]
        # filter if a common filter is None. e.g., filter if treatment protocol is not defined.
        mhd_assays: dict[str, mhd_domain.Assay] = self.create_assays(
            mhd_builder,
            mw_tab_data=mw_data,
            mhd_study=mhd_study,
            mw_study_id=mw_study_id,
            common_protocols=common_protocols,
        )

        #####################################################################################
        # Add Submitter
        #####################################################################################
        mhd_submitter, mhd_study_organization = self.create_submitter(
            mhd_builder, study_section, mhd_study, cv_term_helper=cv_term_helper
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
        # Define publication : No doi means pending status
        #####################################################################################
        self.create_publication(mhd_builder, mhd_study, mw_study_id, project_section)

        #####################################################################################
        # Create Project and link project and Organization
        #####################################################################################
        mhd_project = self.create_project(
            mhd_builder, project_section, mhd_study, cv_term_helper=cv_term_helper
        )

        mhd_builder.link(
            mhd_project_organization,
            "manages",
            mhd_project,
            reverse_relationship_name="managed-by",
        )

        # #####################################################################################
        # # Create MS protocols for assays
        # #####################################################################################
        ms_run_configs = self.create_ms_protocols(
            mhd_builder, mw_data, mhd_study, mhd_assays
        )

        # #####################################################################################
        # # Create Chromatograpy protocols for assays
        # ####################################################################################
        chromatography_run_configs = self.create_chromatography_protocols(
            mhd_builder, mw_data, mhd_study, mhd_assays
        )
        protocol_run_configs = {}
        for item in analysis_list:
            items = []
            if collection_run_config:
                items.append(collection_run_config)
            if preparation_run_config:
                items.append(preparation_run_config)
            if treatment_run_config:
                items.append(treatment_run_config)
            chromatography_run_configs_list = chromatography_run_configs.get(item)
            if chromatography_run_configs_list:
                items.append(chromatography_run_configs_list)
            ms_run_config_list = ms_run_configs.get(item)
            if ms_run_config_list:
                items.append(ms_run_config_list)
            if items:
                protocol_run_configs[item] = items
        # #####################################################################################
        # # Add raw and result data files
        # #####################################################################################
        # files_dict = first_analysis
        self.process_study_files(
            mhd_builder, mhd_study, mw_data, mhd_assays, protocol_run_configs
        )

        # #####################################################################################
        # # Add study factors, raw-data-files, samples, subjects, factor values.
        # #####################################################################################
        self.process_study_design(
            mhd_builder,
            mw_data,
            first_analysis,
            mhd_study,
            mhd_assays,
            mw_study_id,
            characteristic_definitions=characteristic_definitions,
            protocol_run_configs=protocol_run_configs,
        )

        # #####################################################################################
        # # Add metabolites and metabolite-identifiers
        # #####################################################################################
        self.create_reported_metabolites(mhd_builder, mw_data, mhd_study, mhd_assays)

        #####################################################################################
        # Build and save dataset
        #####################################################################################

        mhd_dataset: BaseMhDatasetProfile = mhd_builder.build_dataset(
            start_item_refs=[mhd_study.id_]
        )
        filename = mw_study_id
        if isinstance(mhd_output_path, str):
            mhd_output_path = Path(mhd_output_path)
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

    def create_publication(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        mw_study_id: str,
        project_section: dict,
    ):
        doi = project_section.get("PUBLICATION_DOI") or ""
        if doi:
            # Assumption: There is one publication in PUBLICATIONS field
            doi = (
                doi.replace("http://dx.doi.org/", "")
                .replace("http://doi.org/", "")
                .replace("https://doi.org/", "")
            )
            title = project_section.get("PUBLICATIONS") or ""
            title = title.strip()
            if title and doi:
                mhd_publication = mhd_domain.Publication(
                    uri=get_urn(mw_study_id, mhd_domain.Publication, doi),
                    title=title,
                    doi=doi,
                )
                mhd_builder.add(mhd_publication)
                mhd_builder.link(
                    mhd_study,
                    "has-publication",
                    mhd_publication,
                    reverse_relationship_name="describes",
                )
        else:
            pending = MISSING_PUBLICATION_REASON["pending publication"]
            mhd_publication_status = self.create_cv_term_object(
                type_="descriptor",
                accession=pending.accession,
                name=pending.name,
                source=pending.source,
            )
            mhd_builder.add(mhd_publication_status)
            mhd_builder.link(
                mhd_study,
                "defined-as",
                mhd_publication_status,
                reverse_relationship_name="publication-status-of",
            )

    def get_dataset_class(self) -> type[T]:
        # cls.__orig_bases__ holds (Repository[User],)
        orig_class = getattr(self, "__orig_class__", None)
        if orig_class is not None:
            return get_args(orig_class)[0]
        raise TypeError("Could not instantiated with a type parameter")

    def create_dataset(
        self,
        mw_study_id: str,
        mhd_id: None | str,
        repository_name: str,
        mw_section: dict,
        study_section: dict,
        target_mhd_model_profile_uri: None | str,
        target_mhd_model_schema_uri: None | str,
    ):
        mhd_id = mw_section.get("MHD_ID", "") or mhd_id
        study_id = mw_section.get("STUDY_ID", "") or mw_study_id
        if not study_id:
            study_id = mw_study_id
        if not study_id or (mw_study_id and study_id != mw_study_id):
            raise ValueError(
                f"Study error is not defined or does not match input. Input: {study_id} {mw_study_id}"
            )
        version = mw_section.get("VERSION") or None
        if version:
            try:
                repository_revision = int(version) or None
            except Exception as ex:
                logger.warning("Version information is not valid %s: %s", version, ex)
                version = None
        revision_date = mw_section.get("VERSION_DATE") or None
        if revision_date:
            try:
                revision_date = datetime.datetime.fromisoformat(revision_date) or None
            except Exception as ex:
                logger.warning(
                    "Version date information is not valid %s: %s", revision_date, ex
                )
                revision_date = None

        release_date = mw_section.get("RELEASE_DATE") or None
        if release_date:
            try:
                release_date = datetime.datetime.fromisoformat(release_date) or None
            except Exception:
                logger.warning("Release date information is not valid %s", release_date)
                release_date = None
        submission_date = mw_section.get("SUBMISSION_DATE") or None
        if submission_date:
            try:
                submission_date = (
                    datetime.datetime.fromisoformat(submission_date) or None
                )
            except Exception:
                logger.warning(
                    "Submission date information is not valid %s", submission_date
                )
                submission_date = None
        if version == 1 and not revision_date:
            revision_date = release_date
        mhd_id = mhd_id if mhd_id and mhd_id.startswith("MHD") else None
        identifier = mhd_id or mw_study_id
        target_mhd_model_profile_uri = (
            mw_section.get("MHD_MODEL_PROFILE") or target_mhd_model_profile_uri
        )
        if target_mhd_model_profile_uri not in (
            MHD_MODEL_V1_0_MS_PROFILE_NAME,
            MHD_MODEL_V1_0_LEGACY_PROFILE_NAME,
            MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
            MHD_MODEL_V0_1_MS_PROFILE_NAME,
        ):
            raise ValueError(f"Unsupported profile: {target_mhd_model_profile_uri}")

        schema_uri = MHD_MODEL_PROFILE_SCHEMA_MAP.get(target_mhd_model_profile_uri)
        target_mhd_model_schema_uri = (
            schema_uri
            or target_mhd_model_schema_uri
            or MHD_MODEL_V1_0_DEFAULT_SCHEMA_NAME
        )
        now = datetime.datetime.now(datetime.UTC)
        title = study_section.get("STUDY_TITLE") or ""
        dataset_class = self.get_dataset_class()
        dataset = dataset_class(
            uri=get_urn(identifier, dataset_class, None),
            repository_short_name="MW",
            created_at=now,
            repository_name=repository_name,
            name=f"{identifier}: {title}",
            description=f"{repository_name} dataset with {study_id} accession",
            mhd_identifier=mhd_id,
            repository_identifier=study_id,
            schema_name=target_mhd_model_schema_uri,
            profile_uri=target_mhd_model_profile_uri,
            repository_revision=repository_revision or 0,
            repository_revision_datetime=revision_date,
            submission_date=submission_date,
            public_release_date=release_date,
        )
        return dataset

    def process_study_files(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        mw_data: dict,
        mhd_assays: dict[str, mhd_domain.Assay],
        protocol_run_configs: dict[str, list[mhd_domain.SampleRunConfiguration]],
    ) -> dict[str, dict[str, list[mhd_domain.RawDataFile]]]:
        data_files: dict[str, dict[str, list[mhd_domain.RawDataFile]]] = {}
        study_id = mhd_study.repository_identifier
        sample_file_mapping = {}
        samples = {}
        archive_files = {}
        for assay_name, analysis in mw_data.get("analysis", {}).items():
            values = analysis.get("MS_METABOLITE_DATA", {}).get("Data", {})
            if not values:
                continue
            raw_file_dict = [
                x for x in values if x and x.get("Metabolite") == "raw archive name"
            ]
            if not raw_file_dict:
                continue
            raw_file_dict = raw_file_dict[0] if raw_file_dict else {}

            data_file_dict = [
                x for x in values if x and x.get("Metabolite") == "raw file name"
            ]
            data_file_dict = data_file_dict[0] if data_file_dict else {}
            samples[assay_name] = [
                x for x in raw_file_dict if x.lower() != "metabolite"
            ]
            archive_files[assay_name] = list(
                {v for k, v in raw_file_dict.items() if k.lower() != "metabolite"}
            )
            for sample in samples[assay_name]:
                if sample not in sample_file_mapping:
                    sample_file_mapping[sample] = {}
                sample_file_mapping[sample][assay_name] = (
                    raw_file_dict.get(sample),
                    data_file_dict.get(sample),
                )
        if not sample_file_mapping:
            return
        raw_archive_names = {}
        assay_raw_archive_names = {}
        raw_data_folders = set()
        samples = {}
        mw_study_id = mhd_study.repository_identifier
        for idx, (sample_name, assay_mappings) in enumerate(
            sample_file_mapping.items()
        ):
            if sample_name not in samples:
                sample_id = sample_name
                sample_id = sample_id if sample_id.replace("-", "") else ""
                sample_id = sample_id or f"sample-{idx:05d}"
                subject_id = sample_name
                subject_id = subject_id if subject_id.replace("-", "") else ""
                subject_id = subject_id or sample_id or f"subject-{idx:05d}"
                subject = mhd_domain.Subject(
                    uri=get_urn(mw_study_id, mhd_domain.Subject, subject_id),
                    name=subject_id,
                )
                sample = mhd_domain.Sample(
                    uri=get_urn(mw_study_id, mhd_domain.Sample, sample_id),
                    name=sample_id,
                )
                samples[sample_name] = (subject, sample)
            subject, sample = samples[sample_name]

            for assay_name, (archive_file, raw_file) in assay_mappings.items():
                run_identifier = f"{assay_name}:{sample_id}"
                run_config_refs = [
                    x.id_ for x in protocol_run_configs.get(assay_name)
                ] or []
                sample_run = mhd_domain.SampleRun(
                    uri=get_urn(mw_study_id, mhd_domain.SampleRun, run_identifier),
                    repository_identifier=run_identifier,
                    name=run_identifier,
                    sample_ref=sample.id_,
                    raw_data_file_refs=[],
                    sample_run_configuration_refs=run_config_refs,
                )
                # sample_runs[sample.name] = sample_run
                mhd_builder.add(sample_run, use_label_for_invalid_cv_term=True)
                index_number_node = self.create_cv_term_object(
                    type_="descriptor",
                    source="NCIT",
                    accession="NCIT:C25390",
                    name="Index",
                )
                if index_number_node.id_ not in mhd_builder.objects:
                    mhd_builder.add(index_number_node)
                tag_list = [KeyValue(key=index_number_node.id_, value=idx)]
                mhd_builder.link(
                    mhd_assays[assay_name],
                    "has-sample-run",
                    sample_run,
                    reverse_relationship_name="part-of",
                    tag_list=tag_list,
                )
                mhd_builder.add(subject, use_label_for_invalid_cv_term=True)
                mhd_builder.add(sample, use_label_for_invalid_cv_term=True)
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

                if archive_file not in raw_archive_names:
                    raw_data_name = Path(archive_file)
                    extension = Path(archive_file).suffix
                    url = f"https://www.metabolomicsworkbench.org/studydownload/{archive_file}"
                    if extension.lower() in [".txt"]:
                        file = mhd_domain.ResultFile(
                            uri=get_urn(study_id, mhd_domain.ResultFile, archive_file),
                            name=archive_file,
                            extension=extension,
                            url_list=[url],
                        )
                        mhd_builder.add(file)
                        mhd_builder.link(
                            mhd_study,
                            "has-result-file",
                            file,
                            reverse_relationship_name="created-in",
                        )
                    else:
                        file = mhd_domain.RawDataFile(
                            uri=get_urn(study_id, mhd_domain.RawDataFile, archive_file),
                            name=archive_file,
                            extension=extension,
                            url_list=[url],
                        )
                        mhd_builder.add(file)
                        data_files[archive_file] = file
                        mhd_builder.link(
                            mhd_study,
                            "has-raw-data-file",
                            file,
                            reverse_relationship_name="created-in",
                        )
                        if archive_file not in assay_raw_archive_names:
                            assay_raw_archive_names[archive_file] = {}
                        assay_raw_archive_names[archive_file][assay_name] = file
                        raw_archive_names[archive_file] = file
                raw_data_name = re.sub(r"(?i)(\.(raw|d|m))/.*$", r"\1", raw_file)

                if raw_data_name in raw_data_folders:
                    continue
                k = (
                    archive_file
                    if archive_file.startswith(mw_study_id)
                    else f"{mw_study_id}_{archive_file}"
                )
                url = f"https://www.metabolomicsworkbench.org/studydownload/{k}#{raw_file}"
                file_path = Path(raw_file)
                if sample_name not in data_files:
                    data_files[sample_name] = {}
                if assay_name not in data_files[sample_name]:
                    data_files[sample_name][assay_name] = []
                ext = file_path.suffix
                file_id = f"{k}#{raw_data_name}"
                file = mhd_domain.RawDataFile(
                    uri=get_urn(study_id, mhd_domain.RawDataFile, file_id),
                    name=file_id,
                    extension=ext,
                    url_list=[url],
                )
                mhd_builder.add(file)
                raw_data_folders.add(raw_data_name)

                data_files[sample_name][assay_name].append(file)
                sample_run.raw_data_file_refs.append(file.id_)
                mhd_builder.link(
                    mhd_study,
                    "has-raw-data-file",
                    file,
                    reverse_relationship_name="created-in",
                )

        # raw_data_file_names = [
        #     x for x in values if x and x.get("Metabolite") == "raw file name"
        # ]
        # raw_data_file_names = raw_data_file_names[0] if raw_data_file_names else {}
        # for sample_name, filename in raw_data_file_names.items():
        #     if sample_name == "Metabolite":
        #         continue
        #     raw_data_name = re.sub(r"(?i)(\.(raw|d|m))/.*$", r"\1", filename)

        #     if raw_data_name in raw_data_folders:
        #         continue
        #     k = raw_archive_names.get(sample_name)
        #     if not k:
        #         continue
        #     url = f"https://www.metabolomicsworkbench.org/studydownload/{k}#{raw_data_name}"
        #     file_path = Path(raw_data_name)
        #     filename = file_path.name
        #     if filename not in data_files:
        #         data_files[filename] = {}
        #     if raw_data_name not in data_files[filename]:
        #         data_files[filename][raw_data_name] = []
        #     ext = file_path.suffix
        #     file_id = f"{k}#{raw_data_name}"
        #     file = mhd_domain.RawDataFile(
        #         uri=get_urn(study_id, mhd_domain.RawDataFile, file_id),
        #         name=file_id,
        #         extension=ext,
        #         url_list=[url],
        #     )
        #     mhd_builder.add(file)
        #     raw_data_folders.add(raw_data_name)

        #     data_files[filename][raw_data_name].append(file)
        #     mhd_builder.link(
        #         mhd_study,
        #         "has-raw-data-file",
        #         file,
        #         reverse_relationship_name="created-in",
        #     )
        # raw_data_file_names.pop("Metabolite", None)
        # return raw_data_file_names

    def process_study_design(
        self,
        mhd_builder: MhDatasetBuilder,
        mw_tab_data: dict[str, Any],
        first_analysis: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
        mw_study_id: str,
        characteristic_definitions: dict[str, dict[str, tuple]],
        protocol_run_configs: dict[str, list[mhd_domain.SampleRunConfiguration]],
    ):
        """Process study design on SUBJECT_SAMPLE_FACTORS section and create
        subject, sample, factor definition, factor value.
        If raw data file and organism part are defined,  it creates nodes for them as well.

        Args:
            mhd_builder (MhDatasetBuilder): graph builder
            mw_tab_data (dict[str, Any]): mwTab content as dictionary
            mhd_study (mhd_domain.Study): study mode
            mhd_assays (dict[str, mhd_domain.Assay]): assays
        """
        analysis_list = list(mw_tab_data["analysis"].keys())
        analysis_list.sort()
        samples = {
            x.name: x
            for x in mhd_builder.objects.values()
            if isinstance(x, mhd_domain.Sample)
        }
        relationship_map = {
            x.id_: x
            for x in mhd_builder.objects.values()
            if isinstance(x, relationships.Relationship)
            and isinstance(mhd_builder.objects[x.source_ref], mhd_domain.Sample)
            and isinstance(mhd_builder.objects[x.target_ref], mhd_domain.Subject)
            and x.relationship_name == "derived-from"
        }
        sample_source_map = {}
        for sample in samples.values():
            sample_source_map[sample.id_] = [
                x for x in relationship_map.values() if x.source_ref == sample.id_
            ]
        sample_runs = {
            x.repository_identifier: x
            for x in mhd_builder.objects.values()
            if isinstance(x, mhd_domain.SampleRun)
        }
        # # analysis_data = mw_tab_data.get(analysis_list[0], {})
        # ion_mode = first_analysis.get("MS", {}).get("ION_MODE")

        # TODO: There is no direct relationship that shows
        # which study design row is used in which analysis
        # It is not possible to create sample run for each analysis.
        # sample runs will be created only for the first analysis
        # sample_runs: OrderedDict[str, mhd_domain.SampleRun] = OrderedDict()

        sample_factors_section = first_analysis.get("SUBJECT_SAMPLE_FACTORS", {})
        # iterate on study design and create a sample and subject
        # create factor definitions and factor values
        run_configs = protocol_run_configs.get(analysis_list[0]) or []
        run_config_refs = [x.id_ for x in run_configs]
        characteristic_field_names = {}
        # check 'sample source' or tissue column is defined in study design section
        # If it is defined use it organism part value
        if sample_factors_section:
            # try to identify which field is the best candidate for organism part
            sample_factors = sample_factors_section[0].get("Factors", {})
            for field_type, selection in [
                ("organism", ("species", "organism")),
                ("organism part", ("sample source", "tissue")),
                ("disease", ("disease",)),
                ("cell type", ("cell type", "celltype")),
            ]:
                for k in sample_factors:
                    k = k.replace("_", " ")
                    if k.lower() in selection:
                        characteristic_field_names[field_type] = k
                        break
                # if field_type not in characteristic_field_names:
                #     characteristic_field_names[field_type] = "not available"

        for idx, item in enumerate(sample_factors_section, start=0):
            sample_id = item.get("Sample ID", "")
            sample_id = sample_id if sample_id.replace("-", "") else ""

            sample = samples.get(sample_id)
            subject = sample_source_map.get(sample.id_)
            if subject:
                subject = mhd_builder.objects[subject[0].target_ref]
            else:
                sample_id = sample_id or f"sample-{idx:05d}"
                subject_id = item.get("Subject ID", "")
                subject_id = subject_id if subject_id.replace("-", "") else ""
                subject_id = subject_id or sample_id or f"subject-{idx:05d}"
                subject = mhd_domain.Subject(
                    uri=get_urn(mw_study_id, mhd_domain.Subject, subject_id),
                    name=subject_id,
                )
                sample = mhd_domain.Sample(
                    uri=get_urn(mw_study_id, mhd_domain.Sample, sample_id),
                    name=sample_id,
                )
                run_identifier = f"{analysis_list[0]}:{sample_id}"
                sample_run = mhd_domain.SampleRun(
                    uri=get_urn(mw_study_id, mhd_domain.SampleRun, run_identifier),
                    repository_identifier=run_identifier,
                    name=run_identifier,
                    sample_ref=sample.id_,
                    raw_data_file_refs=[],
                    sample_run_configuration_refs=run_config_refs,
                )
                sample_runs[sample.name] = sample_run
                mhd_builder.add(sample_run, use_label_for_invalid_cv_term=True)
                index_number_node = self.create_cv_term_object(
                    type_="descriptor",
                    source="NCIT",
                    accession="NCIT:C25390",
                    name="Index",
                )
                if index_number_node.id_ not in mhd_builder.objects:
                    mhd_builder.add(index_number_node)
                tag_list = [KeyValue(key=index_number_node.id_, value=idx)]
                mhd_builder.link(
                    mhd_assays[analysis_list[0]],
                    "has-sample-run",
                    sample_run,
                    reverse_relationship_name="part-of",
                    tag_list=tag_list,
                )
                mhd_builder.add(subject, use_label_for_invalid_cv_term=True)
                mhd_builder.add(sample, use_label_for_invalid_cv_term=True)
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
            characteristic_values = {}
            # map sample source or tissue -> organism part
            # others will be sample factor
            for field_type, field in characteristic_field_names.items():
                if not field_type:
                    continue
                field_value = sample_factors.get(field) or ""
                val_ = None
                if field_value:
                    if field_value in characteristic_values:
                        val_ = characteristic_values[field_value]
                    else:
                        values = characteristic_definitions.get(field_type, {})
                        result = values.get(field_value.lower())
                        if result:
                            _, _, val_ = result
                        else:
                            val_cv_term = convert_to_cv_term_with_mapping(
                                field_type, field_value
                            )
                            if val_cv_term:
                                val_ = self.create_cv_term_object_from(
                                    "characteristic-value", val_cv_term
                                )
                            else:
                                val_ = self.create_cv_term_value_object(
                                    type_="characteristic-value",
                                    name=field_value,
                                )
                            mhd_builder.add(val_)
                            characteristic_definition = next(iter(values.values()))[0]
                            mhd_builder.link(
                                mhd_study,
                                "has-characteristic-definition",
                                characteristic_definition,
                                reverse_relationship_name="used-in",
                            )
                            # mhd_builder.link(
                            #     subject,
                            #     "instance-of",
                            #     val_,
                            #     reverse_relationship_name="has-instance",
                            # )
                            mhd_builder.link(
                                val_,
                                "instance-of",
                                characteristic_definition,
                                reverse_relationship_name="has-instance",
                            )
                if val_:
                    mhd_builder.link(
                        subject,
                        "has-characteristic-value",
                        val_,
                        reverse_relationship_name="value-of",
                    )
                else:
                    pass

    def add_missing_characteristic_values(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        characteristic_name: str,
    ):
        characteristic_type = self.create_cv_term_object_from(
            "characteristic-type",
            cv=COMMON_CHARACTERISTIC_DEFINITIONS[characteristic_name],
        )
        mhd_builder.add(characteristic_type)
        characteristic_definition = mhd_domain.CharacteristicDefinition(
            repository_identifier=mhd_study.repository_identifier
            + ":"
            + characteristic_name,
            name=characteristic_name,
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
        characteristic_value = self.create_cv_term_object_from(
            "characteristic-value", cv=COMMON_MISSING_DATA_TERMS["not available"]
        )
        mhd_builder.add(characteristic_value)
        mhd_builder.link(
            characteristic_definition,
            "has-instance",
            characteristic_value,
            reverse_relationship_name="instance-of",
        )

    def create_default_organism_part_description(
        self,
        mhd_builder: MhDatasetBuilder,
        mw_tab_data: dict[str, Any],
        first_analysis: dict[str, Any],
        mhd_study: mhd_domain.Study,
        organism_part_field: None | str,
    ):
        study_id = mhd_study.repository_identifier
        analysis_data = first_analysis
        subject_section: dict[str, Any] = analysis_data.get("SUBJECT", {})

        characteristic_type = self.create_cv_term_object_from(
            "characteristic-type",
            cv=COMMON_CHARACTERISTIC_DEFINITIONS["organism part"],
        )
        mhd_builder.add(characteristic_type)
        definition_name = (
            organism_part_field.lower().replace("_", " ")
            if organism_part_field
            else "organism part"
        )
        characteristic_definition = mhd_domain.CharacteristicDefinition(
            uri=get_urn(study_id, mhd_domain.CharacteristicDefinition, definition_name),
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
        default_organism_part_value = self.create_cv_term_object(
            "characteristic-value",
            definitions.convert_to_cv_term_with_mapping(
                "organism part", subject_section.get("SAMPLE_SOURCE", {})
            ),
        )
        if default_organism_part_value:
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
        mw_tab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        reported_metabolite_names = {}

        metabolites_dict = mw_tab_data.get("metabolites", {})
        metabolites: dict[str, definitions.MetaboliteIdentification] = {
            str(k): definitions.MetaboliteIdentification.model_validate(v)
            for k, v in metabolites_dict.items()
        }
        for key, item in metabolites.items():
            name = item.metabolite_name
            if not name or len(name.strip()) < 2:
                continue
            analysis = item.analysis_id
            # Skip if analysis id is not defined in study
            if not mhd_assays.get(analysis):
                continue
            refmet_id = item.refmet_id
            if name in reported_metabolite_names:
                reported_metabolite = reported_metabolite_names[name]
            else:
                molecular_id = f"{item.analysis_id}/{key.zfill(5)}"
                reported_metabolite = mhd_domain.MolecularEntity(
                    uri=get_urn(
                        mhd_study.repository_identifier,
                        mhd_domain.MolecularEntity,
                        molecular_id,
                    ),
                    name=name,
                )
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

            if refmet_id:
                identifier_type: CvTerm = definitions.COMMON_COMPOUND_IDENTIFIERS_MAP[
                    "refmet"
                ]
                identifier = self.create_cv_term_value_object(
                    type_="molecular-entity-identifier",
                    accession=identifier_type.accession,
                    source=identifier_type.source,
                    name=identifier_type.name,
                    value=refmet_id,
                )

                mhd_builder.add(identifier)
                mhd_builder.link(
                    reported_metabolite,
                    "identified-as",
                    identifier,
                    reverse_relationship_name="reported-identifier-of",
                )

    def create_chromatography_protocols(
        self,
        mhd_builder: MhDatasetBuilder,
        mw_tab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        analysis_list = list(mw_tab_data["analysis"].keys())
        analysis_list.sort()
        chromatography_protocols: dict[str, mhd_domain.Protocol] = {}
        configurations: dict[str, mhd_domain.SampleRunConfiguration] = {}
        analysis_dict = mw_tab_data["analysis"]
        for analysis in analysis_list:
            analysis_data = analysis_dict.get(analysis, {})
            chromatography_protocols[analysis], _ = self.create_a_protocol(
                mhd_builder,
                mhd_study,
                analysis_data,
                section_name="CHROMATOGRAPHY",
                description_field_name="CHROMATOGRAPHY_SUMMARY",
                protocol_name=f"{analysis}:chromatography",
                protocol_id=f"{analysis}:chromatography".lower(),
                add_to_study=False,
            )
            if chromatography_protocols[analysis]:
                protocol = chromatography_protocols[analysis]
                index_number_node = self.create_cv_term_object(
                    type_="descriptor",
                    source="NCIT",
                    accession="NCIT:C25390",
                    name="Index",
                )
                if index_number_node.id_ not in mhd_builder.objects:
                    mhd_builder.add(index_number_node)
                tag_list = [KeyValue(key=index_number_node.id_, value=1)]
                mhd_builder.link(
                    mhd_assays[analysis],
                    "follows",
                    protocol,
                    reverse_relationship_name="used-in",
                    tag_list=tag_list,
                )
                excludes = {"CHROMATOGRAPHY_SUMMARY"}
                protocol.parameter_definition_refs = []
                protocol_section: dict[str, Any] = analysis_data.get(
                    "CHROMATOGRAPHY", {}
                )
                configuration = self.define_protocol_parameters(
                    mhd_builder, mhd_study, protocol, protocol_section, excludes
                )
                configurations[analysis] = configuration
        return configurations

    def create_ms_protocols(
        self,
        mhd_builder: MhDatasetBuilder,
        mw_tab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mhd_assays: dict[str, mhd_domain.Assay],
    ):
        analysis_list = list(mw_tab_data["analysis"].keys())
        analysis_list.sort()
        ms_protocols: dict[str, mhd_domain.Protocol] = {}
        analysis_dict = mw_tab_data["analysis"]
        configurations: dict[str, mhd_domain.SampleRunConfiguration] = {}
        for idx, analysis in enumerate(analysis_list):
            analysis_data = analysis_dict.get(analysis, {})

            ms_protocols[analysis], _ = self.create_a_protocol(
                mhd_builder,
                mhd_study,
                analysis_data,
                section_name="MS",
                description_field_name="MS_COMMENTS",
                protocol_name=f"{analysis}:mass spectrometry",
                protocol_id=f"{analysis}:mass spectrometry".lower(),
                add_to_study=False,
            )
            if ms_protocols[analysis]:
                protocol = ms_protocols[analysis]
                index_number_node = self.create_cv_term_object(
                    type_="descriptor",
                    source="NCIT",
                    accession="NCIT:C25390",
                    name="Index",
                )
                if index_number_node.id_ not in mhd_builder.objects:
                    mhd_builder.add(index_number_node)
                tag_list = [KeyValue(key=index_number_node.id_, value=0)]
                mhd_builder.link(
                    mhd_assays[analysis],
                    "follows",
                    protocol,
                    reverse_relationship_name="used-in",
                    tag_list=tag_list,
                )
                excludes = {"MS_COMMENTS"}
                protocol.parameter_definition_refs = []
                protocol_section: dict[str, Any] = analysis_data.get("MS", {})
                configuration = self.define_protocol_parameters(
                    mhd_builder, mhd_study, protocol, protocol_section, excludes
                )
                configurations[analysis] = configuration
        return configurations

    def create_project(
        self,
        mhd_builder: MhDatasetBuilder,
        project_section: dict[str, Any],
        mhd_study: mhd_domain.Study,
        cv_term_helper: BaseCvTermHelper,
    ) -> mhd_domain.Project:
        project_title = project_section.get("PROJECT_TITLE", "")
        project_description = project_section.get("PROJECT_SUMMARY", "")
        project_doi = (
            project_section.get("DOI", "")
            .replace("http://dx.doi.org/", "")
            .replace("http://doi.org/", "")
            .replace("https://doi.org/", "")
        )
        project_doi = project_doi or None
        study_id = mhd_study.repository_identifier
        project_identifier = project_doi or "000"
        mhd_project = mhd_domain.Project(
            uri=get_urn(study_id, mhd_domain.Project, project_identifier),
            title=project_title,
            description=project_description,
            doi=project_doi,
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
        funding_source = project_section.get("FUNDING_SOURCE", None)
        funding_source_ror_id = project_section.get("FUNDING_SOURCE_ROR_ID", None)
        ror_id = funding_source_ror_id
        if ror_id:
            term, _ = cv_term_helper.find_cv_term_with_accession("ror", ror_id)
            if term:
                funding_source = term.name
            ror_id = term.accession if term else None
            if ror_id and not ror_id.startswith(("http://", "https://")):
                ror_id = cv_term_helper.get_uri(term)

        if funding_source and len(funding_source) > 2:
            funder = mhd_domain.Organization(
                uri=get_urn(
                    mhd_study.repository_identifier,
                    mhd_domain.Organization,
                    funding_source,
                ),
                name=funding_source,
                ror_id=ror_id or None,
            )
            mhd_builder.add(funder)
            mhd_builder.link(
                mhd_study,
                "funded-by",
                funder,
                reverse_relationship_name="funds",
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
                study_id = mhd_study.repository_identifier
                pi_emails = self.parse_email(study_id, pi_email)
                identifier = pi_emails[0].lower() if pi_emails else pi_full_name.lower()
                mhd_pi = mhd_domain.Person(
                    uri=get_urn(
                        mhd_study.repository_identifier, mhd_domain.Person, identifier
                    ),
                    full_name=pi_full_name,
                    email_list=pi_emails or None,
                    address_list=[pi_address] if pi_address else None,
                    phone_list=[pi_phone] if pi_phone else None,
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
                # # select longest organization name
                # mhd_project_organization.name = max(
                #     mhd_project_organization.name, organization_name
                # )

        if not mhd_project_organization:
            mhd_project_organization = mhd_domain.Organization(
                uri=get_urn(
                    mhd_study.repository_identifier,
                    mhd_domain.Organization,
                    organization_name,
                ),
                name=organization_name,
                address=organization_address,
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
            logger.warning("%s: '%s' email is not valid.", mw_study_id, email)
            return []
        email = email.replace(";", ",")
        email = email.replace(" ", "")
        emails = []
        for x in email.split(","):
            try:
                validate_email(x.strip())
                emails.append(x.strip().lower())
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
        cv_term_helper: BaseCvTermHelper,
    ) -> tuple[mhd_domain.Person, mhd_domain.Organization]:
        submitter_first_name = study_section.get("FIRST_NAME", "")
        submitter_last_name = study_section.get("LAST_NAME", "")
        submitter_phone = study_section.get("PHONE", "")
        submitter_address = study_section.get("ADDRESS", "")

        submitter_full_name = " ".join(
            [x for x in (submitter_first_name, submitter_last_name) if x]
        ).strip()
        mhd_study_organization = None
        if submitter_full_name:
            submitter_email = study_section.get("EMAIL", None)
            submitter_emails = self.parse_email(
                mhd_study.repository_identifier, submitter_email
            )
            identifier = (
                submitter_emails[0].lower()
                if submitter_emails
                else submitter_full_name.lower()
            )
            mhd_submitter = mhd_domain.Person(
                uri=get_urn(
                    mhd_study.repository_identifier, mhd_domain.Person, identifier
                ),
                full_name=submitter_full_name,
                email_list=submitter_emails or None,
                address_list=[submitter_address] if submitter_address else None,
                phone_list=[submitter_phone] if submitter_phone else None,
            )
            mhd_builder.add(mhd_submitter)
            mhd_builder.link(
                mhd_submitter,
                "submits",
                mhd_study,
                reverse_relationship_name="submitted-by",
            )
            organization_name = study_section.get("INSTITUTE", "")
            organization__ror_id = study_section.get("INSTITUTE_ROR_ID", "")
            ror_id = organization__ror_id or ""
            if ror_id:
                term, _ = cv_term_helper.find_cv_term_with_accession("ror", ror_id)
                if term:
                    organization_name = term.name
                ror_id = term.accession if term else None
                if ror_id and not ror_id.startswith(("http://", "https://")):
                    ror_id = cv_term_helper.get_uri(term)

            organization_address = study_section.get("ADDRESS", "")
            mhd_study_organization = mhd_domain.Organization(
                uri=get_urn(
                    mhd_study.repository_identifier,
                    mhd_domain.Organization,
                    organization_name.lower(),
                ),
                name=organization_name,
                address=organization_address,
                ror_id=ror_id or None,
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
        mw_tab_data: dict[str, Any],
        mhd_study: mhd_domain.Study,
        mw_study_id: str,
        common_protocols: list[mhd_domain.Protocol],
    ):
        mhd_assays: dict[str, mhd_domain.Assay] = {}
        analysis_list = list(mw_tab_data["analysis"].keys())
        analysis_data_dict = mw_tab_data["analysis"]
        analysis_list.sort()

        mw_tab_file_format = self.create_cv_term_object(
            type_="descriptor",
            accession="EDAM:format_4070",
            source="EDAM",
            name="mwTab",
        )

        mhd_builder.add(mw_tab_file_format)

        for analysis in analysis_list:
            file_name = f"{mw_study_id}_{analysis}.txt"
            metadata_http_file_url = (
                "https://www.metabolomicsworkbench.org/data/study_textformat_view.php"
                f"?STUDY_ID={mw_study_id}&ANALYSIS_ID={analysis}"
            )
            extension = ".txt"
            metadata_file = mhd_domain.MetadataFile(
                uri=get_urn(
                    mhd_study.repository_identifier, mhd_domain.MetadataFile, file_name
                ),
                name=file_name,
                url_list=[metadata_http_file_url],
                extension=extension,
                format_ref=mw_tab_file_format.id_,
            )

            mhd_builder.add(metadata_file)
            mhd_builder.link(
                mhd_study,
                "has-metadata-file",
                metadata_file,
                reverse_relationship_name="describes",
            )
            analysis_dict = analysis_data_dict[analysis].get("ANALYSIS", {})
            omics_type = definitions.convert_to_cv_term_with_mapping(
                "omics type", analysis_dict.get("OMICS_TYPE", {})
            )
            assay_type = definitions.convert_to_cv_term_with_mapping(
                "assay type", analysis_dict.get("ASSAY_TYPE", {})
            )
            technology_type = definitions.convert_to_cv_term_with_mapping(
                "technology type", analysis_dict.get("ANALYSIS_TYPE", {})
            )
            measurement_type = definitions.convert_to_cv_term_with_mapping(
                "measurement type", analysis_dict.get("MEASUREMENT_TYPE", {})
            )
            omics_type_node = self.create_cv_term_object_from(
                type_="descriptor", cv=omics_type
            )
            technology_type_node = self.create_cv_term_object_from(
                type_="descriptor", cv=technology_type
            )
            assay_type_node = self.create_cv_term_object_from(
                type_="descriptor", cv=assay_type
            )
            measurement_type_node = self.create_cv_term_object_from(
                type_="descriptor", cv=measurement_type
            )
            if omics_type_node:
                mhd_builder.add(omics_type_node)
            if technology_type_node:
                mhd_builder.add(technology_type_node)
            if assay_type_node:
                mhd_builder.add(assay_type_node)
            if measurement_type_node:
                mhd_builder.add(measurement_type_node)

            mhd_assays[analysis] = mhd_domain.Assay(
                uri=get_urn(
                    mhd_study.repository_identifier, mhd_domain.Assay, analysis
                ),
                name=file_name,
                repository_identifier=analysis,
                metadata_file_ref=metadata_file.id_ if metadata_file else None,
                technology_type_ref=technology_type_node.id_
                if technology_type_node
                else None,
                assay_type_ref=assay_type_node.id_ if assay_type_node else None,
                measurement_type_ref=measurement_type_node.id_
                if measurement_type_node
                else None,
                omics_type_ref=omics_type_node.id_ if omics_type_node else None,
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
            # for protocol in common_protocols:
            #     mhd_builder.link(
            #         mhd_assays[analysis],
            #         "follows",
            #         protocol,
            #         reverse_relationship_name="used-in",
            #     )
            result_file_data = (
                analysis_data_dict[analysis].get("MS", {}).get("MS_RESULTS_FILE", "")
            )
            if result_file_data:
                result_file_name = result_file_data.split()[0]
                result_file_url = f"https://www.metabolomicsworkbench.org/studydownload/{result_file_name}"
                extension = Path(result_file_name).suffix

                tsv_file_format = self.create_cv_term_object(
                    type_="descriptor",
                    accession="EDAM:format_3475",
                    source="EDAM",
                    name="TSV",
                )
                mhd_builder.add(tsv_file_format)
                result_file = mhd_domain.ResultFile(
                    uri=get_urn(
                        mhd_study.repository_identifier,
                        mhd_domain.ResultFile,
                        result_file_name,
                    ),
                    name=result_file_name,
                    url_list=[result_file_url],
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
            protocol_idx=2,
        )
        run_configuration = None
        if treatment_protocol:
            excludes = {
                "TREATMENT_SUMMARY",
                "TREATMENT_PROTOCOL_ID",
                "TREATMENT_PROTOCOL_FILENAME",
                "TREATMENT_PROTOCOL_COMMENTS",
            }
            treatment_protocol.parameter_definition_refs = []
            run_configuration = self.define_protocol_parameters(
                mhd_builder, mhd_study, treatment_protocol, treatment_section, excludes
            )

        return treatment_protocol, run_configuration

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
            protocol_idx=1,
        )
        run_configuration = None
        if preparation_protocol:
            excludes = {
                "SAMPLEPREP_SUMMARY",
                "SAMPLEPREP_PROTOCOL_ID",
                "SAMPLEPREP_PROTOCOL_FILENAME",
                "SAMPLEPREP_PROTOCOL_COMMENTS",
            }
            preparation_protocol.parameter_definition_refs = []
            run_configuration = self.define_protocol_parameters(
                mhd_builder,
                mhd_study,
                preparation_protocol,
                sample_prep_section,
                excludes,
            )

        return preparation_protocol, run_configuration

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
            protocol_idx=0,
        )
        run_configuration = None
        if collection_protocol:
            excludes = {
                "COLLECTION_SUMMARY",
                "SAMPLE_TYPE",
                "COLLECTION_PROTOCOL_ID",
                "COLLECTION_PROTOCOL_FILENAME",
                "COLLECTION_PROTOCOL_COMMENTS",
            }
            collection_protocol.parameter_definition_refs = []
            run_configuration = self.define_protocol_parameters(
                mhd_builder,
                mhd_study,
                collection_protocol,
                collection_section,
                excludes,
            )

        return collection_protocol, run_configuration

    def create_subject_characteristics(
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

        organism = subject_section.get("SUBJECT_SPECIES", None)
        organism_part = subject_section.get("SAMPLE_SOURCE", None)
        disease = subject_section.get("DISEASE_ASSOCIATION", None)
        cell_line = subject_section.get("CELL_LINE", None)
        cell_type = subject_section.get("CELL_TYPE", None)
        taxonomy_id = subject_section.get("TAXONOMY_ID", None)
        if taxonomy_id and isinstance(organism, str):
            organism = {
                "termSource": "NCBITaxon",
                "termAccession": f"NCBITaxon:{taxonomy_id}",
                "term": organism or "",
            }

        characteristic_definitions: dict[str, dict[str, tuple]] = {}

        for term_type, terms, common_term, definition, common in [
            (
                "organism",
                organism,
                COMMON_CHARACTERISTIC_DEFINITIONS["organism"],
                "subject-species",
                True,
            ),
            (
                "organism part",
                organism_part,
                COMMON_CHARACTERISTIC_DEFINITIONS["organism part"],
                "sample-source",
                True,
            ),
            (
                "disease",
                disease,
                COMMON_CHARACTERISTIC_DEFINITIONS["disease"],
                "disease-association",
                True,
            ),
            (
                "cell type",
                cell_type,
                COMMON_CHARACTERISTIC_DEFINITIONS["cell type"],
                "cell-type",
                True,
            ),
            (
                "cell line",
                cell_line,
                CvTerm(source="CLO", accession="CLO:0000031", name="cell line "),
                "cell-line",
                False,
            ),
        ]:
            values = {}

            characteristic_type_ = (
                "characteristic-type" if common else "x-mw-characteristic-type"
            )
            characteristic_value_type_ = (
                "characteristic-value" if common else "x-mw-characteristic-value"
            )
            characteristic_type = self.create_cv_term_object_from(
                type_=characteristic_type_, cv=common_term
            )

            characteristic_definition = mhd_domain.CharacteristicDefinition(
                uri=get_urn(
                    mhd_study.repository_identifier,
                    mhd_domain.CharacteristicDefinition,
                    f"{definition}/000",
                ),
                name=definition,
                characteristic_type_ref=characteristic_type.id_,
            )
            if isinstance(terms, list):
                for item in terms:
                    sub_item = convert_to_cv_term_with_mapping(term_type, item)
                    if sub_item and sub_item.name:
                        values[sub_item.name.lower()] = sub_item
            elif isinstance(terms, str):
                values[terms.lower()] = CvTerm(name=terms)
            elif isinstance(terms, dict) and "term" in terms:
                sub_item = convert_to_cv_term_with_mapping(term_type, terms)
                values[sub_item.name.lower()] = sub_item
            elif isinstance(terms, dict):
                for k, v in terms.items():
                    if isinstance(v, dict) and "term" in v:
                        sub_item = convert_to_cv_term_with_mapping(term_type, v)
                        values[k.lower()] = sub_item
            elif terms:
                raise ValueError(f"Type is not supported: {terms}")
            characteristic_definitions[term_type] = {}

            if not values:
                not_available = COMMON_MISSING_DATA_TERMS.get("not available")
                characteristic_value = self.create_cv_term_object_from(
                    characteristic_value_type_, not_available
                )
                characteristic_definitions[term_type][not_available.name.lower()] = (
                    characteristic_definition,
                    characteristic_type,
                    characteristic_value,
                )
            else:
                for key, value in values.items():
                    characteristic_value = self.create_cv_term_object_from(
                        characteristic_value_type_, value
                    )
                    characteristic_definitions[term_type][key.lower()] = (
                        characteristic_definition,
                        characteristic_type,
                        characteristic_value,
                    )

            for idx, (_, _, value_node) in enumerate(
                characteristic_definitions[term_type].values()
            ):
                only_add_node = True if idx > 0 else False
                self.add_characteristic_value(
                    mhd_builder,
                    mhd_study,
                    characteristic_type,
                    characteristic_definition,
                    value_node,
                    only_add_node=only_add_node,
                )

        return characteristic_definitions

    def create_study(
        self,
        mhd_builder: MhDatasetBuilder,
        study_section: dict[str, Any],
        mw_section: dict[str, Any],
        mw_study_id: str,
        dataset_provider: mhd_domain.CvTermValueObject,
        mhd_id: None | str = None,
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
        mhd_id = mw_section.get("MHD_ID", "") or mhd_id
        study_title = study_section.get("STUDY_TITLE", "")
        study_description = study_section.get("STUDY_SUMMARY", "")

        submission_date = self.convert_str_to_datetime(
            study_section.get("SUBMISSION_DATE", "")
        )
        release_date = self.convert_str_to_datetime(
            study_section.get("RELEASE_DATE", "")
        )

        if not submission_date:
            submission_date = datetime.datetime.now(datetime.UTC)
            release_date = submission_date
        mw_study_repository_url = (
            f"{definitions.PUBLIC_MW_STUDY_URL_PREFIX}{mw_study_id}"
        )

        #####################################################################################
        license = mw_section.get("LICENSE") or None
        license_url = definitions.LICENSE_MAP.get(license or "")
        #####################################################################################

        mhd_study = mhd_domain.Study(
            uri=get_urn(mw_study_id, mhd_domain.Study, "000"),
            repository_identifier=mw_study_id,
            created_by_ref=dataset_provider.id_,
            mhd_identifier=mhd_id,
            title=study_title,
            description=BeautifulSoup(study_description, "html.parser").get_text(),
            submission_date=submission_date,
            public_release_date=release_date,
            url_list=[mw_study_repository_url],
            license=license_url,
            protocol_refs=[],
        )
        mhd_builder.add(mhd_study)
        mhd_builder.add_node(dataset_provider, use_label_for_invalid_cv_term=True)
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
            mhd_builder.add(descriptor_cv, use_label_for_invalid_cv_term=True)
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
        only_add_node: bool = False,
    ):
        if not only_add_node:
            mhd_builder.add(characteristic_type, use_label_for_invalid_cv_term=True)
            mhd_builder.add(
                characteristic_definition, use_label_for_invalid_cv_term=True
            )
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
        mhd_builder.add(characteristic_value, use_label_for_invalid_cv_term=True)

        mhd_builder.link(
            characteristic_definition,
            "has-instance",
            characteristic_value,
            reverse_relationship_name="instance-of",
        )

    def define_protocol_parameters(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        protocol: mhd_domain.Protocol,
        protocol_section: dict[str, Any],
        excludes: list[str],
    ) -> mhd_domain.SampleRunConfiguration:
        mw_term_mappings = definitions.get_cv_terms_mapping()
        # sample_run_configurations = {}

        repository_id = protocol.repository_identifier

        configuration = mhd_domain.SampleRunConfiguration(
            uri=get_urn(
                mhd_study.repository_identifier,
                mhd_domain.SampleRunConfiguration,
                repository_id,
            ),
            protocol_ref=protocol.id_,
        )
        configuration.parameter_value_refs = []
        mhd_builder.add(configuration)
        # sample_run_configurations[protocol.repository_identifier] = configuration
        protocol_name = (
            protocol.name if ":" not in protocol.name else protocol.name.split(":")[1]
        )
        mw_parameter_map = definitions.MW_PROTOCOL_PARAMETER_DEFINITIONS_MAP[
            protocol_name
        ]
        common_parameters_map = definitions.COMMON_PROTOCOL_PARAMETER_DEFINITIONS_MAP[
            protocol_name
        ]
        for field in protocol_section:
            if field and protocol_section.get(field) and field not in excludes:
                field_val = protocol_section.get(field)
                if not field_val:
                    continue
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
                mhd_builder.add(parameter_type, use_label_for_invalid_cv_term=True)
                def_id = f"{protocol.repository_identifier}:{definition_name}".lower()
                definition = mhd_domain.ParameterDefinition(
                    uri=get_urn(
                        mhd_study.repository_identifier,
                        mhd_domain.ParameterDefinition,
                        def_id,
                    ),
                    repository_identifier=def_id,
                    name=definition_name,
                    parameter_type_ref=parameter_type.id_,
                )
                mhd_builder.add(definition, use_label_for_invalid_cv_term=True)
                protocol.parameter_definition_refs.append(definition.id_)

                # Define parameter value type.
                # If it is type of a definition that has custom type, create custom value with prefix x-mw-
                type_ = (
                    "x-mw-parameter-value"
                    if parameter_type.type_.startswith("x-mw-")
                    else "parameter-value"
                )

                if isinstance(field_val, dict):
                    cv_term = definitions.convert_to_cv_term(
                        protocol_section.get(field, {})
                    )
                    term = mw_term_mappings.get(parameter_type.name.lower(), {}).get(
                        cv_term.name.lower()
                    )
                    cv_term = term or cv_term
                else:
                    term = mw_term_mappings.get(parameter_type.name.lower(), {}).get(
                        field_val.lower()
                    )
                    cv_term = term if term else CvTerm(name=field_val)
                field_value = self.create_cv_term_value_object(
                    type_=type_,
                    accession=cv_term.accession if cv_term else "",
                    source=cv_term.source if cv_term else "",
                    name=cv_term.name if cv_term else "",
                )
                configuration.parameter_value_refs.append(field_value.id_)
                mhd_builder.add(field_value, use_label_for_invalid_cv_term=True)
                mhd_builder.link(
                    definition,
                    "has-type",
                    parameter_type,
                    reverse_relationship_name="type-of",
                )
                mhd_builder.link(
                    protocol,
                    "has-parameter-definition",
                    definition,
                    reverse_relationship_name="used-in",
                )
                mhd_builder.link(
                    definition,
                    "has-instance",
                    field_value,
                    reverse_relationship_name="instance-of",
                )
        return configuration if configuration.parameter_value_refs else None

    def create_a_protocol(
        self,
        mhd_builder: MhDatasetBuilder,
        mhd_study: mhd_domain.Study,
        analysis_data: dict[str, Any],
        section_name: str,
        description_field_name: str,
        protocol_name: str,
        protocol_id: None | str = None,
        ignore_if_no_description: bool = False,
        protocol_idx: None | int = None,
        add_to_study: bool = True,
    ) -> tuple[mhd_domain.Protocol, mhd_domain.CvTermObject]:
        protocol_section: dict[str, Any] = analysis_data.get(section_name, {})
        protocol_type_node = None
        protocol = None
        if protocol_section:
            desc = protocol_section.get(description_field_name, "")
            desc = desc if len(desc) > 1 else None
            if ignore_if_no_description and not desc:
                return protocol, protocol_type_node
            original_protocol_name = protocol_name
            if ":" in protocol_name:
                protocol_name = protocol_name.split(":")[1]

            if protocol_name in COMMON_PROTOCOLS:
                type_ = "protocol-type"
            else:
                type_ = "x-mw-protocol-type"
            protocol_type_node = self.create_cv_term_object_from(
                type_=type_, cv=definitions.MW_PROTOCOLS_MAP[protocol_name]
            )
            mhd_builder.add(protocol_type_node, use_label_for_invalid_cv_term=True)
            if not protocol_id:
                protocol_id = f"{protocol_name.lower()}"
            protocol = mhd_domain.Protocol(
                uri=get_urn(
                    mhd_study.repository_identifier,
                    mhd_domain.Protocol,
                    protocol_id,
                ),
                name=original_protocol_name,
                repository_identifier=protocol_id,
                protocol_type_ref=protocol_type_node.id_,
                description=desc,
            )
            mhd_builder.add(protocol, use_label_for_invalid_cv_term=True)
            if add_to_study:
                tag_list = None
                if protocol_idx is not None:
                    index_number_node = self.create_cv_term_object(
                        type_="descriptor",
                        source="NCIT",
                        accession="NCIT:C25390",
                        name="Index",
                    )
                    if index_number_node.id_ not in mhd_builder.objects:
                        mhd_builder.add(index_number_node)
                    tag_list = [KeyValue(key=index_number_node.id_, value=protocol_idx)]

                mhd_builder.link(
                    mhd_study,
                    "has-protocol",
                    protocol,
                    reverse_relationship_name="used-in",
                    tag_list=tag_list,
                )

            mhd_builder.link(
                protocol,
                "has-type",
                protocol_type_node,
                reverse_relationship_name="type-of",
            )
        return protocol, protocol_type_node

    def create_cv_term_object(
        self, type_: str, accession: str, source: str, name: str | list
    ) -> mhd_domain.CvTermObject:
        if not source or not accession:
            if source or accession:
                logger.warning(
                    "Source or accession is not defined for term %s: '%s', '%s'",
                    name,
                    source,
                    accession,
                )
            return mhd_domain.CvTermObject(type_=type_, name=name)

        return mhd_domain.CvTermObject(
            type_=type_, accession=accession, source=source, name=name
        )

    def create_cv_term_object_from(
        self, type_: str, cv: CvTerm
    ) -> mhd_domain.CvTermObject:
        if not cv or not cv.name:
            return None
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
