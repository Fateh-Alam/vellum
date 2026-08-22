"""Privacy-conscious rotating file logging for Vellum."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "vellum"


def configure_logging(data_dir: Path, debug: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        return logger

    log_path = (data_dir / "vellum.log").resolve()
    existing = next(
        (
            handler
            for handler in logger.handlers
            if isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == log_path
        ),
        None,
    )
    if existing is None:
        try:
            handler = RotatingFileHandler(
                log_path,
                maxBytes=512_000,
                backupCount=2,
                encoding="utf-8",
            )
        except OSError:
            if not logger.handlers:
                logger.addHandler(logging.NullHandler())
            return logger
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger
