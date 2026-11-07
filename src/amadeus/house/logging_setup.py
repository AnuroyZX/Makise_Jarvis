from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from typing import Optional

from amadeus.config import get_default_data_dir

SECRET_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9_\-]{8,})|(AIza[a-zA-Z0-9_\-]{10,})|(hf_[a-zA-Z0-9_\-]{10,})"
)


class SecretMaskingFilter(logging.Filter):
    """ECC AgentShield filter to mask API keys and credentials in all log records."""

    @staticmethod
    def _mask_match(m: re.Match) -> str:
        s = m.group(0)
        if len(s) <= 8:
            return "***"
        return f"{s[:4]}***{s[-3:]}"

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = SECRET_PATTERN.sub(self._mask_match, record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (SECRET_PATTERN.sub(self._mask_match, v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    SECRET_PATTERN.sub(self._mask_match, str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def setup_logging(
    data_dir: Optional[Path] = None,
    level: int = logging.INFO,
    log_file_name: str = "amadeus.log",
) -> logging.Logger:
    """
    Configure root/amadeus logger with secret masking and size-bounded rotating file handler.
    """
    target_dir = data_dir or get_default_data_dir()
    logs_dir = target_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / log_file_name

    logger = logging.getLogger("amadeus")
    logger.setLevel(level)

    # Avoid duplicate handlers on re-initialization
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        file_handler.addFilter(SecretMaskingFilter())
        logger.addHandler(file_handler)

    return logger
