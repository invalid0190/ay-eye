"""
Pluggable visual styles for the desktop pet.

Each style is a small ``PetStyle`` record (name, description,
widget_size, draw) registered in a global dict. The widget reads the
active style name from ``pet_settings.style`` and dispatches every
paint frame to the selected style's ``draw`` function.

Switching at runtime
--------------------
Type ``/pet style <name>`` in the dashboard's command input.
Type ``/pet styles`` to list everything that's available.

Adding a new style
------------------
1. Drop a new module ``core/ui/pet_styles/your_style.py`` with a
   ``draw(painter, paint_input)`` function.
2. Build a ``PetStyle(...)`` record and call ``register(...)`` at
   module level so it self-registers on import.
3. Import the module from ``_load_styles()`` below so the registry
   sees it.

That's the entire plugin contract — no config file, no entry-point
discovery, no plugin manager. Just plain Python imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class PetStyle:
    """A single visual style.

    ``draw(painter, paint_input)`` is the only Qt-touching surface;
    everything else is descriptive metadata that helps the runtime
    style-picker UI present meaningful choices.
    """

    name: str
    description: str
    widget_size: Tuple[int, int]   # (width, height) in pixels
    draw: Callable                  # (QPainter, PaintInput) -> None


_REGISTRY: Dict[str, PetStyle] = {}

# ``pixel`` is the default — Tamagotchi-style mascot. Every other
# style is an opt-in switch via ``/pet style <name>``.
DEFAULT_STYLE = "pixel"


def register(style: PetStyle) -> None:
    """Add a style to the global registry. Last-wins on name collision."""
    _REGISTRY[style.name] = style


def get(name: str) -> PetStyle:
    """Look up a style by name, falling back to the default if missing."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    return _REGISTRY[DEFAULT_STYLE]


def has(name: str) -> bool:
    return name in _REGISTRY


def list_styles() -> List[str]:
    """All registered style names, sorted alphabetically."""
    return sorted(_REGISTRY.keys())


def list_descriptions() -> List[Tuple[str, str]]:
    """Pairs of ``(name, description)`` for every registered style.

    Used by the ``/pet styles`` command to show a friendly menu.
    """
    return [(name, _REGISTRY[name].description)
            for name in sorted(_REGISTRY.keys())]


def _load_styles() -> None:
    """Import every style module so each one registers itself.

    Called on this module's import. Idempotent — re-imports are no-ops
    because Python caches module objects.
    """
    from . import pixel       # noqa: F401
    from . import ascii_face  # noqa: F401
    from . import orb         # noqa: F401
    from . import shiba       # noqa: F401
    from . import cat         # noqa: F401


_load_styles()
