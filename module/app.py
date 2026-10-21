import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import threading
import subprocess
import time

from module.base_clicker import safe_log, install_log_queue
from module.scenes import SCENE_BUILDERS
from module.desktop_ui import build_ui, show_task_dialog, scene_name
from module.queue_runner import QueueRunner


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MuMu 自动点击器 - 模块化版")
        self.bots = {}
        self.threads = {}
        self.task_timers = {}
        self.task_queue = []
        self.scheduler_running = False
        self.scheduler_thread = None
        self.queue_cancel = threading.Event()
        self.queue_runners = {}
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def build_ui(self):
        self.scene_codes = tuple(SCENE_BUILDERS)
        build_ui(self)
        install_log_queue(self.log_box)

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
        task = show_task_dialog(self)
        if task is None:
            return
        scene, minutes, tickets = task
        self.task_queue.append(task)
        duration = f"{minutes} 分钟" if minutes else "不限时长"
        if scene == "liaotupo":
            quota = f"  ·  最多 {tickets} 次" if tickets else "  ·  次数不限"
        else:
            quota = (f"  ·  {tickets} 张突破券" if tickets else "  ·  券数不限") if scene == "tupo" else ""
        self.task_listbox.insert(tk.END, f"  {scene_name(scene)}  ·  {duration}{quota}")

    def delete_task(self):
        for i in reversed(list(self.task_listbox.curselection())):
            self.task_listbox.delete(i)
            del self.task_queue[i]

    def start_bots(self):
        settings = getattr(self, "settings_window", None)
        if settings is not None and settings.busy:
            messagebox.showinfo("设置进行中", "请等待设备设置完成后再启动任务。", parent=self.root)
            return
        if (self.scheduler_thread is not None and self.scheduler_thread.is_alive()) or any(t.is_alive() for t in tuple(self.threads.values())):
            messagebox.showinfo("任务正在运行", "请先停止现有任务并等待退出，再启动新的任务。", parent=self.root)
            return
        selected = self.port_listbox.curselection()
        if not selected:
            messagebox.showwarning("警告", "请选择至少一个端口")
            return
        ports = [self.port_listbox.get(i) for i in selected]
        if self.task_queue:
            if self.scheduler_running:
                return
            self.scheduler_running = True
            self.queue_cancel.clear()
            tasks = tuple(self.task_queue)
            self.scheduler_thread = threading.Thread(target=self.run_task_queue, args=(ports, tasks), daemon=True)
            self.scheduler_thread.start()
        else:
            self.start_single_scene(ports)

    def start_single_scene(self, ports):
        scene = self.scene_var.get()
        if scene not in SCENE_BUILDERS:
            messagebox.showwarning("错误", "无效场景")
            return
        try:
            minutes = int(self.duration_var.get())
            tickets = int(self.ticket_var.get()) if scene in ("tupo", "liaotupo") else 0
            if tickets < 0 or minutes < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("错误", "时长和券数请输入非负整数，0 表示无限制")
            return
        for port in ports:
            if port not in self.bots:
                bot = SCENE_BUILDERS[scene](
                    log_fn=lambda msg, p=port: safe_log(self.log_box, f"[{p}] {msg}"),
                    port=port, **({"ticket_limit": tickets} if scene in ("tupo", "liaotupo") else {}))
                t = threading.Thread(target=bot.run, daemon=True)
                self.bots[port] = bot
                self.threads[port] = t
                t.start()
                self.root.after(500, lambda p=port, b=bot, th=t: self.check_single_task(p, b, th))
                duration = f"{minutes}分钟" if minutes else "无限制"
                safe_log(self.log_box, f"[{port}] {scene} 任务时长: {duration}")
                if minutes:
                    self.arm_task_timer(port, bot, minutes)

    def arm_task_timer(self, port, bot, minutes):
        if self.bots.get(port) is not bot or bot.cancel_requested.is_set():
            return
        ready = getattr(bot, "task_ready", None)
        if ready is not None and not ready.is_set():
            self.task_timers[port] = self.root.after(100, lambda: self.arm_task_timer(port, bot, minutes))
            return
        safe_log(self.log_box, f"[{port}] 入场完成，开始任务计时")
        self.task_timers[port] = self.root.after(minutes * 60 * 1000, lambda: self.finish_timed_task(port, bot))

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
        safe_log(self.log_box, f"[{port}] 时间结束，正在停止当前任务")

    def run_task_queue(self, ports, tasks=None):
        safe_log(self.log_box, "开始执行任务队列，任务切换将确认实际游戏页面")
        runners=[]
        try:
            for port in ports:
                if self.queue_cancel.is_set():
                    break
                def on_bot(bot, p=port):
                    if bot is None:
                        self.bots.pop(p,None)
                    else:
                        self.bots[p]=bot
                runner=QueueRunner(port,tuple(self.task_queue) if tasks is None else tasks,
                                   self.queue_cancel,
                                   lambda message,p=port:safe_log(self.log_box,f"[{p}] {message}"),on_bot)
                self.queue_runners[port]=runner
                self.threads[port]=runner.thread
                runners.append(runner)
                runner.start()
            for runner in runners:
                runner.thread.join()
        finally:
            for runner in runners:
                self.bots.pop(runner.port,None)
                if self.threads.get(runner.port) is runner.thread:
                    self.threads.pop(runner.port,None)
                self.queue_runners.pop(runner.port,None)
            self.scheduler_running=False
            safe_log(self.log_box,"所有设备的任务队列已结束")

    def stop_all_bots(self):
        self.scheduler_running = False
        self.queue_cancel.set()
        for runner in tuple(self.queue_runners.values()):
            runner.stop()
        self.stop_current_bots()

    def stop_current_bots(self):
        for timer in tuple(self.task_timers.values()):
            self.root.after_cancel(timer)
        self.task_timers.clear()
        for port, bot in tuple(self.bots.items()):
            try:
                bot.stop()
            except Exception:
                pass
            thread=self.threads.get(port)
            if thread is None or not thread.is_alive():
                self.bots.pop(port,None)
                self.threads.pop(port,None)

    def on_closing(self):
        settings = getattr(self, "settings_window", None)
        if settings is not None:
            settings.close()
            if getattr(self, "settings_window", None) is not None:
                return
        self.ui_closing = True
        if getattr(self, "ui_poll_id", None):
            self.root.after_cancel(self.ui_poll_id)
        self.stop_all_bots()
        self.ui_summary.set("正在停止设备任务，等待日志保存后关闭…")
        def finish_close():
            scheduler_alive=self.scheduler_thread is not None and self.scheduler_thread.is_alive()
            if scheduler_alive or any(t.is_alive() for t in tuple(self.threads.values())):
                self.root.after(100,finish_close)
                return
            self.root.destroy()
        finish_close()
