import tkinter as tk
import threading
import cv2
import numpy as np
import time
import os
import subprocess
import ctypes

# ---------------- 配置路径 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "breakthrough")
TEMPLATE_IMAGE_1_PATH = os.path.join(IMAGE_DIR, "start.png")
TEMPLATE_IMAGE_2_PATH = os.path.join(IMAGE_DIR, "attack.png")
TEMPLATE_IMAGE_3_PATH = os.path.join(IMAGE_DIR, "tianzhao.png")
TEMPLATE_IMAGE_4_PATH = os.path.join(IMAGE_DIR, "Finish.png")
TEMPLATE_IMAGE_5_PATH = os.path.join(IMAGE_DIR, "fail.png")
SCREENSHOT_PATH = os.path.join(IMAGE_DIR, "mumu_screenshot.png")
THRESHOLD_CONFIG_PATH = os.path.join(IMAGE_DIR, "阈值配置要求.txt")

MUMU_WIDTH = 1600
MUMU_HEIGHT = 900

running = False
log_lock = threading.Lock()

# ---------------- 默认阈值 ----------------
thresholds = {
    "start": 0.95,
    "attack": 0.4,
    "tianzhao": 0.55,
    "finish": 0.4,
    "fail": 0.7,
    "sleep_time": 1.0,
}

# ---------------- 读取阈值文件 ----------------
def load_thresholds():
    if not os.path.exists(THRESHOLD_CONFIG_PATH):
        print("⚠️ 未找到阈值配置文件，使用默认值")
        return
    try:
        with open(THRESHOLD_CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if key in thresholds:
                    try:
                        thresholds[key] = float(value)
                    except ValueError:
                        print(f"⚠️ 无法解析阈值 {key}: {value}")
    except Exception as e:
        print(f"⚠️ 读取阈值配置失败: {e}")

load_thresholds()

# ---------------- 日志函数（线程安全） ----------------
def thread_safe_log(log_widget, msg):
    def append():
        with log_lock:
            log_widget.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {msg}\n")
            log_widget.see(tk.END)
    try:
        log_widget.after(0, append)
    except RuntimeError:
        pass  # 窗口关闭时避免报错

# ---------------- 图像识别函数 ----------------
def compare_images(template_path, screenshot):
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None or screenshot is None:
        return 0, (0, 0)
    img_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    h, w = template.shape
    center_x = min(max_loc[0] + w // 2, MUMU_WIDTH - 1)
    center_y = min(max_loc[1] + h // 2, MUMU_HEIGHT - 1)
    return max_val, (center_x, center_y)

# ---------------- 截图与点击 ----------------
def capture_screenshot():
    try:
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True, check=True)
        subprocess.run(f"adb pull /sdcard/screen.png \"{SCREENSHOT_PATH}\"", shell=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def adb_click(x, y):
    try:
        subprocess.run(f"adb shell input tap {x} {y}", shell=True, check=True)
        time.sleep(0.5)
    except subprocess.CalledProcessError:
        pass

# ---------------- 机器人循环 ----------------
def bot_loop(log_widget):
    global running
    running = True
    thread_safe_log(log_widget, "🚀 自动点击器启动")

    while running:
        if not capture_screenshot():
            thread_safe_log(log_widget, "❌ 截图失败，3秒后重试")
            time.sleep(3)
            continue

        screenshot = cv2.imread(SCREENSHOT_PATH)
        if screenshot is None:
            thread_safe_log(log_widget, "❌ 无法读取截图文件，7秒后重试")
            time.sleep(7)
            continue

        val1, loc1 = compare_images(TEMPLATE_IMAGE_1_PATH, screenshot)
        val2, loc2 = compare_images(TEMPLATE_IMAGE_2_PATH, screenshot)
        val3, loc3 = compare_images(TEMPLATE_IMAGE_3_PATH, screenshot)
        val4, loc4 = compare_images(TEMPLATE_IMAGE_4_PATH, screenshot)
        val5, loc5 = compare_images(TEMPLATE_IMAGE_5_PATH, screenshot)

        thread_safe_log(log_widget, f"匹配度: 选人={val1:.3f}, 进攻={val2:.3f}, 天照={val3:.3f}, 胜利={val4:.3f}, 失败={val5:.3f}")

        # 根据匹配点击
        if val1 >= thresholds["start"] or val2 >= thresholds["attack"]:
            if val1 - val2 < 0.1:
                adb_click(*loc2)
                thread_safe_log(log_widget, "点击：进攻按钮")
            else:
                adb_click(*loc1)
                thread_safe_log(log_widget, "点击：选人按钮")
        elif val3 > thresholds["tianzhao"] or val4 > thresholds["finish"]:
            if val3 > val4:
                adb_click(*loc3)
                thread_safe_log(log_widget, "点击：天照")
            else:
                adb_click(*loc4)
                thread_safe_log(log_widget, "点击：胜利")
        elif val5 > thresholds["fail"]:
            thread_safe_log(log_widget, "检测到失败界面，任务停止")
            ctypes.windll.user32.MessageBoxW(0, "检测到失败界面，请检查！", "⚠️ 错误提示", 0x40)
            break
        else:
            thread_safe_log(log_widget, "未检测到目标界面")

        time.sleep(thresholds.get("sleep_time", 1))

    thread_safe_log(log_widget, "🛑 自动点击器已停止")
    global running
    running = False

# ---------------- 阈值配置编辑 ----------------
def open_threshold_config():
    if os.path.exists(THRESHOLD_CONFIG_PATH):
        os.startfile(THRESHOLD_CONFIG_PATH)
    else:
        with open(THRESHOLD_CONFIG_PATH, "w", encoding="utf-8") as f:
            for k, v in thresholds.items():
                f.write(f"{k}: {v}\n")
        os.startfile(THRESHOLD_CONFIG_PATH)

# ---------------- Tkinter GUI ----------------
def main():
    global running
    root = tk.Tk()
    root.title("突破自动点击器")

    frame = tk.Frame(root)
    frame.pack(pady=10)

    log_box = tk.Text(root, height=20, width=70)
    log_box.pack(pady=10)

    def start():
        if not running:
            start_button.config(state="disabled")
            stop_button.config(state="normal")
            threading.Thread(target=bot_loop, args=(log_box,), daemon=True).start()

    def stop():
        global running
        running = False
        start_button.config(state="normal")
        stop_button.config(state="disabled")

    start_button = tk.Button(frame, text="▶ 启动", command=start, width=10)
    start_button.grid(row=0, column=0, padx=10)

    stop_button = tk.Button(frame, text="⏹ 停止", command=stop, width=10, state="disabled")
    stop_button.grid(row=0, column=1, padx=10)

    config_button = tk.Button(frame, text="⚙️ 编辑阈值配置", command=open_threshold_config, width=15)
    config_button.grid(row=0, column=2, padx=10)

    root.mainloop()

if __name__ == "__main__":
    main()
