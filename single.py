"""单实例守卫：命名互斥体 + 命名事件。

- 第一个进程拿到互斥体，正常启动；
- 之后的进程检测到已存在，就发一次"显示"信号给已有实例，然后自己安静退出。
这样重复双击 start_hint.vbs / 开始菜单 / 任务栏按钮都不会长出第二个托盘图标。
"""
from __future__ import annotations

import ctypes
import threading

kernel32 = ctypes.windll.kernel32

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
INFINITE = 0xFFFFFFFF
EVENT_MODIFY_STATE = 0x0002

MUTEX_NAME = "Local\\CadenceHints.SingleInstance.v1"
EVENT_NAME = "Local\\CadenceHints.ShowSignal.v1"


class InstanceGuard:
    def __init__(self) -> None:
        kernel32.SetLastError(0)
        self.mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        self.first = kernel32.GetLastError() != ERROR_ALREADY_EXISTS
        self.event = kernel32.CreateEventW(None, False, False, EVENT_NAME) if self.first else None
        self._thread: threading.Thread | None = None

    def signal_existing(self) -> bool:
        """叫醒已经在跑的那个实例。"""
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_NAME)
        if not handle:
            return False
        try:
            return bool(kernel32.SetEvent(handle))
        finally:
            kernel32.CloseHandle(handle)

    def start_watcher(self, callback) -> None:
        """后台等信号，收到就调 callback（用于切回主线程显示浮窗）。"""
        if self.event is None:
            return

        def run() -> None:
            while True:
                result = kernel32.WaitForSingleObject(self.event, INFINITE)
                if result != WAIT_OBJECT_0:
                    return
                try:
                    callback()
                except Exception:
                    pass

        self._thread = threading.Thread(target=run, daemon=True, name="instance-guard")
        self._thread.start()