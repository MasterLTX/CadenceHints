"""任务栏按钮宿主。

Windows 11 默认把新托盘图标折叠进溢出区，所以另外给一个「任务栏按钮」：
一个真实窗口（常驻最小化、放在屏幕外），点它的任务栏按钮就等于切换浮窗显示。
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from pathlib import Path

OFFSCREEN = -32000


class TaskbarHost:
    def __init__(self, root: tk.Misc, title: str, icon_path: Path, on_click) -> None:
        self.on_click = on_click
        self.ok = False
        try:
            self.win = tk.Toplevel(root)
            self.win.title(title)
            self.win.geometry(f"240x140{OFFSCREEN:+d}{OFFSCREEN:+d}")
            if icon_path.exists():
                try:
                    # Tk 的 PhotoImage 不支持 .ico，这里用 PNG
                    self._icon = tk.PhotoImage(file=str(icon_path))
                    self.win.iconphoto(True, self._icon)
                except tk.TclError:
                    pass
            self.win.protocol("WM_DELETE_WINDOW", self._on_close)
            self.win.bind("<Map>", self._on_map)
            self.win.iconify()
            # 启动时的首次映射不算"用户点击"，延迟武装，避免一启动就把浮窗收起来
            self._armed = False
            self.win.after(1500, self._arm)
            self.ok = True
        except tk.TclError:
            self.ok = False

    def _arm(self) -> None:
        self._armed = True

    def _on_map(self, event: tk.Event) -> None:
        """用户点了任务栏按钮 → 窗口被还原 → 立刻再最小化，同时切换浮窗。"""
        if event.widget is not self.win or not getattr(self, "_armed", False):
            return
        self.win.after(1, self._reminimize)
        try:
            self.on_click()
        except Exception:
            pass

    def _reminimize(self) -> None:
        try:
            self.win.iconify()
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        self._reminimize()

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass

    def show(self, visible: bool) -> None:
        try:
            self.win.iconify() if visible else self.win.withdraw()
        except tk.TclError:
            pass