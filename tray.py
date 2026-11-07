"""托盘图标（通知区）。让浮窗收起后还能找回来。

pystray 的回调在它自己的线程里跑，所有 UI 操作都通过队列切回 Tk 主线程。
"""
from __future__ import annotations

from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw

    HAVE_TRAY = True
except Exception:  # pystray 没装就安静降级
    HAVE_TRAY = False


def make_icon(card: str = "#16181C", accent: str = "#4EA1FF", size: int = 64) -> "Image.Image":
    """图标：深色圆角块 + 强调色键帽 + 几条提示行。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, size // 32)
    d.rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1),
                        radius=size // 5, fill=card, outline=accent, width=max(2, size // 24))
    d.rounded_rectangle((size * 0.22, size * 0.22, size * 0.47, size * 0.40),
                        radius=size // 16, fill=accent)
    for i, (y, w) in enumerate(((0.50, 0.56), (0.66, 0.44), (0.82, 0.30))):
        d.rounded_rectangle((size * 0.22, size * y, size * (0.22 + w), size * y + max(3, size // 14)),
                            radius=size // 32, fill=(255, 255, 255, 220 - i * 50))
    return img


def write_png(path: Path, card: str, accent: str, size: int = 64) -> Path:
    if not HAVE_TRAY:
        return path
    make_icon(card, accent, size).save(path)
    return path


def write_ico(path: Path, card: str, accent: str) -> Path:
    if not HAVE_TRAY:
        return path
    make_icon(card, accent).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
    return path


class Tray:
    """托盘；任何失败都只记日志，不影响主程序。"""

    def __init__(self, *, title: str, icon_path: Path, on_toggle, on_quit, on_palette, palette_ids):
        self.title = title
        self.icon_path = icon_path
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self.on_palette = on_palette
        self.palette_ids = palette_ids
        self.icon = None
        self.ok = False

    def start(self) -> bool:
        if not HAVE_TRAY:
            return False
        try:
            image = Image.open(self.icon_path).convert("RGBA") \
                if self.icon_path.exists() else make_icon()
            menu = pystray.Menu(
                pystray.MenuItem("显示 / 收起", lambda *_: self.on_toggle(), default=True),
                pystray.Menu.SEPARATOR,
                *[pystray.MenuItem(f"配色 {pid}", lambda *_, p=pid: self.on_palette(p),
                                   checked=lambda item, p=pid: getattr(self, "_pal", "A") == p)
                  for pid in self.palette_ids],
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda *_: self.on_quit()),
            )
            self.icon = pystray.Icon("CadenceHints", image, self.title, menu)
            self.icon.run_detached()
            self.ok = True
        except Exception:
            self.ok = False
        return self.ok

    def set_palette(self, pid: str) -> None:
        self._pal = pid

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass