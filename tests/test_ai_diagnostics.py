import logging
from pathlib import Path

from lafvin_hat.ai import configure_ai_logging


def test_configure_ai_logging_writes_local_file(tmp_path: Path) -> None:
    path = tmp_path / "chatbot.log"
    logger_name = "lafvin_hat.tests.diagnostics"

    configured = configure_ai_logging(
        logger_name,
        default_path=path,
    )
    logging.getLogger(logger_name).error("stage=test event=failure")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert configured == path.resolve()
    assert "stage=test event=failure" in path.read_text(encoding="utf-8")
