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
#   fetch         Fetch a Metabolomics Workbench study as json file.
#   mhd           Convert a Metabolomics Workbench study to MHD file format.
#   validate      Validate MHD model and annoucenment file.
####################################################################

mw-mhd-cli fetch 

####################################################################
# Usage: mw-mhd-cli fetch [OPTIONS] STUDY_ID

#   Fetch a Metabolomics Workbench study as json file.

# Options:
#   --output-dir TEXT       Output directory for MHD file  [default: outputs]
#   --output-filename TEXT  MHD filename (e.g., MHD000001_mhd.json,
#                           ST000001_mhd.json)
#   -h, --help              Show this message and exit.
####################################################################

mw-mhd-cli fetch ST004083
# ST004083 is fetched

ls outputs
# ST004083.json

mw-mhd-cli mhd
####################################################################
# Usage: mw-mhd-cli mhd [OPTIONS] STUDY_ID

#   Convert a Metabolomics Workbench study to MHD file format.

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

mw-mhd-cli mhd ST004083
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

```