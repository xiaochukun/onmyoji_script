import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from module import settings_store as store


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch_root = patch.object(store, "ROOT", self.root)
        self.patch_preferences = patch.object(store, "PREFERENCES", self.root / "settings.local.json")
        self.patch_root.start(); self.patch_preferences.start()
        self.addCleanup(self.patch_root.stop); self.addCleanup(self.patch_preferences.stop)

    def test_preferences_are_independent_by_port(self):
        store.save_resolution("7555", 1280, 720)
        store.save_resolution("5555", 1920, 1080)
        self.assertEqual(store.get_resolution("7555"), (1280, 720))
        self.assertEqual(store.get_resolution("5555"), (1920, 1080))
        self.assertEqual(store.get_resolution("7777"), (1600, 900))

    def test_invalid_values_are_rejected(self):
        for port in ("", "a", "0", "65536", "7555;echo"):
            with self.assertRaises(ValueError): store.validate_port(port)
        for value in ("nan", "inf", "-0.1", "abc"):
            with self.assertRaises(ValueError): store.validate_thresholds({"img_1": value})
        with self.assertRaises(ValueError): store.validate_thresholds({"sleep_time": 0})
        with self.assertRaises(ValueError): store.validate_resolution(0, 720)
        self.assertEqual(store.validate_thresholds({"img_3": 10})["img_3"],10)

    def test_threshold_file_roundtrip_preserves_comments_and_other_keys(self):
        path = store.threshold_path("tansuo")
        path.parent.mkdir(parents=True)
        path.write_text("# existing comment\nimg_1=0.4\nsleep_time:2\ncustom:0.6\n", encoding="utf-8")
        data = store.read_thresholds("tansuo")
        data["img_1"] = .85; data["sleep_time"] = .5
        store.save_thresholds("tansuo", data)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# existing comment", text)
        self.assertIn("img_1:0.85", text)
        self.assertIn("custom:0.6", text)
        self.assertEqual(store.read_thresholds("tansuo")["sleep_time"], .5)

    def test_failed_validation_does_not_modify_file(self):
        path=store.threshold_path("tupo"); path.parent.mkdir(parents=True)
        path.write_text("img_1:0.6\n",encoding="utf-8")
        with self.assertRaises(ValueError):store.save_thresholds("tupo",{"img_1":"nan"})
        self.assertEqual(path.read_text(encoding="utf-8"),"img_1:0.6\n")

    def test_resolution_applies_rotated_raw_axes_and_verifies(self):
        previous={"raw_size":(900,1600),"display_size":(1600,900),"override":None}
        with patch.object(store,"inspect_resolution",return_value=previous), patch.object(store,"adb_command") as command, patch.object(store,"screenshot_size",return_value=(1280,720)), patch.object(store.time,"sleep"):
            self.assertEqual(store.apply_resolution("7555",1280,720),(1280,720))
            command.assert_called_once_with("7555","shell","wm","size","720x1280")
        self.assertEqual(store.get_resolution("7555"),(1280,720))

    def test_failed_resolution_restores_previous_override(self):
        previous={"raw_size":(1600,900),"display_size":(1600,900),"override":(1600,900)}
        with patch.object(store,"inspect_resolution",return_value=previous), patch.object(store,"adb_command") as command, patch.object(store,"screenshot_size",return_value=(900,1280)), patch.object(store.time,"sleep"):
            with self.assertRaises(RuntimeError):store.apply_resolution("7555",1280,720)
            self.assertEqual(command.call_args_list[-1].args,("7555","shell","wm","size","1600x900"))
        self.assertFalse(store.PREFERENCES.exists())


if __name__ == "__main__": unittest.main()
