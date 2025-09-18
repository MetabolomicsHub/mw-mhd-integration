import logging
from pathlib import Path

import click
from mhd_model.model.definitions import (
    MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
    MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
)

from mw2mhd.convertor_factory import Mw2MhdConvertorFactory

logger = logging.getLogger(__name__)


@click.command(name="convert", no_args_is_help=True)
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
@click.option(
    "--schema_uri",
    default=MHD_MODEL_V0_1_DEFAULT_SCHEMA_NAME,
    show_default=True,
    help="Target MHD model schema. It defines format of MHD model structure.",
)
@click.option(
    "--profile_uri",
    default=MHD_MODEL_V0_1_LEGACY_PROFILE_NAME,
    show_default=True,
    help="Target MHD model profile. It is used to validate MHD model",
)
def create_mhd_file(
    study_id: str,
    output_dir: str,
    output_filename: str,
    schema_uri: str,
    profile_uri: str,
):
    """Convert a Metabolomics Workbench study to MHD format."""

    factory = Mw2MhdConvertorFactory()
    convertor = factory.get_convertor(
        target_mhd_model_schema_uri=schema_uri,
        target_mhd_model_profile_uri=profile_uri,
    )
    mhd_output_root_path = Path(output_dir)
    mhd_output_root_path.mkdir(exist_ok=True, parents=True)
    try:
        convertor.convert(
            repository_name="Metabolomics Workbench",
            repository_identifier=study_id,
            mhd_identifier=None,
            mhd_output_folder_path=mhd_output_root_path,
            mhd_output_filename=output_filename,
        )
        logger.info("%s successful.", study_id)
    except Exception as ex:
        click.echo("%s failed. %s", study_id, ex)


if __name__ == "__main__":
    create_mhd_file(["--study-id", "ST000001"])
