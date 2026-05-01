import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from core.engine.action_state import ActionState
from core.engine.executor import ActionExecutor
from core.state.manager import state_manager
from core.state.models import UIElement
from core.vision.live_perception import LivePerceptionService
from core.vision.screen_locator import ScreenLocator, ScreenLocatorResult


class FakeFrame:
    raw_size = (3840, 1080)
    desktop_offset = (-1920, 0)


class FakeImageFrame:
    def __init__(self, image, offset=(0, 0)):
        self.raw_image = image
        self.processed_image = image
        self.raw_size = image.size
        self.processed_size = image.size
        self.desktop_offset = offset


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

    def test_screen_locator_uses_uia_center(self):
        state_manager.update(
            app="TestApp",
            window="Main",
            ui_elements=[UIElement(name="Submit", role="button", rect=[100, 100, 50, 20])],
        )
        locator = ScreenLocator()

        result = locator.locate("Submit", methods=("uia",))

        self.assertIsNotNone(result)
        self.assertEqual(result.method, "uia")
        self.assertEqual((result.x, result.y), (125, 110))

    def test_screen_locator_ocr_phrase_uses_full_bbox_and_offset(self):
        locator = ScreenLocator()
        ocr_data = {
            "text": ["Import", "option", "Other"],
            "left": [10, 70, 200],
            "top": [20, 20, 20],
            "width": [50, 60, 40],
            "height": [20, 20, 20],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
            "conf": ["96", "92", "88"],
        }

        result = locator._best_ocr_result("import option", ocr_data, offset=(-100, 5))

        self.assertIsNotNone(result)
        self.assertEqual(result.method, "ocr")
        self.assertEqual(result.label, "Import option")
        self.assertEqual(result.bbox, (-90, 25, 120, 20))
        self.assertEqual((result.x, result.y), (-30, 35))

    def test_node_ocr_words_are_grouped_for_phrase_matching(self):
        locator = ScreenLocator()
        ocr_data = locator._words_to_ocr_data([
            {"text": "Import", "left": 10, "top": 20, "width": 50, "height": 20, "conf": 91},
            {"text": "option", "left": 70, "top": 22, "width": 60, "height": 19, "conf": 89},
        ])

        result = locator._best_ocr_result("import option", ocr_data, offset=(0, 0))

        self.assertIsNotNone(result)
        self.assertEqual(result.label, "Import option")
        self.assertEqual((result.x, result.y), (70, 30))

    def test_screen_change_verification_can_ignore_click_overlay_region(self):
        before = Image.new("RGB", (100, 100), (255, 255, 255))
        after = Image.new("RGB", (100, 100), (255, 255, 255))
        draw = ImageDraw.Draw(after)
        draw.rectangle([20, 20, 40, 40], fill=(0, 0, 0))

        service = LivePerceptionService()
        previous_frame = FakeImageFrame(before)
        current_frame = FakeImageFrame(after)
        with service._lock:
            service._latest_frame = current_frame

        self.assertTrue(service.verify_screen_changed(previous_frame))
        self.assertFalse(
            service.verify_screen_changed(
                previous_frame,
                ignore_regions=[(15, 15, 35, 35)],
            )
        )

    def test_screen_locator_visual_refines_near_icon(self):
        image = Image.new("RGB", (120, 120), (240, 240, 240))
        draw = ImageDraw.Draw(image)
        draw.rectangle([45, 40, 70, 65], fill=(30, 30, 30))
        frame = FakeImageFrame(image, offset=(-20, 10))
        locator = ScreenLocator()

        result = locator.locate(
            "brush icon",
            frame=frame,
            methods=("visual",),
            approximate=(38, 62),
            min_confidence=0.45,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.method, "visual")
        self.assertLess(abs(result.x - 37), 5)
        self.assertLess(abs(result.y - 62), 5)

    @patch("core.engine.executor.pyautogui.click")
    @patch("core.engine.executor.pyautogui.moveTo")
    @patch("core.engine.executor.screen_locator.locate")
    @patch("core.engine.executor.live_perception.verify_screen_changed", return_value=True)
    def test_click_prefers_locator_over_supplied_coordinates(self, verify, locate, move_to, click):
        locate.return_value = ScreenLocatorResult(
            target="Submit",
            method="uia",
            label="Submit",
            x=125,
            y=110,
            bbox=(100, 100, 50, 20),
            confidence=1.0,
        )
        executor = ActionExecutor()

        executor.execute_single({"type": "click", "target": "Submit", "x": 999, "y": 999})

        move_to.assert_called()
        click.assert_called_once()
        x, y = move_to.call_args.args[:2]
        self.assertEqual((x, y), (125, 110))

    @patch("core.engine.executor.pyautogui.click")
    @patch("core.engine.executor.pyautogui.moveTo")
    @patch("core.engine.executor.screen_locator.locate")
    @patch("core.engine.executor.live_perception.verify_screen_changed", return_value=True)
    def test_click_uses_visual_locator_when_text_locators_miss(self, verify, locate, move_to, click):
        locate.side_effect = [
            None,
            ScreenLocatorResult(
                target="Brush icon",
                method="visual",
                label="visual target near (10,20)",
                x=80,
                y=85,
                bbox=(70, 75, 20, 20),
                confidence=0.74,
            ),
        ]
        executor = ActionExecutor()

        executor.execute_single({"type": "click", "target": "Brush icon", "x": 10, "y": 20})

        self.assertEqual(locate.call_args_list[1].kwargs["methods"], ("visual",))
        self.assertEqual(locate.call_args_list[1].kwargs["approximate"], (10, 20))
        x, y = move_to.call_args.args[:2]
        self.assertEqual((x, y), (80, 85))
        click.assert_called_once()

    @patch("core.engine.executor.pyautogui.click")
    @patch("core.engine.executor.pyautogui.moveTo")
    @patch("core.engine.executor.screen_locator.locate")
    @patch("core.engine.executor.live_perception.get_latest_frame", return_value=None)
    @patch("core.engine.executor.live_perception.verify_screen_changed", side_effect=[False, True])
    def test_click_retries_with_visual_locator_after_no_change(self, verify, latest_frame, locate, move_to, click):
        locate.return_value = ScreenLocatorResult(
            target="Settings icon",
            method="visual",
            label="visual target near (40,50)",
            x=40,
            y=50,
            bbox=(30, 40, 20, 20),
            confidence=0.71,
        )
        executor = ActionExecutor()

        ok = executor._click_with_retry(
            10,
            10,
            "left",
            1,
            None,
            "Settings icon",
            ScreenLocatorResult(
                target="Settings icon",
                method="uia",
                label="Settings",
                x=10,
                y=10,
                bbox=(0, 0, 20, 20),
                confidence=0.8,
            ),
            original_point=(40, 50),
        )

        self.assertTrue(ok)
        self.assertEqual(move_to.call_count, 2)
        self.assertEqual(click.call_count, 2)
        second_x, second_y = move_to.call_args_list[1].args[:2]
        self.assertEqual((second_x, second_y), (40, 50))

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
