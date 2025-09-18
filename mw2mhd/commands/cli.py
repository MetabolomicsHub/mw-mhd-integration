import sys

import click
from mhd_model import __version__

from mw2mhd.commands.create_mhd_file import create_mhd_file
from mw2mhd.commands.fetch_mw_study import fetch_mw_study


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__)
def cli():
    """Metabomics Workbench - MHD Integration CLI with subcommands."""
    pass


cli.add_command(create_mhd_file)
cli.add_command(fetch_mw_study)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        cli(["--help"])
    else:
        cli()
