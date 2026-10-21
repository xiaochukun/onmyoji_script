import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import threading
import subprocess
import time

from module.base_clicker import safe_log
from module.scenes import SCENE_BUILDERS


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MuMu 自动点击器 - 模块化版")
        self.bots = {}
        self.threads = {}
        self.task_timers = {}
        self.task_queue = []
        self.scheduler_running = False
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def build_ui(self):
        frame = ttk.Frame(self.root)
        frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(frame, text="单场景选择:").grid(row=0, column=0)
        self.scene_var = tk.StringVar(value="tansuo")
        self.scene_dropdown = ttk.Combobox(frame, textvariable=self.scene_var,
                                         values=list(SCENE_BUILDERS.keys()), state="readonly")
        self.scene_dropdown.grid(row=0, column=1)
        self.duration_var = tk.StringVar(value="0")
        ttk.Label(frame, text="单场景时长(分钟):").grid(row=0, column=2)
        ttk.Entry(frame, textvariable=self.duration_var, width=8).grid(row=0, column=3)
        ttk.Label(frame, text="0 = 无限制").grid(row=0, column=4)
        self.ticket_var = tk.StringVar(value="0")
        ttk.Label(frame, text="单场景突破券数:").grid(row=2, column=3)
        ttk.Entry(frame, textvariable=self.ticket_var, width=8).grid(row=2, column=4)
        ttk.Label(frame, text="0 = 无限制（每个端口分别计数）").grid(row=3, column=4)
        ttk.Label(frame, text="任务队列:").grid(row=1, column=0, sticky="ne")
        self.task_listbox = tk.Listbox(frame, height=5)
        self.task_listbox.grid(row=1, column=1)
        ttk.Button(frame, text="添加任务", command=self.add_task).grid(row=1, column=2)
        ttk.Button(frame, text="删除任务", command=self.delete_task).grid(row=2, column=2)
        ttk.Label(frame, text="端口列表:").grid(row=3, column=0, sticky="ne")
        self.port_listbox = tk.Listbox(frame, selectmode="multiple", height=5)
        self.port_listbox.grid(row=3, column=1)
        ttk.Button(frame, text="刷新端口", command=self.refresh_ports).grid(row=3, column=2)
        ttk.Button(frame, text="添加端口", command=self.add_port).grid(row=4, column=1)
        ttk.Button(frame, text="删除端口", command=self.delete_port).grid(row=4, column=2)
        ttk.Button(frame, text="▶ 开始", command=self.start_bots).grid(row=5, column=0, pady=10)
        ttk.Button(frame, text="■ 停止全部", command=self.stop_all_bots).grid(row=5, column=1)
        self.log_box = scrolledtext.ScrolledText(self.root, width=80, height=20,
                                               state="disabled", font=("Consolas", 10))
        self.log_box.pack(padx=10, pady=10)
        self.refresh_ports()

    def refresh_ports(self):
        self.port_listbox.delete(0, tk.END)
        for port in self.get_adb_ports():
            self.port_listbox.insert(tk.END, port)

    def get_adb_ports(self):
        ports = []
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            for line in result.stdout.strip().split('\n')[1:]:
                if 'device' in line and 'offline' not in line:
                    ports.append(line.split(':')[1].split()[0])
        except:
            pass
        return ports

    def add_port(self):
        port = simpledialog.askstring("添加端口", "请输入端口号:")
        if port:
            self.port_listbox.insert(tk.END, port)

    def delete_port(self):
        for i in reversed(list(self.port_listbox.curselection())):
            self.port_listbox.delete(i)

    def add_task(self):
        scene = simpledialog.askstring("添加任务", f"输入场景名:\n可用:{','.join(SCENE_BUILDERS.keys())}")
        if scene not in SCENE_BUILDERS:
            messagebox.showwarning("错误", "无效场景")
            return
        minutes = simpledialog.askinteger("运行时间", "请输入运行分钟数 (0 = 无限制):", initialvalue=0, minvalue=0)
        if minutes is None:
            return
        tickets = 0
        if scene == "tupo":
            tickets = simpledialog.askinteger("突破券数", "请输入突破券数 (0 = 无限制):", initialvalue=0, minvalue=0)
            if tickets is None:
                return
        self.task_queue.append((scene, minutes, tickets))
        duration = f"{minutes}分钟" if minutes else "无限制"
        quota = (f" - {tickets}张券" if tickets else " - 券数无限制") if scene == "tupo" else ""
        self.task_listbox.insert(tk.END, f"{scene} - {duration}{quota}")

    def delete_task(self):
        for i in reversed(list(self.task_listbox.curselection())):
            self.task_listbox.delete(i)
            del self.task_queue[i]

    def start_bots(self):
        selected = self.port_listbox.curselection()
        if not selected:
            messagebox.showwarning("警告", "请选择至少一个端口")
            return
        ports = [self.port_listbox.get(i) for i in selected]
        if self.task_queue:
            if self.scheduler_running:
                return
            self.scheduler_running = True
            threading.Thread(target=self.run_task_queue, args=(ports,), daemon=True).start()
        else:
            self.start_single_scene(ports)

    def start_single_scene(self, ports):
        scene = self.scene_var.get()
        if scene not in SCENE_BUILDERS:
            messagebox.showwarning("错误", "无效场景")
            return
        try:
            minutes = int(self.duration_var.get())
            tickets = int(self.ticket_var.get()) if scene == "tupo" else 0
            if tickets < 0 or minutes < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("错误", "时长和券数请输入非负整数，0 表示无限制")
            return
        for port in ports:
            if port not in self.bots:
                bot = SCENE_BUILDERS[scene](
                    log_fn=lambda msg, p=port: safe_log(self.log_box, f"[{p}] {msg}"),
                    port=port, **({"ticket_limit": tickets} if scene == "tupo" else {}))
                t = threading.Thread(target=bot.run, daemon=True)
                self.bots[port] = bot
                self.threads[port] = t
                t.start()
                self.root.after(500, lambda p=port, b=bot, th=t: self.check_single_task(p, b, th))
                duration = f"{minutes}分钟" if minutes else "无限制"
                safe_log(self.log_box, f"[{port}] {scene} 任务时长: {duration}")
                if minutes:
                    self.task_timers[port] = self.root.after(
                        minutes * 60 * 1000, lambda p=port, b=bot: self.finish_timed_task(p, b))

    def check_single_task(self, port, bot, thread):
        if self.bots.get(port) is not bot:
            return
        if thread.is_alive():
            self.root.after(500, lambda: self.check_single_task(port, bot, thread))
            return
        timer = self.task_timers.pop(port, None)
        if timer is not None:
            self.root.after_cancel(timer)
        self.bots.pop(port, None)
        self.threads.pop(port, None)

    def finish_timed_task(self, port, bot):
        if self.bots.get(port) is not bot:
            return
        self.task_timers.pop(port, None)
        bot.stop()
        self.bots.pop(port, None)
        self.threads.pop(port, None)
        safe_log(self.log_box, f"[{port}] 时间结束，当前任务已停止")

    def run_task_queue(self, ports):
        safe_log(self.log_box, "开始执行任务队列")
        for scene, minutes, tickets in tuple(self.task_queue):
            if not self.scheduler_running:
                break
            safe_log(self.log_box, f"任务开始: {scene} " + (f"{minutes}分钟" if minutes else "无限制"))
            for port in ports:
                bot = SCENE_BUILDERS[scene](
                    log_fn=lambda msg, p=port: safe_log(self.log_box, f"[{p}] {msg}"),
                    port=port, **({"ticket_limit": tickets} if scene == "tupo" else {}))
                t = threading.Thread(target=bot.run, daemon=True)
                self.bots[port] = bot
                self.threads[port] = t
                t.start()
            start = time.monotonic()
            while minutes == 0 or time.monotonic() - start < minutes * 60:
                if not self.scheduler_running:
                    break
                if not any(t.is_alive() for t in self.threads.values()):
                    break
                time.sleep(1)
            self.stop_current_bots()
            safe_log(self.log_box, f"任务结束: {scene}")
            if not self.scheduler_running:
                break
            time.sleep(3)
        self.scheduler_running = False
        safe_log(self.log_box, "任务队列执行完毕")

    def stop_all_bots(self):
        self.scheduler_running = False
        self.stop_current_bots()

    def stop_current_bots(self):
        for timer in self.task_timers.values():
            self.root.after_cancel(timer)
        self.task_timers.clear()
        for _, bot in self.bots.items():
            try:
                bot.stop()
            except:
                pass
        self.bots.clear()
        self.threads.clear()

    def on_closing(self):
        self.stop_all_bots()
        self.root.destroy()
