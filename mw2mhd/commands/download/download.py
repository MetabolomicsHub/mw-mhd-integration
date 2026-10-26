import sys

import click

from mw2mhd.commands.download.fetch_mw_study import fetch_mw_study


@click.group(name="client", context_settings={"help_option_names": ["-h", "--help"]})
def download_group():
    """Download resources from Metabolomics Workbench."""


download_group.add_command(fetch_mw_study)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        download_group(["--help"])
    else:
        download_group()
