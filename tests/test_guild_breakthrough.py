import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import cv2
import numpy as np

from module.tupo_clicker import AutoClicker
from module.scenes import SCENE_BUILDERS
from module.settings_store import read_thresholds


class GuildBreakthroughTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.images=self.root/"yys"/"liaotupo"
        self.images.mkdir(parents=True)
        frame=np.random.default_rng(2).integers(0,255,(30,40),dtype=np.uint8)
        for name in ("img_1","img_2","img_3","img_4","img_7"):
            cv2.imencode(".jpg",frame[:10,:10])[1].tofile(str(self.images/(name+".jpg")))
        cv2.imencode(".png",frame)[1].tofile(str(self.images/"liaotupo_screenshot_7555.png"))
        self.logs=[]

    def make_bot(self,check_ticket=False,limit=0):
        with patch("module.base_clicker.os.getcwd",return_value=str(self.root)):
            bot=AutoClicker(self.logs.append,"liaotupo","7555",ticket_limit=limit,check_ticket=check_ticket)
        return bot

    def test_guild_runs_full_cycle_and_alternative_without_ticket_detection(self):
        bot=self.make_bot(limit=2)
        bot.has_breakthrough_ticket=Mock(side_effect=AssertionError("Guild must not detect tickets"))
        bot.connect_device=Mock()
        bot.capture_screenshot=lambda:True
        bot.check_cycle_restart=lambda screenshot:None
        bot.recognize_awards=lambda screenshot:None
        sequence=iter(["img_1","img_2","img_4","img_3","img_1","img_2","img_7"])
        bot.match_current_step=lambda screenshot:(next(sequence),.99,(0,0),(10,10))
        bot.click_target=Mock(return_value=True)
        with patch("module.tupo_clicker.time.sleep"):
            bot._run_breakthrough()
        self.assertEqual(bot.completed_count,2)
        self.assertFalse(bot.running)
        bot.has_breakthrough_ticket.assert_not_called()
        self.assertEqual([call.args[0] for call in bot.click_target.call_args_list],
                         ["img_1","img_2","img_4","img_3","img_1","img_2","img_7"])

    def test_personal_mode_still_requires_ticket_templates(self):
        bot=self.make_bot(check_ticket=True)
        bot.connect_device=Mock()
        bot._run_breakthrough()
        bot.connect_device.assert_not_called()
        self.assertFalse(bot.running)
        self.assertTrue(any("img_9.jpg" in message and "ticket_zero.png" in message for message in self.logs))

    def test_no_ticket_finishes_even_without_img1_match(self):
        frame=np.arange(100,dtype=np.uint8).reshape(10,10)
        cv2.imencode(".jpg",frame)[1].tofile(str(self.images/"img_9.jpg"))
        cv2.imencode(".png",frame)[1].tofile(str(self.images/"ticket_zero.png"))
        bot=self.make_bot(check_ticket=True,limit=3)
        bot.connect_device=Mock()
        bot.capture_screenshot=lambda:True
        bot.has_breakthrough_ticket=Mock(return_value=False)
        bot.match_current_step=Mock(side_effect=AssertionError("No ticket must finish before selecting opponent"))
        bot.recognize_awards=Mock()
        bot._run_breakthrough()
        self.assertEqual(bot.finish_reason,"no_ticket")
        self.assertFalse(bot.running)
        self.assertEqual(bot.completed_count,0)
        bot.match_current_step.assert_not_called()
        bot.recognize_awards.assert_not_called()

    def test_zero_ticket_stops_at_every_stage_without_any_action(self):
        frame=np.arange(100,dtype=np.uint8).reshape(10,10)
        for name in ("img_9.jpg","ticket_zero.png"):
            cv2.imencode(Path(name).suffix,frame)[1].tofile(str(self.images/name))
        for step in ("img_1","img_2","img_4","img_3"):
            with self.subTest(step=step):
                bot=self.make_bot(check_ticket=True)
                bot.connect_device=Mock()
                def capture():
                    bot.step=step;bot.attempt_active=True
                    return True
                bot.capture_screenshot=capture
                bot.has_breakthrough_ticket=Mock(return_value=False)
                bot.recognize_awards=Mock();bot.check_cycle_restart=Mock()
                bot.match_current_step=Mock();bot.click_target=Mock()
                bot._run_breakthrough()
                self.assertEqual(bot.finish_reason,"no_ticket")
                self.assertFalse(bot.running)
                for action in (bot.recognize_awards,bot.check_cycle_restart,bot.match_current_step,bot.click_target):
                    action.assert_not_called()

    def test_guild_missing_action_template_stops(self):
        (self.images/"img_4.jpg").unlink()
        bot=self.make_bot()
        bot.connect_device=Mock()
        bot._run_breakthrough()
        bot.connect_device.assert_not_called()
        self.assertTrue(any("img_4.jpg" in message for message in self.logs))

    def test_scene_registration_and_guild_thresholds(self):
        self.assertIn("liaotupo",SCENE_BUILDERS)
        with patch("module.settings_store.ROOT",self.root):
            values=read_thresholds("liaotupo")
        self.assertNotIn("ticket_zero",values)
        self.assertNotIn("img_9",values)
        self.assertIn("award",values)

    def test_zero_limit_remains_unlimited(self):
        bot=self.make_bot()
        bot.running=True
        for _ in range(3):
            for name in ("img_1","img_2","img_4","img_3"):
                bot.advance_step(name)
        self.assertTrue(bot.running)
        self.assertEqual(bot.completed_count,3)


if __name__=="__main__":unittest.main()
