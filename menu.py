"""自绘右键菜单。

原生 tk.Menu 在「无边框 + 永远置顶」的浮窗上会被遮挡、且空焦点下不可靠，
所以这里自己画一个同风格的菜单，放在独立的置顶窗口里 —— 层级问题从根上没了，
视觉也和卡片一致。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

import chrome
import theme

SS = chrome.SS
ROW_H = 22
PAD_X = 12
PAD_Y = 6
SEP_H = 9
RADIUS = 9


def _s(v: float) -> int:
    return int(round(v * SS))


class PopupMenu:
    """items: dict(label=..., action=callable, checked=bool) 或 None 表示分隔线。"""

    def __init__(self, master: tk.Misc, items: list[dict | None], palette, scale: float,
                 at: tuple[int, int]) -> None:
        self.items = items
        self.pal = palette
        self.scale = scale
        self._hover = -1
        self._rows: list[tuple[float, float, float, float]] = []

        fam, size, _w = theme.FONTS["desc"]
        self.font = tkfont.Font(family=fam, size=round(size * scale), weight="normal")
        self.font_check = tkfont.Font(family="Cascadia Mono", size=round(-12 * scale), weight="bold")

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", chrome.KEY_HEX)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=chrome.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack()

        self._layout(at)
        self._draw()
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_click)
        self.canvas.bind("<Button-3>", lambda e: self.close())
        self.canvas.bind("<Leave>", lambda e: self._set_hover(-1))
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("<FocusOut>", lambda e: self.close())
        # 先置顶再抬升：浮窗也是 topmost，必须显式压过它
        self.win.attributes("-topmost", True)
        self.win.lift()
        self.win.focus_force()

    # ---------- 布局 ----------
    def _layout(self, at: tuple[int, int]) -> None:
        s = lambda v: int(round(v * self.scale))
        widest = max((self.font.measure(it["label"]) for it in self.items if it), default=80)
        w = widest + s(PAD_X) * 2 + s(30)
        rows = []
        y = s(PAD_Y)
        for it in self.items:
            h = s(SEP_H) if it is None else s(ROW_H)
            rows.append((y, h, w, 0))
            y += h
        h = y + s(PAD_Y)
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = min(max(0, at[0]), sw - w)
        y0 = min(max(0, at[1]), sh - h)
        self.win.geometry(f"{w}x{h}+{x}+{y0}")
        self.canvas.configure(width=w, height=h)
        self._rows = rows
        self.size = (w, h)

    # ---------- 绘制 ----------
    def _draw(self) -> None:
        w, h = self.size
        img = Image.new("RGB", (w * SS, h * SS), chrome.KEY_COLOR)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((_s(0), _s(0), _s(w - 1), _s(h - 1)), radius=_s(RADIUS * self.scale),
                            fill=self.pal.card, outline=self.pal.card_edge, width=_s(1))
        d.line((_s(RADIUS * self.scale), _s(1), _s(w - RADIUS * self.scale), _s(1)),
               fill=self.pal.highlight(), width=_s(1))
        accent = self.pal.accent_of("capture")
        for i, (it, (y, row_h, _w, _h)) in enumerate(zip(self.items, self._rows)):
            if it is None:
                mid = y + row_h / 2
                d.line((_s(self.scale * PAD_X), _s(mid), _s(w - self.scale * PAD_X), _s(mid)),
                       fill=self.pal.divider(), width=_s(1))
                continue
            if i == self._hover:
                d.rounded_rectangle(
                    (_s(4 * self.scale), _s(y + 1), _s(w - 4 * self.scale), _s(y + row_h - 1)),
                    radius=_s(5 * self.scale), fill=self.pal.pill_active_bg("capture"))
            if it.get("checked"):
                cx = 4 * self.scale + 9 * self.scale
                d.ellipse((_s(cx - 2.5 * self.scale), _s(y + row_h / 2 - 2.5 * self.scale),
                           _s(cx + 2.5 * self.scale), _s(y + row_h / 2 + 2.5 * self.scale)),
                          fill=accent)
        self._img = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self._img, anchor="nw")
        sx = self.scale
        for i, (it, (y, row_h, _w, _h)) in enumerate(zip(self.items, self._rows)):
            if it is None:
                continue
            color = self.pal.text if i == self._hover else self.pal.text_dim
            if it.get("checked"):
                color = accent
            c.create_text(PAD_X * sx + 18 * sx, y + row_h / 2, text=it["label"],
                          anchor="w", font=self.font, fill=color)

    # ---------- 交互 ----------
    def _row_at(self, y: int) -> int:
        for i, (ry, rh, _w, _h) in enumerate(self._rows):
            if ry <= y < ry + rh:
                return i if self.items[i] is not None else -1
        return -1

    def _set_hover(self, idx: int) -> None:
        if idx != self._hover:
            self._hover = idx
            self._draw()

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._row_at(event.y))

    def _on_click(self, event: tk.Event) -> None:
        idx = self._row_at(event.y)
        if idx < 0:
            return
        action = self.items[idx].get("action")
        self.close()
        if action:
            action()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass