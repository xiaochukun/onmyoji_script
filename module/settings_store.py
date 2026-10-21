"""Local preferences, scene configuration and explicit ADB display operations."""
import json
import math
import os
import re
import struct
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "settings.local.json"
CONFIG_NAME = "阈值配置要求.txt"


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def validate_resolution(width, height):
    width, height = int(width), int(height)
    if not (320 <= width <= 7680 and 320 <= height <= 7680):
        raise ValueError("宽和高须为 320 至 7680 的整数")
    return width, height


def validate_port(port):
    port = str(port).strip()
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("请输入 1 至 65535 的模拟器端口号")
    return str(int(port))


def read_preferences():
    if not PREFERENCES.exists():
        return {"resolutions": {}}
    data = json.loads(PREFERENCES.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("resolutions", {}), dict):
        raise ValueError("本地分辨率设置格式不正确")
    return data


def get_resolution(port):
    try:
        value = read_preferences().get("resolutions", {}).get(str(port))
        if value is not None:
            return validate_resolution(value["width"], value["height"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 1600, 900


def save_resolution(port, width, height):
    port = validate_port(port)
    width, height = validate_resolution(width, height)
    data = read_preferences()
    data.setdefault("resolutions", {})[port] = {"width": width, "height": height}
    atomic_write(PREFERENCES, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def threshold_path(scene):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", scene):
        raise ValueError("无效场景名称")
    return ROOT / "yys" / scene / CONFIG_NAME


def read_thresholds(scene):
    path = threshold_path(scene)
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([a-zA-Z0-9_]+)\s*[:=]\s*(.*?)\s*$", line)
            if not match:
                continue
            try:
                values[match[1]] = float(match[2])
            except ValueError:
                continue
    default = 0.7 if scene == "tansuo" else 0.4
    for image in sorted(path.parent.glob("img_*.jpg")):
        if re.fullmatch(r"img_\d+", image.stem):
            values.setdefault(image.stem, default)
    if scene in ("tupo", "liaotupo"):
        values.setdefault("award", 0.85)
        for image in sorted((path.parent / "award").glob("*")):
            if image.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                values.setdefault("award_" + image.stem, values["award"])
        if scene == "tupo":
            values.setdefault("ticket_zero", 0.8)
    values.setdefault("sleep_time", 2.0 if scene == "tansuo" else 1.0)
    return values


def validate_thresholds(values):
    result = {}
    for key, raw in values.items():
        if not re.fullmatch(r"[a-zA-Z0-9_]+", key):
            raise ValueError(f"配置项名称无效: {key}")
        try:
            number = float(raw)
        except (ValueError, TypeError):
            raise ValueError(f"{key} 必须为数字") from None
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{key} 必须为有限的非负数字")
        if key == "sleep_time" and number <= 0:
            raise ValueError("点击间隔必须大于 0 秒")
        result[key] = number
    return result


def save_thresholds(scene, values):
    values = validate_thresholds(values)
    path = threshold_path(scene)
    original = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    result, written = [], set()
    for line in original:
        match = re.match(r"^\s*([a-zA-Z0-9_]+)\s*[:=]", line)
        if match and match[1] in values:
            key = match[1]
            if key not in written:
                result.append(f"{key}:{values[key]:g}")
                written.add(key)
        else:
            result.append(line)
    result.extend(f"{key}:{value:g}" for key, value in values.items() if key not in written)
    atomic_write(path, "\n".join(result) + "\n")


def adb_command(port, *args):
    port = validate_port(port)
    adb = ROOT / "adb.exe"
    if not adb.is_file():
        raise FileNotFoundError("项目目录中没有 adb.exe")
    try:
        return subprocess.run([str(adb), "-s", f"127.0.0.1:{port}", *map(str, args)],
                              capture_output=True, check=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"ADB 操作失败，端口 {port}") from exc


def screenshot_size(port):
    raw = adb_command(port, "exec-out", "screencap", "-p").stdout
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("设备未返回有效 PNG 截图，请确认端口连接")
    return struct.unpack(">II", raw[16:24])


def inspect_resolution(port):
    text = adb_command(port, "shell", "wm", "size").stdout.decode("utf-8", errors="replace")
    sizes = re.findall(r"(\d+)x(\d+)", text)
    if not sizes:
        raise ValueError("无法读取设备分辨率: " + text.strip())
    return {"raw_size": tuple(map(int, sizes[-1])), "display_size": screenshot_size(port),
            "override": tuple(map(int, sizes[-1])) if len(sizes) > 1 else None,
            "details": text.strip()}


def apply_resolution(port, width, height):
    port = validate_port(port)
    width, height = validate_resolution(width, height)
    previous = inspect_resolution(port)
    raw_width, raw_height = previous["raw_size"]
    display_width, display_height = previous["display_size"]
    rotated = (raw_width > raw_height) != (display_width > display_height)
    target = (height, width) if rotated else (width, height)
    adb_command(port, "shell", "wm", "size", f"{target[0]}x{target[1]}")
    try:
        actual = None
        for _ in range(5):
            time.sleep(0.5)
            actual = screenshot_size(port)
            if actual == (width, height):
                save_resolution(port, width, height)
                return actual
        raise RuntimeError(f"应用后截图为 {actual}，未达到 {width}×{height}")
    except Exception:
        old = previous["override"]
        try:
            adb_command(port, "shell", "wm", "size", f"{old[0]}x{old[1]}" if old else "reset")
        except Exception as rollback_error:
            raise RuntimeError(f"设置未完成，且旧分辨率恢复失败: {rollback_error}") from rollback_error
        raise
