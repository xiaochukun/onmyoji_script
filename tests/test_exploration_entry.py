import time
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.tansuo_clicker import AutoClicker


class ExplorationEntryTests(unittest.TestCase):
    def setUp(self):
        b=AutoClicker.__new__(AutoClicker)
        b.name="test";b.log=Mock();b.running=True;b.in_battle=False
        b.no_target_count=0;b.recent_clicks=[];b.thresholds={}
        b.reset_entry_state()
        b.is_mainline_page=Mock(return_value=True)
        b.tap_by_loc=Mock(return_value=True)
        b.scroll_chapters=Mock()
        b.find_entry_template=Mock(return_value=((1335,575),(130,30)))
        self.bot=b
        self.screen=np.zeros((900,1600),np.uint8)

    def test_chapter_then_explore_then_fresh_frames(self):
        b=self.bot
        self.assertTrue(b.handle_chapter_entry(self.screen))
        self.assertEqual(b.entry_phase,"enter_exploration")
        self.assertIn("img_11.jpg",b.tap_by_loc.call_args.kwargs["image_name"])
        self.assertTrue(b.handle_chapter_entry(self.screen))
        self.assertEqual(b.entry_phase,"wait_map")
        self.assertIn("img_2.jpg",b.tap_by_loc.call_args.kwargs["image_name"])
        b.is_mainline_page.return_value=False
        self.assertTrue(b.handle_chapter_entry(self.screen))
        self.assertFalse(b.handle_chapter_entry(self.screen))
        self.assertEqual(b.entry_phase,"active")
        b.scroll_chapters.assert_not_called()

    def test_run_enters_chapter_then_executes_original_battle_cycle(self):
        b=self.bot;b.init_lifecycle()
        import threading
        b.task_ready=threading.Event()
        b.templates={name:np.zeros((5,5),np.uint8) for name in ("img_11","img_2","mainline_page")}
        b.connect_device=Mock();b.capture_screenshot=Mock(return_value=True)
        b.screenshot_path="unused";b.sleep_time=0
        b.is_mainline_page.side_effect=[True,True,False,False,False]
        b.match_template=Mock(side_effect=[("img_4",.99,(0,0),(5,5)),("img_3",.99,(0,0),(5,5))])
        def clicked(name):
            if name=="img_3":b.running=False
        b.check_repeated_clicks=clicked
        with patch("module.tansuo_clicker.np.fromfile",return_value=np.zeros(5,np.uint8)), patch("module.tansuo_clicker.cv2.imdecode",return_value=self.screen), patch("module.tansuo_clicker.time.sleep"):
            b.run()
        names=[call.kwargs["image_name"] for call in b.tap_by_loc.call_args_list]
        self.assertIn("img_11.jpg",names[0]);self.assertIn("img_2.jpg",names[1])
        self.assertEqual(names[2:],["img_4.jpg","img_3.jpg"])
        self.assertTrue(b.task_ready.is_set());self.assertFalse(b.in_battle)
        self.assertTrue(any("原探索逻辑" in c.args[0] for c in b.log.call_args_list))

    def test_chapter_disappears_then_old_loop_clicks_explore_and_fights(self):
        b=self.bot;b.init_lifecycle()
        import threading
        b.task_ready=threading.Event()
        b.templates={name:np.zeros((5,5),np.uint8) for name in ("img_11","img_2","mainline_page")}
        b.connect_device=Mock();b.capture_screenshot=Mock(return_value=True)
        b.screenshot_path="unused";b.sleep_time=0
        b.is_mainline_page.side_effect=[True,False,False,False]
        b.match_template=Mock(side_effect=[(name,.99,(0,0),(5,5)) for name in ("img_2","img_4","img_3")])
        b.check_repeated_clicks=lambda name:setattr(b,"running",False) if name=="img_3" else None
        with patch("module.tansuo_clicker.np.fromfile",return_value=np.zeros(5,np.uint8)), patch("module.tansuo_clicker.cv2.imdecode",return_value=self.screen), patch("module.tansuo_clicker.time.sleep"):
            b.run()
        names=[call.kwargs["image_name"] for call in b.tap_by_loc.call_args_list]
        self.assertIn("img_11.jpg",names[0])
        self.assertEqual(names[1:],["img_2.jpg","img_4.jpg","img_3.jpg"])
        self.assertEqual(b.entry_phase,"active")
        self.assertFalse(b.in_battle)

    def test_chapter_marker_disappearance_hands_off_before_entry_timeout(self):
        b=self.bot;b.entry_phase="enter_exploration"
        b.entry_started=time.monotonic()-46
        b.is_mainline_page.return_value=False
        self.assertFalse(b.handle_chapter_entry(self.screen))
        self.assertTrue(b.running)
        self.assertEqual(b.entry_phase,"active")
        b.find_entry_template.assert_not_called()

    def test_resume_verified_map_skips_chapter_navigation(self):
        b=self.bot;b.is_mainline_page.return_value=False
        self.assertFalse(b.handle_chapter_entry(self.screen))
        self.assertEqual(b.entry_phase,"active")
        b.tap_by_loc.assert_not_called()

    def test_entry_button_at_bottom_uses_configured_threshold(self):
        b=self.bot;b.entry_phase="enter_exploration"
        b.thresholds={"img_2":.4}
        b.handle_chapter_entry(self.screen)
        args=b.find_entry_template.call_args.args
        self.assertEqual(args[2],.4)
        self.assertEqual(args[3][3],self.screen.shape[0])
        self.assertEqual(b.entry_phase,"wait_map")
        self.assertTrue(any("最高分" in call.args[0] for call in b.log.call_args_list))

    def test_unmatched_entry_keeps_waiting_and_reports_score(self):
        b=self.bot;b.entry_phase="enter_exploration"
        b.find_entry_template.return_value=None
        b.entry_match_scores={"img_2":.35}
        b.entry_last_click=time.monotonic()
        self.assertTrue(b.handle_chapter_entry(self.screen))
        b.tap_by_loc.assert_not_called()
        self.assertTrue(any("0.350" in call.args[0] for call in b.log.call_args_list))

    def test_list_search_stops_at_unchanged_bottom(self):
        b=self.bot;b.find_entry_template.return_value=None
        for _ in range(3):b.handle_chapter_entry(self.screen)
        self.assertFalse(b.running)
        self.assertEqual(b.scroll_chapters.call_count,2)
        b.tap_by_loc.assert_not_called()

    def test_unknown_page_never_scrolls(self):
        b=self.bot;b.is_mainline_page.return_value=False
        b.find_entry_template.return_value=None
        self.assertTrue(b.handle_chapter_entry(self.screen))
        b.scroll_chapters.assert_not_called();b.tap_by_loc.assert_not_called()
        self.assertEqual(b.no_target_count,0)

    def test_battle_keeps_original_flow(self):
        b=self.bot;b.in_battle=True
        self.assertFalse(b.handle_chapter_entry(self.screen))
        b.is_mainline_page.assert_not_called()

    def test_return_to_mainline_restarts_entry(self):
        b=self.bot;b.entry_phase="active";b.no_target_count=2
        self.assertTrue(b.handle_chapter_entry(self.screen))
        self.assertEqual(b.entry_phase,"enter_exploration")
        self.assertEqual(b.no_target_count,0)

    def test_entry_timeout_stops_without_click(self):
        b=self.bot;b.entry_phase="enter_exploration"
        b.entry_started=time.monotonic()-46
        b.handle_chapter_entry(self.screen)
        self.assertFalse(b.running)
        b.tap_by_loc.assert_not_called()

    def test_entry_templates_excluded_from_combat_matching(self):
        b=self.bot
        b.templates={key:np.zeros((5,5),np.uint8) for key in ("img_4","img_11","mainline_page")}
        b._match_score=Mock(side_effect=lambda name,*args:(name,.95,(0,0),(5,5)))
        self.assertEqual(b.match_template(self.screen)[0],"img_4")
        self.assertEqual([c.args[0] for c in b._match_score.call_args_list],["img_4"])

    def test_scaled_chapter_template(self):
        b=self.bot
        template=np.random.default_rng(9).integers(0,255,(40,174),dtype=np.uint8)
        scaled=cv2.resize(template,(130,30))
        screen=np.zeros((200,300),np.uint8);screen[100:130,50:180]=scaled
        b.templates={"img_11":template}
        result=AutoClicker.find_entry_template(b,"img_11",screen,.85)
        self.assertEqual(result,((50,100),(130,30)))


if __name__=="__main__":unittest.main()
