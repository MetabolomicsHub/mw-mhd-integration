import logging

import click

from mw2mhd.v0_1.legacy.mw_utils import fetch_mw_data

logger = logging.getLogger(__name__)


@click.command(name="fetch", no_args_is_help=True)
@click.option(
    "--study-id",
    show_default=True,
    help="Metabolomics Workbench study id (e.g. ST000001)",
)
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
def fetch_mw_study(
    study_id: str,
    output_dir: str,
    output_filename: str,
):
    """Fetch a Metabolomics Workbench study as json file."""
    data = fetch_mw_data(
        study_id, output_folder_path=output_dir, output_filename=output_filename
    )
    if not data:
        click.echo("%s failed.", study_id)
        exit(1)
    click.echo("%s is fetched", study_id)


if __name__ == "__main__":
    fetch_mw_study(["--study-id", "ST000001"])
