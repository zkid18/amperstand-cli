"""Local CLI configuration — server URL, API-key env var name, log settings.

Lives at ~/.amperstand/config.json. The CLI keeps nothing else on disk —
all vault state (feeds, docs, allowlists) is server-side.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".amperstand"
CONFIG_FILE = "config.json"

DEFAULTS: dict[str, dict] = {
    "logging": {
        "level": "INFO",
        "file": "~/.amperstand/amperstand.log",
    },
}


def _config_path(state_dir: Path = DEFAULT_STATE_DIR) -> Path:
    return state_dir / CONFIG_FILE


def load_config(state_dir: Path = DEFAULT_STATE_DIR) -> dict:
    """Load the full config dict from config.json."""
    path = _config_path(state_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict, state_dir: Path = DEFAULT_STATE_DIR) -> None:
    """Write the full config dict to config.json."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _config_path(state_dir)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_section(section: str, state_dir: Path = DEFAULT_STATE_DIR) -> dict:
    """Return a config section merged with built-in defaults."""
    defaults = DEFAULTS.get(section, {})
    data = load_config(state_dir).get(section, {})
    return {**defaults, **data}


def set_value(dotted_key: str, value: str, state_dir: Path = DEFAULT_STATE_DIR) -> None:
    """Set a config value using a dotted key, e.g. 'logging.level'."""
    parts = dotted_key.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Key must be in 'section.key' format, got: {dotted_key!r}")
    section, key = parts
    config = load_config(state_dir)
    if section not in config:
        config[section] = {}
    config[section][key] = value
    save_config(config, state_dir)


# ── Vault backend config ────────────────────────────────────────────


def load_backend_config(state_dir: Path = DEFAULT_STATE_DIR) -> dict | None:
    """Load the `[vault.backend]` config section.

    Shape: {"kind": "http", "http": {"url": "...", "api_key_env": "..."}}
    Returns None if not configured.
    """
    config = load_config(state_dir)
    return config.get("vault", {}).get("backend") or None


def save_backend_config(
    backend_config: dict, state_dir: Path = DEFAULT_STATE_DIR
) -> None:
    """Persist the `[vault.backend]` config section."""
    config = load_config(state_dir)
    config.setdefault("vault", {})["backend"] = backend_config
    save_config(config, state_dir)


def clear_backend_config(state_dir: Path = DEFAULT_STATE_DIR) -> None:
    """Remove the `[vault.backend]` section."""
    config = load_config(state_dir)
    if "vault" in config and "backend" in config["vault"]:
        del config["vault"]["backend"]
        if not config["vault"]:
            del config["vault"]
        save_config(config, state_dir)
