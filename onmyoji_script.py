import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import threading
import subprocess
import time
import os
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# --------------------- 日志锁 ---------------------
log_lock = threading.Lock()


def safe_log(log_widget, msg):
    with log_lock:
        log_widget.config(state='normal')
        log_widget.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        log_widget.see(tk.END)
        log_widget.config(state='disabled')


# --------------------- 自动点击器 ---------------------
class AutoClicker:
    def __init__(self, log_fn, scene_name, adb_port, thresholds=None):
        self.log = log_fn
        self.scene_name = scene_name
        self.adb_port = adb_port
        self.running = False
        self.thresholds = thresholds or {}

        self.image_dir = os.path.join(os.getcwd(), "yys", scene_name)
        self.adb_exe = os.path.join(os.getcwd(), "adb.exe")  # 固定使用项目里的 adb
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

        # ⭐ 每个端口独立截图文件，避免多端口冲突
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
            subprocess.run([self.adb_exe, 'kill-server'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'start-server'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([self.adb_exe, 'connect', device_id],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)

            if self.is_device_connected():
                self.log(f"✅ 端口 {self.adb_port} 已连接")
            else:
                self.log(f"❌ 端口 {self.adb_port} 未检测到设备")
        except Exception as e:
            self.log(f"❌ 连接异常: {e}")

    def is_device_connected(self):
        try:
            result = subprocess.run([self.adb_exe, 'devices'],
                                    capture_output=True, text=True)
            devices = result.stdout.strip().split('\n')
            devices = [d for d in devices[1:] if 'device' in d and 'offline' not in d]
            return any(f"127.0.0.1:{self.adb_port}" in d for d in devices)
        except:
            return False

    def capture_screenshot(self):
        """直接把截图流导出到本地，避免 /sdcard 权限问题"""
        if not self.is_device_connected():
            self.connect_device()
            return False
        try:
            with open(self.template_paths["screenshot"], "wb") as f:
                subprocess.run(
                    [self.adb_exe, "-s", f"127.0.0.1:{self.adb_port}",
                     "exec-out", "screencap", "-p"],
                    stdout=f, check=True
                )
            return True
        except Exception as e:
            self.log(f"❌ 截图失败: {e}")
            return False

    def tap_screen(self, x, y):
        cmd = [
            self.adb_exe,
            "-s", f"127.0.0.1:{self.adb_port}",
            "shell", "input", "tap", str(x), str(y)
        ]
        self.log(f"准备点击: {x}, {y}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.log(f"点击成功: {x}, {y}")
            if result.stdout.strip():
                self.log(f"点击输出: {result.stdout.strip()}")
            if result.stderr.strip():
                self.log(f"点击错误: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            self.log(f"点击失败! 命令: {' '.join(cmd)}")
            self.log(f"错误码: {e.returncode}")
            if e.stdout:
                self.log(f"stdout: {e.stdout}")
            if e.stderr:
                self.log(f"stderr: {e.stderr}")

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

            # 每个端口独立线程池，避免冲突
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

                click_x = int(center_x * self.mumu_width / screenshot.shape[1])
                click_y = int(center_y * self.mumu_height / screenshot.shape[0])

                self.tap_screen(click_x, click_y)
                self.check_repeated_clicks(best_match)

            time.sleep(self.sleep_time)


# --------------------- GUI ---------------------
class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MuMu 自动点击器 - 多端口版")
        self.bots = {}      # port -> bot
        self.threads = {}   # port -> thread

        self.build_ui()
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

        ttk.Label(frame, text="端口列表:").grid(row=1, column=0, sticky="ne")
        self.port_listbox = tk.Listbox(frame, selectmode="multiple", height=5)
        self.port_listbox.grid(row=1, column=1, sticky="w")

        self.refresh_ports_btn = ttk.Button(frame, text="刷新端口", command=self.refresh_ports)
        self.refresh_ports_btn.grid(row=1, column=2, padx=5)

        self.add_port_btn = ttk.Button(frame, text="添加端口", command=self.add_port)
        self.add_port_btn.grid(row=2, column=1, sticky="w")

        self.del_port_btn = ttk.Button(frame, text="删除端口", command=self.delete_port)
        self.del_port_btn.grid(row=2, column=2, sticky="w")

        self.start_button = ttk.Button(frame, text="▶ 开始", command=self.start_bots)
        self.start_button.grid(row=3, column=0, pady=10)

        self.stop_button = ttk.Button(frame, text="■ 停止全部", command=self.stop_all_bots)
        self.stop_button.grid(row=3, column=1, pady=10)

        self.log_box = scrolledtext.ScrolledText(
            self.root, width=80, height=20,
            state='disabled', font=("Consolas", 10)
        )
        self.log_box.pack(padx=10, pady=10)

        self.refresh_ports()

    def refresh_ports(self):
        self.port_listbox.delete(0, tk.END)
        ports = self.get_adb_ports()
        for p in ports:
            self.port_listbox.insert(tk.END, p)

    def get_adb_ports(self):
        ports = []
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                if 'device' in line and 'offline' not in line:
                    port = line.split(':')[1].split()[0]
                    ports.append(port)
        except:
            pass
        return ports

    def add_port(self):
        port = simpledialog.askstring("添加端口", "请输入端口号:")
        if port:
            self.port_listbox.insert(tk.END, port)

    def delete_port(self):
        selected = list(self.port_listbox.curselection())
        for i in reversed(selected):
            self.port_listbox.delete(i)

    def start_bots(self):
        scene = self.scene_var.get()
        if scene == "请选择场景":
            messagebox.showwarning("警告", "请选择场景！")
            return

        selected_indices = self.port_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请选择至少一个端口！")
            return

        for idx in selected_indices:
            port = self.port_listbox.get(idx)
            if port not in self.bots:
                bot = AutoClicker(
                    log_fn=lambda msg, p=port: safe_log(self.log_box, f"[{p}] {msg}"),
                    scene_name=scene, adb_port=port
                )
                t = threading.Thread(target=bot.run, daemon=True)
                self.bots[port] = bot
                self.threads[port] = t
                t.start()

    def stop_all_bots(self):
        for port, bot in self.bots.items():
            bot.stop()
        self.bots.clear()
        self.threads.clear()

    def on_closing(self):
        self.stop_all_bots()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
