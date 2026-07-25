from __future__ import annotations

import logging
import os
from pathlib import Path


def configure_ai_logging(
    app_name: str,
    *,
    default_path: str | Path,
) -> Path:
    path = Path(os.getenv("LAFVIN_AI_LOG_FILE", str(default_path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(
        getattr(
            logging,
            os.getenv("LAFVIN_AI_LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        )
    )

    resolved = path.resolve()
    has_file = any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == resolved
        for handler in root.handlers
    )
    if not has_file:
        file_handler = logging.FileHandler(
            resolved,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    logging.getLogger(app_name).info("event=log_ready path=%s", resolved)
    return resolved
