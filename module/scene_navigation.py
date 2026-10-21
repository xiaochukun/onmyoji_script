"""Verified navigation between the mainline list and personal/guild raids."""
import time
from pathlib import Path
import subprocess

import cv2
import numpy as np
from module.settings_store import read_thresholds

ROOT=Path(__file__).resolve().parents[1]


def read_image(path):
    try:return cv2.imdecode(np.fromfile(str(path),np.uint8),cv2.IMREAD_GRAYSCALE)
    except (OSError,ValueError,cv2.error):return None


class SceneNavigator:
    def __init__(self,port,cancel,log):
        self.port=str(port);self.cancel=cancel;self.log=log
        self.templates={}
        for key in ("raid_entry","raid_page","raid_close","guild_close","personal_tab","personal_active","guild_tab","guild_active"):
            self.templates[key]=read_image(ROOT/"yys"/"navigation"/(key+".png"))
        self.templates["mainline"]=read_image(ROOT/"yys"/"tansuo"/"mainline_page.png")
        self.templates["explore_back"]=read_image(ROOT/"yys"/"tansuo"/"img_8.jpg")
        self.templates["confirm"]=read_image(ROOT/"yys"/"tansuo"/"img_9.jpg")
        self.templates["raid_medals"]=read_image(ROOT/"yys"/"tupo"/"img_1.jpg")
        self.transition_thresholds = {}
        for scene, names in (("tansuo", ("img_3",)), ("tupo", ("img_3", "img_7", "img_4")), ("liaotupo", ("img_3", "img_7", "img_4"))):
            self.transition_thresholds[scene] = read_thresholds(scene)
            for name in names:
                self.templates[f"{scene}/{name}"] = read_image(ROOT/"yys"/scene/(name+".jpg"))

    def command(self,*args):
        if self.cancel.is_set():raise InterruptedError("任务已停止")
        return subprocess.run([str(ROOT/"adb.exe"),"-s",f"127.0.0.1:{self.port}",*map(str,args)],
                              capture_output=True,check=True,timeout=15,
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

    def connect(self):
        if self.cancel.is_set():raise InterruptedError("任务已停止")
        subprocess.run([str(ROOT/"adb.exe"),"connect",f"127.0.0.1:{self.port}"],
                       capture_output=True,check=True,timeout=15,
                       creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        self.command("get-state")

    def screenshot(self):
        result=self.command("exec-out","screencap","-p")
        image=cv2.imdecode(np.frombuffer(result.stdout,np.uint8),cv2.IMREAD_GRAYSCALE)
        if image is None:raise RuntimeError("场景切换截图失败")
        return image

    def find(self,name,image,region=(0,0,1,1),threshold=.86):
        template=self.templates.get(name)
        if template is None:return None
        h,w=image.shape[:2]
        x1,y1,x2,y2=int(w*region[0]),int(h*region[1]),int(w*region[2]),int(h*region[3])
        search=image[y1:y2,x1:x2]
        best=None
        for scale in (.6,.65,.7,.75,.8,.85,.9,.95,1.,1.05,1.1,1.15,1.2,1.25,1.3,1.4,1.5,1.6):
            width,height=max(1,round(template.shape[1]*scale)),max(1,round(template.shape[0]*scale))
            if width>search.shape[1] or height>search.shape[0]:continue
            resized=cv2.resize(template,(width,height))
            _,score,_,loc=cv2.minMaxLoc(cv2.matchTemplate(search,resized,cv2.TM_CCOEFF_NORMED))
            if score>=threshold and (best is None or score>best[0]):
                best=(score,(x1+loc[0]+width//2,y1+loc[1]+height//2))
        return best[1] if best else None

    def mainline(self,image):
        return self.find("mainline",image,(.80,.19,1,.32),.9) is not None

    def raid_page(self,image):
        return (self.find("raid_page",image,(.32,.06,.66,.2),.84) is not None
                or self.find("guild_active",image,(.90,.25,1,.75),.90) is not None)

    def raid_ready(self,image,scene):
        if self.mainline(image):
            return False
        if scene == "tupo":
            threshold = read_thresholds("tupo").get("img_1", .6)
            if self.find("raid_medals", image, threshold=threshold) is not None:
                self.log(f"已识别 yys/tupo/img_1.jpg（阈值 {threshold}），执行原结界突破流程")
                return True
        tab="guild_active" if scene=="liaotupo" else "personal_active"
        return self.raid_page(image) and self.find(tab,image,(.90,.25,1,.75),.88) is not None

    def click(self,name,point):
        self.command("shell","input","tap",*point)
        self.log(f"场景切换：点击 {name}")

    def settlement_action(self, image, source=None):
        """Finish result screens during navigation without starting another attempt."""
        scenes = (source,) if source in ("tansuo", "tupo", "liaotupo") else ("tansuo", "tupo", "liaotupo")
        for scene in scenes:
            names = ("img_3",) if scene == "tansuo" else ("img_3", "img_7", "img_4")
            for name in names:
                point = self.find(f"{scene}/{name}", image,
                                  threshold=max(.85, self.transition_thresholds[scene].get(name, .7)))
                if point is not None:
                    return f"{scene}/{name}.jpg（切换前继续结算）", point
        return None

    def exit_action(self, image, source=None):
        if source in (None, "tansuo"):
            point=self.find("confirm",image,(.45,.40,.75,.70),.88)
            if point is not None:
                return "img_9.jpg（确认退出探索）",point
        for name in ("raid_close", "guild_close"):
            point=self.find(name,image,(.88,.06,1,.3),.88)
            if point is not None:
                return name+".png（粉红色×）",point
        return None

    def ensure_mainline(self,source=None,timeout=60):
        self.log("场景切换：结算后退出当前玩法，返回主线页面")
        start=time.monotonic();stable=0;last_click=0;attempts=0
        while not self.cancel.is_set() and time.monotonic()-start<timeout:
            image=self.screenshot()
            # Explicit modal/close buttons take priority over generic result text.
            pending=self.exit_action(image,source)
            if pending is None and self.mainline(image):
                stable+=1
                if stable>=2:
                    self.log("场景切换完成：已确认 mainline_page.png")
                    return True
            else:
                stable=0
                if time.monotonic()-last_click>=1.5:
                    if pending is None:
                        pending=self.settlement_action(image,source)
                    if pending is None and source in (None,"tansuo"):
                        point=self.find("explore_back",image,(0,0,.2,.22),.86)
                        if point is not None:
                            pending="img_8.jpg（退出探索，随后确认）",point
                    if pending is not None:
                        attempts+=1
                        if attempts>12:raise RuntimeError("返回主线重复点击过多，停止队列")
                        self.click(*pending)
                    else:
                        self.log(f"场景切换：等待 {source or '当前场景'} 结算图片或退出按钮，尚未确认主线")
                    last_click=time.monotonic()
            self.cancel.wait(.5)
        if self.cancel.is_set():return False
        raise RuntimeError("返回主线超时，未确认 mainline_page.png；队列已停止")

    def prepare(self,target,source=None,timeout=60):
        self.connect()
        if target not in ("tansuo","tupo","liaotupo"):
            if source is None:return True
            raise RuntimeError(f"暂未配置 {target} 的自动切换路线，不能直接接续")
        if target in ("tupo","liaotupo"):
            if self.raid_ready(self.screenshot(),target):
                if target == "tupo":
                    return not self.cancel.is_set()
                if self.cancel.wait(.3):return False
                if self.raid_ready(self.screenshot(),target):
                    self.log("已确认突破页面，无需重复入场")
                    return True
        if not self.ensure_mainline(source,timeout):return False
        if target=="tansuo":return True
        self.log("场景切换：从主线进入"+("寮突破" if target=="liaotupo" else "结界突破"))
        start=time.monotonic();stable=0;last_click=0;attempts=0
        while not self.cancel.is_set() and time.monotonic()-start<timeout:
            image=self.screenshot()
            if self.raid_ready(image,target):
                stable+=1
                if target == "tupo" or stable>=2:
                    self.log("场景切换完成：开始原突破任务 img_1 → img_2 → img_4 → img_3 / img_7")
                    return True
            else:
                stable=0
                if time.monotonic()-last_click>=1.5:
                    if self.raid_page(image):
                        name="guild_tab" if target=="liaotupo" else "personal_tab"
                        point=self.find(name,image,(.90,.25,1,.75),.82)
                    elif self.mainline(image):
                        name="raid_entry"
                        point=self.find(name,image,(.1,.8,.4,1),.86)
                    else:
                        pending=self.settlement_action(image, source)
                        if pending is None:
                            point=None
                            self.log("场景切换：等待入口、突破 img_1.jpg 或结算图片")
                        else:
                            name,point=pending
                    if point:
                        attempts+=1
                        if attempts>6:raise RuntimeError("进入突破重复点击过多，停止队列")
                        self.click(name+".png",point);last_click=time.monotonic()
            self.cancel.wait(.5)
        if self.cancel.is_set():return False
        raise RuntimeError("进入突破超时；未确认目标页面，队列已停止")
