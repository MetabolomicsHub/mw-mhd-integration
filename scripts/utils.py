import logging

from mw2mhd.logging_utils import configure_logging


def setup_basic_logging_config(
    level: int = logging.INFO, log_file_path: str | None = None
):
    configure_logging(
        log_file_path=log_file_path,
        verbose=level <= logging.DEBUG,
    )
