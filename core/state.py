
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_state(filename: str) -> dict[str, Any]:
    _ensure_dir(STATE_DIR)
    path = STATE_DIR / filename
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read state file %s: %s — starting fresh.", path, exc)
        return {}


def save_state(filename: str, data: dict[str, Any]) -> None:
    _ensure_dir(STATE_DIR)
    path = STATE_DIR / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    logger.debug("State saved to %s.", path)


def get_value(state: dict[str, Any], key: str, default: Any = None) -> Any:
    return state.get(key, default)