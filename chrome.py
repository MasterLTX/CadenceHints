"""抗锯齿图形层。

tk 的 Canvas 没有抗锯齿，圆角会锯齿成楼梯。所以所有**形状**（卡片、键帽、
pill、分页点）都交给 Pillow 在 4 倍超采样下绘制再 LANCZOS 缩放；
**文字**留给 tk 原生渲染（CJK 更清晰）。

透明处理：窗口用 -transparentcolor 抠掉纯黑，因此这里把背景铺成纯黑，
形状边缘的抗锯齿像素混向黑色 → 形成一圈极淡的暗边，正好当作描边的延伸。
"""
from __future__ import annotations

from PIL import Image, ImageDraw

SS = 4  # 超采样倍数
KEY_COLOR = (0, 0, 0)  # PIL 用：与窗口 -transparentcolor 一致
KEY_HEX = "#000000"    # tk 用


def _s(v: float) -> int:
    return int(round(v * SS))


def _box(b: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = b
    return (_s(x), _s(y), _s(x + w), _s(y + h))


def render(layout: dict, palette, scale: float) -> Image.Image:
    """按 layout 画一张整窗尺寸的抗锯齿底图。"""
    w = int(round(layout["w"]))
    h = int(round(layout["h"]))
    img = Image.new("RGB", (w * SS, h * SS), KEY_COLOR)
    d = ImageDraw.Draw(img)

    if layout.get("capsule"):
        d.rounded_rectangle(
            _box((0, 0, w - 1, h - 1)),
            radius=_s(layout["card_r"]),
            fill=palette.card,
            outline=palette.card_edge,
            width=_s(1),
        )
        dot = layout.get("dot")
        if dot:
            d.ellipse(
                (
                    _s(dot["cx"] - dot["r"]), _s(dot["cy"] - dot["r"]),
                    _s(dot["cx"] + dot["r"]), _s(dot["cy"] + dot["r"]),
                ),
                fill=dot["color"],
            )
        return img.resize((w, h), Image.LANCZOS)

    # --- 卡片 ---
    d.rounded_rectangle(
        _box((0, 0, w - 1, h - 1)),
        radius=_s(layout["card_r"]),
        fill=palette.card,
        outline=palette.card_edge,
        width=_s(1),
    )

    # --- 顶部 1px 高光（玻璃感） ---
    d.line(
        (_s(layout["card_r"]), _s(1), _s(w - layout["card_r"]), _s(1)),
        fill=palette.highlight(), width=_s(1),
    )

    # --- 顶部强调色圆点 ---
    dot = layout.get("dot")
    if dot:
        d.ellipse(
            (
                _s(dot["cx"] - dot["r"]), _s(dot["cy"] - dot["r"]),
                _s(dot["cx"] + dot["r"]), _s(dot["cy"] + dot["r"]),
            ),
            fill=dot["color"],
        )

    # --- 分隔线 ---
    div = palette.divider()
    for y in layout.get("dividers", []):
        d.rectangle((_s(layout["inset"]), _s(y), _s(w - layout["inset"]), _s(y + 1)), fill=div)

    # --- 分类 pill ---
    accent_color = palette.accent_of(layout["tool"])
    for pill in layout.get("pills", []):
        if pill["active"]:
            d.rounded_rectangle(
                _box(pill["box"]), radius=_s(layout["pill_r"]),
                fill=palette.pill_active_bg(layout["tool"]),
                outline=accent_color, width=_s(1),
            )
        else:
            d.rounded_rectangle(
                _box(pill["box"]), radius=_s(layout["pill_r"]),
                fill=palette.pill_idle_bg(),
            )

    # --- 键帽 ---
    for chip in layout.get("chips", []):
        d.rounded_rectangle(
            _box(chip["box"]),
            radius=_s(layout["chip_r"]),
            fill=palette.chip,
            outline=palette.chip_edge,
            width=_s(1),
        )

    # --- 右下角缩放抓手 ---
    grip = layout.get("grip")
    if grip:
        gs = grip["size"]
        x0, y0 = grip["x"], grip["y"]
        for i, frac in enumerate((0.30, 0.52, 0.74)):
            d.line(
                (_s(x0 + gs * frac), _s(y0 + gs),
                 _s(x0 + gs), _s(y0 + gs * frac)),
                fill=palette.text_dim, width=_s(1),
            )

    # --- 分页点 ---
    accent = palette.accent_of(layout["tool"])
    for dot_ in layout.get("page_dots", []):
        color = accent if dot_["active"] else palette.text_dim
        alpha_box = (
            _s(dot_["cx"] - dot_["r"]), _s(dot_["cy"] - dot_["r"]),
            _s(dot_["cx"] + dot_["r"]), _s(dot_["cy"] + dot_["r"]),
        )
        if dot_["active"]:
            d.ellipse(alpha_box, fill=color)
        else:
            d.ellipse(alpha_box, fill=palette.card, outline=color, width=_s(1))

    return img.resize((w, h), Image.LANCZOS)