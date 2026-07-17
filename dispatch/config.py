"""
Paths and settings.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from . import __version__

APP_DIR_NAME = "Dispatch"
REPO_URL = "https://github.com/HawaiizFynest/dispatch"
USER_AGENT = f"Dispatch/{__version__} (+{REPO_URL})"

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Fuzzy title match score (0-100) required to fold an article into an
    # existing cluster. Lower catches more duplicates and risks false merges.
    "cluster_threshold": 82,
    # Only compare a new article against clusters seen in this many days.
    "cluster_window_days": 5,
    # Drop articles older than this on cleanup. 0 disables cleanup.
    "retention_days": 120,
    # Seconds before a feed request gives up.
    "fetch_timeout": 20,
    # Parallel feed fetches.
    "fetch_workers": 6,
    # Refresh every N minutes while the app is open. 0 disables.
    "auto_refresh_minutes": 0,
    # User-Agent sent to feed hosts.
    # CISA and others run firewalls that reject vague or browser-imitating
    # agents. A Product/Version token with a contact URL gets through and is
    # honest about what is knocking. Built from __version__ so the two cannot
    # drift apart.
    "user_agent": USER_AGENT,
    # Name of the template selected in the compose pane.
    "last_template": "Forum post (BBCode)",
    # Thread title length your forum accepts. Dispatch warns past this.
    "title_max_chars": 100,
    # Auto-tag new clusters with a category guess.
    "auto_categorize": True,
}


def data_dir() -> Path:
    """Per-user writable directory for the database and config."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / APP_DIR_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "dispatch.db"


def config_path() -> Path:
    return data_dir() / "config.json"


def _heal_user_agent(stored: str) -> str:
    """
    Replace a User-Agent this app wrote in an older version.

    A value starting with "Dispatch/" came from a previous default, not from
    anybody's decision, so it gets brought up to date. The first one shipped
    was refused by CISA's firewall, and leaving it in place means the fix never
    reaches the people who hit the bug.

    Anything else is a deliberate override and stays exactly as written, which
    is the whole point of exposing the setting.
    """
    if not stored:
        return USER_AGENT
    if stored == USER_AGENT:
        return stored
    if stored.lower().startswith("dispatch/"):
        return USER_AGENT
    return stored


def load_settings() -> Dict[str, Any]:
    """Read config.json, filling anything missing from defaults."""
    settings = dict(DEFAULT_SETTINGS)
    path = config_path()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in DEFAULT_SETTINGS:
                        settings[key] = value
        except (json.JSONDecodeError, OSError):
            # A corrupt config should not stop the app from opening.
            pass
    settings["user_agent"] = _heal_user_agent(str(settings.get("user_agent", "")))
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    """
    Write only what differs from the defaults.

    Writing every key looks harmless until a default changes. The stored copy
    wins on load, so a value the user never chose gets pinned forever and the
    new default never reaches them. That is not hypothetical: the first
    User-Agent this app shipped got refused by CISA's firewall, and anyone
    carrying a full config would have kept the broken one after the fix landed.

    Keeping the file to real choices also means it stays short enough to read
    and edit by hand.
    """
    changed = {
        k: v
        for k, v in settings.items()
        if k in DEFAULT_SETTINGS and v != DEFAULT_SETTINGS[k]
    }
    tmp = config_path().with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(changed, fh, indent=2, sort_keys=True)
    tmp.replace(config_path())
