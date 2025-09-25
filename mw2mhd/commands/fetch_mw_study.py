import logging

import click

from mw2mhd.v0_1.legacy.mw_utils import fetch_mw_data

logger = logging.getLogger(__name__)


@click.command(name="download", no_args_is_help=True)
@click.option(
    "--output-dir",
    default="outputs",
    show_default=True,
    help="Output directory for MHD file",
)
@click.option(
    "--output-filename",
    default=None,
    show_default=True,
    help="MHD filename (e.g., MHD000001_mhd.json, ST000001_mhd.json)",
)
@click.argument("massive_study_id")
def fetch_mw_study(
    massive_study_id: str,
    output_dir: str,
    output_filename: str,
):
    """Download a Metabolomics Workbench study as json file."""
    data = fetch_mw_data(
        massive_study_id, output_folder_path=output_dir, output_filename=output_filename
    )
    if not data:
        click.echo(f"{massive_study_id} failed.")
        exit(1)
    click.echo(f"{massive_study_id} is downloaded")


if __name__ == "__main__":
    fetch_mw_study(["ST000001"])
