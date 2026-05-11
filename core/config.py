
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root is two levels up from this file
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"


def load_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"config.yaml must be a YAML mapping, got {type(data)}")
    return data


def get_github_token() -> str:
    load_env()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN is not set. "
            "Create a .env file with GITHUB_TOKEN=<your_token> or export it in your shell."
        )
    return token


def is_kill_switch_active(cfg: dict[str, Any]) -> bool:
    """Return True if the kill-switch flag is set in config."""
    return bool(cfg.get("kill_switch", False))