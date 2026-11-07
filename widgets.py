"""浮窗本体：布局计算 + 图形层贴图 + tk 文字层。"""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
import tkinter.font as tkfont

from PIL import ImageTk

import chrome
import theme

KEY = chrome.KEY_HEX


class HintPanel:
    def __init__(self, root: tk.Misc, palette: str = "A", rows: int = 6):
        self.root = root
        self.pal = theme.PALETTES[palette]
        self.m = theme.Metrics(rows=rows)
        self.rows = rows
        self.width = self.m.width
        try:
            self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self.scale = 1.0
        if abs(self.scale - 1.0) < 0.01:
            # withdraw/未映射窗口的 winfo_fpixels 会退到 ~96（实测 96.047，并非精确 96），
            # 1e-9 阈值抓不到；且 GetDpiForSystem() 依赖进程 DPI awareness，
            # 未设 awareness 的进程里它返回 96（实测），兜底等于没有。
            # 改用 GetDeviceCaps(LOGPIXELSX)：不受 awareness 影响，150% 下实测返回 144。
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)
                if dpi and dpi > 0:
                    self.scale = max(1.0, dpi / 96.0)
            except Exception:
                pass

        self.tool = "idle"
        self.tool_label = theme.TOOL_LABELS["idle"]
        self.groups: list[tuple[str, list[dict]]] = [("常用", [])]
        self.sel = 0
        self.page = 0
        self.collapsed = False
        self._img = None
        self._layout: dict = {}
        self._press: tuple[int, int] | None = None
        self.on_resize = None
        self.opacity = 1.0          # 整体不透明度
        self.idle_alpha = 0.45      # 空闲时再乘这个系数
        self.font_scale = 1.0

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0, takefocus=0)
        self.canvas.pack(fill="both", expand=True)

        self.f_key = self._mkfont("key")
        self.f_desc = self._mkfont("desc")
        self.f_title = self._mkfont("title")
        self.f_pill = self._mkfont("pill")
        self.f_pill_on = self._mkfont("pill_on")
        self.f_footer = self._mkfont("footer")

        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self._resizing = False
        self._resize_from = None
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.win.bind("<Escape>", lambda e: self.hide())

    # ---------- 基础 ----------
    def _mkfont(self, role: str) -> tkfont.Font:
        family, size, weight = theme.FONTS[role]
        # theme 里的字号是负数（Tk 语义 = 像素）。clamp 必须用 min，否则负数会被
        # max(6, ...) 压成 6pt，导致字号设置完全失效。
        px = min(-6, round(size * self.scale * self.font_scale))
        return tkfont.Font(family=family, size=px, weight=weight)

    def s(self, v: float) -> int:
        return int(round(v * self.scale))

    def _fit(self, text: str, font: tkfont.Font, maxw: int) -> str:
        if font.measure(text) <= maxw:
            return text
        ell = "…"
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + ell) <= maxw:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + ell

    # ---------- 数据 ----------
    def set_data(self, payload: dict) -> None:
        pinned: list[dict] = []
        seen: set[str] = set()
        for sec in payload.get("sections", []):
            if not sec.get("pinned"):
                continue
            for it in sec.get("items", []):
                if it["key"] in seen:
                    continue
                seen.add(it["key"])
                pinned.append(it)
        groups = [("常用", pinned)]
        for sec in payload.get("sections", []):
            groups.append((sec["name"], list(sec.get("items", []))))
        self.groups = [g for g in groups if g[1]]
        self.tool = payload.get("tool", "idle")
        self.tool_label = theme.TOOL_LABELS.get(self.tool, self.tool)
        self._apply_alpha()
        self.sel = 0
        self.page = 0
        self.refresh()

    def _apply_alpha(self) -> None:
        factor = self.idle_alpha if self.tool == "idle" else 1.0
        try:
            self.win.attributes("-alpha", max(0.05, min(1.0, self.opacity * factor)))
        except tk.TclError:
            pass

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.2, min(1.0, float(value)))
        self._apply_alpha()

    def set_idle_alpha(self, value: float) -> None:
        self.idle_alpha = max(0.1, min(1.0, float(value)))
        self._apply_alpha()

    def set_font_scale(self, value: float) -> None:
        self.font_scale = max(0.7, min(1.6, float(value)))
        for role, attr in (("key", "f_key"), ("desc", "f_desc"), ("title", "f_title"),
                           ("pill", "f_pill"), ("pill_on", "f_pill_on"), ("footer", "f_footer")):
            setattr(self, attr, self._mkfont(role))
        self.refresh()

    def set_tool(self, tool: str) -> None:
        if tool == self.tool:
            return
        self.tool = tool
        self.tool_label = theme.TOOL_LABELS.get(tool, tool)
        self._apply_alpha()
        self.refresh()

    # ---------- 分页 ----------
    def _items(self) -> list[dict]:
        return self.groups[self.sel][1] if self.groups else []

    def _page_count(self) -> int:
        return max(1, math.ceil(len(self._items()) / self.rows))

    def _visible(self) -> list[dict]:
        items = self._items()
        return items[self.page * self.rows:(self.page + 1) * self.rows]

    def turn(self, delta: int) -> None:
        n = self._page_count()
        if n <= 1:
            return
        self.page = (self.page + delta) % n
        self.refresh()

    def set_rows(self, rows: int) -> None:
        self.rows = max(self.m.rows_min, min(int(rows), self.m.rows_max))
        self.page = 0
        self.refresh()

    def set_width(self, width: int) -> None:
        self.width = max(self.m.width_min, min(int(width), self.m.width_max))
        self.refresh()

    def select(self, index: int) -> None:
        if 0 <= index < len(self.groups):
            self.sel = index
            self.page = 0
            self.refresh()

    # ---------- 几何 ----------
    def geometry(self) -> tuple[int, int, int, int]:
        return (self.win.winfo_rootx(), self.win.winfo_rooty(),
                self.win.winfo_width(), self.win.winfo_height())

    def move_to(self, x: int, y: int) -> None:
        self.win.geometry(f"+{int(x)}+{int(y)}")

    # ---------- 布局 ----------
    def _compute_layout(self) -> dict:
        m, s = self.m, self.s
        rows = self.rows
        if self.collapsed:
            short = theme.CAPSULE_LABELS.get(self.tool, "空闲")
            w = s(14) + self.f_title.measure(short) + s(12)
            h = s(24)
            return {
                "w": w, "h": h, "card_r": s(9), "tool": self.tool, "inset": s(8),
                "capsule": True,
                "dot": {"cx": s(11), "cy": h / 2, "r": m.accent_dot_r,
                        "color": self.pal.accent_of(self.tool)},
                "text": {"capsule": short, "x": s(19), "y": h / 2},
            }

        inset = s(m.inset)
        avail = s(self.width) - inset * 2
        pad, header_h, div = s(m.pad), s(m.header_h), s(m.divider_h)

        # 分类 pill 一排排布，必要时换行
        pills_lines, pills = 1, []
        x = inset
        for i, (name, _items) in enumerate(self.groups):
            pw = self.f_pill.measure(name) + s(m.pill_pad_x) * 2
            if x + pw > inset + avail and x > inset:
                pills_lines += 1
                x = inset
            pills.append({
                "box": (x, pad + header_h + div + (pills_lines - 1) * s(m.pills_row_h) + s(4),
                        pw, s(m.pill_h)),
                "active": i == self.sel,
                "label": name,
            })
            x += pw + s(m.pill_gap)

        y0 = pad + header_h + div + s(m.pills_row_h) * pills_lines
        visible = self._visible()
        # 数据不够一页时按实际条数收高度，别留一大片空白（多页时保持定高，避免翻页跳动）
        if self._page_count() == 1 and len(visible) < rows:
            rows = max(1, len(visible))

        col_w = max([max(self.f_key.measure(it["key"]) + s(m.chip_pad_x) * 2, s(m.chip_min_w))
                     for it in visible] or [s(m.chip_min_w)])

        rows_box, chips = [], []
        for i, it in enumerate(visible):
            cy = y0 + i * s(m.row_h)
            chip_w = max(self.f_key.measure(it["key"]) + s(m.chip_pad_x) * 2, s(m.chip_min_w))
            chips.append({"box": (inset, cy + (s(m.row_h) - s(m.chip_h)) // 2,
                                  chip_w, s(m.chip_h))})
            rows_box.append({
                "key": it["key"],
                "desc": it["desc"],
                "desc_x": inset + col_w + s(m.desc_gap),
                "cy": cy + s(m.row_h) // 2,
            })

        dividers = [y0 + s(m.row_h) * rows]
        footer_y = dividers[0] + div
        h = footer_y + s(m.footer_h) + pad

        # 分页点
        n = self._page_count()
        page_dots = []
        if n > 1:
            cy = footer_y + s(m.footer_h) // 2
            for i in range(min(n, 9)):
                page_dots.append({
                    "cx": inset + i * s(m.dot_gap) + s(m.dot_r),
                    "cy": cy, "r": s(m.dot_r), "active": i == self.page,
                })

        return {
            "w": s(self.width), "h": h, "card_r": s(m.card_r), "tool": self.tool,
            "inset": inset, "pill_r": s(m.pill_r), "chip_r": s(m.chip_r),
            "dividers": dividers,
            "dot": {"cx": inset, "cy": pad + header_h / 2, "r": s(m.accent_dot_r),
                    "color": self.pal.accent_of(self.tool)},
            "pills": pills, "chips": chips, "rows": rows_box, "page_dots": page_dots,
            "header": {"title_x": inset + s(10), "cy": pad + header_h / 2},
            "grip": {"x": s(self.width) - s(m.grip), "y": h - s(m.grip), "size": s(m.grip)},
            "footer": {"cy": footer_y + s(m.footer_h) // 2,
                       "page_text_x": inset + (min(n, 9) * s(m.dot_gap) + s(6) if n > 1 else 0),
                       "hint_x": s(self.width) - inset,
                       "page_text": f"{self.page + 1}/{n}" if n > 1 else "",
                       "hint_text": "滚轮翻页" if n > 1 else ""},
        }

    # ---------- 绘制 ----------
    def refresh(self) -> None:
        lay = self._compute_layout()
        self._layout = lay
        img = chrome.render(lay, self.pal, self.scale)
        self._img = ImageTk.PhotoImage(img)

        c = self.canvas
        c.delete("all")
        c.configure(width=lay["w"], height=lay["h"])
        c.create_image(0, 0, image=self._img, anchor="nw")

        if lay.get("capsule"):
            c.create_text(lay["text"]["x"], lay["text"]["y"], text=lay["text"]["capsule"],
                          anchor="w", font=self.f_title, fill=self.pal.text)
            self.win.geometry(f"{lay['w']}x{lay['h']}")
            return

        accent = self.pal.accent_of(self.tool)
        header = lay["header"]
        c.create_text(header["title_x"], header["cy"], text=self.tool_label,
                      anchor="w", font=self.f_title,
                      fill=self.pal.text if self.tool != "idle" else self.pal.text_dim)
        w = lay["w"]
        inset = lay["inset"]

        for pill in lay["pills"]:
            x, y, pw, ph = pill["box"]
            c.create_text(x + pw / 2, y + ph / 2, text=pill["label"], anchor="center",
                          font=self.f_pill_on if pill["active"] else self.f_pill,
                          fill=accent if pill["active"] else self.pal.text_dim)

        desc_max = w - inset - (lay["rows"][0]["desc_x"] if lay["rows"] else 0)
        for row, chip in zip(lay["rows"], lay["chips"]):
            x, y, cw, ch = chip["box"]
            c.create_text(x + cw / 2, y + ch / 2, text=row["key"], anchor="center",
                          font=self.f_key, fill=self.pal.text)
            c.create_text(row["desc_x"], row["cy"],
                          text=self._fit(row["desc"], self.f_desc, max(0, desc_max)),
                          anchor="w", font=self.f_desc, fill=self.pal.text_dim)

        foot = lay["footer"]
        if foot["page_text"]:
            c.create_text(foot["page_text_x"], foot["cy"], text=foot["page_text"],
                          anchor="w", font=self.f_footer, fill=self.pal.text_dim)
        if foot["hint_text"]:
            c.create_text(foot["hint_x"], foot["cy"], text=foot["hint_text"], anchor="e",
                          font=self.f_footer,
                          fill=theme.blend(self.pal.text_dim, self.pal.card, 0.72))

        self.win.geometry(f"{lay['w']}x{lay['h']}")

    # ---------- 交互 ----------
    def _on_release(self, event: tk.Event) -> None:
        self._press = None
        if getattr(self, "_resizing", False):
            self._resizing = False
            if self.on_resize:
                self.on_resize(self.width, self.rows)

    def _on_wheel(self, event: tk.Event) -> None:
        self.turn(-1 if event.delta > 0 else 1)

    def _on_press(self, event: tk.Event) -> None:
        lay = self._layout
        if lay.get("capsule"):
            return
        grip = lay.get("grip")
        if grip and event.x >= grip["x"] and event.y >= grip["y"]:
            self._resizing = True
            self._resize_from = (event.x_root, event.y_root, self.width, self.rows)
            return
        for i, pill in enumerate(lay.get("pills", [])):
            x, y, pw, ph = pill["box"]
            if x <= event.x <= x + pw and y <= event.y <= y + ph:
                self.select(i)
                return
        if event.y <= lay["header"]["cy"] * 2:
            self._press = (event.x_root - self.win.winfo_rootx(),
                           event.y_root - self.win.winfo_rooty())

    def _on_motion(self, event: tk.Event) -> None:
        if getattr(self, "_resizing", False) and self._resize_from:
            x0, y0, w0, r0 = self._resize_from
            s = self.scale
            dw = (event.x_root - x0) / s
            dh = (event.y_root - y0) / s
            new_w = int(round(w0 + dw))
            # 行数按"增量"算：非行高部分（标题/分类/页脚）不参与换算，否则会多算几行
            new_rows = int(round(r0 + dh / self.m.row_h))
            self.rows = max(self.m.rows_min, min(new_rows, self.m.rows_max))
            self.width = max(self.m.width_min, min(new_w, self.m.width_max))
            self.refresh()
            return
        if not self._press:
            return
        dx, dy = self._press
        self.move_to(event.x_root - dx, event.y_root - dy)

    def _on_double(self, event: tk.Event) -> None:
        self.toggle_collapsed()

    def toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        self.refresh()

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.win.withdraw()

    @property
    def visible(self) -> bool:
        return self.win.state() != "withdrawn"