from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

# Honor the same override as paths.LOGS_DIR (kept import-free: this module is
# imported before sys.path setup in some entrypoints).
_env_logs = os.environ.get("ORRIN_LOGS_DIR")
_LOG_DIR = Path(_env_logs).resolve() if _env_logs else Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "orrin_runtime.log"

_configured: set[str] = set()


def get_logger(name: str = "orrin") -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured:
        return logger
    _configured.add(name)

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass

    logger.propagate = False
    return logger
