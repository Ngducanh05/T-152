import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(log_level: str = "INFO") -> None:
    """Configure process logging without opening external connections."""
    normalized_level = log_level.upper()
    numeric_level = getattr(logging, normalized_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=_LOG_FORMAT,
    )
    logging.getLogger().setLevel(numeric_level)
