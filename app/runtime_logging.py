import logging


def get_runtime_logger(module_name):
    logger_name = module_name.removeprefix("app.")
    return logging.getLogger(f"uvicorn.error.meowstreet.{logger_name}")
