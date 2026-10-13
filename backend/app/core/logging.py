"""Logging setup: single-line format, INFO in containers, DEBUG locally."""

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    level = logging.DEBUG if settings.environment == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Noise control for chatty libraries.
    for noisy in ("httpx", "httpcore", "botocore", "urllib3", "pika"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
