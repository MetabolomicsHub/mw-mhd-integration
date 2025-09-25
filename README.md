# Metabolomics Workbench - MHD Model Integration Framework



## Development Environment


Development environment for linux or mac
```bash

# install python package manager uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# add $HOME/.local/bin to your PATH, either restart your shell or run
export PATH=$HOME/.local/bin:$PATH

# install git from https://git-scm.com/downloads
# Linux command
apt update; apt install git -y

# Mac command
# brew install git

# clone project from github
git clone https://github.com/MetabolomicsHub/mw-mhd-integration.git

cd mw-mhd-integration

# install python if it is not installed
uv python install 3.12

# install python dependencies
uv sync

# install pre-commit to check repository integrity and format checking
uv run pre-commit

# open your IDE (vscode, pycharm, etc.) and set python interpreter as .venv/bin/python

```

## Commandline Usage


```bash
# you can use any python version >= 3.12
pip install mw-mhd-integration

mw-mhd-cli
####################################################################
# Usage: mw-mhd-cli [OPTIONS] COMMAND [ARGS]...

#   Metabomics Workbench - MHD Integration CLI with subcommands.

# Options:
#   --version   Show the version and exit.
#   -h, --help  Show this message and exit.

# Commands:
#   announcement  Create announcement file from MHD data model file.
#   download      Download a Metabolomics Workbench study as json file.
#   mhd           Convert a Metabolomics Workbench study to MHD file format.
#   validate      Validate MHD model and annoucenment file.
####################################################################

mw-mhd-cli download

####################################################################
# Usage: mw-mhd-cli download [OPTIONS] STUDY_ID

#   Download a Metabolomics Workbench study as json file.

# Options:
#   --output-dir TEXT       Output directory for MHD file  [default: outputs]
#   --output-filename TEXT  MHD filename (e.g., MHD000001_mhd.json,
#                           ST000001_mhd.json)
#   -h, --help              Show this message and exit.
####################################################################

mw-mhd-cli download ST004083
# ST004083 is downloaded

ls outputs
# ST004083.json

mw-mhd-cli create mhd
####################################################################
# Usage: mw-mhd-cli create mhd [OPTIONS] MW_STUDY_ID MHD_IDENTIFIER

#   Convert a Metabolomics Workbench study to MHD file format.

#   Args:

#       mw_study_id (str): MW study accession id. e.g, ST0000001.

#       mhd_identifier (str): MHD accession number.      Use same value of
#       mw_study_id if study profile is legacy. e.g., ST0000001.

# Options:
#   --output-dir TEXT       Output directory for MHD file  [default: outputs]
#   --output-filename TEXT  MHD filename (e.g., MHD000001_mhd.json,
#                           ST000001_mhd.json)
#   --schema_uri TEXT       Target MHD model schema. It defines format of MHD
#                           model structure.  [default:
#                           https://metabolomicshub.github.io/mhd-
#                           model/schemas/v0_1/common-data-
#                           model-v0.1.schema.json]
#   --profile_uri TEXT      Target MHD model profile. It is used to validate MHD
#                           model  [default:
#                           https://metabolomicshub.github.io/mhd-
#                           model/schemas/v0_1/common-data-model-v0.1.legacy-
#                           profile.json]
#   -h, --help              Show this message and exit.
####################################################################

mw-mhd-cli create mhd ST004083 ST004083
ls outputs
# ST004083.json  ST004083.mhd.json

mw-mhd-cli validate
####################################################################
# Usage: mw-mhd-cli validate [OPTIONS] COMMAND [ARGS]...

#   Validate MHD model and annoucenment file.

# Options:
#   -h, --help  Show this message and exit.

# Commands:
#   announcement  Validate MHD announcement file.
#   mhd           Validate MHD model file.
####################################################################

mw-mhd-cli validate mhd ST004083 outputs/ST004083.mhd.json
####################################################################
# ST004083: outputs/ST004083.mhd.json MHD file validation started.
# Used schema: https://metabolomicshub.github.io/mhd-model/schemas/v0_1/common-data-model-v0.1.schema.json
# Validation profile: https://metabolomicshub.github.io/mhd-model/schemas/v0_1/common-data-model-v0.1.legacy-profile.json
# ST004083: File 'outputs/ST004083.mhd.json' is validated successfully.
####################################################################
mw-mhd-cli create announcement

####################################################################
# Usage: mw-mhd-cli create announcement [OPTIONS] MHD_STUDY_ID MHD_MODEL_FILE_PATH
#                                TARGET_MHD_MODEL_FILE_URL

#   Create announcement file from MHD data model file.

#   Args:

#   mhd_study_id (str): MHD study identifier

#   mhd_model_file_path (str): MHD data model path

#   target_mhd_model_file_url (str): target URL of MHD data model

#   output_dir (str): Output directory of announcement file

#   output_filename (str): Name of MHD announcement file. Default is <repository
#   identifier>.announcement.json

# Options:
#   --output-dir TEXT       Output directory for MHD file  [default: outputs]
#   --output-filename TEXT  MHD announcement filename (e.g.,
#                           MHD000001.announcement.json,
#                           ST000001.announcement.json)
#   -h, --help              Show this message and exit.
####################################################################


# MHD identifier will be reserved for each private study
# The following command assumes that MHD999999 is reserved for ST004083
mw-mhd-cli create announcement MHD999999  outputs/ST004083.mhd.json --target_mhd_model_file_url=https://www.metabolomicsworkbench.org/data/study_textformat_list.php?MHD_ID=MHD999999

####################################################################
# MHD999999 announcement file conversion completed.
# MHD identifier will be reserved for each private study
####################################################################

ls outputs
####################################################################
# MHD999999.announcement.json  ST004083.json  ST004083.mhd.json
####################################################################

mw-mhd-cli validate announcement

####################################################################
# Usage: mw-mhd-cli validate announcement [OPTIONS] MHD_STUDY_ID
#                                         ANNOUNCEMENT_FILE_PATH

#   Validate MHD announcement file.

#   Args:

#   mhd_study_id (str): MHD study id

#   announcement_file_path (str): MHD announcement file path

#   output_path (None | str): If it is defined, validation results are saved in
#   output file path.

# Options:
#   --output-path TEXT  Validation output file path
#   -h, --help          Show this message and exit.
####################################################################

mw-mhd-cli validate announcement MHD999999 outputs/MHD999999.announcement.json

####################################################################
# MHD999999: File 'outputs/MHD999999.announcement.json' is validated successfully.
####################################################################

```
