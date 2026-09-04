import importlib
import logging

import pytest

from app.runtime_logging import get_runtime_logger


RUNTIME_LOGGER_NAMES = [
    ("app.api", "uvicorn.error.meowstreet.api"),
    (
        "app.routers.macro_dashboard",
        "uvicorn.error.meowstreet.routers.macro_dashboard",
    ),
    (
        "app.routers.market_assistant",
        "uvicorn.error.meowstreet.routers.market_assistant",
    ),
    (
        "app.services.market_assistant",
        "uvicorn.error.meowstreet.services.market_assistant",
    ),
    (
        "app.services.market_assistant_llm",
        "uvicorn.error.meowstreet.services.market_assistant_llm",
    ),
    (
        "app.services.market_setup_current",
        "uvicorn.error.meowstreet.services.market_setup_current",
    ),
]


def test_runtime_logger_emits_info_through_uvicorn_with_module_identity(caplog):
    logger = get_runtime_logger("app.services.market_assistant")

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        logger.info("market assistant request started")

    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "market assistant request started"
    )
    assert record.name == "uvicorn.error.meowstreet.services.market_assistant"


@pytest.mark.parametrize(("module_name", "logger_name"), RUNTIME_LOGGER_NAMES)
def test_runtime_modules_emit_with_source_specific_logger(
    caplog, module_name, logger_name
):
    module = importlib.import_module(module_name)
    message = f"{module_name} runtime event"

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        module.LOGGER.info(message)

    record = next(record for record in caplog.records if record.getMessage() == message)
    assert record.name == logger_name
