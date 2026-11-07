"""临时端到端测试：启动 app → 把 Capture 拉到前台 → 验证浮窗内容是否跟着切。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

import focus

user32 = ctypes.windll.user32
BASE = Path(__file__).parent

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def windows_of(tool: str) -> list[int]:
    found: list[int] = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and focus.process_name(hwnd) == tool:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 8:
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def force_foreground(hwnd: int) -> bool:
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    tg_tid = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(fg_tid, tg_tid, True)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    ok = user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(fg_tid, tg_tid, False)
    return bool(ok)


def main() -> int:
    log = (BASE / "preview" / "app.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=BASE,
                            stdout=log, stderr=subprocess.STDOUT)
    time.sleep(3.0)

    targets = windows_of("capture")
    print("capture 窗口:", [(h, focus.foreground_title(h)) for h in targets])
    if targets:
        done = force_foreground(targets[0])
        time.sleep(1.6)
        print("置前:", done, "| detect():", focus.detect())

    img = ImageGrab.grab(all_screens=True)
    out = BASE / "preview" / "live.png"
    img.save(out)
    print("屏幕截图 ->", out, img.size)

    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    print((BASE / "preview" / "app.log").read_text(encoding="utf-8", errors="replace")[-800:])
    return 0


if __name__ == "__main__":
    sys.exit(main())