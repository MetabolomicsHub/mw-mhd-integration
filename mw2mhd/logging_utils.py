import logging
import sys
from pathlib import Path

LOG_FORMAT = (
    "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
)
LOG_DATE_FORMAT = "%d/%b/%Y %H:%M:%S"


def configure_logging(
    *,
    log_file_path: str | Path | None = None,
    verbose: bool = False,
) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file_path is not None:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    for handler in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    logging.getLogger("fake_useragent").setLevel(logging.ERROR)
    logging.getLogger("mhd_model.model.v0_1.dataset.validation.base").setLevel(
        logging.WARNING
    )
    logging.getLogger("httpx").setLevel(logging.ERROR)
