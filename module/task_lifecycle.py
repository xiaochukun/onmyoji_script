"""Cooperative finishing at task boundaries without starting another battle."""
import threading


class TaskLifecycle:
    def init_lifecycle(self):
        self.finish_requested=threading.Event()
        self.cancel_requested=threading.Event()
        self.finish_reason=None

    def request_finish(self):
        self.finish_requested.set()

    def finish_if_ready(self):
        if self.cancel_requested.is_set():
            self.running=False;self.finish_reason="cancelled"
            return True
        busy=getattr(self,"in_battle",False) or getattr(self,"attempt_active",False)
        if self.finish_requested.is_set() and not busy:
            self.running=False;self.finish_reason="time_limit"
            return True
        return False
