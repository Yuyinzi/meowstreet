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
        "base_url": getattr(args, "openai_base_url", None)
        or os.getenv("OPENAI_BASE_URL"),
        "model": getattr(args, "model", None)
        or os.getenv("METHOD_EXTRACTION_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_METHOD_EXTRACTION_MODEL,
    }


def _first_non_empty_env(env_names):
    for env_name in env_names:
        value = os.getenv(env_name)
        if value:
            return value
    return None


def load_market_assistant_config(args=None, root=ROOT):
    load_env(root)
    config = {
        "api_key": getattr(args, "openai_api_key", None) or os.getenv("OPENAI_API_KEY"),
        "base_url": getattr(args, "openai_base_url", None)
        or os.getenv("OPENAI_BASE_URL"),
    }
    model = getattr(args, "market_assistant_model", None) or os.getenv(
        "MARKET_ASSISTANT_MODEL"
    )
    if not model:
        raise RuntimeError("MARKET_ASSISTANT_MODEL is required")
    structured_output_mode = os.getenv(
        "MARKET_ASSISTANT_STRUCTURED_OUTPUT_MODE", "json_schema"
    )
    if structured_output_mode not in {"json_schema", "json_object"}:
        raise RuntimeError(
            "MARKET_ASSISTANT_STRUCTURED_OUTPUT_MODE must be json_schema or json_object"
        )
    reasoning_effort = os.getenv("MARKET_ASSISTANT_REASONING_EFFORT", "low")
    if reasoning_effort not in {"low", "medium", "high"}:
        raise RuntimeError(
            "MARKET_ASSISTANT_REASONING_EFFORT must be low, medium, or high"
        )
    audit_timeout_value = os.getenv("MARKET_ASSISTANT_AUDIT_TIMEOUT_SECONDS")
    audit_timeout_seconds = (
        120.0
        if audit_timeout_value is None
        else _parse_market_audit_timeout(audit_timeout_value)
    )
    research_enabled = _parse_market_bool(
        getattr(args, "market_assistant_research_enabled", None)
        or os.getenv("MARKET_ASSISTANT_RESEARCH_ENABLED")
    )
    research_model = None
    provider = None
    supports_web_search = False
    if research_enabled:
        research_model = getattr(
            args, "market_assistant_research_model", None
        ) or os.getenv("MARKET_ASSISTANT_RESEARCH_MODEL")
        if not research_model:
            raise RuntimeError("MARKET_ASSISTANT_RESEARCH_MODEL is required")
        provider = getattr(
            args, "market_assistant_research_provider", None
        ) or os.getenv("MARKET_ASSISTANT_RESEARCH_PROVIDER")
        if provider != "openai_responses":
            raise RuntimeError(
                "MARKET_ASSISTANT_RESEARCH_PROVIDER must be openai_responses"
            )
        supports_web_search = _parse_market_bool(
            getattr(args, "market_assistant_research_supports_web_search", None)
            or os.getenv("MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH")
        )
        if config["base_url"] and not supports_web_search:
            raise RuntimeError("web search support must be explicitly enabled")
    claim_validation_value = os.getenv("MARKET_ASSISTANT_CLAIM_VALIDATION_ENABLED")
    claim_validation_enabled = (
        True
        if claim_validation_value is None
        else _parse_market_bool(claim_validation_value)
    )
    return {
        "api_key": config["api_key"],
        "base_url": config["base_url"],
        "model": model,
        "structured_output_mode": structured_output_mode,
        "reasoning_effort": reasoning_effort,
        "claim_validation_enabled": claim_validation_enabled,
        "audit_timeout_seconds": audit_timeout_seconds,
        "research_model": research_model,
        "provider": provider,
        "research_enabled": research_enabled,
        "supports_web_search": supports_web_search,
    }


def _parse_market_audit_timeout(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "MARKET_ASSISTANT_AUDIT_TIMEOUT_SECONDS must be between 1 and 900"
        ) from exc
    if not 1.0 <= parsed <= 900.0:
        raise RuntimeError(
            "MARKET_ASSISTANT_AUDIT_TIMEOUT_SECONDS must be between 1 and 900"
        )
    return parsed


def _parse_market_bool(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise RuntimeError("market assistant boolean must be true or false")


def build_async_client(
    config, *, max_retries=0, timeout=300.0, error_context="LLM extraction"
):
    if AsyncOpenAI is None:
        raise RuntimeError("openai package is required for LLM extraction")
    if not config.get("api_key"):
        raise RuntimeError(f"OPENAI_API_KEY is required for {error_context}")
    kwargs = {
        "api_key": config["api_key"],
        "max_retries": max_retries,
        "timeout": timeout,
    }
    if config.get("base_url"):
        kwargs["base_url"] = config["base_url"]
    return AsyncOpenAI(**kwargs)


def build_async_client_bundle(
    args=None,
    root=ROOT,
    *,
    model_specs,
    max_retries=0,
    timeout=300.0,
    error_context="LLM extraction",
):
    load_env(root)
    config = {
        "api_key": getattr(args, "openai_api_key", None) or os.getenv("OPENAI_API_KEY"),
        "base_url": getattr(args, "openai_base_url", None)
        or os.getenv("OPENAI_BASE_URL"),
    }
    models = {}
    for spec in model_specs:
        value = getattr(args, spec["arg_name"], None) or _first_non_empty_env(
            spec["env_names"]
        )
        if not value:
            raise RuntimeError(f"{spec['label']} is required")
        models[spec["name"]] = value
    client = build_async_client(
        config,
        max_retries=max_retries,
        timeout=timeout,
        error_context=error_context,
    )
    return {"client": client, "config": config, "models": models}
