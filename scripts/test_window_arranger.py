"""
Tests for the Auto-Aesthetic Window Arranger.

We mock the Win32 layer (``_Win32``) entirely so the suite can run on any
machine and never moves a real window. Every test is a pure-logic assertion
against ``WindowArranger`` and the layout helpers.

Run:
    .venv\\Scripts\\python scripts\\test_window_arranger.py
"""

from __future__ import annotations

import os
import sys

# Make the project root importable when run directly.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.engine.window_arranger import (
    WindowArranger,
    WindowInfo,
    MonitorRect,
    compute_layout_for_monitor,
    _golden_split,
    _golden_split_horizontal,
    _split_vertically,
    _split_horizontally,
)


# ── Tiny test runner (mirrors the project's existing scripts) ────────

PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Mock Win32 layer ─────────────────────────────────────────────────


class _MockWin32:
    """Drop-in replacement for ``window_arranger._Win32``.

    Holds a synthetic list of windows + monitors and records every mutation
    so tests can assert what was moved / minimized without touching the OS.
    """

    def __init__(
        self,
        windows: list[dict] | None = None,
        monitors: list[MonitorRect] | None = None,
        cursor: tuple[int, int] = (100, 100),
    ):
        # windows = [{hwnd, title, class, rect, is_minimized, is_maximized,
        #             cloaked, ex_style, owner}]
        self._windows = windows or []
        self._monitors = monitors or [MonitorRect(0, 0, 1920, 1080)]
        self._cursor = cursor

        # Recorded mutations
        self.moves: list[tuple[int, int, int, int, int]] = []
        self.minimizes: list[int] = []
        self.restores: list[int] = []

    # ---- enumeration ----

    def enum_windows(self) -> list[int]:
        return [w["hwnd"] for w in self._windows]

    def _w(self, hwnd: int) -> dict:
        for w in self._windows:
            if w["hwnd"] == hwnd:
                return w
        return {}

    def is_window_visible(self, hwnd: int) -> bool:
        return self._w(hwnd).get("visible", True)

    def get_window_text(self, hwnd: int) -> str:
        return self._w(hwnd).get("title", "")

    def get_class_name(self, hwnd: int) -> str:
        return self._w(hwnd).get("class", "")

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        return self._w(hwnd).get("rect", (0, 0, 800, 600))

    def is_iconic(self, hwnd: int) -> bool:
        return self._w(hwnd).get("is_minimized", False)

    def is_zoomed(self, hwnd: int) -> bool:
        return self._w(hwnd).get("is_maximized", False)

    def get_ex_style(self, hwnd: int) -> int:
        return self._w(hwnd).get("ex_style", 0)

    def is_cloaked(self, hwnd: int) -> bool:
        return self._w(hwnd).get("cloaked", False)

    def has_owner(self, hwnd: int) -> bool:
        return self._w(hwnd).get("owner", False)

    # ---- monitors ----

    def monitor_rects(self) -> list[MonitorRect]:
        return list(self._monitors)

    def cursor_pos(self) -> tuple[int, int]:
        return self._cursor

    # ---- mutation ----

    def restore(self, hwnd: int) -> None:
        self.restores.append(hwnd)

    def minimize(self, hwnd: int) -> None:
        self.minimizes.append(hwnd)

    def set_window_pos(self, hwnd: int, x: int, y: int, w: int, h: int) -> bool:
        self.moves.append((hwnd, x, y, w, h))
        return True


def _arr(windows=None, monitors=None, cursor=(100, 100)) -> tuple[WindowArranger, _MockWin32]:
    mock = _MockWin32(windows=windows, monitors=monitors, cursor=cursor)
    return WindowArranger(win32=mock), mock


# ── Categorisation ───────────────────────────────────────────────────


def test_categorize_ide_titles():
    arr, _ = _arr()
    check(arr.categorize("brain.py - Visual Studio Code") == "ide",
          "VS Code window categorized as 'ide'")
    check(arr.categorize("Cursor - main.ts") == "ide",
          "Cursor window categorized as 'ide'")
    check(arr.categorize("PyCharm Community Edition - ay-eye") == "ide",
          "PyCharm window categorized as 'ide'")


def test_categorize_chat_titles():
    arr, _ = _arr()
    check(arr.categorize("#general - Discord") == "chat",
          "Discord categorized as 'chat'")
    check(arr.categorize("Slack | invalid0190") == "chat",
          "Slack categorized as 'chat'")
    check(arr.categorize("Microsoft Teams") == "chat",
          "Teams categorized as 'chat'")


def test_categorize_browser_titles():
    arr, _ = _arr()
    check(arr.categorize("GitHub: ay-eye - Google Chrome") == "browser",
          "Chrome categorized as 'browser'")
    check(arr.categorize("Reddit - Mozilla Firefox") == "browser",
          "Firefox categorized as 'browser'")
    check(arr.categorize("Outlook - Microsoft Edge") == "browser",
          "Edge categorized as 'browser'")


def test_categorize_terminal_via_class_name():
    arr, _ = _arr()
    # Even with empty title, terminal class should win
    check(arr.categorize("", "ConsoleWindowClass") == "terminal",
          "ConsoleWindowClass class -> 'terminal'")
    check(arr.categorize("PowerShell", "") == "terminal",
          "PowerShell title -> 'terminal'")


def test_categorize_music_titles():
    arr, _ = _arr()
    check(arr.categorize("Spotify Premium") == "music",
          "Spotify categorized as 'music'")


def test_categorize_unknown_falls_through_to_other():
    arr, _ = _arr()
    check(arr.categorize("Some Random Window") == "other",
          "Unknown window classified as 'other'")
    check(arr.categorize("", "") == "other",
          "Empty inputs -> 'other'")


# ── Layout math ──────────────────────────────────────────────────────


def test_golden_split_sums_to_total():
    for total in (1920, 1080, 3840, 2560, 1366, 999, 13):
        major, minor = _golden_split(total)
        check(major + minor == total,
              f"_golden_split({total}) sums exactly ({major}+{minor})")


def test_golden_split_major_is_about_618():
    major, _ = _golden_split(1000)
    # Allow ±1 px rounding noise
    check(abs(major - 618) <= 1,
          f"_golden_split(1000) major ~ 618 (got {major})")


def test_golden_split_horizontal_no_overlap_no_gap():
    rect = (0, 0, 1920, 1080)
    left, right = _golden_split_horizontal(rect)
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    check(lx == 0 and ly == 0,
          "left slab starts at the rect origin")
    check(lh == 1080 and rh == 1080,
          "both slabs span full height")
    check(lx + lw == rx,
          "left slab ends exactly where right slab begins (no gap, no overlap)")
    check(lw + rw == 1920,
          "left + right widths equal full rect width")


def test_split_vertically_halves_evenly_with_no_gap():
    rect = (0, 0, 800, 1000)
    top, bottom = _split_vertically(rect)
    tx, ty, tw, th = top
    bx, by, bw, bh = bottom
    check(ty + th == by,
          "top.bottom-edge equals bottom.top-edge (no gap)")
    check(th + bh == 1000,
          "top + bottom heights equal full height")
    check(tw == 800 and bw == 800,
          "both halves span full width")


def test_split_horizontally_halves_evenly_with_no_gap():
    rect = (10, 20, 1000, 600)
    left, right = _split_horizontally(rect)
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    check(lx + lw == rx,
          "left.right-edge equals right.left-edge")
    check(lw + rw == 1000,
          "two-column split sums to full width")


# ── compute_layout_for_monitor ───────────────────────────────────────


def _mk(hwnd: int, category: str, title: str = "") -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        title=title or category,
        class_name="",
        rect=(0, 0, 800, 600),
        category=category,
    )


def test_layout_one_window_fills_monitor():
    monitor = MonitorRect(0, 0, 1920, 1080)
    layout = compute_layout_for_monitor([_mk(1, "ide")], monitor)
    check(layout[1] == (0, 0, 1920, 1080),
          "single window covers the whole monitor")


def test_layout_two_windows_golden_split_with_ide_on_left():
    monitor = MonitorRect(0, 0, 1920, 1080)
    layout = compute_layout_for_monitor(
        [_mk(1, "chat"), _mk(2, "ide")], monitor
    )
    # IDE has higher priority -> should get the bigger left slab
    ide_x, ide_y, ide_w, ide_h = layout[2]
    chat_x, chat_y, chat_w, chat_h = layout[1]
    check(ide_x == 0 and ide_y == 0 and ide_h == 1080,
          "IDE pinned to left edge, full height")
    check(ide_w > chat_w,
          f"IDE width ({ide_w}) > chat width ({chat_w}) (golden ratio)")
    check(ide_x + ide_w == chat_x,
          "IDE right edge meets chat left edge exactly")


def test_layout_three_windows_secondary_column_splits_vertically():
    monitor = MonitorRect(0, 0, 1920, 1080)
    layout = compute_layout_for_monitor(
        [_mk(1, "ide"), _mk(2, "chat"), _mk(3, "browser")], monitor
    )
    # Priority: ide > browser > chat (per _CATEGORY_PRIORITY)
    ide_rect = layout[1]
    browser_rect = layout[3]
    chat_rect = layout[2]

    check(ide_rect[2] > browser_rect[2],
          "IDE gets the big left slab")
    check(browser_rect[0] == chat_rect[0] and browser_rect[2] == chat_rect[2],
          "browser and chat share the same right column (same x and width)")
    check(browser_rect[1] + browser_rect[3] == chat_rect[1],
          "browser bottom edge meets chat top edge (no overlap)")


def test_layout_offscreen_monitor_keeps_negative_origin():
    """Real dual-monitor setups place the second monitor at negative
    coordinates. Make sure the layout respects the monitor's origin."""
    monitor = MonitorRect(-1920, 0, 1920, 1080)
    layout = compute_layout_for_monitor([_mk(1, "ide")], monitor)
    x, y, w, h = layout[1]
    check(x == -1920,
          "layout starts at the monitor's negative left origin")
    check(w == 1920 and h == 1080,
          "layout spans the full monitor on negative-x display")


def test_layout_empty_input_returns_empty():
    check(compute_layout_for_monitor([], MonitorRect(0, 0, 800, 600)) == {},
          "empty input -> empty layout")


# ── Window enumeration filters ───────────────────────────────────────


def test_enumeration_filters_invisible_windows():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Visible", "rect": (0, 0, 800, 600), "visible": True},
        {"hwnd": 2, "title": "Hidden", "rect": (0, 0, 800, 600), "visible": False},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Visible"],
          "invisible windows skipped during enumeration")


def test_enumeration_filters_cloaked_uwp_shells():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Real App", "rect": (0, 0, 800, 600)},
        {"hwnd": 2, "title": "Ghost UWP", "rect": (0, 0, 800, 600), "cloaked": True},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Real App"],
          "DWM-cloaked windows dropped")


def test_enumeration_filters_owned_dialogs():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Main", "rect": (0, 0, 800, 600)},
        {"hwnd": 2, "title": "Save dialog", "rect": (200, 200, 600, 400), "owner": True},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Main"],
          "owned dialogs dropped (only the main window remains)")


def test_enumeration_filters_tool_windows_without_appwindow_flag():
    # WS_EX_TOOLWINDOW = 0x80
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Real", "rect": (0, 0, 800, 600)},
        {"hwnd": 2, "title": "Tooltip", "rect": (10, 10, 200, 50), "ex_style": 0x80},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Real"],
          "tool windows without WS_EX_APPWINDOW filtered out")


def test_enumeration_drops_empty_titles():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Has Title", "rect": (0, 0, 800, 600)},
        {"hwnd": 2, "title": "", "rect": (0, 0, 800, 600)},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Has Title"],
          "windows with empty titles are skipped")


def test_enumeration_protects_ay_eye_dashboard():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Discord", "rect": (0, 0, 800, 600)},
        {"hwnd": 2, "title": "Ay-Eye Dashboard", "rect": (1500, 0, 1920, 1080)},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check("Ay-Eye Dashboard" not in titles,
          "Ay-Eye dashboard is never enumerated as a movable window")
    check("Discord" in titles,
          "real windows still appear alongside the protected one")


def test_enumeration_drops_tiny_windows():
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Big", "rect": (0, 0, 800, 600)},
        # 50x50 — below the MIN_WINDOW_PIXELS threshold
        {"hwnd": 2, "title": "Tiny widget", "rect": (10, 10, 60, 60)},
    ])
    titles = [w.title for w in arr.list_visible_windows()]
    check(titles == ["Big"],
          "tiny non-minimized windows excluded from arrangement")


def test_enumeration_keeps_minimized_windows():
    """Minimized windows have garbage rects, but the user expects 'arrange'
    to PULL them onto the active monitor."""
    arr, _ = _arr(windows=[
        {"hwnd": 1, "title": "Discord",
         "rect": (-32000, -32000, -31840, -31980), "is_minimized": True},
    ])
    wins = arr.list_visible_windows()
    check(len(wins) == 1 and wins[0].is_minimized,
          "minimized windows survive enumeration")


# ── Monitor selection ───────────────────────────────────────────────


def test_pick_monitor_explicit_index_wins():
    arr, _ = _arr(monitors=[
        MonitorRect(0, 0, 1920, 1080),
        MonitorRect(1920, 0, 1920, 1080),
    ])
    m = arr.pick_active_monitor(monitor_index=2)
    check(m.left == 1920,
          "monitor_index=2 returns the right-hand monitor")


def test_pick_monitor_falls_back_to_cursor():
    # cursor at (2500, 200) sits on monitor #2
    arr, _ = _arr(
        monitors=[
            MonitorRect(0, 0, 1920, 1080),
            MonitorRect(1920, 0, 1920, 1080),
        ],
        cursor=(2500, 200),
    )
    m = arr.pick_active_monitor(monitor_index=None)
    check(m.left == 1920,
          "cursor on monitor #2 -> picks monitor #2")


def test_pick_monitor_invalid_index_falls_back_to_cursor():
    arr, _ = _arr(
        monitors=[MonitorRect(0, 0, 1920, 1080)],
        cursor=(100, 100),
    )
    m = arr.pick_active_monitor(monitor_index=999)
    check(m.left == 0,
          "out-of-range monitor_index falls back to cursor monitor")


# ── windows_on_monitor ──────────────────────────────────────────────


def test_windows_on_monitor_filters_by_center_point():
    arr, _ = _arr()
    monitor = MonitorRect(0, 0, 1920, 1080)
    win_on = WindowInfo(hwnd=1, title="A", class_name="",
                        rect=(100, 100, 700, 500))
    win_off = WindowInfo(hwnd=2, title="B", class_name="",
                         rect=(2000, 100, 2400, 500))
    out = arr.windows_on_monitor([win_on, win_off], monitor)
    check([w.hwnd for w in out] == [1],
          "off-monitor window is excluded by center test")


def test_windows_on_monitor_always_includes_minimized():
    arr, _ = _arr()
    monitor = MonitorRect(0, 0, 1920, 1080)
    minimized = WindowInfo(hwnd=1, title="Min", class_name="",
                           rect=(-32000, -32000, -31000, -31000),
                           is_minimized=True)
    out = arr.windows_on_monitor([minimized], monitor)
    check(out == [minimized],
          "minimized window is included regardless of bogus rect")


# ── apply_layout ────────────────────────────────────────────────────


def test_apply_layout_calls_set_window_pos_for_each():
    arr, mock = _arr()
    layout = {1: (0, 0, 1186, 1080), 2: (1186, 0, 734, 540), 3: (1186, 540, 734, 540)}
    moved = arr.apply_layout(layout)
    check(moved == 3,
          "apply_layout returns count of successful moves")
    check(len(mock.moves) == 3,
          "SetWindowPos called once per layout entry")
    check(set(m[0] for m in mock.moves) == {1, 2, 3},
          "every hwnd in layout was moved exactly once")


def test_apply_layout_restores_before_moving():
    """Maximized windows ignore SetWindowPos until restored. We must call
    restore() on every hwnd we move."""
    arr, mock = _arr()
    layout = {7: (0, 0, 1920, 1080)}
    arr.apply_layout(layout)
    check(7 in mock.restores,
          "ShowWindow(SW_RESTORE) called before SetWindowPos")


def test_apply_layout_minimizes_leftover_hwnds():
    arr, mock = _arr()
    arr.apply_layout({1: (0, 0, 100, 100)}, minimize_others=[2, 3])
    check(set(mock.minimizes) == {2, 3},
          "minimize_others list is forwarded to ShowWindow(SW_MINIMIZE)")


# ── Top-level arrange() ─────────────────────────────────────────────


def test_arrange_full_pipeline_three_apps_one_monitor():
    arr, mock = _arr(
        windows=[
            {"hwnd": 10, "title": "main.py - Visual Studio Code",
             "rect": (100, 100, 1000, 800)},
            {"hwnd": 20, "title": "#general - Discord",
             "rect": (1100, 100, 1900, 800)},
            {"hwnd": 30, "title": "GitHub - Google Chrome",
             "rect": (200, 200, 1100, 900)},
        ],
        monitors=[MonitorRect(0, 0, 1920, 1080)],
    )

    summary = arr.arrange()

    check(summary["considered"] == 3,
          "three windows considered for arrangement")
    check(summary["moved"] == 3,
          "three windows actually moved")
    placed_hwnds = sorted(p["hwnd"] for p in summary["placed"])
    check(placed_hwnds == [10, 20, 30],
          "all three target windows landed in the layout")
    # IDE should be the biggest slab
    ide_entry = next(p for p in summary["placed"] if p["category"] == "ide")
    chat_entry = next(p for p in summary["placed"] if p["category"] == "chat")
    check(ide_entry["rect"][2] > chat_entry["rect"][2],
          "IDE slab is wider than chat slab in the final placement")


def test_arrange_minimizes_extras_beyond_top_three():
    arr, mock = _arr(
        windows=[
            {"hwnd": i,
             "title": f"App {i}", "rect": (i * 5, i * 5, i * 5 + 800, i * 5 + 600)}
            for i in (10, 20, 30, 40, 50)
        ],
        monitors=[MonitorRect(0, 0, 1920, 1080)],
    )

    summary = arr.arrange()

    check(len(summary["placed"]) == 3,
          "only the top 3 windows get a layout slot")
    check(len(summary["minimized"]) == 2,
          "the leftover 2 windows are minimized")
    check(len(mock.minimizes) == 2,
          "ShowWindow(SW_MINIMIZE) called twice")


def test_arrange_returns_empty_summary_when_no_windows():
    arr, _ = _arr(monitors=[MonitorRect(0, 0, 1920, 1080)])
    summary = arr.arrange()
    check(summary["placed"] == [] and summary["minimized"] == [],
          "no windows -> empty placed/minimized lists")
    check(summary["moved"] == 0,
          "no windows -> zero moves")


def test_arrange_skips_off_monitor_windows():
    arr, _ = _arr(
        windows=[
            {"hwnd": 1, "title": "On monitor",
             "rect": (100, 100, 900, 700)},
            {"hwnd": 2, "title": "Far away",
             "rect": (5000, 5000, 5800, 5700)},
        ],
        monitors=[MonitorRect(0, 0, 1920, 1080)],
    )
    summary = arr.arrange()
    placed_hwnds = [p["hwnd"] for p in summary["placed"]]
    check(placed_hwnds == [1],
          "off-monitor window is excluded from the active-monitor arrangement")


def test_arrange_two_column_preset_uses_50_50_split():
    arr, _ = _arr(
        windows=[
            {"hwnd": 1, "title": "VS Code",
             "rect": (100, 100, 900, 700)},
            {"hwnd": 2, "title": "Discord",
             "rect": (1000, 100, 1800, 700)},
        ],
        monitors=[MonitorRect(0, 0, 1920, 1080)],
    )
    summary = arr.arrange(preset="two_column")
    widths = sorted(p["rect"][2] for p in summary["placed"])
    # 50/50 of 1920 = 960 each (with rounding tolerance)
    check(abs(widths[0] - widths[1]) <= 1,
          "two_column preset gives both windows ~equal width")


def test_arrange_protects_dashboard_through_full_pipeline():
    arr, mock = _arr(
        windows=[
            {"hwnd": 1, "title": "Discord",
             "rect": (100, 100, 900, 700)},
            {"hwnd": 99, "title": "Ay-Eye Dashboard",
             "rect": (1500, 0, 1920, 1080)},
        ],
        monitors=[MonitorRect(0, 0, 1920, 1080)],
    )
    summary = arr.arrange()
    moved_hwnds = [m[0] for m in mock.moves]
    check(99 not in moved_hwnds,
          "Ay-Eye dashboard is never moved by SetWindowPos")
    check(1 in moved_hwnds,
          "non-protected windows are still moved normally")


# ── Schema integration ─────────────────────────────────────────────


def test_schema_accepts_arrange_windows_action():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Tidying your desktop.",
        "actions": [{"type": "arrange_windows", "preset": "golden_ratio"}],
        "confidence": 0.9,
    })
    check(out["valid"] is True,
          "schema accepts arrange_windows action")
    check(out["response"]["actions"][0]["preset"] == "golden_ratio",
          "preset survives schema normalization")


def test_schema_normalizes_unknown_arrange_preset():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Arranging.",
        "actions": [{"type": "arrange_windows", "preset": "neon-lounge-mode"}],
        "confidence": 0.8,
    })
    check(out["valid"] is True,
          "unknown preset doesn't kill the action")
    check(out["response"]["actions"][0]["preset"] == "golden_ratio",
          "unknown preset coerced back to default 'golden_ratio'")


def test_schema_drops_invalid_monitor_index():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Arranging.",
        "actions": [{
            "type": "arrange_windows",
            "preset": "golden_ratio",
            "monitor_index": "left",  # wrong type
        }],
        "confidence": 0.8,
    })
    action = out["response"]["actions"][0]
    check("monitor_index" not in action,
          "non-int monitor_index dropped from the cleaned action")


# ── Response_format JSON Schema ─────────────────────────────────────


def test_response_format_includes_arrange_windows_in_enum():
    from core.engine.response_format import build_action_schema
    schema = build_action_schema()
    enum = schema["properties"]["type"]["enum"]
    check("arrange_windows" in enum,
          "structured-output JSON Schema lists arrange_windows in the type enum")


def test_response_format_includes_preset_and_monitor_index_fields():
    from core.engine.response_format import build_action_schema
    schema = build_action_schema()
    props = schema["properties"]
    check("preset" in props and "monitor_index" in props,
          "preset + monitor_index present in action JSON Schema properties")
    required = set(schema["required"])
    check("preset" in required and "monitor_index" in required,
          "preset + monitor_index listed in required (strict mode)")


# ── Run ─────────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Window arranger: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
