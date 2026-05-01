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


if __name__ == "__main__":
    unittest.main()
