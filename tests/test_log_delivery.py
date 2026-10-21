import threading
import unittest
from unittest.mock import Mock
from module.base_clicker import install_log_queue, safe_log

class LogDeliveryTests(unittest.TestCase):
    def test_worker_never_calls_tk_and_main_thread_drains(self):
        widget=Mock()
        install_log_queue(widget)
        drain=widget.after.call_args.args[1]
        widget.reset_mock()
        worker=threading.Thread(target=lambda:safe_log(widget,"点击 img_4.jpg"))
        worker.start();worker.join(1)
        self.assertFalse(worker.is_alive())
        widget.after.assert_not_called();widget.insert.assert_not_called()
        drain()
        self.assertIn("点击 img_4.jpg",widget.insert.call_args.args[1])
