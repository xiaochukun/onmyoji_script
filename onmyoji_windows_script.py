import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import threading
import time
import os
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyautogui
import pygetwindow as gw
import numpy as np
import keyboard
import win32api
import win32con
# --------------------- 日志锁 ---------------------
log_lock = threading.Lock()

def safe_log(log_widget, msg):
    with log_lock:
        log_widget.config(state='normal')
        log_widget.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        log_widget.see(tk.END)
        log_widget.config(state='disabled')

# --------------------- 自动点击器 ---------------------
class AutoClickerDesktop:
    def __init__(self, log_fn, scene_name, thresholds=None):
        self.log = log_fn
        self.scene_name = scene_name
        self.running = False
        self.thresholds = thresholds or {}

        self.image_dir = os.path.join(os.getcwd(), "yys", scene_name)
        self.recent_clicks = []
        self.templates = {}
        self.template_paths = {}
        self.sleep_time = 1

        self.window = None
        self.window_box = None  # (left, top, width, height)

        self.load_templates()
        self.load_thresholds_from_file()

        keyboard.on_press_key("esc", lambda e: self.stop())
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

    def find_window(self):
        try:
            wins = gw.getWindowsWithTitle("阴阳师-网易游戏")
            if wins:
                self.window = wins[0]
                self.window_box = (self.window.left, self.window.top,
                                   self.window.width, self.window.height)
                self.log(f"✅ 找到阴阳师窗口: {self.window_box}")
                return True
            else:
                self.log("❌ 未找到阴阳师窗口")
                return False
        except Exception as e:
            self.log(f"❌ 窗口检测异常: {e}")
            return False

    def capture_screenshot(self):
        if not self.window:
            if not self.find_window():
                return None
        try:
            left, top, width, height = self.window_box
            screenshot = pyautogui.screenshot(region=(left, top, width, height))
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
            return screenshot_cv
        except Exception as e:
            self.log(f"❌ 截图失败: {e}")
            return None

    def tap_screen(self, x, y):
        try:
            if not self.window:
                if not self.find_window():
                    return
            left, top, _, _ = self.window_box
            screen_x = left + x
            screen_y = top + y

            self.log(f"📌 等待1秒后真实点击坐标: ({screen_x}, {screen_y})")

            # 激活窗口
            self.window.activate()
            time.sleep(1)  # 等1秒再点击

            # 移动鼠标到目标位置
            win32api.SetCursorPos((screen_x, screen_y))
            time.sleep(0.05)

            # 模拟鼠标按下和松开
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
            time.sleep(0.05)  # 按住50毫秒
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)

        except Exception as e:
            self.log(f"❌ 点击失败: {e}")

    def match_template_score(self, name, template, screenshot):
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        w, h = template.shape[::-1]
        return name, max_val, max_loc, (w, h)

    def stop(self):
        self.running = False
        self.log(f"🛑 自动点击停止")

    def check_repeated_clicks(self, name):
        self.recent_clicks.append(name)
        if len(self.recent_clicks) > 20:
            self.recent_clicks.pop(0)
        if len(self.recent_clicks) == 20 and all(n == name for n in self.recent_clicks):
            self.running = False
            self.log(f"⚠️ 重复点击 {name} 超过20次，停止运行")

    def run(self):
        self.running = True
        self.recent_clicks = []
        self.log(f"🚀 自动点击启动")

        if not self.find_window():
            self.log("❌ 启动失败: 找不到窗口")
            return

        while self.running:
            screenshot = self.capture_screenshot()
            if screenshot is None:
                time.sleep(2)
                continue

            # 多线程匹配模板
            with ThreadPoolExecutor(max_workers=len(self.templates)) as executor:
                futures = {
                    executor.submit(self.match_template_score, name, t, screenshot): name
                    for name, t in self.templates.items()
                }
                best_match = None
                best_score = 0
                best_location = None
                best_size = None

                for future in as_completed(futures):
                    try:
                        name, score, loc, size = future.result()
                        threshold = self.thresholds.get(name, 0.4)
                        self.log(f"模板 {name}: score={score:.3f}, 阈值={threshold}")
                        if score >= threshold and score > best_score:
                            best_score = score
                            best_match = name
                            best_location = loc
                            best_size = size
                    except:
                        continue

            if best_match:
                w, h = best_size
                center_x = best_location[0] + w // 2
                center_y = best_location[1] + h // 2

                self.tap_screen(center_x, center_y)
                self.check_repeated_clicks(best_match)


            time.sleep(self.sleep_time)

# --------------------- GUI ---------------------
class AutoClickerAppDesktop:
    def __init__(self, root):
        self.root = root
        self.root.title("阴阳师桌面版自动点击器")
        self.bot = None
        self.thread = None

        self.build_ui()
        self.root.bind("<Escape>", lambda e: self.stop_bot())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def build_ui(self):
        frame = ttk.Frame(self.root)
        frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(frame, text="选择场景:").grid(row=0, column=0, sticky="e")
        self.scene_var = tk.StringVar(value="请选择场景")
        self.scene_dropdown = ttk.Combobox(
            frame, textvariable=self.scene_var,
            values=["yuling", "yeyuanhuo", "huodong", "tansuo", "yuhun"],
            state="readonly"
        )
        self.scene_dropdown.grid(row=0, column=1, sticky="w")

        self.start_button = ttk.Button(frame, text="▶ 开始", command=self.start_bot)
        self.start_button.grid(row=1, column=0, pady=10)

        self.stop_button = ttk.Button(frame, text="■ 停止", command=self.stop_bot)
        self.stop_button.grid(row=1, column=1, pady=10)

        self.log_box = scrolledtext.ScrolledText(
            self.root, width=80, height=20,
            state='disabled', font=("Consolas", 10)
        )
        self.log_box.pack(padx=10, pady=10)

    def start_bot(self):
        scene = self.scene_var.get()
        if scene == "请选择场景":
            messagebox.showwarning("警告", "请选择场景！")
            return
        if self.bot is None:
            self.bot = AutoClickerDesktop(
                log_fn=lambda msg: safe_log(self.log_box, msg),
                scene_name=scene
            )
            self.thread = threading.Thread(target=self.bot.run, daemon=True)
            self.thread.start()

    def stop_bot(self):
        if self.bot:
            self.bot.stop()
            self.bot = None
            self.thread = None

    def on_closing(self):
        self.stop_bot()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerAppDesktop(root)
    root.mainloop()
