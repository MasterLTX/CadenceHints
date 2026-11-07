"""解析 Allegro PCB Editor 的 env 文件，生成 data/allegro.json。

快捷键来自本机真实配置，不是网上抄的通用表：
  1. 先读全局 env（安装目录）
  2. 再读用户 env（pcbenv），同键覆盖 —— 用户自定义优先
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

GLOBAL_ENV = Path(r"C:\Cadence\SPB_17.4\share\pcb\text\env")
USER_ENVS = [
    Path(r"C:\Cadence\SPB_Data\pcbenv\env"),
    Path(os.path.expanduser("~")) / "pcbenv" / "env",
]

LINE_RE = re.compile(r'^\s*(funckey|alias)\s+(" "|\S+)\s+(.+?)\s*$')

KEY_NAMES = {
    "pgup": "PageUp", "pgdown": "PageDown", "pgdn": "PageDown",
    "del": "Delete", "ins": "Insert", "bksp": "Backspace",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "home": "Home", "end": "End", "esc": "Esc", "tab": "Tab",
    "space": "Space", "bs": "Backspace", "enter": "Enter",
}

MOD_ORDER = ["Ctrl", "Shift", "Alt"]

# 命令 → 人话。按最长前缀匹配，未命中原样保留（不猜不丢）
COMMANDS: dict[str, str] = {
    "zoom fit": "缩放全图",
    "zoom in": "放大",
    "zoom out": "缩小",
    "zoom previous": "上一视图",
    "zoom world": "全宇宙视图",
    "zoom center": "缩放到中心",
    "redraw": "重绘屏幕",
    "grid toggle": "栅格开关",
    "layer up": "上一层",
    "layer down": "下一层",
    "subclass -+": "下一子类",
    "subclass --": "上一子类",
    "add connect": "布线",
    "slide": "推挤/滑线",
    "move": "移动",
    "copy": "复制",
    "delete": "删除",
    "oops": "撤销上一步",
    "undo": "撤销",
    "redo": "重做",
    "done": "完成当前命令",
    "cancel": "取消当前命令",
    "next": "选择下一项",
    "vertex": "编辑顶点",
    "show element": "查看对象属性",
    "show measure": "测量距离",
    "property edit": "编辑属性",
    "hilight pick": "高亮所选",
    "dehilight": "取消高亮",
    "save": "保存",
    "save_as temp": "临时另存",
    "new": "新建",
    "open": "打开",
    "pick": "拾取点",
    "pick l": "拾取相对点",
    "ipick": "增量拾取",
    "padedit": "焊盘编辑",
    "replace padstack": "替换焊盘栈",
    "report unplaced": "报告未放置器件",
    "status": "查看状态",
    "color192": "颜色面板",
    "layer priority": "层优先级",
    
    "prepopup": "右键菜单",
    "settoggle": "切换开关",
    "options bubble_space": "气泡空间",
    "open -q": "重新打开",
    "cdsdoc": "打开帮助",
}

# 分区归属（按命令关键字判断，先匹配先生效）
SECTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("布线", ("add connect", "slide", "bubble", "neck", "route")),
    ("视图", ("zoom", "redraw", "roam", "layer up", "layer down", "grid", "color192", "subclass")),
    ("编辑", ("move", "copy", "delete", "oops", "undo", "redo", "vertex", "replace padstack", "padedit")),
    ("查询", ("show", "status", "report", "property", "hilight", "dehilight", "measure")),
    ("文件", ("new", "open", "save", "revert", "reopen")),
]
DEFAULT_SECTION = "操作"


VALID_BASE_RE = re.compile(
    r"^(?:[A-Za-z0-9+~\-=,./\\;'\[\]]|F\d{1,2}|PageUp|PageDown|Space|Home|End|"
    r"Insert|Delete|Backspace|Tab|Esc|Enter|↑|↓|←|→)$"
)


def is_real_key(normalized: str) -> bool:
    """区分「真快捷键」和「多字母命令别名」（后者是命令行里敲的，不是按键）。"""
    base = normalized.rsplit("+", 1)[-1]
    return bool(VALID_BASE_RE.match(base))


def norm_key(raw: str) -> str:
    if raw == '" "' or raw.strip() == "":
        return "Space"
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    mods: list[str] = []
    rest = raw
    if rest.startswith("~"):
        mods.append("Ctrl")
        rest = rest[1:]
    while len(rest) >= 2 and rest[0] in "CSA":
        mods.append({"C": "Ctrl", "S": "Shift", "A": "Alt"}[rest[0]])
        rest = rest[1:]
    base = KEY_NAMES.get(rest.lower(), rest)
    if not base:
        base = raw
    mods = [m for m in MOD_ORDER if m in mods]
    return "+".join(mods + [base])


ROAM_RE = re.compile(r"^roam\s+([xy])\s+(-?)\$?roamInc", re.I)


def clean(text: str, limit: int = 26) -> str:
    t = text.strip().strip("'\"").replace("  ", " ")
    return t if len(t) <= limit else t[: limit - 1] + "…"


def describe(cmd: str, alias_cmd: dict[str, str], depth: int = 0) -> str:
    cmd = cmd.strip()
    if depth < 4 and cmd in alias_cmd:
        return describe(alias_cmd[cmd], alias_cmd, depth + 1)
    m = ROAM_RE.match(cmd)
    if m:
        axis, sign = m.group(1).lower(), m.group(2)
        return f"平移视图 {axis}{'-' if sign else '+'}"
    best = ""
    for k in COMMANDS:
        if cmd.startswith(k) and len(k) > len(best):
            best = k
    if best:
        base = COMMANDS[best]
        tail = cmd[len(best):].strip(" ;\"'$")
        return f"{base}（{clean(tail, 16)}）" if tail else base
    return clean(cmd)


def section_of(cmd: str) -> str:
    for name, keys in SECTION_RULES:
        if any(k in cmd for k in keys):
            return name
    return DEFAULT_SECTION


def parse(paths: list[Path]) -> tuple[dict[str, dict], dict[str, str]]:
    entries: dict[str, dict] = {}
    alias_cmd: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        origin = "default" if "share" in str(path).lower() else "user"
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.split("#", 1)[0].rstrip()
            m = LINE_RE.match(line)
            if not m:
                continue
            kind, raw_key, cmd = m.group(1), m.group(2), m.group(3).strip()
            key = norm_key(raw_key)
            if not is_real_key(key):
                # 多字母「别名」是命令行里敲的，不是按键 —— 只留作解析链
                if kind == "alias":
                    alias_cmd[raw_key.strip('"')] = cmd
                continue
            snippet = cmd.strip("'\"")
            snippet = snippet.split(";")[0].strip()
            entries[key] = {
                "key": key,
                "raw": f"{kind} {raw_key} {cmd}"[:120],
                "cmd": snippet,
                "source": origin,
                "section": section_of(snippet),
            }
    return entries, alias_cmd


def build(entries: dict[str, dict], alias_cmd: dict[str, str]) -> dict:
    sections: dict[str, list[dict]] = {}
    for e in entries.values():
        desc = describe(e["cmd"], alias_cmd)
        sections.setdefault(e["section"], []).append(
            {"key": e["key"], "desc": desc, "raw": e["raw"], "source": e["source"]}
        )

    order = ["布线", "视图", "编辑", "查询", "文件", DEFAULT_SECTION]
    out = []
    for name in order:
        items = sections.get(name)
        if not items:
            continue
        items.sort(key=lambda it: (len(it["key"]), it["key"]))
        out.append({"name": name, "pinned": name in ("布线", "视图"), "items": items})
    return {"tool": "allegro", "title": "Allegro PCB Editor", "sections": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parent / "data" / "allegro.json")
    args = ap.parse_args()

    paths = [GLOBAL_ENV, *USER_ENVS]
    entries, alias_cmd = parse(paths)
    if not entries:
        print(f"[!] 没从这些文件里解析到快捷键: {[str(p) for p in paths]}", file=sys.stderr)
        return 1
    payload = build(entries, alias_cmd)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(s["items"]) for s in payload["sections"])
    print(f"解析 {total} 条快捷键 → {args.out}")
    for s in payload["sections"]:
        print(f"  {s['name']}: {len(s['items'])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())