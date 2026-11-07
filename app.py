"""CadenceHints 入口：探针 + 数据 + 浮窗 + 热键 + 托盘 + 右键菜单。

用法：pythonw app.py          静默常驻（start_hint.vbs 走这条）
      python  app.py --debug  带控制台日志
"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import sys
import tkinter as tk
import traceback
from pathlib import Path

import focus
import hotkey
import menu
import settings
import single
import taskbar
import theme
import tray
import widgets

BASE = Path(__file__).parent
DATA = BASE / "data"
CONFIG = BASE / "hint.json"
LOGS = BASE / "logs"
VERSION = "1.0.0"
ICON = BASE / "app.ico"
ICON_PNG = BASE / "app.png"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
AUTOSTART = STARTUP_DIR / "CadenceHints.vbs"


MAX_LOG_BYTES = 512 * 1024


def log(msg: str) -> None:
    """pythonw 没有控制台，日志一律落文件，否则崩了没人知道。"""
    try:
        LOGS.mkdir(exist_ok=True)
        target = LOGS / "app.log"
        if target.exists() and target.stat().st_size > MAX_LOG_BYTES:
            target.replace(LOGS / "app.log.1")   # 只留一代，避免无限长
        with target.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


DEFAULTS = {
    "palette": "A",
    "rows": 6,
    "width": None,
    "x": None,
    "y": None,
    "hotkey": "Ctrl+Alt+H",
    "probe_ms": 400,
    "tray": True,
    "taskbar": False,
    "opacity": 1.0,
    "idle_alpha": 0.45,
    "idle_mode": "hide",
    "font_scale": 1.0,
}

DATASETS = {
    "capture": DATA / "capture.json",
    "allegro": DATA / "allegro.json",
    "dehdl": DATA / "dehdl.json",
}


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class App:
    VERSION = VERSION   # 让设置面板能取到

    def __init__(self) -> None:
        self.cfg = self._load_cfg()
        self.payloads: dict[str, dict] = {}
        self._load_data()
        self._ui_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = widgets.HintPanel(self.root, palette=self.cfg["palette"],
                                       rows=self.cfg["rows"])
        if self.cfg.get("width"):
            self.panel.set_width(self.cfg["width"])
        self.panel.on_resize = self._on_user_resize
        self.panel.set_opacity(self.cfg.get("opacity", 1.0))
        self.panel.set_idle_alpha(self.cfg.get("idle_alpha", 0.45))
        self.panel.set_font_scale(self.cfg.get("font_scale", 1.0))

        first = self.payloads.get("capture") or next(iter(self.payloads.values()), None)
        if first:
            self.panel.set_data(first)
        self.panel.set_tool("idle")

        x, y = self.cfg.get("x"), self.cfg.get("y")
        self.panel.move_to(*(self._clamp(x, y) if x is not None and y is not None
                             else self._default_pos()))
        if self.cfg.get("idle_mode", "hide") == "dim":
            self.panel.show()

        self._popup_open = None
        self._settings_open = None
        self.panel.canvas.bind("<Button-3>", self._popup)

        self.hotkey = hotkey.GlobalHotkey(self.cfg["hotkey"], self._post(self._do_toggle))
        if not self.hotkey.start():
            log(f"[warn] 全局热键 {self.cfg['hotkey']} 注册失败（可能被占用），改用双击标题栏折叠")

        self.tray = None
        if self.cfg.get("tray", True):
            self._start_tray()

        self.taskbar = None
        if self.cfg.get("taskbar", True):
            self.taskbar = taskbar.TaskbarHost(
                self.root, "CadenceHints · 快捷键提示", ICON_PNG, self._post(self._do_toggle))
            if not self.taskbar.ok:
                log("[warn] 任务栏按钮创建失败")

        log(f"[start] CadenceHints v{VERSION} scale={self.panel.scale:.4f} "
            f"visible={self.panel.visible} "
            f"pos={self.cfg.get('x')},{self.cfg.get('y')} "
            f"logical={self.panel.width}x{self.panel.rows} tray={bool(self.tray and self.tray.ok)} "
            f"taskbar={bool(self.taskbar and self.taskbar.ok)}")

        self._current_tool = None
        # 手动收起只是会话内状态，不落盘 —— 否则一旦存成 hidden=true，
        # 切回 Cadence 也永远不弹了（这正是之前的 bug）
        self._user_hidden = False
        self.root.after(self.cfg["probe_ms"], self._probe)
        self.root.after(120, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------- 跨线程 ----------
    def _post(self, fn):
        """把回调丢进 UI 队列，供热键/托盘线程安全调用。"""
        return lambda *a, **k: self._ui_queue.put(lambda: fn(*a, **k))

    def _drain_queue(self) -> None:
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log("[error] UI 回调异常\n" + traceback.format_exc())
        self.root.after(120, self._drain_queue)

    # ---------- 配置 ----------
    def _load_cfg(self) -> dict:
        cfg = dict(DEFAULTS)
        if CONFIG.exists():
            try:
                cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
            except Exception:
                pass
        return cfg

    def _save_cfg(self) -> None:
        if self.panel.visible:
            x, y, _w, _h = self.panel.geometry()
        else:
            x, y = self.cfg.get("x"), self.cfg.get("y")
        self.cfg.update({
            "x": x, "y": y,
            "rows": self.panel.rows,
            "width": self.panel.width,
        })
        self.cfg.pop("hidden", None)
        CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def _default_pos(self) -> tuple[int, int]:
        sw = self.root.winfo_screenwidth()
        return sw - self.panel._layout.get("w", 340) - 28, 90

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = self.panel._layout.get("w", 340)
        h = self.panel._layout.get("h", 260)
        x = max(-(w // 2), min(int(x), sw - w // 2))
        y = max(0, min(int(y), sh - 40))
        return x, y

    # ---------- 数据 ----------
    def _load_data(self) -> None:
        self.payloads.clear()
        for tool, path in DATASETS.items():
            if not path.exists():
                continue
            try:
                self.payloads[tool] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log(f"[warn] 读取 {path.name} 失败: {e}")

    # ---------- 探测 ----------
    def _probe(self) -> None:
        tool, _why = focus.detect()
        if tool not in self.payloads:
            tool = "idle"
        if tool != self._current_tool:
            self._current_tool = tool
            if tool == "idle":
                # 非 Cadence 前台：默认完全静默隐藏，不占前台
                if self.cfg.get("idle_mode", "hide") == "hide":
                    self.panel.hide()
                else:
                    self.panel.set_tool("idle")
            else:
                self.panel.set_data(self.payloads[tool])
                self.panel.set_tool(tool)
                if not self._user_hidden:
                    self.panel.show()
        if self.panel.visible:
            try:
                overlay = self._settings_open or self._popup_open
                if overlay is not None:
                    # 菜单/设置开着时绝不能重断言浮窗置顶，否则会把浮层压到下面
                    overlay.win.lift()
                else:
                    self.panel.win.attributes("-topmost", True)
            except tk.TclError:
                pass
        self.root.after(self.cfg["probe_ms"], self._probe)

    # ---------- 托盘 ----------
    def _start_tray(self) -> None:
        if not tray.HAVE_TRAY:
            log("[warn] 没装 pystray，托盘不可用（pip install pystray）")
            return
        try:
            pal = theme.PALETTES[self.cfg["palette"]]
            tray.write_ico(ICON, pal.card, pal.accent_of("capture"))
            tray.write_png(ICON_PNG, pal.card, pal.accent_of("capture"))
        except Exception:
            log("[warn] 生成托盘图标失败\n" + traceback.format_exc())
        self.tray = tray.Tray(
            title="CadenceHints · Cadence 快捷键提示",
            icon_path=ICON,
            on_toggle=self._post(self._do_toggle),
            on_quit=self._post(self._quit),
            on_palette=self._post(self._set_palette),
            palette_ids=list(theme.PALETTES),
        )
        self.tray.set_palette(self.cfg["palette"])
        if not self.tray.start():
            log("[warn] 托盘图标启动失败")

    # ---------- 菜单（自绘，放在独立置顶窗口里，不会被浮窗盖住） ----------
    def _menu_items(self) -> list[dict | None]:
        items: list[dict | None] = []
        for key, p in theme.PALETTES.items():
            items.append({"label": f"配色 {key} · {p.name}",
                          "checked": self.cfg["palette"] == key,
                          "action": lambda k=key: self._set_palette(k)})
        items.append(None)
        for n in theme.ROWS_CHOICES:
            items.append({"label": f"每页 {n} 行",
                          "checked": self.panel.rows == n,
                          "action": lambda v=n: self._set_rows(v)})
        items.append(None)
        items.append({"label": "设置…", "action": self._open_settings})
        items.append({"label": "重载快捷键数据", "action": self._reload})
        items.append({"label": "收起 / 展开", "action": self._do_toggle})
        items.append({"label": "退出", "action": self._quit})
        return items

    def _popup(self, event: tk.Event) -> None:
        log(f"[menu] open at {event.x_root},{event.y_root}")
        self._close_popup()
        self._popup_open = menu.PopupMenu(
            self.root, self._menu_items(), self.panel.pal, self.panel.scale,
            (event.x_root, event.y_root),
        )

    def _close_popup(self) -> None:
        if self._popup_open is not None:
            try:
                self._popup_open.close()
            except Exception:
                pass
            self._popup_open = None

    # ---------- 动作 ----------
    def _set_palette(self, key: str) -> None:
        self.cfg["palette"] = key
        self.panel.pal = theme.PALETTES[key]
        self.panel.refresh()
        if self.tray:
            self.tray.set_palette(key)
        try:
            pal = theme.PALETTES[key]
            tray.write_ico(ICON, pal.card, pal.accent_of("capture"))
            if self.tray and self.tray.icon is not None:
                self.tray.icon.icon = tray.make_icon(pal.card, pal.accent_of("capture"))
        except Exception:
            pass
        self._save_cfg()

    def _set_rows(self, n: int) -> None:
        self.cfg["rows"] = n
        self.panel.set_rows(n)
        self._save_cfg()

    def _on_user_resize(self, width: int, rows: int) -> None:
        self.cfg["width"] = width
        self.cfg["rows"] = rows
        self._save_cfg()

    def _open_settings(self) -> None:
        if self._settings_open is not None:
            try:
                self._settings_open.win.lift()
                return
            except tk.TclError:
                self._settings_open = None
        self._close_popup()
        x, y, _w, _h = self.panel.geometry()
        self._settings_open = settings.SettingsWindow(
            self.root, app=self, palette=self.panel.pal, scale=self.panel.scale,
            at=(x + 24, y + 40),
        )

    def _settings_closed(self) -> None:
        self._settings_open = None

    def apply_setting(self, key: str, value) -> None:
        self.cfg[key] = value
        if key == "opacity":
            self.panel.set_opacity(value)
        elif key == "idle_alpha":
            self.panel.set_idle_alpha(value)
        elif key == "font_scale":
            self.panel.set_font_scale(value)
        elif key == "palette":
            self._set_palette(value)
        elif key == "rows":
            self.panel.set_rows(int(value))
        elif key == "width":
            self.panel.set_width(int(value))
        elif key == "autostart":
            self.set_autostart(bool(value))
        elif key == "taskbar":
            self._set_taskbar(bool(value))
        elif key == "idle_mode":
            pass  # 探针下一轮自然生效

    def persist_settings(self) -> None:
        self._save_cfg()

    def reset_settings(self) -> None:
        for k in ("opacity", "idle_alpha", "font_scale", "rows", "width", "palette"):
            self.cfg[k] = DEFAULTS[k]
        self.apply_setting("opacity", DEFAULTS["opacity"])
        self.apply_setting("idle_alpha", DEFAULTS["idle_alpha"])
        self.apply_setting("font_scale", DEFAULTS["font_scale"])
        self.apply_setting("palette", DEFAULTS["palette"])
        self.panel.set_rows(DEFAULTS["rows"])
        self.panel.set_width(DEFAULTS["width"] or self.panel.m.width)
        self._save_cfg()

    def autostart_enabled(self) -> bool:
        return AUTOSTART.exists()

    def set_autostart(self, enabled: bool) -> None:
        try:
            if enabled:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                STARTUP_DIR.mkdir(parents=True, exist_ok=True)
                body = (
                    "' CadenceHints autostart (generated, ASCII only)\n"
                    f'CreateObject("WScript.Shell").Run """{pyw}"" ""{BASE / "app.py"}""", 0, False\n'
                )
                AUTOSTART.write_text(body, encoding="ascii", errors="replace")
            elif AUTOSTART.exists():
                AUTOSTART.unlink()
        except Exception:
            log("[warn] 开机自启设置失败\n" + traceback.format_exc())

    def _set_taskbar(self, enabled: bool) -> None:
        if enabled and self.taskbar is None:
            self.taskbar = taskbar.TaskbarHost(
                self.root, "CadenceHints · 快捷键提示", ICON_PNG, self._post(self._do_toggle))
        elif not enabled and self.taskbar is not None:
            self.taskbar.destroy()
            self.taskbar = None

    def _reload(self) -> None:
        self._load_data()
        tool = self._current_tool if self._current_tool in self.payloads else "capture"
        if tool in self.payloads:
            self.panel.set_data(self.payloads[tool])

    def _do_show(self) -> None:
        self._user_hidden = False
        self.panel.show()
        self._save_cfg()

    def _do_toggle(self) -> None:
        if self.panel.visible:
            self.panel.hide()
            self._user_hidden = True
        else:
            self.panel.show()
            self._user_hidden = False
        self._save_cfg()

    def _quit(self) -> None:
        self._save_cfg()
        self.hotkey.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    set_dpi_aware()

    allow_multi = "--allow-multi" in sys.argv
    guard = single.InstanceGuard() if not allow_multi else None
    if guard is not None and not guard.first:
        # 已经有实例在跑：叫它显示一下，然后自己退出，绝不长出第二个托盘图标
        guard.signal_existing()
        log("[start] 已有实例在运行，本次启动请求已转发并退出")
        sys.exit(0)

    try:
        application = App()
        if guard is not None:
            guard.start_watcher(application._post(application._do_show))
        application.run()
    except Exception:
        log("[fatal]\n" + traceback.format_exc())
        raise