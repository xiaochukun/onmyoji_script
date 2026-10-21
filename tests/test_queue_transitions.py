import threading
import time
import unittest
from unittest.mock import Mock, patch

from module.queue_runner import QueueRunner
from module.scene_navigation import SceneNavigator
from module.task_lifecycle import TaskLifecycle


class NavigationTests(unittest.TestCase):
    def make_nav(self):
        nav=SceneNavigator("7555",threading.Event(),Mock())
        nav.connect=Mock()
        nav.mainline=lambda frame:frame=="main"
        nav.raid_page=lambda frame:frame=="raid"
        nav.raid_ready=lambda frame,scene:frame=="raid"
        nav.click=Mock()
        return nav

    def test_return_uses_pink_close_then_confirms_mainline(self):
        nav=self.make_nav()
        nav.screenshot=Mock(side_effect=["raid","main","main"])
        nav.find=lambda name,frame,*args,**kwargs:(100,20) if name=="raid_close" and frame=="raid" else None
        with patch.object(nav.cancel,"wait",return_value=False):
            self.assertTrue(nav.ensure_mainline("tupo"))
        self.assertIn("粉红色",nav.click.call_args.args[0])
        self.assertEqual(nav.screenshot.call_count,3)

    def test_enter_from_mainline_clicks_icon_before_starting(self):
        nav=self.make_nav()
        nav.screenshot=Mock(side_effect=["main","main","main","main","raid","raid"])
        nav.find=lambda name,*args,**kwargs:(350,830) if name=="raid_entry" else None
        with patch.object(nav.cancel,"wait",return_value=False):
            self.assertTrue(nav.prepare("tupo","tansuo"))
        nav.click.assert_called_once_with("raid_entry.png",(350,830))
        self.assertEqual(nav.screenshot.call_count,5)

    def test_personal_img1_is_sufficient_without_title_or_tab(self):
        nav=SceneNavigator("7555",threading.Event(),Mock())
        nav.find=Mock(side_effect=lambda name,*args,**kwargs:(10,20) if name=="raid_medals" else None)
        nav.raid_page=Mock(return_value=False)
        nav.mainline=Mock(return_value=False)
        with patch("module.scene_navigation.read_thresholds",return_value={"img_1":.63}):
            self.assertTrue(nav.raid_ready("frame","tupo"))
        nav.find.assert_called_once_with("raid_medals","frame",threshold=.63)
        nav.raid_page.assert_not_called()

    def test_personal_ready_starts_without_returning_to_mainline(self):
        nav=self.make_nav();nav.screenshot=Mock(return_value="raid")
        nav.ensure_mainline=Mock()
        self.assertTrue(nav.prepare("tupo"))
        nav.ensure_mainline.assert_not_called()
        nav.click.assert_not_called()
        self.assertEqual(nav.screenshot.call_count,1)

    def test_guild_does_not_use_personal_img1(self):
        nav=SceneNavigator("7555",threading.Event(),Mock())
        nav.find=Mock(return_value=None);nav.raid_page=Mock(return_value=False);nav.mainline=Mock(return_value=False)
        self.assertFalse(nav.raid_ready("frame","liaotupo"))
        nav.find.assert_not_called()

    def test_switch_finishes_result_then_closes_raid_and_confirms_mainline(self):
        nav=self.make_nav()
        nav.screenshot=Mock(side_effect=["result","raid","main","main"])
        nav.find=lambda name,frame,*args,**kwargs: (50,60) if (name,frame) in (("tupo/img_3","result"),("raid_close","raid")) else None
        with patch.object(nav.cancel,"wait",return_value=False), patch("module.scene_navigation.time.monotonic",side_effect=range(0,100,2)):
            self.assertTrue(nav.ensure_mainline("tupo"))
        actions=[c.args[0] for c in nav.click.call_args_list]
        self.assertIn("tupo/img_3.jpg",actions[0])
        self.assertIn("粉红色",actions[1])
        self.assertEqual(len(actions),2)

    def test_settlement_images_are_scene_specific_and_exclude_battle_entry(self):
        nav=self.make_nav();seen=[]
        def find(name,*args,**kwargs):
            seen.append(name)
            return (10,20) if name=="tupo/img_7" else None
        nav.find=find
        action=nav.settlement_action("result","tupo")
        self.assertIn("tupo/img_7.jpg",action[0])
        self.assertTrue(all(name.startswith("tupo/") for name in seen))
        self.assertNotIn("tupo/img_1",seen);self.assertNotIn("tupo/img_2",seen)

    def test_exit_confirmation_wins_over_false_settlement_match(self):
        nav=self.make_nav()
        nav.screenshot=Mock(side_effect=["dialog","main","main"])
        nav.find=lambda name,frame,*args,**kwargs:(966,505) if (name,frame)==("confirm","dialog") else None
        nav.settlement_action=Mock(return_value=("false img_3",(1295,761)))
        with patch.object(nav.cancel,"wait",return_value=False):
            self.assertTrue(nav.ensure_mainline("tansuo"))
        nav.settlement_action.assert_not_called()
        self.assertIn("确认退出探索",nav.click.call_args.args[0])

    def test_map_back_then_confirm_then_mainline(self):
        nav=self.make_nav();nav.screenshot=Mock(side_effect=["map","dialog","main","main"])
        nav.find=lambda name,frame,*args,**kwargs:(100,50) if (name,frame) in (("explore_back","map"),("confirm","dialog")) else None
        with patch.object(nav.cancel,"wait",return_value=False), patch("module.scene_navigation.time.monotonic",side_effect=range(0,100,2)):
            self.assertTrue(nav.ensure_mainline("tansuo"))
        self.assertIn("img_8.jpg",nav.click.call_args_list[0].args[0])
        self.assertIn("img_9.jpg",nav.click.call_args_list[1].args[0])

    def test_mainline_never_counts_as_ready_even_if_img1_matches(self):
        nav=self.make_nav();nav.mainline=Mock(return_value=True)
        nav.find=Mock(return_value=(10,20))
        self.assertFalse(SceneNavigator.raid_ready(nav,"main","tupo"))
        nav.find.assert_not_called()

    def test_navigation_timeout_never_claims_success(self):
        nav=self.make_nav()
        with self.assertRaises(RuntimeError):nav.ensure_mainline("tupo",timeout=0)
        nav.click.assert_not_called()

    def test_cancel_prevents_clicks(self):
        nav=self.make_nav();nav.cancel.set()
        self.assertFalse(nav.ensure_mainline("tupo"))
        nav.click.assert_not_called()


class QueueTests(unittest.TestCase):
    def test_exploration_then_no_ticket_then_exploration(self):
        events=[];active=[];created=[]
        class FakeBot(TaskLifecycle):
            def __init__(self,scene,**kwargs):
                self.scene=scene;self.running=False;self.init_lifecycle()
                self.in_battle=False
                created.append(self)
            def run(self):
                self.running=True;active.append(self.scene)
                if len(active)>1:raise AssertionError("Overlapping device owners")
                events.append(("start",self.scene))
                try:
                    if self.scene=="tupo":
                        self.finish_reason="no_ticket";self.running=False;return
                    self.in_battle=True
                    began=time.monotonic()
                    while time.monotonic()-began<.16:
                        if self.cancel_requested.is_set():break
                        time.sleep(.003)
                    self.in_battle=False
                    while not self.finish_if_ready():time.sleep(.003)
                finally:
                    active.remove(self.scene);events.append(("end",self.scene))
            def stop(self):
                self.cancel_requested.set();self.running=False
        class Navigator:
            def __init__(self,*args):pass
            def prepare(self,target,source):
                if active:raise AssertionError("Navigation while previous bot still running")
                events.append(("prepare",target));return True
            def ensure_mainline(self,source):
                if active:raise AssertionError("Closing page during battle")
                events.append(("main",source));return True
        factories={scene:(lambda s=scene,**kwargs:FakeBot(s,**kwargs)) for scene in ("tansuo","tupo")}
        with patch("module.queue_runner.SceneNavigator",Navigator),patch.dict("module.queue_runner.SCENE_BUILDERS",factories):
            runner=QueueRunner("7555",[("tansuo",.001,0),("tupo",0,3),("tansuo",.001,0)],threading.Event(),Mock())
            runner.start();runner.thread.join(3)
        self.assertFalse(runner.thread.is_alive())
        self.assertEqual([event for event in events if event[0]=="prepare"],[("prepare","tansuo"),("prepare","tupo"),("prepare","tansuo")])
        self.assertEqual([bot.finish_reason for bot in created],["time_limit","no_ticket","time_limit"])
        self.assertEqual(events.index(("main","tansuo"))+1,events.index(("prepare","tupo")))
        self.assertFalse(any(bot.cancel_requested.is_set() for bot in created))

    def test_navigation_failure_does_not_start_next_bot(self):
        navigator=Mock();navigator.prepare.side_effect=RuntimeError("missing mainline")
        builder=Mock()
        with patch("module.queue_runner.SceneNavigator",return_value=navigator),patch.dict("module.queue_runner.SCENE_BUILDERS",{"tansuo":builder}):
            runner=QueueRunner("7555",[("tansuo",1,0)],threading.Event(),Mock())
            runner.run()
        builder.assert_not_called()

    def test_finish_waits_for_current_battle(self):
        class Bot(TaskLifecycle):pass
        b=Bot();b.init_lifecycle();b.running=True;b.in_battle=True
        b.request_finish()
        self.assertFalse(b.finish_if_ready())
        b.in_battle=False
        self.assertTrue(b.finish_if_ready())
        self.assertEqual(b.finish_reason,"time_limit")


if __name__=="__main__":unittest.main()
