"""Presentation layer for the existing Tkinter task application."""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

SCENE_NAMES = {"tansuo": "探索", "tupo": "结界突破", "liaotupo": "寮突破", "yuhun": "御魂", "yuling": "御灵", "yeyuanhuo": "业原火", "huodong": "活动"}
BG = "#eef2f7"
INK = "#1c304b"
MUTED = "#75849a"
BLUE = "#2563eb"


def scene_name(code):
    return SCENE_NAMES.get(code, code)


def configure_styles(root):
    root.configure(background=BG)
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    root.option_add("*TCombobox*Listbox.font", ("Microsoft YaHei UI", 10))
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Microsoft YaHei UI", 10), foreground=INK, background=BG)
    style.configure("Card.TFrame", background="white")
    style.configure("Card.TLabel", background="white")
    style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 12, "bold"), background="white")
    style.configure("Hint.TLabel", foreground=MUTED, background="white", font=("Microsoft YaHei UI", 9))
    style.configure("TButton", padding=(12, 8), borderwidth=0, background="#eaf0f7", foreground=INK)
    style.map("TButton", background=[("active", "#dae5f3"), ("disabled", "#f1f4f8")], foreground=[("disabled", "#a2adbb")])
    style.configure("Primary.TButton", background=BLUE, foreground="white", font=("Microsoft YaHei UI", 10, "bold"))
    style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9bb8f5")], foreground=[("disabled", "white")])
    style.configure("Stop.TButton", background="#fff0ef", foreground="#ba4545")
    style.map("Stop.TButton", background=[("active", "#fee2e2"), ("disabled", "#f5f5f7")], foreground=[("disabled", "#a2adbb")])
    style.configure("TEntry", padding=7, fieldbackground="#f8fafc", bordercolor="#dce4ef", lightcolor="#dce4ef", darkcolor="#dce4ef")
    style.configure("TCombobox", padding=7, fieldbackground="#f8fafc", bordercolor="#dce4ef", arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", "#f8fafc")], selectbackground=[("readonly", "#f8fafc")], selectforeground=[("readonly", INK)])


def card(parent, title, subtitle=None):
    frame = ttk.Frame(parent, padding=18, style="Card.TFrame")
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(frame, text=subtitle, style="Hint.TLabel").pack(anchor="w", pady=(5, 12))
    return frame


def styled_list(parent, **kwargs):
    return tk.Listbox(parent, bg="#f8fafc", fg=INK, selectbackground="#dce9ff",
                      selectforeground="#164da8", activestyle="none", relief="flat",
                      highlightthickness=1, highlightbackground="#e2e8f0", highlightcolor=BLUE,
                      exportselection=False, borderwidth=0, font=("Microsoft YaHei UI", 10), **kwargs)


def build_ui(app):
    root = app.root
    root.title("阴阳师助手 · 任务控制台")
    root.geometry("1180x850")
    root.minsize(1020, 760)
    configure_styles(root)
    header = tk.Frame(root, background="#14243c", padx=26, pady=22)
    header.pack(fill="x")
    brand = tk.Frame(header, bg="#14243c")
    brand.pack(side="left")
    tk.Label(brand, text="阴阳师助手", bg="#14243c", fg="white", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
    tk.Label(brand, text="任务控制台  /  AUTOMATION CONSOLE", bg="#14243c", fg="#a6bad6", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(4,0))
    def settings():
        from module.settings_ui import open_settings
        open_settings(app)
    ttk.Button(header, text="设置", command=settings).pack(side="right", padx=(14,0))
    app.ui_state = tk.StringVar(value="●  就绪")
    tk.Label(header, textvariable=app.ui_state, bg="#203750", fg="#9bdcc6", padx=16, pady=9, font=("Microsoft YaHei UI", 11, "bold")).pack(side="right")
    content = ttk.Frame(root, padding=18)
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=0, minsize=266)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(1, weight=1)
    sidebar = card(content, "设备管理", "选择一个或多个模拟器端口")
    sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0,16))
    app.ui_device_count = tk.StringVar(value="0 个设备 · 已选 0 个")
    ttk.Label(sidebar, textvariable=app.ui_device_count, style="Hint.TLabel").pack(anchor="w", pady=(0,8))
    port_frame = ttk.Frame(sidebar, style="Card.TFrame")
    port_frame.pack(fill="both", expand=True)
    app.port_listbox = styled_list(port_frame, selectmode="multiple", height=9, width=23)
    app.port_listbox.pack(side="left", fill="both", expand=True)
    scroll = ttk.Scrollbar(port_frame, command=app.port_listbox.yview)
    scroll.pack(side="right", fill="y")
    app.port_listbox.configure(yscrollcommand=scroll.set)
    ttk.Button(sidebar, text="刷新设备列表", command=app.refresh_ports).pack(fill="x", pady=(12,8))
    controls = ttk.Frame(sidebar, style="Card.TFrame")
    controls.pack(fill="x")
    ttk.Button(controls, text="添加端口", command=app.add_port).pack(side="left", expand=True, fill="x", padx=(0,4))
    ttk.Button(controls, text="移除选中", command=app.delete_port).pack(side="left", expand=True, fill="x", padx=(4,0))
    tk.Frame(sidebar, bg="#e7edf5", height=1).pack(fill="x", pady=20)
    ttk.Label(sidebar, text="连接说明", style="Heading.TLabel").pack(anchor="w")
    ttk.Label(sidebar, text="• 点击端口即可选中或取消\n• 多个端口分别执行与计数\n• 未检测到设备时可手动添加", style="Hint.TLabel", justify="left").pack(anchor="w", pady=(10,0))
    top = ttk.Frame(content)
    top.grid(row=0, column=1, sticky="nsew", pady=(0,14))
    top.columnconfigure(0, weight=1)
    settings = card(top, "任务设置", "单场景直接运行；需要连续执行时，将任务加入队列")
    settings.grid(row=0,column=0,sticky="ew")
    form = ttk.Frame(settings, style="Card.TFrame")
    form.pack(fill="x")
    form.columnconfigure(0,weight=2); form.columnconfigure(1,weight=1); form.columnconfigure(2,weight=1)
    for col,text in enumerate(("任务场景", "运行时长 · 分钟", "突破券额度 · 张")):
        label=ttk.Label(form,text=text,style="Card.TLabel")
        label.grid(row=0,column=col,sticky="w",padx=(0,18))
        if col==2:
            app.ui_limit_label=label
    app.scene_var = tk.StringVar(value="tansuo")
    app.ui_scene_var = tk.StringVar(value=scene_name("tansuo"))
    app.duration_var = tk.StringVar(value="0")
    app.ticket_var = tk.StringVar(value="0")
    app.scene_dropdown = ttk.Combobox(form,textvariable=app.ui_scene_var,
                                    values=[scene_name(k) for k in app.scene_codes],state="readonly",width=16)
    app.scene_dropdown.grid(row=1,column=0,sticky="ew",padx=(0,18),pady=8)
    ttk.Entry(form,textvariable=app.duration_var,width=12).grid(row=1,column=1,sticky="ew",padx=(0,18))
    app.ui_ticket_entry = ttk.Entry(form,textvariable=app.ticket_var,width=12)
    app.ui_ticket_entry.grid(row=1,column=2,sticky="ew")
    def sync_scene(*args):
        code=next((k for k in app.scene_codes if scene_name(k)==app.ui_scene_var.get()),"tansuo")
        app.scene_var.set(code)
        app.ui_ticket_entry.configure(state="normal" if code in ("tupo", "liaotupo") else "disabled")
        app.ui_limit_label.configure(text="执行次数 · 次" if code=="liaotupo" else "突破券额度 · 张")
    app.ui_scene_var.trace_add("write",sync_scene)
    sync_scene()
    ttk.Label(settings,text="0 表示无限制；结界突破按券数限制，寮突破按执行次数限制。",style="Hint.TLabel").pack(anchor="w",pady=(0,0))
    tasks = card(top,"执行队列", "队列按顺序执行；探索与突破之间会自动返回主线并确认入场")
    tasks.grid(row=1,column=0,sticky="ew",pady=(14,0))
    task_frame = ttk.Frame(tasks,style="Card.TFrame")
    task_frame.pack(fill="x")
    app.task_listbox = styled_list(task_frame,height=3,selectmode="extended")
    app.task_listbox.pack(side="left",fill="both",expand=True)
    task_scroll=ttk.Scrollbar(task_frame,command=app.task_listbox.yview)
    task_scroll.pack(side="right",fill="y")
    app.task_listbox.configure(yscrollcommand=task_scroll.set)
    task_controls=ttk.Frame(tasks,style="Card.TFrame")
    task_controls.pack(fill="x",pady=(10,0))
    ttk.Button(task_controls,text="＋ 添加任务",command=app.add_task).pack(side="left")
    ttk.Button(task_controls,text="删除选中",command=app.delete_task).pack(side="left",padx=8)
    app.ui_queue_count=tk.StringVar(value="0 项任务")
    ttk.Label(task_controls,textvariable=app.ui_queue_count,style="Hint.TLabel").pack(side="right")
    logs=card(content,"运行日志")
    logs.grid(row=1,column=1,sticky="nsew")
    toolbar=ttk.Frame(logs,style="Card.TFrame")
    toolbar.pack(fill="x",pady=(8,8))
    ttk.Label(toolbar,text="查看设备连接、图片匹配和点击结果",style="Hint.TLabel").pack(side="left")
    def clear_log():
        app.log_box.configure(state="normal"); app.log_box.delete("1.0","end"); app.log_box.configure(state="disabled")
    ttk.Button(toolbar,text="清空显示",command=clear_log).pack(side="right")
    app.log_box=scrolledtext.ScrolledText(logs,width=65,height=7,state="disabled",font=("Consolas",10),
                                         bg="#f8fafc",fg="#34465e",relief="flat",borderwidth=0,padx=12,pady=10,insertbackground=INK)
    app.log_box.pack(fill="both",expand=True)
    footer=ttk.Frame(root,padding=(22,14))
    footer.pack(side="bottom", fill="x", before=content)
    app.ui_summary=tk.StringVar(value="请选择设备后开始执行")
    ttk.Label(footer,textvariable=app.ui_summary,foreground=MUTED).pack(side="left")
    app.ui_stop_button=ttk.Button(footer,text="停止全部",command=app.stop_all_bots,style="Stop.TButton")
    app.ui_stop_button.pack(side="right",padx=(10,0))
    ttk.Button(footer,text="▶  开始执行",command=app.start_bots,style="Primary.TButton").pack(side="right")
    app.ui_poll_id=root.after(300,lambda:update_status(app))
    app.refresh_ports()


def update_status(app):
    if getattr(app,"ui_closing",False):
        return
    selected=len(app.port_listbox.curselection())
    count=app.port_listbox.size()
    active=sum(thread.is_alive() for thread in tuple(app.threads.values()))
    app.ui_device_count.set(f"{count} 个设备 · 已选 {selected} 个")
    app.ui_queue_count.set(f"{len(app.task_queue)} 项任务")
    app.ui_state.set("●  队列执行中" if app.scheduler_running else (f"●  {active} 个设备运行中" if active else "●  就绪"))
    mode=f"任务队列 · {len(app.task_queue)} 项" if app.task_queue else f"单场景 · {scene_name(app.scene_var.get())}"
    app.ui_summary.set(f"{mode}    |    已选 {selected} 个设备    |    运行 {active} 个")
    app.ui_stop_button.configure(state="normal" if active or app.scheduler_running else "disabled")
    app.ui_poll_id=app.root.after(500,lambda:update_status(app))


def show_task_dialog(app):
    """Return the same (scene, minutes, tickets) tuple as the original dialogs."""
    window=tk.Toplevel(app.root)
    window.title("添加队列任务")
    window.resizable(False,False)
    window.transient(app.root)
    panel=ttk.Frame(window,padding=24,style="Card.TFrame")
    panel.pack(fill="both",expand=True)
    ttk.Label(panel,text="添加队列任务",style="Heading.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,6))
    ttk.Label(panel,text="设置此任务的运行时长和突破券额度",style="Hint.TLabel").grid(row=1,column=0,columnspan=2,sticky="w",pady=(0,20))
    scene=tk.StringVar(value=scene_name(app.scene_var.get()))
    minutes=tk.StringVar(value=app.duration_var.get())
    tickets=tk.StringVar(value=app.ticket_var.get())
    fields=(("任务场景",ttk.Combobox(panel,textvariable=scene,values=[scene_name(k) for k in app.scene_codes],state="readonly",width=21)),
            ("运行时长（分钟）",ttk.Entry(panel,textvariable=minutes,width=24)),
            ("突破券额度（张）",ttk.Entry(panel,textvariable=tickets,width=24)))
    for i,(label,widget) in enumerate(fields,2):
        field_label=ttk.Label(panel,text=label,style="Card.TLabel")
        field_label.grid(row=i,column=0,sticky="w",padx=(0,20),pady=9)
        if i==4:
            limit_label=field_label
        widget.grid(row=i,column=1,sticky="ew",pady=9)
    def sync(*args):
        guild=scene.get()==scene_name("liaotupo")
        fields[2][1].configure(state="normal" if guild or scene.get()==scene_name("tupo") else "disabled")
        limit_label.configure(text="执行次数（次）" if guild else "突破券额度（张）")
    scene.trace_add("write",sync);sync()
    ttk.Label(panel,text="0 表示无限制；券数或执行次数按每个端口独立计算。",style="Hint.TLabel").grid(row=5,column=0,columnspan=2,sticky="w",pady=10)
    result=[]
    def confirm():
        try:
            code=next(k for k in app.scene_codes if scene_name(k)==scene.get())
            duration=int(minutes.get()); quota=int(tickets.get()) if code in ("tupo", "liaotupo") else 0
            if duration<0 or quota<0: raise ValueError
        except (ValueError,StopIteration):
            messagebox.showwarning("输入有误","时长和券数请输入非负整数。",parent=window)
            return
        result.append((code,duration,quota));window.destroy()
    buttons=ttk.Frame(panel,style="Card.TFrame")
    buttons.grid(row=6,column=0,columnspan=2,sticky="e",pady=(14,0))
    ttk.Button(buttons,text="取消",command=window.destroy).pack(side="left",padx=8)
    ttk.Button(buttons,text="加入队列",command=confirm,style="Primary.TButton").pack(side="left")
    window.bind("<Escape>",lambda event:window.destroy())
    window.bind("<Return>",lambda event:confirm())
    window.update_idletasks()
    x=app.root.winfo_rootx()+(app.root.winfo_width()-window.winfo_reqwidth())//2
    y=app.root.winfo_rooty()+(app.root.winfo_height()-window.winfo_reqheight())//2
    window.geometry(f"+{max(0,x)}+{max(0,y)}")
    window.grab_set(); fields[0][1].focus_set()
    app.root.wait_window(window)
    return result[0] if result else None
