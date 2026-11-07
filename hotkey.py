"""全局热键：默认 Ctrl+Alt+H，在任何窗口（包括 Cadence 内部）都能触发。

实现要点：RegisterHotKey 必须和消息循环在同一线程，所以在独立线程里注册并
跑 GetMessageW 循环，触发时通过回调切回主线程。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
         "shift": MOD_SHIFT, "win": MOD_WIN}


def parse(spec: str) -> tuple[int, int]:
    """'Ctrl+Alt+H' → (modifiers, vk)。"""
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"无法解析热键: {spec!r}")
    mods = 0
    for p in parts[:-1]:
        key = p.lower()
        if key not in _MODS:
            raise ValueError(f"未知修饰键: {p!r}")
        mods |= _MODS[key]
    last = parts[-1].upper()
    vk = ord(last) if len(last) == 1 else _vk_named(last)
    return mods | MOD_NOREPEAT, vk


def _vk_named(name: str) -> int:
    table = {"SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ENTER": 0x0D}
    if name in table:
        return table[name]
    if name.startswith("F") and name[1:].isdigit():
        return 0x70 + int(name[1:]) - 1
    raise ValueError(f"不支持的按键: {name!r}")


class GlobalHotkey:
    def __init__(self, spec: str, callback) -> None:
        self.spec = spec
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self.ok = False
        self._tid: int | None = None

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True, name="hotkey")
        self._thread.start()
        self._ready.wait(1.5)
        return self.ok

    def _run(self) -> None:
        try:
            mods, vk = parse(self.spec)
        except ValueError:
            self._ready.set()
            return
        self._tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, mods, vk):
            self._ready.set()
            return
        self.ok = True
        self._ready.set()
        msg = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == 1 and self.callback:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)