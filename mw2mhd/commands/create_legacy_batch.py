import logging
from pathlib import Path

import click

from mw2mhd.legacy_batch import convert_legacy_batch
from mw2mhd.logging_utils import configure_logging

logger = logging.getLogger(__name__)


@click.command(name="legacy-batch", no_args_is_help=False)
@click.option(
    "--study-list",
    default="legacy.txt",
    show_default=True,
    help="Path to a newline-delimited list of MW study IDs.",
)
@click.option(
    "--output-dir",
    default=".outputs/mhd_legacy",
    show_default=True,
    help="Output directory for MHD and announcement files.",
)
@click.option(
    "--data-path",
    default=".outputs/mw_dataset",
    show_default=True,
    help="Path to the directory containing MW metadata.",
)
@click.option(
    "--log-file",
    default=None,
    help=(
        "Path to write a conversion log. Defaults to "
        "<output-dir>/conversion.log."
    ),
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Write DEBUG logs and full exception tracebacks.",
)
def create_legacy_batch_task(
    study_list: str,
    output_dir: str,
    data_path: str,
    log_file: str | None,
    verbose: bool,
) -> None:
    """Convert a batch of legacy Metabolomics Workbench studies."""

    output_dir_path = Path(output_dir)
    log_file_path = Path(log_file) if log_file else output_dir_path / "conversion.log"
    configure_logging(log_file_path=log_file_path, verbose=verbose)
    logger.info("Writing conversion log to %s", log_file_path)
    convert_legacy_batch(
        study_list=Path(study_list),
        output_dir=output_dir_path,
        data_path=Path(data_path),
        verbose=verbose,
    )
