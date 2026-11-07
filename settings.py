"""设置面板：与浮窗同风格的独立置顶窗口。

滑块、步进器、分段选择、开关全部自绘，不引入任何系统控件，
所以视觉和卡片完全一致，也不会被浮窗遮挡。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

import chrome
import theme

SS = chrome.SS
PADX = 14
ROW_H = 32
HEADER_H = 34
FOOTER_H = 46
RADIUS = 11


def _s(v: float) -> int:
    return int(round(v * SS))


class SettingsWindow:
    WIDTH = 316

    def __init__(self, master: tk.Misc, *, app, palette, scale: float,
                 at: tuple[int, int] | None = None) -> None:
        self.app = app
        self.pal = palette
        self.scale = scale
        self._drag: str | None = None
        self._drag_win: tuple[int, int] | None = None
        self._rows: list[dict] = []

        fam_desc, size_desc, _ = theme.FONTS["desc"]
        fam_title, size_title, _ = theme.FONTS["title"]
        self.font = tkfont.Font(family=fam_desc, size=round(size_desc * scale))
        self.font_bold = tkfont.Font(family=fam_title, size=round(size_title * scale), weight="bold")
        self.font_small = tkfont.Font(family=fam_desc, size=round(-10 * scale))

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", chrome.KEY_HEX)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=chrome.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack()

        self._controls()
        self._build(at)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()

    # ---------- 控件定义 ----------
    def _controls(self) -> None:
        cfg = self.app.cfg
        self.items = [
            {"type": "slider", "key": "opacity", "label": "不透明度",
             "min": 0.35, "max": 1.0, "step": 0.01, "value": cfg.get("opacity", 1.0),
             "fmt": lambda v: f"{v:.0%}"},
            {"type": "slider", "key": "idle_alpha", "label": "空闲变暗",
             "min": 0.15, "max": 1.0, "step": 0.01, "value": cfg.get("idle_alpha", 0.45),
             "fmt": lambda v: f"{v:.0%}"},
            {"type": "slider", "key": "font_scale", "label": "字号",
             "min": 0.80, "max": 1.40, "step": 0.05, "value": cfg.get("font_scale", 1.0),
             "fmt": lambda v: f"{v:.0%}"},
            {"type": "segment", "key": "palette", "label": "配色",
             "options": [(k, p.name) for k, p in theme.PALETTES.items()],
             "value": cfg.get("palette", "A")},
            {"type": "segment", "key": "idle_mode", "label": "非 Cadence 时",
             "options": [("hide", "隐藏"), ("dim", "变暗")],
             "show_key": False,
             "value": cfg.get("idle_mode", "hide")},
            {"type": "stepper", "key": "rows", "label": "每页行数",
             "min": 3, "max": 40, "step": 1, "value": self.app.panel.rows},
            {"type": "stepper", "key": "width", "label": "卡片宽度",
             "min": 260, "max": 620, "step": 20, "value": self.app.panel.width},
            {"type": "toggle", "key": "taskbar", "label": "任务栏按钮",
             "value": bool(cfg.get("taskbar", False))},
            {"type": "toggle", "key": "autostart", "label": "开机自启",
             "value": self.app.autostart_enabled()},
        ]

    # ---------- 布局 ----------
    def _build(self, at) -> None:
        s = lambda v: int(round(v * self.scale))
        self.W = s(self.WIDTH)
        y = s(HEADER_H)
        self._rows = []
        for it in self.items:
            box = {
                "item": it,
                "label_y": y + s(ROW_H) // 2,
                "row": (0, y, self.W, s(ROW_H)),
            }
            cw = s(self.WIDTH - 130)          # 控件区宽
            cx = self.W - s(PADX) - cw
            if it["type"] == "slider":
                box["track"] = (cx, y + s(ROW_H) // 2 - s(2), cw - s(40), s(4))
                box["value_x"] = self.W - s(PADX)
            elif it["type"] == "stepper":
                box["minus"] = (cx, y + s(8), s(20), s(16))
                box["plus"] = (cx + s(28), y + s(8), s(20), s(16))
                box["value_x"] = cx + s(78)
            elif it["type"] == "segment":
                opt_w = (cw - s(6)) // max(1, len(it["options"]))
                box["opts"] = [(cx + i * (opt_w + s(6)), y + s(6), opt_w, s(20))
                               for i in range(len(it["options"]))]
            elif it["type"] == "toggle":
                box["switch"] = (self.W - s(PADX) - s(38), y + s(8), s(38), s(16))
            y += s(ROW_H)
            self._rows.append(box)

        self._footer_y = y
        self.H = y + s(FOOTER_H)
        self._btn_reset = (s(PADX), y + s(12), s(96), s(24))
        self._btn_close = (self.W - s(PADX) - s(80), y + s(12), s(80), s(24))

        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        ax, ay = at if at else (sw // 2 - self.W // 2, sh // 2 - self.H // 2)
        ax = min(max(0, ax), sw - self.W)
        ay = min(max(0, ay), sh - self.H)
        self.win.geometry(f"{self.W}x{self.H}+{ax}+{ay}")
        self.canvas.configure(width=self.W, height=self.H)
        self._draw()

    # ---------- 绘制 ----------
    def _draw(self) -> None:
        W, H, s = self.W, self.H, lambda v: int(round(v * self.scale))
        img = Image.new("RGB", (W * SS, H * SS), chrome.KEY_COLOR)
        d = ImageDraw.Draw(img)
        accent = self.pal.accent_of("capture")

        d.rounded_rectangle((_s(0), _s(0), _s(W - 1), _s(H - 1)),
                            radius=_s(RADIUS * self.scale), fill=self.pal.card,
                            outline=self.pal.card_edge, width=_s(1))
        d.line((_s(RADIUS * self.scale), _s(1), _s(W - RADIUS * self.scale), _s(1)),
               fill=self.pal.highlight(), width=_s(1))
        d.line((_s(PADX * self.scale), _s(HEADER_H * self.scale - s(1)),
                _s(W - PADX * self.scale), _s(HEADER_H * self.scale - s(1))),
               fill=self.pal.divider(), width=_s(1))

        for box in self._rows:
            it = box["item"]
            if it["type"] == "slider":
                tx, ty, tw, th = box["track"]
                frac = (it["value"] - it["min"]) / (it["max"] - it["min"])
                d.rounded_rectangle((_s(tx), _s(ty), _s(tx + tw), _s(ty + th)),
                                    radius=_s(th / 2), fill=self.pal.chip)
                fill_w = max(th, tw * frac)
                d.rounded_rectangle((_s(tx), _s(ty), _s(tx + fill_w), _s(ty + th)),
                                    radius=_s(th / 2), fill=accent)
                kx = tx + tw * frac
                r = s(6)
                d.ellipse((_s(kx - r / self.scale), _s(ty + th / 2 - r / self.scale),
                           _s(kx + r / self.scale), _s(ty + th / 2 + r / self.scale)),
                          fill=self.pal.text)
            elif it["type"] == "stepper":
                for key in ("minus", "plus"):
                    bx, by, bw, bh = box[key]
                    d.rounded_rectangle((_s(bx), _s(by), _s(bx + bw), _s(by + bh)),
                                        radius=_s(5), fill=self.pal.chip,
                                        outline=self.pal.chip_edge, width=_s(1))
            elif it["type"] == "segment":
                for i, (ox, oy, ow, oh) in enumerate(box["opts"]):
                    active = it["options"][i][0] == it["value"]
                    if active:
                        d.rounded_rectangle((_s(ox), _s(oy), _s(ox + ow), _s(oy + oh)),
                                            radius=_s(5), fill=self.pal.pill_active_bg("capture"),
                                            outline=accent, width=_s(1))
                    else:
                        d.rounded_rectangle((_s(ox), _s(oy), _s(ox + ow), _s(oy + oh)),
                                            radius=_s(5), fill=self.pal.chip)
            elif it["type"] == "toggle":
                bx, by, bw, bh = box["switch"]
                on = bool(it["value"])
                d.rounded_rectangle((_s(bx), _s(by), _s(bx + bw), _s(by + bh)),
                                    radius=_s(bh / 2), fill=accent if on else self.pal.chip,
                                    outline=None if on else self.pal.chip_edge, width=_s(1))
                r = bh / 2 - s(2) / self.scale
                cx = bx + (bw - bh / 2) if on else bx + bh / 2
                d.ellipse((_s(cx - r), _s(by + bh / 2 - r), _s(cx + r), _s(by + bh / 2 + r)),
                          fill=self.pal.card if on else self.pal.text_dim)

        for bx, by, bw, bh in (self._btn_reset, self._btn_close):
            d.rounded_rectangle((_s(bx), _s(by), _s(bx + bw), _s(by + bh)),
                                radius=_s(6), fill=self.pal.chip,
                                outline=self.pal.chip_edge, width=_s(1))

        self._img = ImageTk.PhotoImage(img.resize((W, H), Image.LANCZOS))
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self._img, anchor="nw")

        sx = self.scale
        c.create_text(PADX * sx, s(HEADER_H) / 2, text="设置", anchor="w",
                      font=self.font_bold, fill=self.pal.text)
        version = getattr(self.app, "VERSION", "")
        if version:
            vx = PADX * sx + self.font_bold.measure("设置") + s(8)
            c.create_text(vx, s(HEADER_H) / 2 + s(1), text=f"v{version}", anchor="w",
                          font=self.font_small, fill=self.pal.text_dim)
        c.create_text(self.W - PADX * sx, s(HEADER_H) / 2, text="✕", anchor="e",
                      font=self.font, fill=self.pal.text_dim)

        for box in self._rows:
            it = box["item"]
            c.create_text(PADX * sx, box["label_y"], text=it["label"], anchor="w",
                          font=self.font, fill=self.pal.text_dim)
            if it["type"] == "slider":
                c.create_text(box["value_x"], box["label_y"], text=it["fmt"](it["value"]),
                              anchor="e", font=self.font_small, fill=self.pal.text)
            elif it["type"] == "stepper":
                mx, my, mw, mh = box["minus"]
                c.create_text(mx + mw / 2, my + mh / 2, text="−", anchor="center",
                              font=self.font, fill=self.pal.text_dim)
                px, py, pw, ph = box["plus"]
                c.create_text(px + pw / 2, py + ph / 2, text="+", anchor="center",
                              font=self.font, fill=self.pal.text_dim)
                c.create_text(box["value_x"], box["label_y"], text=str(it["value"]),
                              anchor="w", font=self.font_small, fill=self.pal.text)
            elif it["type"] == "segment":
                for i, (ox, oy, ow, oh) in enumerate(box["opts"]):
                    key, name = it["options"][i]
                    active = key == it["value"]
                    text = f"{key} {name}" if it.get("show_key", True) else name
                    c.create_text(ox + ow / 2, oy + oh / 2, text=text,
                                  anchor="center", font=self.font_small,
                                  fill=accent if active else self.pal.text_dim)
            elif it["type"] == "toggle":
                pass

        for box, label in ((self._btn_reset, "恢复默认"), (self._btn_close, "关闭")):
            bx, by, bw, bh = box
            c.create_text(bx + bw / 2, by + bh / 2, text=label, anchor="center",
                          font=self.font_small, fill=self.pal.text)

    # ---------- 命中 ----------
    @staticmethod
    def _hit(box, x, y) -> bool:
        bx, by, bw, bh = box
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _row_at(self, y: int) -> dict | None:
        for box in self._rows:
            _x, ry, _w, rh = box["row"]
            if ry <= y < ry + rh:
                return box
        return None

    # ---------- 交互 ----------
    def _on_press(self, event: tk.Event) -> None:
        if self._hit(self._btn_close, event.x, event.y):
            self.close()
            return
        if self._hit(self._btn_reset, event.x, event.y):
            self.app.reset_settings()
            self._controls()
            self._build(None)
            return
        if event.y < HEADER_H * self.scale:
            if event.x > self.W - 40 * self.scale:
                self.close()
            else:
                # 标题栏拖动整个设置窗口
                self._drag_win = (event.x_root - self.win.winfo_rootx(),
                                  event.y_root - self.win.winfo_rooty())
            return

        box = self._row_at(event.y)
        if not box:
            return
        it = box["item"]
        if it["type"] == "slider":
            self._drag = it["key"]
            self._set_slider(it, box, event.x)
        elif it["type"] == "stepper":
            if self._hit(box["minus"], event.x, event.y):
                self._bump(it, -it["step"])
            elif self._hit(box["plus"], event.x, event.y):
                self._bump(it, +it["step"])
        elif it["type"] == "segment":
            for i, ob in enumerate(box["opts"]):
                if self._hit(ob, event.x, event.y):
                    it["value"] = it["options"][i][0]
                    self.app.apply_setting(it["key"], it["value"])
                    if it["key"] == "palette":
                        self.pal = theme.PALETTES[it["value"]]
                    self._draw()
        elif it["type"] == "toggle":
            if self._hit(box["switch"], event.x, event.y):
                it["value"] = not it["value"]
                self.app.apply_setting(it["key"], it["value"])
                self._draw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_win:
            dx, dy = self._drag_win
            self.win.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
            return
        if not self._drag:
            return
        for box in self._rows:
            if box["item"]["key"] == self._drag:
                self._set_slider(box["item"], box, event.x)

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_win:
            self._drag_win = None
            return
        if self._drag:
            self._drag = None
            self.app.persist_settings()

    def _set_slider(self, it: dict, box: dict, x: int) -> None:
        tx, _ty, tw, _th = box["track"]
        frac = min(1.0, max(0.0, (x - tx) / max(1, tw)))
        val = it["min"] + frac * (it["max"] - it["min"])
        steps = round((val - it["min"]) / it["step"])
        it["value"] = round(it["min"] + steps * it["step"], 3)
        self.app.apply_setting(it["key"], it["value"])
        self._draw()

    def _bump(self, it: dict, delta: float) -> None:
        it["value"] = max(it["min"], min(it["max"], it["value"] + delta))
        self.app.apply_setting(it["key"], it["value"])
        self._draw()

    def close(self) -> None:
        self.app.persist_settings()
        try:
            self.app._settings_closed()
        except Exception:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass