"""
Persistence for the desktop pet ("Ay").

Stores three things:

* ``hatched`` — whether the pet has played its hatch animation already.
  This flag is the *one* moment the user gets to see the egg-cracking
  reveal; subsequent launches just fade the pet in. Persists across
  app restarts so the surprise doesn't repeat.
* ``position`` — last known on-screen position. The user is allowed
  to drag the pet anywhere on any monitor, and we want it to stay
  put across sessions.
* ``muted`` / ``name`` — small bits of personalisation.

The file lives at ``analytics/pet_settings.json`` next to the
``activity_tracker`` data so all UI state shares a parent directory
(easier to back up or wipe). Writes are atomic (tmp + rename) so a
crash mid-save can never corrupt the JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Optional


_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "analytics")
_DEFAULT_PATH = os.path.join(_DEFAULT_DIR, "pet_settings.json")


@dataclass
class PetSettings:
    """Plain-data settings record. Defaults match the v1 design."""

    hatched: bool = False
    position_x: Optional[int] = None    # None = "snap to default corner on first show"
    position_y: Optional[int] = None
    muted: bool = False
    name: str = "Ay"
    # Pet starts hidden — only spawns when the user types "pet" in the
    # command input (or via the right-click menu / explicit show call).
    # Once shown, this flips to True and persists across sessions.
    visible: bool = False
    # Active visual style. Must match a name registered in
    # ``core.ui.pet_styles``. Switched live via ``/pet style <name>``
    # in the command panel. Unknown names fall back to the default
    # style at lookup time, so a stale value here can never crash
    # the widget.
    style: str = "pixel"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "PetSettings":
        try:
            data = json.loads(text or "{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        # Filter out unknown keys so an older app version reading a
        # newer file (or vice-versa) doesn't crash.
        valid = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in valid}
        return cls(**clean)


def load(path: str = _DEFAULT_PATH) -> PetSettings:
    """Read the settings file. Missing file → defaults."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return PetSettings.from_json(f.read())
    except FileNotFoundError:
        return PetSettings()
    except Exception:
        # Corrupt JSON or permission issue — fall back to defaults
        # rather than crash the app.
        return PetSettings()


def save(settings: PetSettings, path: str = _DEFAULT_PATH) -> bool:
    """Atomically write settings to disk.

    Uses tmp + rename so an interrupted write never leaves the JSON
    file half-written. Returns True on success.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        return False

    try:
        # ``delete=False`` lets us close the handle before the rename.
        # ``dir=`` keeps the tmp file on the same filesystem so
        # ``os.replace`` is genuinely atomic.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".pet_settings.",
            suffix=".tmp",
            dir=os.path.dirname(path),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(settings.to_json())
            os.replace(tmp_path, path)
            return True
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return False
    except Exception:
        return False


# Module-level singleton wired to the default path. The widget reads
# from this on startup and writes back on close / drag-end / hatch-end.
pet_settings: PetSettings = load()


def reload(path: str = _DEFAULT_PATH) -> PetSettings:
    """Reset the in-memory singleton from disk (test helper)."""
    global pet_settings
    pet_settings = load(path)
    return pet_settings
