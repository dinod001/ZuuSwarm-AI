"""Loguru-based logging for ZuuSwarm AI."""

from __future__ import annotations

import logging
import sys

from loguru import logger

from infrastructure.config import LOGGING_ENABLED, LOGS_DIR, get_log_level

_CONFIGURED = False

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level.icon} {level:<8}</level> | "
    "<cyan>{extra[name]}</cyan> | "
    "<level>{message}</level>"
)

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[name]} | "
    "{name}:{function}:{line} | {message}"
)

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _resolve_level(default: str = "INFO") -> str:
    level = get_log_level()
    return level if level in _VALID_LEVELS else default


class _InterceptHandler(logging.Handler):
    """Route stdlib logging calls through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    *,
    console_level: str | None = None,
    file_level: str = "DEBUG",
    log_to_file: bool = True,
) -> None:
    """Configure loguru sinks once for the whole application."""
    global _CONFIGURED
    if _CONFIGURED or not LOGGING_ENABLED:
        _CONFIGURED = True
        return

    console_level = console_level or _resolve_level()
    diagnose = console_level == "DEBUG"

    logger.remove()

    logger.add(
        sys.stderr,
        level=console_level,
        format=_CONSOLE_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=diagnose,
        enqueue=True,
    )

    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            LOGS_DIR / "app_{time:YYYY-MM-DD}.log",
            level=file_level,
            format=_FILE_FORMAT,
            encoding="utf-8",
            rotation="00:00",
            retention="14 days",
            compression="zip",
            enqueue=True,
        )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(name).handlers = [_InterceptHandler()]
        logging.getLogger(name).propagate = False

    _CONFIGURED = True


def get_logger(name: str = __name__):
    """Return a logger bound to *name* (drop-in for stdlib get_logger)."""
    if not _CONFIGURED:
        setup_logging()
    return logger.bind(name=name)


setup_logging()
