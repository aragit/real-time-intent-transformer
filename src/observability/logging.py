import sys
from loguru import logger


def configure_logging():
    """Structured logging with loguru (AXIOMIS pattern)."""
    logger.remove()
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="INFO",
        colorize=True,
    )
    logger.add(
        "logs/intent_transformer.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
    )
