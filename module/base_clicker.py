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
        # 窗口关闭时避免报错
        pass

# ---------------- 自动点击器 ----------------
class AutoClicker:
    def __init__(self, log_fn, scene_name, adb_port, thresholds=None):
        self.log = log_fn  # 这里传入 safe_log 或自定义函数
        self.scene_name = scene_name
        self.adb_port = adb_port
        self.running = False
        self.thresholds = thresholds or {}

        self.image_dir = os.path.join(os.getcwd(), "yys", scene_name)
        self.adb_exe = os.path.join(os.getcwd(), "adb.exe")
        self.mumu_width = 1600
        self.mumu_height = 900
        self.sleep_time = 1
        self.recent_clicks = []
        self.templates = {}
        self.template_paths = {}

        self.load_templates()
        self.load_thresholds_from_file()

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
                    self.log(f"⚠️ 图片[{img_name}]读取失败")
        # 截图路径
        screenshot_name = f"{self.scene_name}_screenshot_{self.adb_port}.png"
        self.template_paths["screenshot"] = os.path.join(self.image_dir, screenshot_name)

    def load_thresholds_from_file(self):
        config_path = os.path.join(self.image_dir, "阈值配置要求.txt")
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ':' not in line:
                        continue
                    name, value = line.split(':', 1)
                    name = name.strip()
                    value = value.strip()
                    if name == "sleep_time":
                        try:
                            self.sleep_time = float(value)
                        except:
                            pass
                    else:
                        try:
                            self.thresholds[name] = float(value)
                        except:
                            pass
        except Exception as e:
            self.log(f"❌ 读取阈值配置失败: {e}")

    def connect_device(self):
        device_id = f"127.0.0.1:{self.adb_port}"
        try:
            subprocess.run([self.adb_exe, 'kill-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'start-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'connect', device_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)

            if self.is_device_connected():
                self.log(f"✅ 端口 {self.adb_port} 已连接")
            else:
                self.log(f"❌ 端口 {self.adb_port} 未检测到设备")
        except Exception as e:
            self.log(f"❌ 连接异常: {e}")

    def is_device_connected(self):
        try:
            result = subprocess.run([self.adb_exe, 'devices'], capture_output=True, text=True)
            devices = result.stdout.strip().split('\n')
            devices = [d for d in devices[1:] if 'device' in d and 'offline' not in d]
            return any(f"127.0.0.1:{self.adb_port}" in d for d in devices)
        except:
            return False

    def capture_screenshot(self):
        if not self.is_device_connected():
            self.connect_device()
            return False
        try:
            with open(self.template_paths["screenshot"], "wb") as f:
                subprocess.run([self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}", "exec-out", "screencap", "-p"],
                               stdout=f, check=True)
            return True
        except Exception as e:
            self.log(f"❌ 截图失败: {e}")
            return False

    def tap_screen(self, x, y):
        try:
            subprocess.run([self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}", "shell", "input", "tap", str(x), str(y)],
                           capture_output=True, text=True, check=True)
            self.log(f"点击屏幕: ({x}, {y})")  # ✅ 新增每次点击日志
        except:
            self.log("点击失败")

    def match_template_score(self, name, template, screenshot):
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        w, h = template.shape[::-1]
        return name, max_val, max_loc, (w, h)

    def stop(self):
        self.running = False
        self.log(f"🛑 端口 {self.adb_port} 停止")

    def check_repeated_clicks(self, name):
        self.recent_clicks.append(name)
        if len(self.recent_clicks) > 20:
            self.recent_clicks.pop(0)
        if len(self.recent_clicks) == 20 and all(n == name for n in self.recent_clicks):
            self.running = False
            self.log(f"⚠️ 端口 {self.adb_port} 重复点击 {name} 超过20次，停止运行")

    def run(self):
        self.running = True
        self.recent_clicks = []
        self.log(f"🚀 端口 {self.adb_port} 自动点击启动")

        self.connect_device()
        while self.running:
            if not self.capture_screenshot():
                time.sleep(2)
                continue

            screenshot = cv2.imread(self.template_paths["screenshot"], cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                time.sleep(1)
                continue

            # 并行匹配
            with ThreadPoolExecutor(max_workers=len(self.templates)) as executor:
                futures = {executor.submit(self.match_template_score, name, t, screenshot): name
                           for name, t in self.templates.items()}
                best_match = None
                best_score = 0
                best_location = None
                best_size = None

                for future in as_completed(futures):
                    try:
                        name, score, loc, size = future.result()
                        threshold = self.thresholds.get(name, 0.4)
                        self.log(f"[{name}] 匹配分数: {score:.3f} (阈值 {threshold})")  # ✅ 新增匹配日志
                        if score >= threshold and score > best_score:
                            best_score = score
                            best_match = name
                            best_location = loc
                            best_size = size
                    except:
                        continue

            # 点击最佳匹配
            if best_match:
                w, h = best_size
                center_x = best_location[0] + w // 2
                center_y = best_location[1] + h // 2

                click_x = int(center_x * self.mumu_width / screenshot.shape[1])
                click_y = int(center_y * self.mumu_height / screenshot.shape[0])

                self.tap_screen(click_x, click_y)
                self.check_repeated_clicks(best_match)
            else:
                self.log("未检测到匹配目标")

            time.sleep(self.sleep_time)
