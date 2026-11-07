"""前台窗口探测：认出当前在用什么 Cadence 工具。

主判据是进程名；若进程句柄拿不到（Cadence 以管理员启动时 OpenProcess 会拒绝），
降级用窗口标题匹配。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 进程名（去掉 .exe，小写） → 工具键
PROCESS_MAP = {
    "capture": "capture",
    "allegro": "allegro",
    "allegro_free_viewer": "allegro",
    "concepthdl": "dehdl",
    "nconcepthdl": "dehdl",
}

# 标题关键词兜底（小写）
TITLE_MAP = (
    ("orcad capture", "capture"),
    ("capture cis", "capture"),
    ("allegro", "allegro"),
    ("design entry", "dehdl"),
)


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow())


def foreground_title(hwnd: int | None = None) -> str:
    hwnd = foreground_hwnd() if hwnd is None else hwnd
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def process_name(hwnd: int | None = None) -> str:
    """返回前台窗口所属进程的 exe 基名（小写、无扩展名）；取不到返回空串。"""
    hwnd = foreground_hwnd() if hwnd is None else hwnd
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        name = buf.value.rsplit("\\", 1)[-1]
        return name[:-4].lower() if name.lower().endswith(".exe") else name.lower()
    finally:
        kernel32.CloseHandle(handle)


def detect() -> tuple[str, str]:
    """返回 (tool_key, 判据说明)。tool_key 为 capture / allegro / dehdl / idle。"""
    hwnd = foreground_hwnd()
    proc = process_name(hwnd)
    if proc in PROCESS_MAP:
        return PROCESS_MAP[proc], f"process:{proc}"
    title = foreground_title(hwnd).lower()
    for keyword, tool in TITLE_MAP:
        if keyword in title:
            return tool, f"title:{keyword}"
    return "idle", f"process:{proc or '?'}"


if __name__ == "__main__":
    tool, why = detect()
    print(f"{tool:<8} ({why})  title={foreground_title()!r}")