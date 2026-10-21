"""Independent settings window, with device actions performed off the UI thread."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from module.desktop_ui import scene_name, BG, card
from module.base_clicker import safe_log
from module.settings_store import (get_resolution, read_preferences, validate_port,
    validate_resolution, inspect_resolution, apply_resolution, read_thresholds, save_thresholds)


def open_settings(app):
    current = getattr(app, "settings_window", None)
    if current is not None and current.window.winfo_exists():
        current.window.deiconify()
        current.window.lift()
        current.window.focus_set()
        return
    app.settings_window = SettingsWindow(app)


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("设置 · 阴阳师助手")
        self.window.geometry("850x720")
        self.window.minsize(760, 650)
        self.window.configure(background=BG)
        self.window.transient(app.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.busy = False
        self.events = queue.Queue()
        self.dirty = False
        self.loading = False
        self.scene = app.scene_var.get()
        self.entries = {}
        heading = ttk.Frame(self.window, padding=(24, 20))
        heading.pack(fill="x")
        ttk.Label(heading, text="设置", font=("Microsoft YaHei UI", 19, "bold")).pack(anchor="w")
        ttk.Label(heading, text="管理模拟器显示尺寸与各场景的识图参数", foreground="#75849a").pack(anchor="w", pady=(6,0))
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill="both", expand=True, padx=20, pady=(0,16))
        resolution = ttk.Frame(tabs, padding=16)
        thresholds = ttk.Frame(tabs, padding=16)
        tabs.add(resolution, text="  模拟器分辨率  ")
        tabs.add(thresholds, text="  场景阈值  ")
        self.build_resolution(resolution)
        self.build_thresholds(thresholds)
        self.poll_id = self.window.after(100, self.poll)

    def build_resolution(self, parent):
        panel = card(parent, "MuMu 显示分辨率", "选择端口后读取实际尺寸，或应用自定义宽高")
        panel.pack(fill="both", expand=True)
        ports = list(self.app.port_listbox.get(0, "end"))
        try:
            ports.extend(p for p in read_preferences().get("resolutions", {}) if p not in ports)
        except (ValueError, OSError):
            pass
        selected = self.app.port_listbox.curselection()
        initial = self.app.port_listbox.get(selected[0]) if selected else (ports[0] if ports else "")
        self.port_var = tk.StringVar(value=initial)
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        form = ttk.Frame(panel, style="Card.TFrame")
        form.pack(fill="x", pady=(8,18))
        ttk.Label(form, text="模拟器端口", style="Card.TLabel").grid(row=0,column=0,sticky="w",pady=8,padx=(0,18))
        ttk.Combobox(form,textvariable=self.port_var,values=ports,width=18).grid(row=0,column=1,sticky="w")
        self.read_button = ttk.Button(form,text="读取当前分辨率",command=self.read_device)
        self.read_button.grid(row=0,column=2,padx=12)
        self.current_var = tk.StringVar(value="尚未读取设备")
        ttk.Label(panel,textvariable=self.current_var,style="Hint.TLabel",wraplength=690).pack(anchor="w",pady=(0,18))
        presets=ttk.Frame(panel,style="Card.TFrame")
        presets.pack(fill="x",pady=(0,14))
        ttk.Label(presets,text="常用尺寸",style="Card.TLabel").pack(side="left",padx=(0,16))
        for width,height in [(1600,900),(1280,720),(1920,1080)]:
            ttk.Button(presets,text=f"{width} × {height}",command=lambda w=width,h=height:self.set_dimensions(w,h)).pack(side="left",padx=(0,8))
        dimensions=ttk.Frame(panel,style="Card.TFrame")
        dimensions.pack(fill="x",pady=(0,20))
        ttk.Label(dimensions,text="宽度（像素）",style="Card.TLabel").grid(row=0,column=0,sticky="w",padx=(0,24))
        ttk.Label(dimensions,text="高度（像素）",style="Card.TLabel").grid(row=0,column=1,sticky="w")
        ttk.Entry(dimensions,textvariable=self.width_var,width=18).grid(row=1,column=0,padx=(0,24),pady=8)
        ttk.Entry(dimensions,textvariable=self.height_var,width=18).grid(row=1,column=1,pady=8)
        ttk.Label(panel,text="应用会修改该模拟器的安卓显示尺寸，并保存脚本点击坐标尺寸。\n请先停止该设备上的任务。改变尺寸后，原模板图片可能需要重新截取。\n重启 MuMu 后，可再次读取尺寸确认显示设置是否保留。",style="Hint.TLabel",wraplength=690,justify="left").pack(anchor="w",pady=(0,18))
        self.apply_button=ttk.Button(panel,text="应用到模拟器并保存",command=self.apply_device,style="Primary.TButton")
        self.apply_button.pack(anchor="w")
        self.resolution_status=tk.StringVar(value="设置按端口保存，下次启动任务使用。")
        ttk.Label(panel,textvariable=self.resolution_status,style="Hint.TLabel",wraplength=690).pack(anchor="w",pady=(16,0))
        self.port_var.trace_add("write",lambda *args:self.load_dimensions())
        self.load_dimensions()

    def set_dimensions(self,width,height):
        self.width_var.set(str(width)); self.height_var.set(str(height))

    def load_dimensions(self):
        self.set_dimensions(*get_resolution(self.port_var.get().strip()))
        self.current_var.set("尚未读取此端口；下方显示已保存尺寸或默认 1600 × 900")

    def device_running(self,port):
        thread=self.app.threads.get(port)
        return self.app.scheduler_running or (thread is not None and thread.is_alive())

    def dispatch(self,kind,work,port):
        if self.busy:
            return
        self.busy=True
        self.read_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.resolution_status.set("正在读取设备…" if kind=="read" else "正在应用并验证分辨率，请稍候…")
        def run():
            try:
                self.events.put((kind,port,work(),None))
            except Exception as exc:
                self.events.put((kind,port,None,str(exc)))
        threading.Thread(target=run,daemon=True).start()

    def read_device(self):
        try:
            port=validate_port(self.port_var.get())
        except ValueError as exc:
            messagebox.showwarning("端口无效",str(exc),parent=self.window);return
        self.dispatch("read",lambda:inspect_resolution(port),port)

    def apply_device(self):
        try:
            port=validate_port(self.port_var.get())
            width,height=validate_resolution(self.width_var.get(),self.height_var.get())
        except (ValueError,TypeError) as exc:
            messagebox.showwarning("输入有误",str(exc),parent=self.window);return
        if self.device_running(port):
            messagebox.showinfo("请先停止任务","停止任务后再修改分辨率，避免点击位置发生变化。",parent=self.window)
            return
        self.dispatch("apply",lambda:apply_resolution(port,width,height),port)

    def poll(self):
        try:
            kind,port,result,error=self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy=False
            self.read_button.configure(state="normal")
            self.apply_button.configure(state="normal")
            if error:
                self.resolution_status.set(f"端口 {port} 操作失败：{error}")
                messagebox.showerror("设备操作失败",error,parent=self.window)
            elif kind=="read":
                width,height=result["display_size"]
                if self.port_var.get().strip()==port:
                    self.set_dimensions(width,height)
                    self.current_var.set(f"端口 {port} 实际截图：{width} × {height}    |    {result['details'].replace(chr(10), ' · ')}")
                self.resolution_status.set("当前尺寸已读取；修改后点击应用才会保存。")
            else:
                width,height=result
                if self.port_var.get().strip()==port:
                    self.set_dimensions(width,height)
                    self.current_var.set(f"端口 {port} 已验证截图：{width} × {height}")
                self.resolution_status.set(f"已应用并保存 {port} 的分辨率：{width} × {height}")
                safe_log(self.app.log_box,f"[{port}] 分辨率设置已保存: {width}×{height}，下次任务生效")
        self.poll_id=self.window.after(100,self.poll)

    def build_thresholds(self,parent):
        panel=card(parent,"场景识图参数","按场景独立保存，已运行的任务需停止后重新开始才会使用新值")
        panel.pack(fill="both",expand=True)
        select=ttk.Frame(panel,style="Card.TFrame");select.pack(fill="x",pady=(0,12))
        ttk.Label(select,text="选择场景",style="Card.TLabel").pack(side="left",padx=(0,14))
        self.scene_var=tk.StringVar(value=scene_name(self.scene))
        box=ttk.Combobox(select,textvariable=self.scene_var,values=[scene_name(k) for k in self.app.scene_codes],state="readonly",width=18)
        box.pack(side="left");box.bind("<<ComboboxSelected>>",self.switch_scene)
        ttk.Label(panel,text="阈值通常为 0～1，越高越严格；大于 1 可禁用对应模板。点击间隔单位为秒。",style="Hint.TLabel",wraplength=690).pack(anchor="w",pady=(0,12))
        viewport=ttk.Frame(panel,style="Card.TFrame");viewport.pack(fill="both",expand=True)
        self.canvas=tk.Canvas(viewport,background="white",highlightthickness=0,height=240)
        scroll=ttk.Scrollbar(viewport,command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left",fill="both",expand=True);scroll.pack(side="right",fill="y")
        self.fields=ttk.Frame(self.canvas,style="Card.TFrame")
        window_id=self.canvas.create_window((0,0),window=self.fields,anchor="nw")
        self.fields.bind("<Configure>",lambda event:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",lambda event:self.canvas.itemconfigure(window_id,width=event.width))
        self.threshold_status=tk.StringVar()
        ttk.Label(panel,textvariable=self.threshold_status,style="Hint.TLabel",wraplength=690).pack(anchor="w",pady=12)
        tools=ttk.Frame(panel,style="Card.TFrame");tools.pack(fill="x")
        ttk.Button(tools,text="重新读取",command=self.reload_scene).pack(side="left")
        ttk.Button(tools,text="保存当前场景",command=self.save_scene,style="Primary.TButton").pack(side="right")
        self.load_scene()

    def mark_dirty(self,*args):
        if not self.loading:
            self.dirty=True
            self.threshold_status.set("有未保存的修改")

    def load_scene(self):
        try:
            values=read_thresholds(self.scene)
        except (OSError,ValueError) as exc:
            messagebox.showerror("读取失败",str(exc),parent=self.window);return
        self.loading=True
        for child in self.fields.winfo_children():child.destroy()
        self.entries={}
        self.fields.columnconfigure(1,weight=1)
        for row,(key,value) in enumerate(values.items()):
            label="点击间隔（秒）" if key=="sleep_time" else key
            ttk.Label(self.fields,text=label,style="Card.TLabel").grid(row=row,column=0,sticky="w",padx=(4,24),pady=5)
            variable=tk.StringVar(value=f"{value:g}")
            self.entries[key]=variable
            entry=ttk.Entry(self.fields,textvariable=variable,width=15)
            entry.grid(row=row,column=1,sticky="w",pady=5)
            variable.trace_add("write",self.mark_dirty)
            def wheel(event):
                self.canvas.yview_scroll(-int(event.delta/120),"units")
                return "break"
            entry.bind("<MouseWheel>",wheel)
        self.canvas.yview_moveto(0)
        self.loading=False;self.dirty=False
        self.threshold_status.set(f"当前配置：yys/{self.scene}/阈值配置要求.txt")

    def save_scene(self):
        try:
            save_thresholds(self.scene,{key:var.get() for key,var in self.entries.items()})
        except (ValueError,OSError) as exc:
            messagebox.showerror("保存失败",str(exc),parent=self.window);return False
        self.dirty=False
        self.threshold_status.set(f"{scene_name(self.scene)} 配置已保存，下次启动任务生效")
        safe_log(self.app.log_box,f"{scene_name(self.scene)} 阈值配置已保存")
        return True

    def resolve_dirty(self):
        if not self.dirty:return True
        answer=messagebox.askyesnocancel("未保存的修改","是否保存当前场景的修改？",parent=self.window)
        if answer is None:return False
        return self.save_scene() if answer else True

    def switch_scene(self,event=None):
        if not self.resolve_dirty():
            self.scene_var.set(scene_name(self.scene));return
        self.scene=next(k for k in self.app.scene_codes if scene_name(k)==self.scene_var.get())
        self.load_scene()

    def reload_scene(self):
        if self.resolve_dirty():self.load_scene()

    def close(self):
        if self.busy:
            messagebox.showinfo("设备操作进行中","请等待设备操作完成后关闭设置窗口。",parent=self.window);return
        if not self.resolve_dirty():return
        self.window.after_cancel(self.poll_id)
        self.window.destroy()
        self.app.settings_window=None
