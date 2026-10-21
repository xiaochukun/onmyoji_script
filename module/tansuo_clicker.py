from module.task_lifecycle import TaskLifecycle
from module.settings_store import get_resolution
import threading
import subprocess
import time
import os
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- 线程安全日志 ----------------
log_lock = threading.Lock()

def safe_log(log_widget, msg):
    """线程安全地打印到 Tkinter 文本框"""
    def append():
        with log_lock:
            log_widget.config(state='normal')
            log_widget.insert("end", f"{time.strftime('%H:%M:%S')} {msg}\n")
            log_widget.see("end")
            log_widget.config(state='disabled')
    try:
        log_widget.after(0, append)
    except RuntimeError:
        pass

# ---------------- 自动点击器 ----------------
class AutoClicker(TaskLifecycle):
    """探索专用自动点击器"""

    def __init__(self, log_fn, scene_name, adb_port, name=None, thresholds=None):
        """
        adb_port: 数字端口，例如 5555
        name: 日志显示名称，例如 tansuo-5555
        """
        self.log = log_fn
        self.scene_name = scene_name
        self.adb_port = adb_port
        self.name = name or f"{scene_name}-{adb_port}"
        self.running = False
        self.init_lifecycle()
        self.task_ready = threading.Event()
        self.thresholds = thresholds or {}

        self.image_dir = os.path.join(os.getcwd(), "yys", scene_name)
        self.adb_exe = os.path.join(os.getcwd(), "adb.exe")
        self.screenshot_path = os.path.join(
            self.image_dir, f"{scene_name}_screenshot_{adb_port}.png"
        )

        self.mumu_width, self.mumu_height = get_resolution(adb_port)
        self.sleep_time = 2

        self.templates = {}
        self.template_paths = {}
        self.load_templates()
        self.load_thresholds()

        self.recent_clicks = []
        self.battle_count = 0
        self.in_battle = False
        self.no_target_count = 0  # Consecutive misses for both img_4 and img_5
        self.reset_entry_state()

    # ---------------- 模板加载 ----------------
    def load_templates(self):
        for i in (*range(1, 10), 11):
            img_name = f"img_{i}"
            img_path = os.path.join(self.image_dir, f"{img_name}.jpg")
            if os.path.exists(img_path):
                self.template_paths[img_name] = img_path
                template_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    self.templates[img_name] = template_img
                else:
                    self.log(f"⚠️ [{self.name}] 图片 {img_name} 读取失败")

        marker_path = os.path.join(self.image_dir, "mainline_page.png")
        marker = cv2.imread(marker_path, cv2.IMREAD_GRAYSCALE)
        if marker is not None:
            self.templates["mainline_page"] = marker
            self.template_paths["mainline_page"] = marker_path

    # ---------------- 阈值加载 ----------------
    def load_thresholds(self):
        """加载阈值配置要求.txt"""
        threshold_file = os.path.join(self.image_dir, "阈值配置要求.txt")
        if os.path.exists(threshold_file):
            with open(threshold_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        # 支持 : 或 = 分隔符
                        if "=" in line:
                            name, value = line.split("=", 1)
                        elif ":" in line:
                            name, value = line.split(":", 1)
                        else:
                            self.log(f"⚠️ [{self.name}] 阈值格式错误: {line}")
                            continue
                        name = name.strip()
                        number = float(value.strip())
                        if name == "sleep_time":
                            self.sleep_time = number
                        else:
                            self.thresholds[name] = number
                    except Exception as e:
                        self.log(f"⚠️ [{self.name}] 阈值解析失败: {line} ({e})")
        else:
            self.log(f"⚠️ [{self.name}] 阈值配置文件不存在")

    # ---------------- ADB 操作 ----------------
    def connect_device(self):
        device_id = f"127.0.0.1:{self.adb_port}"
        try:
            subprocess.run([self.adb_exe, 'start-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            subprocess.run([self.adb_exe, 'connect', device_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            time.sleep(1)

            if self.is_device_connected():
                self.log(f"✅ [{self.name}] 已连接")
            else:
                self.log(f"❌ [{self.name}] 未检测到设备")

        except Exception as e:
            self.log(f"❌ [{self.name}] 连接异常: {e}")

    def is_device_connected(self):
        try:
            result = subprocess.run([self.adb_exe, 'devices'], capture_output=True, text=True, timeout=15)
            return f"127.0.0.1:{self.adb_port}" in result.stdout
        except:
            return False

    def capture_screenshot(self):
        if not self.is_device_connected():
            self.connect_device()
            return False
        try:
            with open(self.screenshot_path, "wb") as f:
                subprocess.run(
                    [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                     "exec-out", "screencap", "-p"],
                    stdout=f,
                    check=True, timeout=15
                )
            return True
        except Exception as e:
            self.log(f"❌ [{self.name}] 截图失败: {e}")
            return False

    def tap_screen(self, x, y, image_name=None):
        if self.cancel_requested.is_set() or not self.running:
            return False
        if self.finish_requested.is_set() and image_name in ("img_4.jpg", "img_5.jpg"):
            return False
        try:
            subprocess.run(
                [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                 "shell", "input", "tap", str(x), str(y)],
                check=True, timeout=15
            )
            self.log(f"[{self.name}] 点击 {image_name or 'unknown'} ({x}, {y})")
            return True
        except:
            self.log(f"❌ [{self.name}] 点击 {image_name or 'unknown'} 失败 ({x}, {y})")
            return False

    # ---------------- 图片匹配 ----------------
    def swipe_left(self):
        if self.cancel_requested.is_set() or self.finish_requested.is_set():
            return
        x1 = int(self.mumu_width * 0.8)
        x2 = int(self.mumu_width * 0.2)
        y = int(self.mumu_height * 0.5)
        try:
            subprocess.run(
                [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                 "shell", "input", "swipe", str(x1), str(y),
                 str(x2), str(y), "500"], check=True, timeout=15
            )
            self.log(f"[{self.name}] Swipe left: ({x1}, {y}) -> ({x2}, {y})")
        except Exception as e:
            self.log(f"[{self.name}] Swipe failed: {e}")

    def match_template(self, screenshot):
        best_match, best_score, best_loc, best_size = None, 0, None, None
        target_match = None

        if not self.templates:
            return None, 0, None, None

        with ThreadPoolExecutor(max_workers=len(self.templates)) as executor:
            futures = [
                executor.submit(self._match_score, name, tpl, screenshot)
                for name, tpl in self.templates.items()
                if name not in ("img_11", "mainline_page")
                and not (self.in_battle and name in ("img_4", "img_5"))
            ]

            for future in as_completed(futures):
                try:
                    name, score, loc, size = future.result()
                    threshold = self.thresholds.get(name, 0.7)
                    self.log(f"[{self.name}] {name} 分数 {score:.3f} / 阈值 {threshold}")
                    priority_names = ("img_3",) if self.in_battle else ("img_4", "img_5")
                    if name in priority_names and score >= threshold:
                        if target_match is None or score > target_match[1]:
                            target_match = (name, score, loc, size)
                    if score >= threshold and score > best_score:
                        best_match, best_score, best_loc, best_size = name, score, loc, size
                except:
                    pass

        if target_match is not None:
            return target_match
        return best_match, best_score, best_loc, best_size

    def _match_score(self, name, template, screenshot):
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        h, w = template.shape
        return name, max_val, max_loc, (w, h)

    def _find_img_location(self, img_name, screenshot):
        """单独查找某张模板"""
        if img_name not in self.templates:
            return None
        _, _, loc, _ = self._match_score(img_name, self.templates[img_name], screenshot)
        return loc

    # ---------------- 逻辑控制 ----------------
    def check_repeated_clicks(self, name):
        self.recent_clicks.append(name)
        if len(self.recent_clicks) > 20:
            self.recent_clicks.pop(0)

        if len(self.recent_clicks) == 20 and all(n == name for n in self.recent_clicks):
            self.running = False
            self.log(f"⚠️ [{self.name}] 重复点击 {name} 超过 20 次，自动停止")

    def tap_by_loc(self, loc, size, screenshot, image_name=None):
        w, h = size
        cx = loc[0] + w // 2
        cy = loc[1] + h // 2
        x = int(cx * self.mumu_width / screenshot.shape[1])
        y = int(cy * self.mumu_height / screenshot.shape[0])
        return self.tap_screen(x, y, image_name=image_name)

    # ---------------- 主线章节入场 ----------------
    def reset_entry_state(self):
        self.entry_phase = "seek_chapter"
        self.entry_started = time.monotonic()
        self.chapter_scrolls = 0
        self.chapter_unchanged = 0
        self.chapter_previous_frame = None
        self.entry_retries = 0
        self.entry_last_click = 0
        self.map_absent_count = 0
        self.entry_debug_saved = False

    def find_entry_template(self, name, screenshot, threshold, roi=None):
        template = self.templates.get(name)
        if template is None:
            return None
        x, y = (0, 0) if roi is None else roi[:2]
        search = screenshot if roi is None else screenshot[roi[1]:roi[3], roi[0]:roi[2]]
        best = None
        highest_score = -1.0
        # Existing chapter/button templates use a different UI scale from the current map.
        for scale in (.6, .65, .7, .75, .8, .85, .9, .95, 1., 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5):
            width = max(1, round(template.shape[1] * scale))
            height = max(1, round(template.shape[0] * scale))
            if height > search.shape[0] or width > search.shape[1]:
                continue
            resized = cv2.resize(template, (width, height))
            _, score, loc, size = self._match_score(name, resized, search)
            highest_score = max(highest_score, float(score))
            if score >= threshold and (best is None or score > best[0]):
                best = (score, (loc[0] + x, loc[1] + y), size)
        self.entry_match_scores = getattr(self, "entry_match_scores", {})
        self.entry_match_scores[name] = highest_score
        return (best[1], best[2]) if best else None

    def is_mainline_page(self, screenshot):
        height, width = screenshot.shape[:2]
        roi = (int(width*.81), int(height*.20), width, int(height*.31))
        return self.find_entry_template("mainline_page", screenshot,
                                        self.thresholds.get("mainline_page", .9), roi) is not None

    def scroll_chapters(self):
        x = int(self.mumu_width * .906)
        start_y = int(self.mumu_height * .711)
        end_y = int(self.mumu_height * .367)
        try:
            subprocess.run([self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                            "shell", "input", "swipe", str(x), str(start_y),
                            str(x), str(end_y), "600"], check=True, timeout=15)
            self.chapter_scrolls += 1
            self.log(f"[{self.name}] 向上滚动主线列表，寻找第二十八章 ({self.chapter_scrolls})")
        except Exception as exc:
            self.running = False
            self.log(f"[{self.name}] 主线列表滑动失败，停止探索: {exc}")

    def handle_chapter_entry(self, screenshot):
        """Return True when this frame belongs to navigation, not map combat."""
        if self.in_battle:
            return False
        mainline = self.is_mainline_page(screenshot)
        self.log(f"[{self.name}] 探索阶段={self.entry_phase}，主线页面={'是' if mainline else '否'}")
        if self.entry_phase == "enter_exploration" and not mainline:
            self.entry_phase = "active"
            self.no_target_count = 0
            self.recent_clicks.clear()
            self.log(f"[{self.name}] 点击第二十八章后主线标记已消失，交给原探索逻辑识别并点击 img_2.jpg（探索）")
            return False
        # Starting or resuming on a verified exploration map needs no chapter navigation.
        if self.entry_phase == "seek_chapter" and not mainline:
            for name in ("img_4", "img_5", "img_8"):
                if self.find_entry_template(name, screenshot, max(.9, self.thresholds.get(name, .7))):
                    self.entry_phase = "active"
                    self.log(f"[{self.name}] 识别到探索地图 {name}，执行原探索循环")
                    return False
        if self.entry_phase == "active":
            if not mainline:
                return False
            self.reset_entry_state()
            self.no_target_count = 0
            self.log(f"[{self.name}] 已返回主线，重新寻找第二十八章")
        self.no_target_count = 0
        if time.monotonic() - self.entry_started > 45:
            self.running = False
            self.log(f"[{self.name}] 入场超时：请检查第二十八章是否解锁，以及 img_11 / img_2 模板是否匹配")
            return True
        if self.entry_phase == "wait_map":
            self.map_absent_count = self.map_absent_count + 1 if not mainline else 0
            if self.map_absent_count >= 2:
                self.entry_phase = "active"
                self.recent_clicks.clear()
                self.log(f"[{self.name}] 已离开主线列表，恢复原探索流程")
                return False
            if mainline and time.monotonic() - self.entry_last_click > 5:
                self.entry_phase = "enter_exploration"
            return True
        if self.entry_phase == "enter_exploration":
            height, width = screenshot.shape[:2]
            entry_roi = (int(width*.15), int(height*.20), width, height)
            threshold = self.thresholds.get("explore_entry", self.thresholds.get("img_2", .7))
            entry = self.find_entry_template("img_2", screenshot, threshold, entry_roi)
            score = getattr(self, "entry_match_scores", {}).get("img_2")
            score_text = f"{score:.3f}" if score is not None else "未知"
            self.log(f"[{self.name}] 查找探索按钮 img_2.jpg：最高分 {score_text} / 阈值 {threshold}")
            if not entry and not getattr(self, "entry_debug_saved", False):
                debug_path = os.path.join(self.image_dir, f"entry_unmatched_{self.adb_port}.png") if hasattr(self, "image_dir") else None
                if debug_path:
                    cv2.imencode(".png", screenshot)[1].tofile(debug_path)
                    self.entry_debug_saved = True
                    self.log(f"[{self.name}] 入口未匹配画面已保存: {debug_path}")
            if entry:
                loc, size = entry
                if self.running and self.tap_by_loc(loc, size, screenshot, image_name="img_2.jpg（探索入口）"):
                    self.entry_phase = "wait_map"
                    self.entry_last_click = time.monotonic()
                    self.map_absent_count = 0
                    self.no_target_count = 0
                    self.chapter_previous_frame = None
                    self.recent_clicks.clear()
                    self.log(f"[{self.name}] 已点击探索入口，等待新截图确认离开主线")
            elif mainline and time.monotonic() - self.entry_last_click > 5 and self.entry_retries < 3:
                self.entry_phase = "seek_chapter"
            return True
        if not mainline:
            self.log(f"[{self.name}] 等待主线列表，请先回到探索主线页面")
            return True
        height, width = screenshot.shape[:2]
        roi = (int(width*.82), int(height*.28), int(width*.995), int(height*.78))
        chapter = self.find_entry_template("img_11", screenshot,
                                           self.thresholds.get("img_11", .85), roi)
        if chapter:
            loc, size = chapter
            if self.running and self.tap_by_loc(loc, size, screenshot, image_name="img_11.jpg（第二十八章）"):
                self.entry_phase = "enter_exploration"
                self.entry_retries += 1
                self.entry_last_click = time.monotonic()
                self.log(f"[{self.name}] 已点击第二十八章，等待探索按钮")
            return True
        frame = cv2.resize(screenshot[roi[1]:roi[3],roi[0]:roi[2]], (80,120))
        if self.chapter_previous_frame is not None:
            difference = cv2.absdiff(frame, self.chapter_previous_frame).mean()
            self.chapter_unchanged = self.chapter_unchanged + 1 if difference < 2 else 0
        self.chapter_previous_frame = frame
        if self.chapter_scrolls >= 20 or self.chapter_unchanged >= 2:
            self.running = False
            self.log(f"[{self.name}] 主线列表已到底或达到滑动上限，未匹配到 img_11.jpg；请检查模板和章节解锁情况")
            return True
        if self.running:
            self.scroll_chapters()
        return True

    # ---------------- 主循环 ----------------
    def run(self):
        self.running = True
        if self.finish_if_ready():
            return
        self.recent_clicks.clear()
        self.battle_count = 0
        self.in_battle = False
        self.no_target_count = 0

        self.task_ready.clear()
        self.reset_entry_state()
        missing = [name for name in ("img_11", "img_2", "mainline_page") if name not in self.templates]
        if missing:
            self.running = False
            self.log(f"[{self.name}] 探索入场模板缺失: {', '.join(missing)}")
            return
        self.log(f"🚀 [{self.name}] 探索启动，先查找第二十八章")
        self.connect_device()

        while self.running:
            if self.finish_if_ready():
                break
            if not self.capture_screenshot():
                time.sleep(1)
                continue

            screenshot = cv2.imdecode(np.fromfile(self.screenshot_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                self.log(f"[{self.name}] 截图读取失败: {self.screenshot_path}")
                time.sleep(1)
                continue

            if self.handle_chapter_entry(screenshot):
                time.sleep(max(1, self.sleep_time))
                continue

            if not self.task_ready.is_set():
                self.task_ready.set()
                self.log(f"[{self.name}] 入场前提已完成，开始原探索逻辑：寻找 img_4/img_5，战斗后点击 img_3，连续3次未找到目标则左划")
            best_match, score, loc, size = self.match_template(screenshot)

            # Only count missing exploration targets outside battle.
            if not self.in_battle:
                if best_match in ("img_2", "img_4", "img_5"):
                    self.no_target_count = 0
                else:
                    self.no_target_count += 1
                    self.log(f"[{self.name}] img_4 / img_5 not found ({self.no_target_count}/3)")

                if self.no_target_count >= 3:
                    if not self.running:
                        break
                    self.swipe_left()
                    self.no_target_count = 0
                    time.sleep(1)
                    continue

            if best_match:
                clicked = self.tap_by_loc(loc, size, screenshot, image_name=f"{best_match}.jpg")
                if clicked:
                    if best_match in ("img_4", "img_5"):
                        self.in_battle = True
                        self.no_target_count = 0
                        self.log(f"[{self.name}] Battle started; exploration swipe paused")
                    elif best_match == "img_3" and self.in_battle:
                        self.in_battle = False
                        self.no_target_count = 0
                        self.log(f"[{self.name}] Battle exited; exploration resumed")
                    self.check_repeated_clicks(best_match)
            else:
                self.log(f"[{self.name}] 未检测到匹配目标")

            time.sleep(self.sleep_time)

    def stop(self):
        self.cancel_requested.set()
        self.running = False
        self.log(f"🛑 [{self.name}] 探索停止")


# ---------------- 创建探索实例 ----------------
def create_tansuo(log_fn, port):
    return AutoClicker(
        log_fn=log_fn,
        scene_name="tansuo",
        adb_port=port,
        name=f"tansuo-{port}"
    )
