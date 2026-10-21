"""Each device owns its complete sequence, including all intermediate pages."""
import threading
import time
from module.scene_navigation import SceneNavigator
from module.scenes import SCENE_BUILDERS


class QueueRunner:
    def __init__(self,port,tasks,cancel,log,on_bot=None):
        self.port=port;self.tasks=tuple(tasks);self.cancel=cancel;self.log=log
        self.on_bot=on_bot or (lambda bot:None)
        self.bot=None;self.bot_thread=None
        self.navigator=SceneNavigator(port,cancel,log)
        self.thread=threading.Thread(target=self.run,daemon=True)

    def start(self):self.thread.start()

    def stop(self):
        if self.bot is not None:self.bot.stop()

    def run(self):
        source=None
        try:
            for index,(scene,minutes,tickets) in enumerate(self.tasks,1):
                if self.cancel.is_set():return
                self.log(f"队列 {index}/{len(self.tasks)}：准备切换到 {scene}")
                if not self.navigator.prepare(scene,source):return
                if self.cancel.is_set():return
                self.bot=SCENE_BUILDERS[scene](log_fn=self.log,port=self.port,
                    **({"ticket_limit":tickets} if scene in ("tupo","liaotupo") else {}))
                self.on_bot(self.bot)
                if self.cancel.is_set():self.bot.stop();return
                errors=[]
                def execute(bot=self.bot):
                    try:bot.run()
                    except Exception as exc:errors.append(str(exc))
                self.bot_thread=threading.Thread(target=execute,daemon=True)
                self.bot_thread.start()
                launched=time.monotonic();started=None;finishing_at=None
                self.log(f"任务开始: {scene}，"+(f"{minutes} 分钟" if minutes else "不限时长"))
                while self.bot_thread.is_alive():
                    ready = getattr(self.bot, "task_ready", None)
                    if started is None and (ready is None or ready.is_set()):
                        started=time.monotonic()
                        self.log(f"{scene} 入场完成，开始执行任务并计时")
                    if started is None and time.monotonic()-launched>90:
                        self.bot.stop()
                        raise RuntimeError(f"{scene} 入场超过90秒，未开始玩法逻辑")
                    if self.cancel.is_set():self.bot.stop()
                    elif minutes and started is not None and time.monotonic()-started>=minutes*60 and finishing_at is None:
                        self.bot.request_finish();finishing_at=time.monotonic()
                        self.log("任务计时结束，停止发起新战斗，等待当前战斗结算")
                    if finishing_at is not None and time.monotonic()-finishing_at>180:
                        self.bot.stop()
                        raise RuntimeError("等待战斗结算超过 180 秒，停止队列；请检查游戏页面")
                    self.bot_thread.join(.1)
                if self.cancel.is_set():return
                if errors:raise RuntimeError(errors[0])
                reason=getattr(self.bot,"finish_reason",None)
                if reason not in ("time_limit","quota","no_ticket"):
                    raise RuntimeError(f"{scene} 非正常结束 ({reason or '未说明原因'})，不继续操作下一任务")
                self.log(f"任务结束: {scene} ({reason})")
                # Completion includes returning to mainline, even for the last item.
                if scene in ("tansuo","tupo","liaotupo"):
                    if not self.navigator.ensure_mainline(scene):return
                source=scene
            self.log("任务队列执行完毕，已返回主线页面")
        except InterruptedError:
            self.log("任务队列已停止")
        except Exception as exc:
            self.log(f"队列停止: {exc}")
        finally:
            if self.bot_thread is not None and self.bot_thread.is_alive():
                self.bot.stop()
                self.bot_thread.join()
            self.on_bot(None)
