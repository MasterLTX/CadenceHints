"""视觉样机渲染器：真实像素渲染 + 截图，并可贴到浅/深背景上对比真实观感。"""
from __future__ import annotations

import ctypes
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageGrab

import widgets

OUT = Path(__file__).parent / "preview"

MOCK_CAPTURE = {
    "tool": "capture",
    "title": "OrCAD Capture",
    "sections": [
        {
            "name": "放置", "pinned": True,
            "items": [
                {"key": "P", "desc": "放置器件", "raw": "Place Part"},
                {"key": "W", "desc": "放置导线", "raw": "Place Wire"},
                {"key": "N", "desc": "放置网络标号", "raw": "Place Net Alias"},
                {"key": "G", "desc": "放置电源（GND）", "raw": "Place Ground"},
                {"key": "F", "desc": "放置电源（VCC）", "raw": "Place Power"},
                {"key": "B", "desc": "放置总线", "raw": "Place Bus"},
                {"key": "J", "desc": "放置连接点", "raw": "Place Junction"},
            ],
        },
        {
            "name": "连线", "pinned": True,
            "items": [
                {"key": "F4", "desc": "重复上一次放置", "raw": "Repeat"},
                {"key": "Shift+W", "desc": "总线分支", "raw": "Bus Entry"},
                {"key": "Ctrl+E", "desc": "编辑属性", "raw": "Edit Properties"},
            ],
        },
        {
            "name": "编辑", "pinned": False,
            "items": [
                {"key": "Ctrl+C", "desc": "复制", "raw": "Copy"},
                {"key": "Delete", "desc": "删除所选", "raw": "Delete"},
                {"key": "Ctrl+Z", "desc": "撤销", "raw": "Undo"},
                {"key": "Ctrl+Shift+Z", "desc": "重做", "raw": "Redo"},
            ],
        },
        {
            "name": "查找", "pinned": False,
            "items": [
                {"key": "Ctrl+F", "desc": "查找器件", "raw": "Find"},
                {"key": "Ctrl+G", "desc": "查找下一个", "raw": "Find Next"},
                {"key": "Shift+F5", "desc": "全图浏览", "raw": "Zoom All"},
            ],
        },
    ],
}


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def capture(palette: str, collapsed: bool = False) -> tuple[Image.Image, int]:
    root = tk.Tk()
    root.withdraw()
    panel = widgets.HintPanel(root, palette=palette, rows=6)
    panel.set_data(MOCK_CAPTURE)
    panel.set_tool("capture")
    if collapsed:
        panel.toggle_collapsed()
    panel.move_to(120, 120)
    panel.show()
    for _ in range(3):
        root.update()
        time.sleep(0.12)
    x, y, w, h = panel.geometry()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    radius = panel._layout["card_r"]
    root.destroy()
    return img, radius


def corner_mask(size: tuple[int, int], radius: int) -> Image.Image:
    ss = 4
    big = Image.new("L", (size[0] * ss, size[1] * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, size[0] * ss - 1, size[1] * ss - 1), radius=radius * ss, fill=255)
    return big.resize(size, Image.LANCZOS)


def sheet(items: dict[str, tuple[Image.Image, int]], out: Path) -> Path:
    """2 配色 × 2 背景 的对比图，模拟在 Capture 白底与深色 IDE 上的真实观感。"""
    backgrounds = [(246, 247, 249), (22, 23, 27)]
    pad, gap, label_h = 26, 28, 20
    shots = list(items.items())
    cw = max(img.width for img, _ in items.values())
    chh = max(img.height for img, _ in items.values())
    W = pad * 2 + len(shots) * cw + (len(shots) - 1) * gap
    H = pad * 2 + len(backgrounds) * (chh + label_h) + (len(backgrounds) - 1) * gap
    canvas = Image.new("RGB", (W, H), (128, 130, 134))
    d = ImageDraw.Draw(canvas)

    for r, bg in enumerate(backgrounds):
        y = pad + r * (chh + label_h + gap)
        d.rectangle((pad, y, W - pad, y + chh + label_h - 1), fill=bg)
        for c, (name, (img, radius)) in enumerate(shots):
            x = pad + c * (cw + gap)
            canvas.paste(img, (x, y), corner_mask(img.size, radius))
    canvas.save(out)
    return out


if __name__ == "__main__":
    set_dpi_aware()
    OUT.mkdir(parents=True, exist_ok=True)

    a, ra = capture("A")
    b, rb = capture("B")
    cap, rc = capture("A", collapsed=True)
    a.save(OUT / "mock_A.png")
    b.save(OUT / "mock_B.png")
    cap.save(OUT / "mock_A_capsule.png")
    print(f"A: {a.width}x{a.height}  B: {b.width}x{b.height}  胶囊: {cap.width}x{cap.height}")
    print("对比图 ->", sheet({"A 冷调": (a, ra), "B 暖调": (b, rb)}, OUT / "sheet.png"))