"""
CLI Config — load settings from config.toml, env vars, and CLI args.

Resolution order (last wins): config file < env var < CLI argument.

Exports:
    DEFAULT_CONFIG_PATH, load_config, merge_with_cli_args
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Python 3.8–3.10


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_config",
    "merge_with_cli_args",
]

DEFAULT_CONFIG_PATH: Path = Path.home() / ".config" / "ai-util" / "config.toml"

# Schema of known config keys with their env-var overrides
_ENV_MAP: Dict[str, str] = {
    "api_key": "OPENAI_API_KEY",
    "base_url": "OPENAI_BASE_URL",
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load config from a TOML file, then overlay environment variables.

    Args:
        config_path: Path to config file. Defaults to ~/.config/ai-util/config.toml.

    Returns:
        Dict with keys: api_key, base_url, model, temperature, system_prompt, etc.
    """
    config: Dict[str, Any] = {}

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "rb") as f:
            config = tomllib.load(f)

    # Environment variables override config file
    for key, env_var in _ENV_MAP.items():
        if env_var in os.environ:
            config[key] = os.environ[env_var]

    return config


def merge_with_cli_args(config: Dict[str, Any], args: Any) -> Dict[str, Any]:
    """
    Override config dict with non-None CLI argparse values.

    Args:
        config: Dict from load_config().
        args: Namespace from argparse.parse_args().

    Returns:
        Updated config dict (modified in place for convenience).
    """
    for attr in ("api_key", "base_url", "model", "temperature", "system_prompt",
                 "prompt", "stream"):
        value = getattr(args, attr, None)
        if value is not None:
            config[attr] = value
    return config
