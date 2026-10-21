import subprocess
import time
import os
import json
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

import cv2

from module.base_clicker import AutoClicker as BaseAutoClicker


class AutoClicker(BaseAutoClicker):
    """Ordered breakthrough clicks with an alternative completion screen."""

    def __init__(self, log_fn, scene_name, adb_port, thresholds=None, ticket_limit=0, check_ticket=True):
        super().__init__(log_fn, scene_name, adb_port, thresholds)
        self.step = "img_1"
        self.img1_count = 0
        self.check_ticket = check_ticket
        self.scene_label = "寮突破" if scene_name == "liaotupo" else "结界突破"
        self.limit_label = "突破券" if check_ticket else "执行次数"
        self.ticket_zero_template = cv2.imread(
            os.path.join(self.image_dir, "ticket_zero.png"),
            cv2.IMREAD_GRAYSCALE
        ) if self.check_ticket else None

        if not isinstance(ticket_limit, int) or ticket_limit < 0:
            raise ValueError("ticket_limit must be a non-negative integer")
        self.ticket_limit = ticket_limit
        self.completed_count = 0
        self.attempt_active = False
        self.ui_log = self.log
        self.session_lock = threading.RLock()
        self.session_path = None
        self.award_templates = {}
        self.award_counts = {}
        self.visible_awards = set()
        self.log = self.session_log

    def write_session_event(self, event, **data):
        with self.session_lock:
            if self.session_path is None:
                return
            record = {"time": datetime.now().isoformat(timespec="milliseconds"),
                      "port": str(self.adb_port), "event": event, **data}
            try:
                with self.session_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as e:
                self.ui_log(f"日志写入失败: {e}")

    def session_log(self, message):
        self.ui_log(message)
        self.write_session_event("message", message=message)

    def start_award_session(self):
        self.award_templates = {}
        self.award_counts = {}
        self.visible_awards = set()
        log_dir = Path(self.image_dir) / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        port = "".join(c if c.isalnum() else "_" for c in str(self.adb_port))
        self.session_path = log_dir / f"{self.scene_name}_{stamp}_{port}_{uuid4().hex[:8]}.jsonl"
        self.session_path.touch(exist_ok=False)
        self.write_session_event("start", ticket_limit=self.ticket_limit)
        award_dir = Path(self.image_dir) / "award"
        if award_dir.is_dir():
            for path in sorted(award_dir.iterdir()):
                if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                    continue
                try:
                    template = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                    if template is None:
                        raise ValueError("Unreadable image")
                    self.award_templates[path.name] = template
                    self.award_counts[path.name] = 0
                except Exception as e:
                    self.log(f"奖励模板读取失败 {path.name}: {e}")
        self.log(f"奖励统计开始，模板 {len(self.award_templates)} 张，日志: {self.session_path}")
        self.write_session_event("counts", counts=dict(self.award_counts))

    def recognize_awards(self, screenshot):
        visible = set()
        for name, template in self.award_templates.items():
            try:
                if template.shape[0] > screenshot.shape[0] or template.shape[1] > screenshot.shape[1]:
                    continue
                _, score, loc, _ = self.match_template_score(name, template, screenshot)
                threshold = self.thresholds.get(f"award_{Path(name).stem}", self.thresholds.get("award", 0.85))
                if score < threshold:
                    continue
                visible.add(name)
                if name not in self.visible_awards:
                    self.award_counts[name] += 1
                    self.write_session_event("award", image=name, score=float(score),
                                             location=list(loc), count=self.award_counts[name],
                                             counts=dict(self.award_counts))
                    self.log(f"奖励 {name} +1，本次累计 {self.award_counts[name]}")
            except Exception as e:
                # Keep the previous visibility on errors to avoid a duplicate count.
                if name in self.visible_awards:
                    visible.add(name)
                self.log(f"奖励识别失败 {name}: {e}")
        self.visible_awards = visible

    def run(self):
        try:
            self.start_award_session()
            self._run_breakthrough()
        except Exception as e:
            self.finish_reason = "error"
            self.log(f"突破任务异常: {e}")
        finally:
            self.running = False
            self.log(f"本次奖励统计: {self.award_counts}")
            with self.session_lock:
                self.write_session_event("end", counts=dict(self.award_counts),
                                         completed_count=self.completed_count)
                self.session_path = None

    def has_breakthrough_ticket(self, screenshot):
        """Return True/False for tickets available, or None when unreadable."""
        if not self.check_ticket:
            return True
        icon = self.templates.get("img_9")
        if icon is None or self.ticket_zero_template is None:
            self.log("突破券检测模板缺失: img_9.jpg / ticket_zero.png")
            return None

        try:
            _, icon_score, icon_loc, _ = self.match_template_score(
                "img_9", icon, screenshot
            )
        except Exception as e:
            self.log(f"突破券图标检测失败: {e}")
            return None

        icon_threshold = self.thresholds.get("img_9", 0.2)
        if icon_score < icon_threshold:
            self.log(
                f"等待突破券计数区域: img_9.jpg 分数 "
                f"{icon_score:.3f}/{icon_threshold}"
            )
            return None

        # At 1600x900 the numerator is immediately to the right of img_9.
        # Use offsets from the matched icon so minor window movement is harmless.
        x, y = icon_loc
        left, top = x + 57, y + 4
        right, bottom = x + 137, y + 64
        left, top = max(0, left), max(0, top)
        right = min(screenshot.shape[1], right)
        bottom = min(screenshot.shape[0], bottom)
        counter_roi = screenshot[top:bottom, left:right]

        zh, zw = self.ticket_zero_template.shape
        if counter_roi.shape[0] < zh or counter_roi.shape[1] < zw:
            self.log("突破券计数区域超出截图范围")
            return None

        result = cv2.matchTemplate(
            counter_roi, self.ticket_zero_template, cv2.TM_CCOEFF_NORMED
        )
        _, zero_score, _, _ = cv2.minMaxLoc(result)
        zero_threshold = self.thresholds.get("ticket_zero", 0.8)
        if zero_score >= zero_threshold:
            self.log(f"检测到突破券数量为 0（分数 {zero_score:.3f}），停止突破")
            return False

        self.log(f"检测到突破券仍有剩余（0 模板分数 {zero_score:.3f}），继续突破")
        return True

    def check_cycle_restart(self, screenshot):
        template = self.templates.get("img_1")
        if template is None:
            self.img1_count = 0
            return
        try:
            result = self.match_template_score("img_1", template, screenshot)
            matched = result[1] >= self.thresholds.get("img_1", 0.4)
        except Exception:
            matched = False
        self.img1_count = self.img1_count + 1 if matched else 0
        if self.img1_count >= 3:
            self.step = "img_1"
            self.img1_count = 0
            self.attempt_active = False
            self.recent_clicks.clear()
            self.log("连续3次识别到 img_1.jpg，重新开始突破循环")

    def match_current_step(self, screenshot):
        # img_7 completes the cycle just like img_3, after img_2 was clicked.
        names = ("img_7", self.step) if self.step in ("img_4", "img_3") else (self.step,)
        for name in names:
            template = self.templates.get(name)
            if template is None:
                continue
            try:
                result = self.match_template_score(name, template, screenshot)
                threshold = self.thresholds.get(name, 0.4)
                self.log(f"[{name}.jpg] 匹配分数: {result[1]:.3f} (阈值 {threshold})")
                if result[1] >= threshold:
                    return result
            except Exception as e:
                self.log(f"{name}.jpg 匹配失败: {e}")
        return None

    def click_target(self, name, loc, size, screenshot):
        if self.cancel_requested.is_set() or not self.running:
            return False
        if name == "img_2" and self.finish_requested.is_set():
            return False
        w, h = size
        x = int((loc[0] + w // 2) * self.mumu_width / screenshot.shape[1])
        y = int((loc[1] + h // 2) * self.mumu_height / screenshot.shape[0])
        try:
            subprocess.run(
                [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                 "shell", "input", "tap", str(x), str(y)],
                capture_output=True, text=True, check=True, timeout=15
            )
        except Exception as e:
            self.log(f"点击 {name}.jpg 失败 ({x}, {y}): {e}")
            return False
        self.log(f"点击 {name}.jpg ({x}, {y})")
        return True

    def advance_step(self, name):
        self.img1_count = 0
        if name == "img_2":
            self.attempt_active = True
        elif name in ("img_3", "img_7") and self.attempt_active:
            self.attempt_active = False
            self.completed_count += 1
            if self.ticket_limit:
                remaining = max(0, self.ticket_limit - self.completed_count)
                self.log(f"突破已执行 {self.completed_count}/{self.ticket_limit}，剩余额度 {remaining}")
                if self.completed_count >= self.ticket_limit:
                    self.running = False
                    self.finish_reason = "quota"
                    self.log(f"{self.limit_label}额度已用完，任务自动停止")
            else:
                self.log(f"突破已执行 {self.completed_count}次（无限制）")
        self.step = {
            "img_1": "img_2", "img_2": "img_4", "img_4": "img_3",
            "img_3": "img_1", "img_7": "img_1"
        }[name]

    def _run_breakthrough(self):
        self.running = True
        self.step = "img_1"
        self.recent_clicks = []
        self.img1_count = 0
        self.completed_count = 0
        self.attempt_active = False
        self.log(f"{self.scene_label} · {self.limit_label}额度: {self.ticket_limit if self.ticket_limit else '无限制'}")
        required = ("img_1", "img_2", "img_4", "img_3", "img_7")
        if self.check_ticket:
            required += ("img_9",)
        missing = [f"{name}.jpg" for name in required if name not in self.templates]
        if self.check_ticket and self.ticket_zero_template is None:
            missing.append("ticket_zero.png")
        if missing:
            self.finish_reason = "missing_templates"
            self.log("突破模板缺失: " + ", ".join(missing))
            self.running = False
            return
        self.log(f"{self.scene_label}启动: img_1 -> img_2 -> img_4 -> img_3 / img_7")
        if self.finish_if_ready():
            return
        self.connect_device()
        while self.running:
            if self.finish_if_ready():
                break
            if not self.capture_screenshot():
                time.sleep(2)
                continue
            screenshot = cv2.imread(self.template_paths["screenshot"], cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                time.sleep(1)
                continue
            # Ticket exhaustion terminates every stage, including a stale battle state.
            if self.check_ticket:
                has_ticket = self.has_breakthrough_ticket(screenshot)
                if has_ticket is False:
                    self.finish_reason = "no_ticket"
                    self.running = False
                    self.log("突破券为 0，立即结束当前突破任务，跳过后续识别和点击")
                    break
                if has_ticket is None and self.step == "img_1" and not self.attempt_active:
                    time.sleep(self.sleep_time)
                    continue
            self.recognize_awards(screenshot)
            if not self.finish_requested.is_set():
                self.check_cycle_restart(screenshot)
            match = self.match_current_step(screenshot)
            if not self.running:
                break
            if match:
                name, score, loc, size = match
                if self.click_target(name, loc, size, screenshot):
                    self.advance_step(name)
                    self.check_repeated_clicks(name)
            else:
                self.log(f"等待 {self.step}.jpg" + (" / img_7.jpg" if self.step in ("img_4", "img_3") else ""))
            time.sleep(self.sleep_time)
