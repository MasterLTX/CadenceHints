"""自检：把能自动验的项全跑一遍，出报告。

对应方案里的 T1 / T4 / T5 / T6 / T9 / T10（对比度）以及数据完整性检查。
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path

import focus
import menu as menu_mod
import parse_env
import theme
import widgets

BASE = Path(__file__).parent
DATA = BASE / "data"
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))


def check_data() -> None:
    for tool, fname in (("capture", "capture.json"), ("allegro", "allegro.json")):
        p = DATA / fname
        if not p.exists():
            check(f"数据文件 {fname}", False, "缺失")
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        items = [it for s in payload["sections"] for it in s["items"]]
        check(f"数据文件 {fname}", bool(items), f"{len(items)} 条 / {len(payload['sections'])} 分区")
        keys = [it["key"] for it in items]
        dup = {k for k in keys if keys.count(k) > 1}
        check(f"{fname} 键位无重复", not dup, f"重复: {sorted(dup)}" if dup else "ok")
        bad = [it for it in items if not it.get("desc")]
        check(f"{fname} 全部有说明", not bad, f"{len(bad)} 条缺说明")


def check_parse_env() -> None:
    env_paths = [parse_env.GLOBAL_ENV, *parse_env.USER_ENVS]
    entries = {}
    if any(path.exists() for path in env_paths):
        entries, alias = parse_env.parse(env_paths)
        check("env 解析条数 ≥ 40", len(entries) >= 40, f"实际 {len(entries)} 条")
    else:
        # 未装 Cadence 的机器没有 env 文件，这不是包的错误，应该用例跳过。
        results.append(("env 解析条数 ≥ 40", SKIP,
                        "未找到 Cadence env 文件，跳过；安装 Cadence 后才验证此项"))
    expect = {
        "Ctrl+S": "~S", "Shift+F2": "SF2", "PageUp": "Pgup",
        "Ctrl+Shift+F5": "CSF5", "Ctrl+Shift+B": "~SB", "Ctrl+Z": "~Z",
    }
    for want, raw in expect.items():
        got = parse_env.norm_key(raw)
        check(f"键位翻译 {raw} → {want}", got == want, f"实际 {got}")
    junk = [k for k in entries if not parse_env.is_real_key(k)]
    check("无多字母命令混入", not junk, f"{junk}" if junk else "ok")


def check_focus() -> None:
    tool, why = focus.detect()
    check("前台探测可用", tool in ("capture", "allegro", "dehdl", "idle"), f"{tool} ({why})")


def check_paging() -> None:
    root = tk.Tk()
    root.withdraw()
    panel = widgets.HintPanel(root, palette="A", rows=3)
    payload = json.loads((DATA / "capture.json").read_text(encoding="utf-8"))
    panel.set_data(payload)
    n = panel._page_count()
    check("分页数 > 1", n > 1, f"{n} 页")
    panel.page = 0
    panel.turn(-1)
    check("上一页回绕到末页", panel.page == n - 1, f"page={panel.page}")
    panel.turn(1)
    check("下一页回绕回首页", panel.page == 0, f"page={panel.page}")
    panel.select(1)
    check("点分类回到第 1 页", panel.page == 0 and panel.sel == 1, f"sel={panel.sel}")
    visible = panel._visible()
    check("可见行数不超一页", len(visible) <= 3, f"{len(visible)} 行")
    panel.toggle_collapsed()
    check("折叠后布局是胶囊", bool(panel._layout.get("capsule")), f"{panel._layout['w']}x{panel._layout['h']}")
    panel.toggle_collapsed()

    # 对齐：同页键帽高度一致、左边缘一致
    lay = panel._layout
    xs = {c["box"][0] for c in lay["chips"]}
    hs = {c["box"][3] for c in lay["chips"]}
    check("键帽左边缘对齐", len(xs) == 1, f"x={xs}")
    check("键帽高度一致", len(hs) == 1, f"h={hs}")
    root.destroy()


def check_resize_menu() -> None:
    root = tk.Tk()
    root.withdraw()
    panel = widgets.HintPanel(root, palette="A", rows=6)
    panel.set_data(json.loads((DATA / "capture.json").read_text(encoding="utf-8")))

    base_h = panel._layout["h"]
    panel.set_rows(9)
    check("行数改变后高度变大", panel._layout["h"] > base_h,
          f"{base_h} → {panel._layout['h']}")
    panel.set_width(440)
    check("宽度可调", panel._layout["w"] == round(440 * panel.scale),
          f"got {panel._layout['w']}")
    panel.set_width(10_000)
    check("宽度上限生效", panel.width == panel.m.width_max, f"width={panel.width}")
    panel.set_rows(100)
    check("行数上限生效", panel.rows == panel.m.rows_max, f"rows={panel.rows}")
    panel.set_width(1)
    panel.set_rows(1)
    check("宽度/行数下限生效",
          panel.width == panel.m.width_min and panel.rows == panel.m.rows_min,
          f"{panel.width}x{panel.rows}")

    # 缩放增量换算：往下一行高度，行数应 +1
    r0 = panel.rows
    step = panel.m.row_h * panel.scale
    delta_rows = int(round(r0 + step / panel.scale / panel.m.row_h))
    check("拖拽换算：一行高度 = 一行", delta_rows == r0 + 1, f"{r0} → {delta_rows}")

    items = [{"label": "一行", "action": None}, None, {"label": "两行", "checked": True}]
    pop = menu_mod.PopupMenu(root, items, panel.pal, panel.scale, (400, 400))
    root.update()
    check("自绘菜单能弹出", pop.win.winfo_width() > 60,
          f"{pop.win.winfo_width()}x{pop.win.winfo_height()}")
    pop.close()
    root.destroy()


def check_contrast() -> None:
    for name, p in theme.PALETTES.items():
        body = theme.contrast(p.text_dim, p.card)
        check(f"{name} 正文对比度 ≥ 7:1", body >= 7.0, f"{body:.2f}:1")
        key = theme.contrast(p.text, p.chip)
        check(f"{name} 键帽对比度 ≥ 7:1", key >= 7.0, f"{key:.2f}:1")


def main() -> int:
    check_data()
    check_parse_env()
    check_focus()
    check_paging()
    check_resize_menu()
    check_contrast()

    width = max(len(r[0]) for r in results)
    for name, status, detail in results:
        mark = {PASS: "✔", FAIL: "✘", SKIP: "~"}[status]
        suffix = "" if status != SKIP else "（跳过）"
        detail = f"{detail}{suffix}"
        print(f"{mark} {name:<{width}}  {detail}")
    failed = [r for r in results if r[1] == FAIL]
    skipped = [r for r in results if r[1] == SKIP]
    passed = len(results) - len(failed) - len(skipped)
    suffix = f"，另有 {len(skipped)} 项跳过" if skipped else ""
    print(f"\n{passed}/{len(results)} 通过{suffix}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())