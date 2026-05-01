import time
import unittest
from unittest.mock import patch

from core.engine.action_state import ActionState
from core.engine.executor import ActionExecutor
from core.state.manager import state_manager
from core.state.models import UIElement


class FakeFrame:
    raw_size = (3840, 1080)
    desktop_offset = (-1920, 0)


class ExecutorRegressionTests(unittest.TestCase):
    def test_stale_action_lock_recovers(self):
        state = ActionState()
        state.max_action_seconds = 1

        self.assertTrue(state.start_action("hung-command"))
        state.started_at = time.time() - 2

        self.assertTrue(state.start_action("next-command"))
        self.assertEqual(state.current_action, "next-command")

    def test_clamp_preserves_negative_monitor_coordinates(self):
        executor = ActionExecutor()

        self.assertEqual(executor._clamp_point(-1919, 5, FakeFrame()), (-1919, 5))
        self.assertEqual(executor._clamp_point(-3000, -20, FakeFrame()), (-1919, 1))

    @patch("core.engine.executor.os.path.exists", return_value=True)
    @patch("core.engine.executor.subprocess.Popen")
    def test_direct_exe_command_launches_detached(self, popen, exists):
        executor = ActionExecutor()

        launched = executor._try_launch_detached_command(
            "& 'C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe'"
        )

        self.assertTrue(launched)
        args = popen.call_args.args[0]
        self.assertEqual(args[:3], ["powershell", "-NoProfile", "-Command"])
        self.assertIn("Start-Process -FilePath", args[3])
        self.assertIn("blender.exe", args[3])

    @patch("core.engine.executor.pyautogui.click")
    @patch("core.engine.executor.pyautogui.moveTo")
    def test_click_can_resolve_named_ui_target(self, move_to, click):
        state_manager.update(
            app="TestApp",
            window="Main",
            ui_elements=[UIElement(name="Submit", role="button", rect=[100, 100, 50, 20])],
        )
        executor = ActionExecutor()

        executor.execute_single({"type": "click", "target": "Submit"})

        move_to.assert_called()
        click.assert_called_once()
        x, y = move_to.call_args.args[:2]
        self.assertEqual((x, y), (125, 110))

    def test_blender_import_script_uses_bpy_importer(self):
        executor = ActionExecutor()

        script = executor._blender_import_script("C:\\assets\\chair.fbx")

        self.assertIn("bpy.ops.import_scene.fbx", script)
        self.assertIn("AYEYE_IMPORT_RESULT", script)

    @patch("core.engine.executor.pyautogui.press")
    @patch("core.engine.executor.pyautogui.hotkey")
    @patch("pyperclip.copy")
    @patch("pyperclip.paste", return_value="old")
    @patch("core.engine.executor.window_manager.switch_to", return_value=True)
    def test_blender_python_uses_console_without_mouse_clicks(self, switch_to, paste, copy, hotkey, press):
        executor = ActionExecutor()

        ok = executor._send_python_to_blender_console(
            "import bpy\nbpy.ops.object.select_all(action='SELECT')",
            "select all",
        )

        self.assertTrue(ok)
        switch_to.assert_called_with("blender")
        hotkey.assert_any_call("shift", "f4")
        hotkey.assert_any_call("ctrl", "v")
        press.assert_called_with("enter")
        copied = copy.call_args_list[0].args[0]
        self.assertIn("bpy.ops.object.select_all", copied)


if __name__ == "__main__":
    unittest.main()
