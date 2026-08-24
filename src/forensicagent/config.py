"""Central configuration for ForensicAgent.

Configuration is resolved from three sources, in increasing priority:

1. ``config.yaml`` (shipped defaults, overridable via ``FORENSIC_CONFIG``).
2. Environment variables (``OPENAI_API_KEY``, ``OPENAI_BASE_URL``,
   ``OPENAI_MODEL_ID``).
3. Explicit overrides passed to :func:`llm_config` (e.g. CLI flags).

The user is free to point the pipeline at any OpenAI-compatible provider
(OpenAI, Azure, Ollama, LM Studio, vLLM, ...) by editing ``config.yaml``,
setting environment variables, or passing CLI flags — without touching code.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dependency
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Environment variables controlling the LLM endpoint.
ENV_API_KEY = "OPENAI_API_KEY"
ENV_BASE_URL = "OPENAI_BASE_URL"
ENV_MODEL_ID = "OPENAI_MODEL_ID"
# Optional override for the config file location.
ENV_CONFIG = "FORENSIC_CONFIG"

DEFAULT_MODEL_ID = "gpt-4o-mini"
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML config file, returning an empty dict on any failure."""
    if yaml is None:
        logger.warning("PyYAML not available; ignoring config file %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load config file %s: %s", path, exc)
        return {}


def _config_path() -> Path:
    env = os.getenv(ENV_CONFIG)
    if env:
        return Path(env)
    return _DEFAULT_CONFIG_PATH


def _file_llm() -> dict[str, Any]:
    """LLM settings from the YAML file (lowest priority)."""
    data = _load_yaml(_config_path())
    llm = data.get("llm", {}) if isinstance(data, dict) else {}
    if not isinstance(llm, dict):
        return {}
    return {
        "api_key": str(llm.get("api_key", "") or ""),
        "base_url": str(llm.get("base_url", "") or ""),
        "model_id": str(llm.get("model_id", "") or DEFAULT_MODEL_ID),
    }


def llm_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve the effective LLM configuration.

    Priority (lowest to highest): config.yaml, environment variables,
    ``overrides`` (e.g. CLI flags).

    Returns an empty dict when no API key is configured, signalling that the
    pipeline should run in deterministic (graph-query) mode.
    """
    file_cfg = _file_llm()
    overrides = overrides or {}

    api_key = overrides.get("api_key") or os.getenv(ENV_API_KEY) or file_cfg["api_key"]
    if not api_key:
        return {}

    model_id = overrides.get("model_id") or os.getenv(ENV_MODEL_ID) or file_cfg["model_id"]
    base_url = overrides.get("base_url") or os.getenv(ENV_BASE_URL) or file_cfg["base_url"]

    config: dict[str, Any] = {
        "api_key": api_key,
        "model_id": model_id,
    }
    if base_url:
        config["base_url"] = base_url
    return config


def llm_enabled(overrides: dict[str, Any] | None = None) -> bool:
    """True when an LLM endpoint is configured (API key present)."""
    return bool(llm_config(overrides))
