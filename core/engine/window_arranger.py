"""
Auto-Aesthetic Window Arranger
==============================

Arranges all visible top-level windows on the active monitor into a clean,
golden-ratio (or other preset) layout via Win32 ``SetWindowPos``.

Design goals
------------
* Pure-Python + ``ctypes`` — no extra deps over what the project already has.
* Window enumeration is read-only and idempotent.
* Layout math is monitor-agnostic and DPI-aware (physical pixels).
* Tool windows, cloaked UWP shells, modal dialogs, and the Ay-Eye dashboard
  itself are filtered out so we don't accidentally throw the agent's own UI
  off-screen.
* All state-changing calls (``SetWindowPos`` / ``ShowWindow``) live behind
  ``apply_layout`` so unit tests can run the whole pipeline without touching
  real windows.

Public surface
--------------
``WindowArranger`` exposes::

    list_visible_windows()                  -> list[WindowInfo]
    categorize(title, class_name)           -> str
    compute_layout(windows, monitor_rect, preset='golden_ratio')
                                            -> dict[hwnd, (x, y, w, h)]
    apply_layout(layout)                    -> int (windows moved)
    arrange(preset='golden_ratio',
            monitor_index=None)             -> dict (summary)

The module-level singleton ``window_arranger`` mirrors the project's
``window_manager`` style and is what the executor imports.
"""

from __future__ import annotations

import re
import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass, field
from typing import Callable, Iterable

from core.utils.logger import logger


# ── Win32 plumbing ───────────────────────────────────────────────────

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
_dwmapi = None
try:
    _dwmapi = ctypes.windll.dwmapi
except Exception:
    _dwmapi = None  # not fatal; cloaking check just becomes a no-op

# Window styles (extended)
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_APPWINDOW = 0x00040000

# DWM cloak attribute (filters out the ghostly UWP "container" windows that
# Windows keeps in EnumWindows even though they're invisible).
_DWMWA_CLOAKED = 14

# SetWindowPos / ShowWindow flags
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_SW_RESTORE = 9
_SW_MINIMIZE = 6


# ── Categorisation ───────────────────────────────────────────────────
#
# We match by *substring* against the lowercased title for chat / IDE / browser
# / etc. Titles change ("filename - Visual Studio Code") so we also look at
# class names where the title is unstable (e.g. terminals).
#
# The order of categories below also defines the *priority* used by the layout
# engine — earlier = bigger area.

@dataclass(frozen=True)
class CategorySpec:
    name: str
    title_patterns: tuple[str, ...] = ()
    class_patterns: tuple[str, ...] = ()


_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        name="ide",
        title_patterns=(
            "visual studio code", "cursor", "pycharm", "intellij idea",
            "webstorm", "rider", "goland", "clion", "phpstorm", "rubymine",
            "android studio", "xcode", "sublime text", "atom",
            "notepad++", "neovim", "vim",
        ),
    ),
    CategorySpec(
        name="design",
        title_patterns=(
            "figma", "photoshop", "illustrator", "blender",
            "premiere pro", "after effects", "davinci resolve",
            "autodesk maya", "3ds max", "cinema 4d", "sketch",
        ),
    ),
    CategorySpec(
        name="productivity",
        title_patterns=(
            "notion", "obsidian", "microsoft word", "microsoft excel",
            "microsoft powerpoint", "onenote", "evernote", "todoist",
            "trello", "asana", "linear",
        ),
    ),
    CategorySpec(
        name="browser",
        title_patterns=(
            " - google chrome", " - mozilla firefox", " - microsoft edge",
            " - brave", " - opera", " - vivaldi", " - arc",
            "google chrome", "mozilla firefox", "microsoft edge",
        ),
    ),
    CategorySpec(
        name="chat",
        title_patterns=(
            "discord", "slack", "microsoft teams", "whatsapp",
            "telegram", "signal", "skype", "zoom", "zulip",
        ),
    ),
    CategorySpec(
        name="terminal",
        title_patterns=(
            "windows terminal", "powershell", "command prompt",
            "git bash", "wsl",
        ),
        class_patterns=(
            "consolewindowclass", "cascadia_hosting_window_class",
            "windowsterminal",
        ),
    ),
    CategorySpec(
        name="music",
        title_patterns=(
            "spotify", "youtube music", "apple music", "tidal",
            "foobar2000", "vlc media player", "winamp",
        ),
    ),
)

# Priority order: lower index = bigger slot. "other" is always last.
_CATEGORY_PRIORITY: tuple[str, ...] = tuple(c.name for c in _CATEGORIES) + ("other",)


# Windows that should NEVER be moved, even if they're enumerated. Match by
# substring of title (case-insensitive). The Ay-Eye dashboard wins itself
# protection here so we don't shove the agent's own UI off-screen.
_PROTECTED_TITLE_PATTERNS = (
    "ay-eye", "ay eye", "program manager",  # the desktop itself
)


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom (physical px)
    is_minimized: bool = False
    is_maximized: bool = False
    category: str = "other"

    @property
    def width(self) -> int:
        l, _, r, _ = self.rect
        return max(0, r - l)

    @property
    def height(self) -> int:
        _, t, _, b = self.rect
        return max(0, b - t)


@dataclass
class MonitorRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


# ── Win32 helper layer (mockable) ────────────────────────────────────


class _Win32:
    """Thin, mockable wrapper around the handful of Win32 calls we use."""

    # ---- enumeration ----

    def enum_windows(self) -> list[int]:
        if _user32 is None:
            return []
        results: list[int] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def _cb(hwnd, _lparam):
            results.append(int(hwnd))
            return True

        _user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return results

    def is_window_visible(self, hwnd: int) -> bool:
        if _user32 is None:
            return False
        return bool(_user32.IsWindowVisible(hwnd))

    def get_window_text(self, hwnd: int) -> str:
        if _user32 is None:
            return ""
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def get_class_name(self, hwnd: int) -> str:
        if _user32 is None:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        if _user32 is None:
            return (0, 0, 0, 0)
        rect = wt.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (0, 0, 0, 0)
        return (rect.left, rect.top, rect.right, rect.bottom)

    def is_iconic(self, hwnd: int) -> bool:
        """True if window is minimized."""
        if _user32 is None:
            return False
        return bool(_user32.IsIconic(hwnd))

    def is_zoomed(self, hwnd: int) -> bool:
        """True if window is maximized."""
        if _user32 is None:
            return False
        return bool(_user32.IsZoomed(hwnd))

    def get_ex_style(self, hwnd: int) -> int:
        if _user32 is None:
            return 0
        # GWL_EXSTYLE = -20
        return int(_user32.GetWindowLongW(hwnd, -20))

    def is_cloaked(self, hwnd: int) -> bool:
        """DWM cloaked windows look visible to EnumWindows but are hidden."""
        if _dwmapi is None:
            return False
        cloaked = ctypes.c_int(0)
        try:
            hr = _dwmapi.DwmGetWindowAttribute(
                wt.HWND(hwnd),
                _DWMWA_CLOAKED,
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked),
            )
            return hr == 0 and cloaked.value != 0
        except Exception:
            return False

    def has_owner(self, hwnd: int) -> bool:
        """True if this is a child / dialog of another window."""
        if _user32 is None:
            return False
        # GW_OWNER = 4
        owner = _user32.GetWindow(hwnd, 4)
        return bool(owner)

    # ---- monitor info ----

    def monitor_rects(self) -> list[MonitorRect]:
        """Return the physical-pixel rect of every connected monitor.

        We use ``mss`` if available because the project already depends on it
        and it gives us virtual-desktop-aware rects with negative origins.
        Falls back to a single primary-monitor rect via Win32.
        """
        try:
            import mss  # type: ignore
            with mss.mss() as sct:
                out = []
                for m in sct.monitors[1:]:  # skip the [0] virtual desktop entry
                    out.append(MonitorRect(
                        left=int(m["left"]),
                        top=int(m["top"]),
                        width=int(m["width"]),
                        height=int(m["height"]),
                    ))
                if out:
                    return out
        except Exception:
            pass

        if _user32 is None:
            return [MonitorRect(0, 0, 1920, 1080)]
        w = _user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = _user32.GetSystemMetrics(1)  # SM_CYSCREEN
        return [MonitorRect(0, 0, w, h)]

    def cursor_pos(self) -> tuple[int, int]:
        if _user32 is None:
            return (0, 0)
        pt = wt.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return (int(pt.x), int(pt.y))

    # ---- mutation ----

    def restore(self, hwnd: int) -> None:
        if _user32 is None:
            return
        _user32.ShowWindow(hwnd, _SW_RESTORE)

    def minimize(self, hwnd: int) -> None:
        if _user32 is None:
            return
        _user32.ShowWindow(hwnd, _SW_MINIMIZE)

    def set_window_pos(self, hwnd: int, x: int, y: int, w: int, h: int) -> bool:
        if _user32 is None:
            return False
        flags = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_SHOWWINDOW
        return bool(_user32.SetWindowPos(hwnd, 0, x, y, w, h, flags))


# ── Layout engine ────────────────────────────────────────────────────


def _golden_split(total: int) -> tuple[int, int]:
    """Split *total* into ``(major, minor)`` using the golden ratio.

    ``major`` is ~61.8% of the total, ``minor`` the remainder. We round so
    that ``major + minor == total`` exactly (avoids 1-pixel gaps).
    """
    major = int(round(total * 0.61803398875))
    minor = total - major
    return major, minor


def _split_vertically(rect: tuple[int, int, int, int]) -> tuple[
    tuple[int, int, int, int], tuple[int, int, int, int]
]:
    """Split *rect* (x, y, w, h) into top and bottom halves of equal height."""
    x, y, w, h = rect
    top_h = h // 2
    bottom_h = h - top_h
    return ((x, y, w, top_h), (x, y + top_h, w, bottom_h))


def _split_horizontally(rect: tuple[int, int, int, int]) -> tuple[
    tuple[int, int, int, int], tuple[int, int, int, int]
]:
    x, y, w, h = rect
    left_w = w // 2
    right_w = w - left_w
    return ((x, y, left_w, h), (x + left_w, y, right_w, h))


def _golden_split_horizontal(rect: tuple[int, int, int, int]) -> tuple[
    tuple[int, int, int, int], tuple[int, int, int, int]
]:
    """Split into a left ~61.8% slab + right ~38.2% slab."""
    x, y, w, h = rect
    major, minor = _golden_split(w)
    return ((x, y, major, h), (x + major, y, minor, h))


def compute_layout_for_monitor(
    windows: list[WindowInfo],
    monitor: MonitorRect,
    preset: str = "golden_ratio",
) -> dict[int, tuple[int, int, int, int]]:
    """Return ``{hwnd: (x, y, w, h)}`` placements for *windows* on *monitor*.

    Behaviour depends on how many windows we get:

    * **0 windows** → empty layout (no-op)
    * **1 window**  → fills the monitor
    * **2 windows** → golden split horizontally; primary on the left
    * **3+ windows** → golden split horizontally; secondary column is split
      vertically so the next two windows share it. Anything beyond the top
      three is left for the caller to minimize.
    """
    if not windows:
        return {}

    # Sort by category priority (lower index = higher priority). Windows in
    # the same category keep their incoming order so the user-visible
    # behaviour is stable.
    pri_index = {c: i for i, c in enumerate(_CATEGORY_PRIORITY)}
    sorted_wins = sorted(
        windows,
        key=lambda w: (pri_index.get(w.category, len(_CATEGORY_PRIORITY)), w.hwnd),
    )

    full = (monitor.left, monitor.top, monitor.width, monitor.height)
    layout: dict[int, tuple[int, int, int, int]] = {}

    n = len(sorted_wins)
    if n == 1:
        layout[sorted_wins[0].hwnd] = full
        return layout

    if preset == "two_column":
        left, right = _split_horizontally(full)
    else:
        # Default: golden ratio split
        left, right = _golden_split_horizontal(full)

    if n == 2:
        layout[sorted_wins[0].hwnd] = left
        layout[sorted_wins[1].hwnd] = right
        return layout

    # 3+ windows: secondary column is split vertically
    right_top, right_bottom = _split_vertically(right)
    layout[sorted_wins[0].hwnd] = left
    layout[sorted_wins[1].hwnd] = right_top
    layout[sorted_wins[2].hwnd] = right_bottom
    return layout


# ── Main facade ──────────────────────────────────────────────────────


class WindowArranger:
    """Public API used by the executor and tests."""

    # Exposed for monkey-patching in tests
    _MIN_WINDOW_PIXELS = 100  # ignore windows smaller than this in either dim

    def __init__(self, win32: _Win32 | None = None):
        self._w = win32 or _Win32()

    # ── Categorisation ───────────────────────────────────────────────

    def categorize(self, title: str, class_name: str = "") -> str:
        """Return the category bucket for a window."""
        t = (title or "").lower()
        c = (class_name or "").lower()
        for spec in _CATEGORIES:
            for pat in spec.title_patterns:
                if pat in t:
                    return spec.name
            for pat in spec.class_patterns:
                if pat in c:
                    return spec.name
        return "other"

    # ── Enumeration ──────────────────────────────────────────────────

    def list_visible_windows(self) -> list[WindowInfo]:
        """Walk EnumWindows and return only the windows we'd consider moving."""
        out: list[WindowInfo] = []
        for hwnd in self._w.enum_windows():
            info = self._inspect(hwnd)
            if info is not None:
                out.append(info)
        return out

    def _inspect(self, hwnd: int) -> WindowInfo | None:
        if not self._w.is_window_visible(hwnd):
            return None
        if self._w.is_cloaked(hwnd):
            return None
        if self._w.has_owner(hwnd):
            return None  # tool / dialog

        ex_style = self._w.get_ex_style(hwnd)
        if ex_style & _WS_EX_TOOLWINDOW and not (ex_style & _WS_EX_APPWINDOW):
            return None

        title = self._w.get_window_text(hwnd)
        if not title:
            return None

        # Skip windows we've explicitly protected (the agent's own UI, etc.)
        title_lower = title.lower()
        for pat in _PROTECTED_TITLE_PATTERNS:
            if pat in title_lower:
                return None

        class_name = self._w.get_class_name(hwnd)
        rect = self._w.get_window_rect(hwnd)
        is_min = self._w.is_iconic(hwnd)
        is_max = self._w.is_zoomed(hwnd)

        info = WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            rect=rect,
            is_minimized=is_min,
            is_maximized=is_max,
            category=self.categorize(title, class_name),
        )

        # Filter out tiny / off-screen windows. We treat a minimized window's
        # rect as untrustworthy (Win32 reports a fake -32000,-32000 rect),
        # so we keep minimized windows in the candidate pool — they'll be
        # restored when we apply the layout.
        if not is_min:
            if info.width < self._MIN_WINDOW_PIXELS or info.height < self._MIN_WINDOW_PIXELS:
                return None

        return info

    # ── Monitor selection ────────────────────────────────────────────

    def pick_active_monitor(
        self,
        monitor_index: int | None = None,
    ) -> MonitorRect:
        """Pick the monitor we should arrange against.

        If *monitor_index* is given (1-based, matching mss convention) and in
        range, that monitor is used. Otherwise we pick whichever monitor
        currently contains the OS cursor.
        """
        rects = self._w.monitor_rects()
        if not rects:
            return MonitorRect(0, 0, 1920, 1080)

        if monitor_index is not None and 1 <= monitor_index <= len(rects):
            return rects[monitor_index - 1]

        cx, cy = self._w.cursor_pos()
        for r in rects:
            if r.left <= cx < r.right and r.top <= cy < r.bottom:
                return r
        return rects[0]

    # ── Layout helpers ───────────────────────────────────────────────

    def windows_on_monitor(
        self,
        windows: Iterable[WindowInfo],
        monitor: MonitorRect,
    ) -> list[WindowInfo]:
        """Return the windows whose center sits on *monitor*.

        Minimized windows are always included (their rect is meaningless, so
        they fall through to whichever monitor we're arranging) — the user's
        intent of "arrange" should pull them onto the active screen.
        """
        out: list[WindowInfo] = []
        for w in windows:
            if w.is_minimized:
                out.append(w)
                continue
            l, t, r, b = w.rect
            cx = (l + r) // 2
            cy = (t + b) // 2
            if monitor.left <= cx < monitor.right and monitor.top <= cy < monitor.bottom:
                out.append(w)
        return out

    def compute_layout(
        self,
        windows: list[WindowInfo],
        monitor: MonitorRect,
        preset: str = "golden_ratio",
    ) -> dict[int, tuple[int, int, int, int]]:
        return compute_layout_for_monitor(windows, monitor, preset)

    # ── Apply ────────────────────────────────────────────────────────

    def apply_layout(
        self,
        layout: dict[int, tuple[int, int, int, int]],
        minimize_others: Iterable[int] = (),
    ) -> int:
        """Move every window in *layout* and minimize *minimize_others*.

        Returns the count of windows successfully moved.
        """
        moved = 0
        for hwnd, (x, y, w, h) in layout.items():
            try:
                self._w.restore(hwnd)
                if self._w.set_window_pos(hwnd, x, y, w, h):
                    moved += 1
            except Exception as e:
                logger.logger.warning(
                    f"WindowArranger: SetWindowPos failed for hwnd {hwnd}: {e}"
                )

        for hwnd in minimize_others:
            try:
                self._w.minimize(hwnd)
            except Exception as e:
                logger.logger.warning(
                    f"WindowArranger: minimize failed for hwnd {hwnd}: {e}"
                )

        return moved

    # ── Top-level orchestrator ───────────────────────────────────────

    def arrange(
        self,
        preset: str = "golden_ratio",
        monitor_index: int | None = None,
        max_primary_windows: int = 3,
    ) -> dict:
        """High-level entry point used by the executor.

        Returns a summary dict with the following keys::

            {
              "monitor": (left, top, width, height),
              "preset": str,
              "considered": int,            # windows on the active monitor
              "placed": list[{hwnd, title, category, rect}],
              "minimized": list[{hwnd, title}],
              "moved": int,                 # successful SetWindowPos calls
            }
        """
        all_windows = self.list_visible_windows()
        monitor = self.pick_active_monitor(monitor_index)
        candidates = self.windows_on_monitor(all_windows, monitor)

        if not candidates:
            logger.logger.info(
                "WindowArranger: No movable windows found on the active monitor"
            )
            return {
                "monitor": (monitor.left, monitor.top, monitor.width, monitor.height),
                "preset": preset,
                "considered": 0,
                "placed": [],
                "minimized": [],
                "moved": 0,
            }

        # Sort candidates the same way compute_layout does so we can pick the
        # leftover ones to minimize.
        pri_index = {c: i for i, c in enumerate(_CATEGORY_PRIORITY)}
        sorted_candidates = sorted(
            candidates,
            key=lambda w: (pri_index.get(w.category, len(_CATEGORY_PRIORITY)), w.hwnd),
        )
        primary = sorted_candidates[:max_primary_windows]
        leftover = sorted_candidates[max_primary_windows:]

        layout = self.compute_layout(primary, monitor, preset=preset)
        moved = self.apply_layout(layout, minimize_others=[w.hwnd for w in leftover])

        placed = [
            {
                "hwnd": w.hwnd,
                "title": w.title,
                "category": w.category,
                "rect": layout.get(w.hwnd),
            }
            for w in primary
            if w.hwnd in layout
        ]
        minimized = [{"hwnd": w.hwnd, "title": w.title} for w in leftover]

        logger.logger.info(
            f"WindowArranger: preset={preset} placed={len(placed)} "
            f"minimized={len(minimized)} on monitor "
            f"{monitor.left},{monitor.top} {monitor.width}x{monitor.height}"
        )
        return {
            "monitor": (monitor.left, monitor.top, monitor.width, monitor.height),
            "preset": preset,
            "considered": len(candidates),
            "placed": placed,
            "minimized": minimized,
            "moved": moved,
        }


# Module-level singleton matches the project's window_manager pattern.
window_arranger = WindowArranger()
