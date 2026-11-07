"""配色、字体、度量的单一真源。

所有视觉常量都在这里，chrome.py（抗锯齿图形层）和 widgets.py（文字层）
共用同一份数字，保证像素级对齐。
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------- 颜色工具 ----------

def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def hx(t: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, c)) for c in t))


def blend(fg: str, bg: str, alpha: float) -> str:
    f, b = rgb(fg), rgb(bg)
    return hx(tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3)))


def contrast(fg: str, bg: str) -> float:
    """WCAG 对比度。"""
    def lum(c: str) -> float:
        r, g, b = (v / 255 for v in rgb(c))
        f = lambda u: u / 12.92 if u <= 0.03928 else ((u + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    a, b_ = lum(fg), lum(bg)
    hi, lo = max(a, b_), min(a, b_)
    return (hi + 0.05) / (lo + 0.05)


# ---------- 配色方案 ----------

@dataclass(frozen=True)
class Palette:
    name: str
    card: str
    card_edge: str
    chip: str
    chip_edge: str
    text: str
    text_dim: str
    accent: dict[str, str]
    divider_alpha: float = 0.07
    highlight_alpha: float = 0.10
    pill_alpha: float = 0.20

    def divider(self) -> str:
        return blend("#FFFFFF", self.card, self.divider_alpha)

    def highlight(self) -> str:
        return blend("#FFFFFF", self.card, self.highlight_alpha)

    def pill_active_bg(self, tool: str) -> str:
        return blend(self.accent_of(tool), self.card, self.pill_alpha)

    def pill_idle_bg(self) -> str:
        return blend("#FFFFFF", self.card, 0.05)

    def accent_of(self, tool: str) -> str:
        return self.accent.get(tool, self.accent["idle"])


PALETTES: dict[str, Palette] = {
    # A · 冷调（主推）
    "A": Palette(
        name="冷调",
        card="#16181C",
        card_edge="#414A57",
        chip="#2B3038",
        chip_edge="#4A525F",
        text="#F0F1F3",
        text_dim="#AEB5C0",
        accent={
            "capture": "#4EA1FF",
            "allegro": "#F0A64B",
            "dehdl": "#9C8CFF",
            "idle": "#6B7280",
        },
    ),
    # B · 暖调
    "B": Palette(
        name="暖调",
        card="#1A1815",
        card_edge="#453C2F",
        chip="#332B21",
        chip_edge="#5C4E3B",
        text="#F5F0E8",
        text_dim="#BCAF9D",
        accent={
            "capture": "#E8B75A",
            "allegro": "#E07B5F",
            "dehdl": "#C9A227",
            "idle": "#7A7166",
        },
    ),
}


# ---------- 度量（100% DPI 逻辑像素） ----------

@dataclass(frozen=True)
class Metrics:
    width: int = 332
    width_min: int = 260
    width_max: int = 620
    rows_min: int = 3
    rows_max: int = 40
    grip: int = 14
    pad: int = 8
    inset: int = 12
    card_r: int = 11
    header_h: int = 26
    divider_h: int = 1
    pills_row_h: int = 26
    pill_h: int = 18
    pill_r: int = 9
    pill_gap: int = 5
    pill_pad_x: int = 9
    row_h: int = 24
    chip_h: int = 17
    chip_r: int = 5
    chip_pad_x: int = 6
    chip_min_w: int = 24
    chip_col_min: int = 24
    desc_gap: int = 9
    footer_h: int = 16
    rows: int = 6
    dot_r: int = 2
    dot_gap: int = 6
    accent_dot_r: int = 3

    def height(self, pills_lines: int = 1) -> int:
        return (self.pad + self.header_h + self.divider_h
                + self.pills_row_h * pills_lines
                + self.row_h * self.rows + self.divider_h
                + self.footer_h + self.pad)


# ---------- 字体（负值 = 像素尺寸，便于按 DPI 精确缩放） ----------

FONTS: dict[str, tuple[str, int, str]] = {
    "key": ("Cascadia Mono", -12, "bold"),
    "desc": ("Microsoft YaHei UI", -12, "normal"),
    "title": ("Microsoft YaHei UI", -13, "bold"),
    "pill": ("Microsoft YaHei UI", -11, "normal"),
    "pill_on": ("Microsoft YaHei UI", -11, "bold"),
    "footer": ("Microsoft YaHei UI", -10, "normal"),
}

TOOL_LABELS = {
    "capture": "OrCAD Capture · 原理图",
    "allegro": "Allegro PCB Editor · PCB",
    "dehdl": "Design Entry HDL",
    "idle": "空闲",
}

CAPSULE_LABELS = {
    "capture": "Capture",
    "allegro": "Allegro",
    "dehdl": "DE HDL",
    "idle": "空闲",
}

ROWS_CHOICES = (6, 9, 12, 16)