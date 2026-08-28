import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def configure_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("siar")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    fh = RotatingFileHandler(
        log_dir / "siar.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger
