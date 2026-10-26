import sys
import warnings
from pathlib import Path

import click
from mhd_model.commands.create.create import create_group
from mhd_model.commands.mhd_client.mhd_client import mhd_client_group
from mhd_model.commands.validate.validate import validate_group

from mw2mhd import __version__
from mw2mhd.commands.create_mhd_file import generate_mhd_file_task

warnings.filterwarnings("ignore", category=UserWarning)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__)
def cli():
    """Metabomics Workbench - MHD Integration CLI with subcommands."""


cli.add_command(generate_mhd_file_task)

cli.add_command(mhd_client_group)
cli.add_command(validate_group)
cli.add_command(create_group)

if __name__ == "__main__":
    sys.path.insert(0, str(Path.cwd()))
    if len(sys.argv) == 1:
        cli(["--help"])
    else:
        cli()
