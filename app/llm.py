import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METHOD_EXTRACTION_MODEL = "gpt-4.1-mini"


def load_env(root=ROOT):
    env_path = Path(root) / ".env"
    if not env_path.exists():
        return
    if load_dotenv is None:
        raise RuntimeError("python-dotenv is required to load .env files")
    load_dotenv(env_path, override=False)


def load_openai_config(args=None, root=ROOT):
    load_env(root)
    return {
        "api_key": getattr(args, "openai_api_key", None) or os.getenv("OPENAI_API_KEY"),
        "base_url": getattr(args, "openai_base_url", None) or os.getenv("OPENAI_BASE_URL"),
        "model": getattr(args, "model", None)
        or os.getenv("METHOD_EXTRACTION_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_METHOD_EXTRACTION_MODEL,
    }


def build_async_client(config, *, max_retries=0, timeout=300.0):
    if AsyncOpenAI is None:
        raise RuntimeError("openai package is required for LLM extraction")
    if not config.get("api_key"):
        raise RuntimeError("OPENAI_API_KEY is required for LLM extraction")
    kwargs = {
        "api_key": config["api_key"],
        "max_retries": max_retries,
        "timeout": timeout,
    }
    if config.get("base_url"):
        kwargs["base_url"] = config["base_url"]
    return AsyncOpenAI(**kwargs)
