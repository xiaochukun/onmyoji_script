import threading
import subprocess
import time
import os
import cv2
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
class AutoClicker:
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
        self.thresholds = thresholds or {}

        self.image_dir = os.path.join(os.getcwd(), "yys", scene_name)
        self.adb_exe = os.path.join(os.getcwd(), "adb.exe")
        self.screenshot_path = os.path.join(
            self.image_dir, f"{scene_name}_screenshot_{adb_port}.png"
        )

        self.mumu_width = 1600
        self.mumu_height = 900
        self.sleep_time = 2

        self.templates = {}
        self.template_paths = {}
        self.load_templates()
        self.load_thresholds()

        self.recent_clicks = []
        self.battle_count = 0
        self.in_battle = False
        self.no_target_count = 0  # Consecutive misses for both img_4 and img_5

    # ---------------- 模板加载 ----------------
    def load_templates(self):
        for i in range(1, 10):
            img_name = f"img_{i}"
            img_path = os.path.join(self.image_dir, f"{img_name}.jpg")
            if os.path.exists(img_path):
                self.template_paths[img_name] = img_path
                template_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    self.templates[img_name] = template_img
                else:
                    self.log(f"⚠️ [{self.name}] 图片 {img_name} 读取失败")

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
                        self.thresholds[name.strip()] = float(value.strip())
                    except Exception as e:
                        self.log(f"⚠️ [{self.name}] 阈值解析失败: {line} ({e})")
        else:
            self.log(f"⚠️ [{self.name}] 阈值配置文件不存在")

    # ---------------- ADB 操作 ----------------
    def connect_device(self):
        device_id = f"127.0.0.1:{self.adb_port}"
        try:
            subprocess.run([self.adb_exe, 'kill-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'start-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'connect', device_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)

            if self.is_device_connected():
                self.log(f"✅ [{self.name}] 已连接")
            else:
                self.log(f"❌ [{self.name}] 未检测到设备")

        except Exception as e:
            self.log(f"❌ [{self.name}] 连接异常: {e}")

    def is_device_connected(self):
        try:
            result = subprocess.run([self.adb_exe, 'devices'], capture_output=True, text=True)
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
                    check=True
                )
            return True
        except Exception as e:
            self.log(f"❌ [{self.name}] 截图失败: {e}")
            return False

    def tap_screen(self, x, y, image_name=None):
        try:
            subprocess.run(
                [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                 "shell", "input", "tap", str(x), str(y)],
                check=True
            )
            self.log(f"[{self.name}] 点击 {image_name or 'unknown'} ({x}, {y})")
            return True
        except:
            self.log(f"❌ [{self.name}] 点击 {image_name or 'unknown'} 失败 ({x}, {y})")
            return False

    # ---------------- 图片匹配 ----------------
    def swipe_left(self):
        x1 = int(self.mumu_width * 0.8)
        x2 = int(self.mumu_width * 0.2)
        y = int(self.mumu_height * 0.5)
        try:
            subprocess.run(
                [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                 "shell", "input", "swipe", str(x1), str(y),
                 str(x2), str(y), "500"], check=True
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
                if not (self.in_battle and name in ("img_4", "img_5"))
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

    # ---------------- 主循环 ----------------
    def run(self):
        self.running = True
        self.recent_clicks.clear()
        self.battle_count = 0
        self.in_battle = False
        self.no_target_count = 0

        self.log(f"🚀 [{self.name}] 探索启动")
        self.connect_device()

        while self.running:
            if not self.capture_screenshot():
                time.sleep(1)
                continue

            screenshot = cv2.imread(self.screenshot_path, cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                time.sleep(1)
                continue

            best_match, score, loc, size = self.match_template(screenshot)

            # Only count missing exploration targets outside battle.
            if not self.in_battle:
                if best_match in ("img_4", "img_5"):
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
