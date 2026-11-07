# CadenceHints —— Cadence 快捷键提示浮窗

> **v1.0.0** · 2026-11-07 · 变更见 [CHANGELOG.md](CHANGELOG.md)

常驻桌面的小浮窗，**自动认出你在用哪个 Cadence 工具**，跟着切换对应的快捷键提示：
在 OrCAD Capture 里显示原理图快捷键，在 Allegro PCB Editor 里显示 PCB 快捷键。

```
┌────────────────────────────┐
│ ●  OrCAD Capture · 原理图  │
│  常用  放置  编辑  视图 …  │
│  ┌─┐                       │
│  │P│  放置器件             │
│  └─┘                       │
│  ●●○  1/3      滚轮翻页  ⣿ │ ← 右下角拖拽缩放
└────────────────────────────┘
```

## 启动

| 方式 | 操作 |
|---|---|
| **开始菜单** | 已创建快捷方式：开始菜单搜 `CadenceHints` |
| 手动 | 双击 `start_hint.vbs`（静默启动，无黑窗） |
| 调试 | `python app.py`（有控制台可看日志） |
| 开机自启 | `Win+R` → `shell:startup` → 把 `start_hint.vbs` 的快捷方式丢进去 |

> 首次运行会在同目录生成 `hint.json` 记住位置、尺寸、配色、行数。
> **单实例**：重复双击（VBS / 开始菜单 / 任务栏按钮）不会冒出第二个托盘图标——
> 新进程检测到已有实例后，会唤出已有的浮窗并自己退出。
> 调试时若确实要开多个：`python app.py --allow-multi`。

## 交互

| 操作 | 效果 |
|---|---|
| 滚轮 | 当前分类内翻页（末页回绕） |
| 点分类 pill | 跳到该分类第 1 页 |
| 拖标题栏 | 移动窗口，位置自动记住 |
| **拖右下角** | 同时调宽和高，**行数随高度自动换算**，松手即保存（一页最多 40 行） |
| 双击标题栏 | 折叠成小胶囊 / 展开 |
| 右键 | 自绘菜单：**设置…**、配色 A/B、每页行数、重载数据、收起、退出 |
| **设置面板** | 不透明度 / 空闲变暗 / 字号 / 配色 / 非 Cadence 时(隐藏或变暗) / 每页行数 / 卡片宽度 / 任务栏按钮 / 开机自启，全部即时生效；标题栏可拖动 |
| `Ctrl+Alt+H` | 全局收起 / 展开（在 Cadence 里也有效） |
| 托盘图标 | 左键点 → 显示/收起；右键 → 菜单（含配色切换、退出） |
| 任务栏按钮 | **默认关闭**（设置里可开）。开启后任务栏出现 `Cadence...` 按钮，点一下 = 显示/收起 |

默认**只有 Cadence 在前台才显示**，切走就完全隐藏（不吃前台、不挡视线）。想改成"变暗但保留"，
在设置面板把「非 Cadence 时」切成 `变暗`。手动用 `Ctrl+Alt+H` 收起后，切回 Cadence 也不会强行弹出。

## 数据从哪来

| 工具 | 来源 | 条数 |
|---|---|---|
| **Allegro PCB Editor** | 解析本机 `C:\Cadence\SPB_17.4\share\pcb\text\env` 里真实的 `funckey`/`alias` | 51 |
| **OrCAD Capture** | 手工策展官方默认快捷键（Capture 磁盘上没有机器可读的快捷键配置） | 26 |

### 改了 Allegro 快捷键

```powershell
python parse_env.py     # 重跑解析
```

然后在浮窗右键「重载快捷键数据」。解析顺序 `share\pcb\text\env`（全局）→ `%HOME%\pcbenv\env`（用户），**同名键用户配置优先**。

### 加 / 改 Capture 提示

编辑 `data\capture.json`：

```json
{ "name": "分类名", "pinned": true,
  "items": [ { "key": "Ctrl+E", "desc": "编辑属性", "raw": "Edit Properties" } ] }
```

- `pinned: true` 的分类会汇总进「常用」首页
- 改完右键「重载快捷键数据」，不用重启

## 自检

```powershell
python selftest.py      # 34 项：数据 / 键位翻译 / 探测 / 分页 / 缩放 / 菜单 / 对比度
                        # 未装 Cadence 的机器上 env 用例标记 SKIP（预期跳过，非失败）
python e2e_check.py     # 端到端：起浮窗 → 拉 Capture 到前台 → 截图
python make_mock.py     # 配色样机对比图 → preview/sheet.png
```

## 依赖

- Python 3.12 + 标准库 `tkinter`
- `Pillow` —— 抗锯齿绘制圆角卡片、键帽、菜单
- `pystray` —— 托盘图标（没装也能跑，只是没有托盘，日志会提示）

```powershell
pip install -r requirements.txt
```

## 迁移到别的机器

1. 整个 `06_Hint` 文件夹拷过去
2. `pip install -r requirements.txt`
3. 改 `parse_env.py` 顶部的 `GLOBAL_ENV` 路径（指向那台机器的 Cadence 安装位置）
4. 跑一次 `python parse_env.py` 重新生成 `allegro.json`
5. 双击 `start_hint.vbs`

> `hint.json`（位置/尺寸/外观）和 `logs/` 是运行时产物，可以不带。

## 已知限制

1. **任务栏按钮默认关闭**：不需要就不用管；想开在设置面板里打开（Win11 显示为 `Cadence...`）。
2. **托盘图标默认折叠**：想让它常驻通知区，去「设置 > 个性化 > 任务栏 > 其他系统托盘图标」把 CadenceHints 打开。
3. **热键被占用**：`Ctrl+Alt+H` 若已被别的软件注册，启动日志会报警，改用双击标题栏。
4. **Cadence 以管理员启动**：拿不到进程句柄时降级用窗口标题匹配。
5. **Capture 快捷键需你核对**：磁盘上没有机器可读配置，`capture.json` 按官方默认整理，实际键位有出入直接改 JSON。
6. **无真阴影**：tk 不支持逐像素 alpha，卡片用 1px 描边 + 顶部高光代替投影。
7. **多显示器**：坐标会夹进主屏范围，拔掉副屏后自动拉回。

## 文件说明

| 文件 | 作用 |
|---|---|
| `app.py` | 入口：探针循环 + 热键 + 托盘 + 菜单装配 |
| `widgets.py` | 浮窗本体：布局计算（含拖拽缩放）+ 图形贴图 + 文字层 |
| `chrome.py` | 抗锯齿图形层（Pillow 4 倍超采样） |
| `menu.py` | **自绘右键菜单**（独立置顶窗口，不会被浮窗遮挡） |
| `tray.py` | 托盘图标 + 图标绘制 |
| `taskbar.py` | 任务栏按钮宿主（最小化窗口，点击切换浮窗；默认不开） |
| `settings.py` | 设置面板：自绘滑块 / 步进器 / 分段选择 / 开关 |
| `single.py` | 单实例守卫（命名互斥体 + 命名事件唤醒） |
| `theme.py` | 配色 A/B、字体、度量（视觉单一真源） |
| `focus.py` | 前台进程探测 |
| `hotkey.py` | 全局热键注册与消息循环 |
| `parse_env.py` | 解析 Allegro env → `data/allegro.json` |
| `selftest.py` / `e2e_check.py` / `make_mock.py` | 自检 / 端到端 / 视觉样机 |
| `hint.json` / `logs/app.log` | 运行时配置 / 运行日志（pythonw 崩溃也查得到） |