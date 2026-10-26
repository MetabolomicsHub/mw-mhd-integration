import logging
import sys

import click

from mw2mhd.v1_0.mw_utils import prepare_input_folder

logger = logging.getLogger(__name__)


@click.command(name="mhd-file", no_args_is_help=True)
@click.option(
    "--mw-study-id",
    default=None,
    required=True,
    help="MW study id",
)
@click.option(
    "--output-dir",
    default="outputs",
    required=True,
    show_default=True,
    help="Output directory for MW study",
)
def fetch_mw_study(
    mw_study_id: str,
    output_dir: str,
):
    """Download a Metabolomics Workbench study metadata files to generate MHD File."""
    data = prepare_input_folder(mw_study_id, output_folder_path=output_dir)
    if not data:
        click.echo(f"{mw_study_id} failed.")
        sys.exit(1)
    click.echo(f"{mw_study_id} is downloaded")


if __name__ == "__main__":
    fetch_mw_study(["ST000001"])
