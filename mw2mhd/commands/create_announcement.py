from __future__ import annotations

import logging
from pathlib import Path

import click
from mhd_model.commands.create.announcement import (
    create_announcement_file_task as base_create_announcement_file_task,
)

from mw2mhd.announcement_enricher import enrich_announcement_file

logger = logging.getLogger(__name__)


@click.command(name="announcement", no_args_is_help=True)
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
    help="MHD announcement filename (e.g., MHD000001.announcement.json, ST000001.announcement.json)",
)
@click.argument("mhd_study_id")
@click.argument("mhd_model_file_path")
@click.argument("target_mhd_model_file_url")
def create_announcement_file_task(
    mhd_study_id: str,
    mhd_model_file_path: str,
    target_mhd_model_file_url: str,
    output_dir: str,
    output_filename: str | None,
):
    """Create announcement file from MHD data model file and enrich it from canonical MHD."""

    args = [
        mhd_study_id,
        mhd_model_file_path,
        target_mhd_model_file_url,
        f"--output-dir={output_dir}",
    ]
    if output_filename:
        args.append(f"--output-filename={output_filename}")

    base_create_announcement_file_task.main(args=args, standalone_mode=False)

    output_path = Path(output_dir) / Path(
        output_filename or f"{mhd_study_id}.announcement.json"
    )
    enrich_announcement_file(Path(mhd_model_file_path), output_path)
    click.echo(f"{mhd_study_id} announcement file conversion completed.")
