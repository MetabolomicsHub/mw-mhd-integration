# How a Metabolomics Workbench study becomes an MHD dataset

This document follows one real study, `ST004083`, through the converter. It
starts with an accession number. It ends with a validated MetabolomicsHub
dataset and an announcement file.

All line references were checked against the source tree. All data examples are
real. The inputs come from `.outputs/mw_dataset/`. The outputs come from
`.outputs/mhd_legacy/`.

**Terms used in this document.** *MW* is Metabolomics Workbench, the source
repository. *MHD* is MetabolomicsHub, the target. *The converter* is the code in
this repository. *`mhd-model`* is the separate library that defines the target
format. A *CV term* is a controlled vocabulary term: a reference to an ontology
entry, not free text.

---

## 1. Why this repository exists

MHD collects datasets from many source repositories. Each dataset must arrive in
one common format. Only then can MHD index, search and announce datasets in a
consistent way.

MW is one of these source repositories. This repository converts MW studies into
the MHD format. It does no more than that.

The converter does not define the MHD format. `mhd-model` defines the schema,
the graph builder, the validation rules and the announcement format.
[pyproject.toml](../pyproject.toml) declares `mhd-model` as a dependency. This
repository supplies only the knowledge that is specific to MW.

### Four problems make the conversion difficult

Almost every unusual part of the code comes from one of these four problems.

| # | Problem | Effect on the code |
|---|---|---|
| 1 | MW JSON is often not valid JSON. It contains joined objects, repeated keys and illegal control characters. | The converter repairs the text before it parses the text. |
| 2 | MHD needs CV terms. MW supplies text that a person typed. | The converter holds large mapping tables. |
| 3 | One study contains many analyses. The analyses can be of different types. | The converter selects and filters analyses. |
| 4 | Required fields are often absent in old MW records. | The converter fails early, and a second pass fills gaps. |

---

## 2. The MHD data model is a graph

An MHD file is a JSON document. Its content is a graph with two parts:

- **Nodes.** Each node has a type. Examples are `study`, `person`,
  `organization`, `protocol`, `assay`, `sample`, `subject`, `raw-data-file` and
  `parameter-definition`.
- **Relationships.** Each relationship connects two nodes. It has a direction. It
  also has a forward name and a reverse name. A `person` node `submits` a study.
  The `study` node `has-submitter` for that person.

Most values are CV terms, not text. A CV term has a source, an accession and a
name. It refers to an ontology such as NCIT, CHEBI, EFO, CHEMINF or MS.

The conversion of MW text into CV terms is the main task of the converter.

### The real output of ST004083

The output file contains **342 nodes and 930 relationships**. It uses 25 node
types.

| Count | Node type | Count | Node type |
|---|---|---|---|
| 106 | `raw-data-file` | 11 | `protocol` |
| 64 | `parameter-definition` | 8 | `result-file` |
| 18 | `sample` | 4 | `assay` |
| 18 | `subject` | 4 | `metadata-file` |
| 18 | `sample-run` | 1 | `study` |

You can trace each count back to the source data. MW reports 18 samples for this
study. MW also reports four MS analyses. The converter makes 18 samples, 18
subjects, 18 sample-runs and 4 assays.

### Values that do not map become extension nodes

Some MW values have no equivalent CV term. The converter does not remove these
values. It makes an `x-mw-*` extension node instead. The node keeps the original
text. Its source and accession stay empty.

These examples come from `ST004083`:

```json
{ "type": "x-mw-factor-type",  "source": "", "accession": "", "name": "group" }
{ "type": "x-mw-factor-value", "source": "", "accession": "", "name": "Control" }
{ "type": "x-mw-factor-value", "source": "", "accession": "", "name": "MetR10" }
```

This behaviour is useful when you read an output file. The `x-mw-` prefix shows
you where the mapping is incomplete. `ST004083` contains 48 extension nodes: 23
`x-mw-parameter-value`, 18 `x-mw-parameter-type`, 6 `x-mw-factor-value` and 1
`x-mw-factor-type`.

---

## 3. Which repository owns which part

| Function | Owner |
|---|---|
| Access to MW services, cache, JSON repair | **this repository** — [mw_utils.py](../mw2mhd/v0_1/legacy/mw_utils.py) |
| Tables that map MW terms to CV terms | **this repository** — [builder.py:45-161](../mw2mhd/v0_1/legacy/builder.py#L45), [cv_mapping_table.csv](../mw2mhd/cv_mapping_table.csv) |
| The order in which the converter builds the graph | **this repository** — [builder.py:253](../mw2mhd/v0_1/legacy/builder.py#L253) |
| The second pass that fills gaps | **this repository** — [mhd_enricher.py](../mw2mhd/mhd_enricher.py), [announcement_enricher.py](../mw2mhd/announcement_enricher.py) |
| Batch control | **this repository** — [legacy_batch.py](../mw2mhd/legacy_batch.py) |
| Definitions of node types and relationship types | `mhd-model` — `profiles/base/graph_nodes.py` |
| The graph builder: `add`, `link`, `add_node`, `create_dataset` | `mhd-model` — `dataset_builder.py:38` |
| Profiles: `MhDatasetBaseProfile`, `MhDatasetLegacyProfile` | `mhd-model` |
| Managed CV terms and validation rules | `mhd-model` — `model/v0_1/rules/` |
| Validation of schema and profile | `mhd-model` — `validation/validator.py` |
| Creation of the announcement file | `mhd-model` — `convertors/announcement/` |
| Convertors for SDRF and Neo4j | `mhd-model` — this repository does not use them |

A simple rule holds for the whole system. **This repository knows about
Metabolomics Workbench. `mhd-model` knows about MetabolomicsHub.** Neither one
knows the internal parts of the other.

---

## 4. The conversion, stage by stage

### Stage 0 — The command line

[cli.py:15-24](../mw2mhd/commands/cli.py#L15) defines a `click` group with three
commands:

| Command | Function |
|---|---|
| `download` | Gets a study from MW and writes it to disk. |
| `create` | Makes an MHD file, an announcement file, or a batch of both. |
| `validate` | Checks an MHD file or an announcement file. |

`pyproject.toml` makes this group available as `mw-mhd-cli`.

The `validate` command contains no logic of its own. It exports the commands of
`mhd-model` ([validate.py:16-17](../mw2mhd/commands/validate.py#L16)).

### Stage 1 — Download the data and repair it

The command `mw-mhd-cli download ST004083` calls
[fetch_mw_data()](../mw2mhd/v0_1/legacy/mw_utils.py#L199). This function requests
`/rest/study/study_id/ST004083/mwtab`
([mw_utils.py:216](../mw2mhd/v0_1/legacy/mw_utils.py#L216)).

**The cache comes first.** Each fetch function looks on disk before it uses the
network ([mw_utils.py:209-214](../mw2mhd/v0_1/legacy/mw_utils.py#L209)). The
same pattern occurs in `fetch_mw_study_summary` (:121), `fetch_mw_study_files`
(:87) and `fetch_mw_metabolites` (:155). After the first run, the converter works
without a network connection. A second run is therefore fast.

**The repair comes before the parse.**
[patch_json_text()](../mw2mhd/v0_1/legacy/mw_utils.py#L257) applies four regular
expressions to the response text:

| Input | Output | Purpose |
|---|---|---|
| `}{` | `}, {` | Joins two objects. |
| `"x":"y":"z"` | `"x":"y z"` | Repairs a bad key and value pair. |
| `"x":}` | `"x":{}}` | Fills an empty value. |
| `\x00`-`\x1F` | removed | Deletes control characters. |

The function [group_duplicates()](../mw2mhd/v0_1/legacy/mw_utils.py#L242) then
runs as the JSON `object_pairs_hook`. It collects repeated keys into a list.
Without this hook, a repeated key would replace the earlier value.

This code looks strange until you see the actual MW response. The repair is the
reason that 3,712 of 3,718 studies parse.

The result is a dictionary. Its keys are MW analysis identifiers. For
`ST004083`:

```
analysis ids : ['AN006761', 'AN006762', 'AN006763', 'AN006764']
sections     : METABOLOMICS WORKBENCH, PROJECT, STUDY, SUBJECT,
               SUBJECT_SAMPLE_FACTORS, COLLECTION, TREATMENT,
               SAMPLEPREP, CHROMATOGRAPHY, ANALYSIS, MS
```

Note the difference in shape. MHD needs one study. MW gives four analyses, and
each analysis repeats the study data.

### Stage 2 — Select a convertor

The command `mw-mhd-cli create mhd ST004083 ST004083` runs
[create_mhd_file.py](../mw2mhd/commands/create_mhd_file.py). This command asks
[Mw2MhdConvertorFactory](../mw2mhd/convertor_factory.py#L11) for a convertor. The
request includes a schema URI and a profile URI.

The factory is a simple table
([convertor_factory.py:17-27](../mw2mhd/convertor_factory.py#L17)). For MHD v0.1
and the legacy profile, it returns `LegacyProfileV01Convertor`. For the MS
profile, it raises `NotImplementedError`
([convertor_factory.py:23-25](../mw2mhd/convertor_factory.py#L23)). The legacy
profile is therefore the only profile that works today.

[legacy/convertor.py:29-41](../mw2mhd/v0_1/legacy/convertor.py#L29) then makes an
`MhdLegacyDatasetBuilder` object and calls its `build()` method.

### Stage 3 — Select the analyses

[builder.py:280-292](../mw2mhd/v0_1/legacy/builder.py#L280) keeps each analysis
that has `MS` in its type. If no analysis remains, the converter raises an error.

If a study contains MS analyses and other types, the converter keeps the MS
analyses. It writes a warning for the other analyses and removes them
([builder.py:294-301](../mw2mhd/v0_1/legacy/builder.py#L294)). It does not fail
the study. Two examples show the result:

| Study | Analyses in MW | Result |
|---|---|---|
| `ST000019` | NMR, MS | Converts. Keeps 1 MS analysis. |
| `ST000098` | 3 × MS, 3 × NMR | Converts. Keeps 3 MS analyses. |

The converter then sorts the analyses and takes the first one. It reads all
study-level data from that analysis
([builder.py:303-311](../mw2mhd/v0_1/legacy/builder.py#L303)).

> **Note.** This is a simplification. If two analyses disagree about a
> study-level field, the first analysis after the sort wins. The converter gives
> no warning.

All four analyses of `ST004083` are MS analyses. The converter removes none of
them.

### Stage 4 — Check the preconditions

[builder.py:317-329](../mw2mhd/v0_1/legacy/builder.py#L317) gets the study
summary and the list of study files. It then checks three fields. Each check that
fails raises a `ValueError`:

1. The study summary must be available.
2. The license URL must have a value.
3. The submission date must have a value.
4. The release date must have a value.

Read these four lines before you diagnose any conversion failure. They cause most
failures.

`ST004083` passes all four checks:

```json
{ "submission_date": "2025-07-31",
  "release_date":    "2025-08-25",
  "license":         "CC BY-NC-ND",
  "license_url":     "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en" }
```

One small detail has a visible effect. The validator
`license_url_validator` adds a slash to the end of the license URL
([mw_utils.py:53-58](../mw2mhd/v0_1/legacy/mw_utils.py#L53)). The `license` value
in the output study node therefore ends with `/deed.en/`.

### Stage 5 — Build the graph

[builder.py:342-353](../mw2mhd/v0_1/legacy/builder.py#L342) makes an
`MhDatasetBuilder` object. This object belongs to `mhd-model`. It collects the
nodes and the relationships.

The converter then adds nodes in a fixed order. The order is necessary, because
later nodes refer to earlier nodes.

| Step | Node or nodes | Line |
|---|---|---|
| 1 | data-provider | [:358](../mw2mhd/v0_1/legacy/builder.py#L358) |
| 2 | study | [:364](../mw2mhd/v0_1/legacy/builder.py#L364) |
| 3 | organism characteristic | [:371](../mw2mhd/v0_1/legacy/builder.py#L371) |
| 4 | collection, preparation and treatment protocols | [:378-396](../mw2mhd/v0_1/legacy/builder.py#L378) |
| 5 | assays — one for each analysis | [:408](../mw2mhd/v0_1/legacy/builder.py#L408) |
| 6 | submitter and organization | [:419](../mw2mhd/v0_1/legacy/builder.py#L419) |
| 7 | principal investigator and project organization | [:427](../mw2mhd/v0_1/legacy/builder.py#L427) |
| 8 | publication status | [:445-458](../mw2mhd/v0_1/legacy/builder.py#L445) |
| 9 | project | [:462](../mw2mhd/v0_1/legacy/builder.py#L462) |
| 10 | MS protocols | [:474](../mw2mhd/v0_1/legacy/builder.py#L474) |
| 11 | chromatography protocols | [:481](../mw2mhd/v0_1/legacy/builder.py#L481) |
| 12 | raw data files and result files | [:490](../mw2mhd/v0_1/legacy/builder.py#L490) |
| 13 | study design: samples, subjects and factors | [:495](../mw2mhd/v0_1/legacy/builder.py#L495) |
| 14 | reported metabolites and their identifiers | [:502](../mw2mhd/v0_1/legacy/builder.py#L502) |

> **Note about step 8.** The publication status is a decision of the converter,
> not a fact from the data. The legacy converter has no DOI. It therefore sets
> the status to *pending publication* for every study.

### Stage 6 — Convert text into CV terms

This is the most important part of the converter. It uses two mechanisms.

**Static tables.** [builder.py:45-161](../mw2mhd/v0_1/legacy/builder.py#L45)
holds tables for known MW vocabulary. The tables cover assay types, measurement
types, protocol types, parameter definitions for each protocol,
characteristics, study factors and types of compound identifier. Some tables
contain `TODO` comments, because the mapping is incomplete.

**A crosswalk file.** [cv_mapping_table.csv](../mw2mhd/cv_mapping_table.csv)
holds 671 rows. The function
[get_mw_terms_mapping()](../mw2mhd/v0_1/legacy/builder.py#L166) reads the file
once and keeps the result in memory. Each row maps one MHD term to its
equivalent in more than one repository:

```
mhd-term-id, mhd-term,     mw-term,                                    mtbls-term,        gnps-term
MS_1000139,  4000 QTRAP,   ABI Sciex 4000 Qtrap; ABI Sciex API 4000..., AB SCIEX QTRAP..., ...
```

The file is therefore not specific to MW. It also has columns for MetaboLights
and GNPS. It is a shared crosswalk between repositories.

If neither mechanism finds a match, the converter makes an `x-mw-*` extension
node. See section 2.

### Stage 7 — Write the file

[builder.py:509-521](../mw2mhd/v0_1/legacy/builder.py#L509) calls
`create_dataset()`. This method makes an `MhDatasetLegacyProfile` object. The
converter gives the object a name. It then writes
`<output-dir>/ST004083.mhd.json`.

The start of the file declares the format that the file uses:

```json
{ "repository_name":       "Metabolomics Workbench",
  "repository_identifier": "ST004083",
  "type":                  "legacy-dataset",
  "$schema":               ".../common-data-model-v0.1.schema.json",
  "profile_uri":           ".../common-data-model-v0.1.legacy-profile.json" }
```

Validation later reads these two URIs. The check therefore uses the declaration
of the file itself.

### Stage 8 — Fill gaps in the MHD file

[create_mhd_file.py:112](../mw2mhd/commands/create_mhd_file.py#L112) calls
[enrich_mhd_file()](../mw2mhd/mhd_enricher.py#L183). This function opens the new
file and fills gaps. It has two conditions.

**Condition 1: summary fields.** The function runs if the license, the submission
date or the release date is absent. It also runs if the release date is equal to
the submission date, because this result is a known fallback of the converter.
The function then gets the MW summary again and writes the correct values
([mhd_enricher.py:69-80](../mw2mhd/mhd_enricher.py#L69), :206-229).

**Condition 2: raw data files.** The function runs if the graph has no
`raw-data-file` node. It reads the MW list of study files. It also reads the
contents of compressed archives. It selects each file that has a raw data
extension ([mhd_enricher.py:24-32](../mw2mhd/mhd_enricher.py#L24)). It then adds
a node and a `has-raw-data-file` relationship for each file
([mhd_enricher.py:136-180](../mw2mhd/mhd_enricher.py#L136)). Each node gets a
GNPS dashboard URL and an archive download URL.

The function writes the file again only if it made a change
([mhd_enricher.py:246-249](../mw2mhd/mhd_enricher.py#L246)).

Both conditions are false for a complete study. `ST004083` needs no changes. Its
dates and license are present and different. Its 106 `raw-data-file` nodes come
from [process_study_files](../mw2mhd/v0_1/legacy/builder.py#L527) in the builder.
The URLs of these nodes use the `studydownload/` form, not the GNPS form.

> **Important: the files on disk do not show this stage.** No file in
> `.outputs/mhd_legacy` contains a `dashboard.gnps2.org` URL. Also, 153 of the
> first 600 output files have no `raw-data-file` node. The 3,718 studies on disk
> were therefore converted before this stage was added. A new batch run would
> change these files.

### Stage 9 — Validate the file and make the announcement

The `validate mhd` command passes the work to `mhd-model`. The validator checks
the file against the JSON schema. It also checks the file against the rules of
the profile.

An announcement file is a flat summary of the graph. It is for public use.
[create_announcement.py:50](../mw2mhd/commands/create_announcement.py#L50) calls
the announcement builder of `mhd-model`. The command then calls
[enrich_announcement_file()](../mw2mhd/announcement_enricher.py#L144).

This function reads the graph. It puts the relationships into two indexes: one by
source and one by target. It then recovers data that the base builder omits:

- **Contact data.** The function follows the `submits` and
  `principal-investigator-of` relationships to each `person` node. It then
  follows `affiliated-with` to each `organization` node. It copies the email
  addresses and the affiliations into the announcement file
  ([announcement_enricher.py:50-93](../mw2mhd/announcement_enricher.py#L50)).
- **Protocol parameters.** The function follows the `has-protocol-definition` and
  `has-instance` relationships. It copies each parameter and its CV term values
  ([announcement_enricher.py:96-141](../mw2mhd/announcement_enricher.py#L96)).

---

## 5. Batch conversion

[legacy_batch.py](../mw2mhd/legacy_batch.py) converts many studies. It reads a
list of study identifiers from a file. The default file is
[legacy.txt](../legacy.txt).

For each study it does five operations: convert, fill gaps, validate, make the
announcement, fill gaps in the announcement. If an operation fails, it writes
`<id>.mhd.errors.json`
([legacy_batch.py:28-84](../mw2mhd/legacy_batch.py#L28)).

You can stop a batch run and start it again. The batch skips a study if the study
has both output files and no error file
([legacy_batch.py:126-131](../mw2mhd/legacy_batch.py#L126)). This behaviour makes
a run of several thousand studies practical.

### Measured results

These figures come from `.outputs/mhd_legacy`:

| Result | Count |
|---|---|
| Studies attempted | 3,718 |
| Studies with an MHD file | 3,712 |
| Studies with an announcement file | 3,709 |
| Studies with both files and no error file | **3,697 (99.4%)** |
| Studies with an error file | 21 |

### The 21 failures

The failures have two causes.

**Cause 1: the converter could not get the source data (7 studies).** Six studies
produced no MHD file: `ST000855`, `ST000866`, `ST001447`, `ST002866`, `ST003408`
and `ST003494`. One study, `ST000386`, failed on the list of study files.

**Cause 2: the file failed validation (14 studies).** The converter wrote an MHD
file, but a text field was shorter than the minimum length of the profile:

| Field | Number of studies | Studies |
|---|---|---|
| `study.description` | 8 | ST000040, ST000070, ST000071, ST000098, ST000122, ST000146, ST000163, ST000171 |
| `project.title` | 4 | ST000156, ST000162, ST000171, ST000176 |
| `study.title` | 2 | ST000609, ST000610 |
| `factor-definition.name` | 1 | ST002821 |

The conclusion matters. **Most failures come from empty text in the MW records,
not from defects in the converter.** Two thirds of all failures are an absent
title or an absent description. The MHD profile requires the field. MW never
recorded it. Work on the converter cannot correct these failures.

> **The gaps document is out of date.** The file `mw_mhd_output_gaps.MD` (now in
> `.outputs/`) reports 15 studies without an MHD file. It also reports failures
> from non-MS analyses and from converter defects. These failures no longer
> occur. The figures above come from the current output directory and replace
> the figures in that file.

---

## 6. Other parts of the repository

| File or directory | Function |
|---|---|
| [config.py](../mw2mhd/config.py) | Holds the schema URI, the profile URIs and the MW base URLs. |
| [logging_utils.py](../mw2mhd/logging_utils.py) | Configures log output to the screen and to a file. It also reduces the log level of `httpx` and the `mhd-model` validator. |
| `scripts/analyze_conversion_log.py` | Reads a batch log and counts the errors. |
| `scripts/audit_conversion_coverage.py` | Measures which MW fields reach the output files. |
| `scripts/audit_semantic_field_coverage.py` | Measures the same data at field level. |
| `scripts/summarize_semantic_coverage.py` | Summarises the two audit files. |

The files in `scripts/` are development tools. They are not part of the
conversion.

---

## 7. Known limitations

1. **Only the legacy profile works.** The MS profile raises
   `NotImplementedError`
   ([convertor_factory.py:23-25](../mw2mhd/convertor_factory.py#L23)).
2. **Study-level data comes from one analysis.** The converter uses the first
   analysis after the sort. It does not report a conflict between analyses.
3. **The publication status is always *pending*.** The converter sets this value.
   It does not read it from the data.
4. **The mapping is incomplete.** Some `TODO` comments remain in the tables.
   Values that do not map become `x-mw-*` nodes.
5. **The output files on disk are older than the gap-filling stage.** A new batch
   run would change them.
