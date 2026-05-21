"""Per-strategy persistent state for Phase 3 ensemble components.

Each strategy gets its own JSON file at `data/strategy_state_<name>.json`.
The state is mutable across fires — strategies read it at the start of decide(),
write to it during decide(), and the orchestrator persists it after.

This module provides load/save helpers. The schema for each strategy's state is
defined by the strategy itself (no global schema).
"""
import json
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "data"


def _state_path(strategy_name: str) -> Path:
    return STATE_DIR / f"strategy_state_{strategy_name}.json"


def load_state(strategy_name: str) -> dict:
    """Read the strategy's state. Returns empty dict if file doesn't exist or is unreadable."""
    path = _state_path(strategy_name)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable — return empty state. Strategy decides what to do
        # with empty state on first run (typically: enter fresh).
        return {}


def save_state(strategy_name: str, state: dict) -> None:
    """Atomically write the strategy's state to disk."""
    path = _state_path(strategy_name)
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    tmp.replace(path)
