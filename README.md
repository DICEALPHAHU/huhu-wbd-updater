# 糊糊爆破模式客户端 更新器

一个给 Minecraft 整合包客户端用的**图形化自动更新器**（Windows，打包成单个 `.exe`）。
放在客户端根目录（与 `Plain Craft Launcher 2.exe` 同级）运行。

作者：糊糊　QQ：2387629002

## 功能

- **版本检查**：读取服务器 `version.json` 与本地 `version.json` 比对；
  已最新时显示「目前已经是最新版本：x.x.x」并把更新按钮置灰。
- **两种更新方式**
  - 方式一 · 逐目录（默认）：`mods` / `config` / `tacz` / `resourcepacks`
    各自独立版本，只下载版本变化了的目录。
  - 方式二 · 全量：下载整包覆盖整个客户端根目录。
- **进度反馈**：进度条 + 下载速度(MB/s) + 剩余时间。
- **暂停 / 继续**：HTTP Range 断点续传，不重头下。
- **取消更新**：已改动的文件从更新前备份**原样还原**。
- **更新检查服务器切换**：界面下拉「默认 / 自定义」，自定义输入会写回 ini。
- **更新公告**：读取服务器 `note.json`，隔离保存在 `HuhuUpdate\note.json`。
- **出错才写日志**：日常运行不产生日志；出错时生成 `更新器日志-年月日时分秒`。

## 目录布局

```
糊糊爆破模式客户端/
  ├── 糊糊爆破模式客户端更新器.exe
  └── HuhuUpdate/
      ├── huhuwbdUpdater.ini     配置（首次运行自动生成）
      ├── version.json           本地已应用的版本号
      ├── note.json              更新公告
      ├── client_versions.json   各目录已应用版本记录
      └── 更新器日志-<时间戳>     仅出错时生成
```

## 服务器上需要放的文件

放在 `DownloadServer` 指向的地址根目录，例如 `http://110.42.109.54:8080/`：

| 文件 | 作用 |
| --- | --- |
| `version.json` | `{"version": "1.0.0"}`，判断是否有更新 |
| `note.json` | 更新公告，`{"notes": "内容（换行用 \\n）"}` 或纯文本 |
| `alphahu.json` | 更新清单，各目录包地址（程序只临时下载，用完即删） |

`alphahu.json` 格式：

```json
{
  "full_url": "https://直链地址/full.zip",
  "mods":   { "version": "1.0", "url": "https://直链地址/mods.zip" },
  "config": { "version": "1.0", "url": "https://直链地址/config.zip" },
  "tacz":   { "version": "1.0", "url": "https://直链地址/tacz.zip" },
  "resourcepacks": { "version": "1.0", "url": "https://直链地址/resourcepacks.zip" }
}
```

`full_url` 供方式二使用；某个目录不想更新就删掉该项，
只改了某个目录就只改它的 `version`（其它保持不变即不会被重复下载）。

示例文件见 [`服务器文件示例/`](服务器文件示例/)。

## 配置

`HuhuUpdate\huhuwbdUpdater.ini`：

```ini
[Server]
DownloadServer = http://110.42.109.54:8080

[Files]
VersionsFolder = 1.20.1-Forge_47.4.23
BackUpFolder = backups

[Overwrite]
OverwriteFiles = on
CleanUpWhenUpdate = off
```

- `DownloadServer` 只填到端口，程序自动补全 `/version.json`、`/note.json`、`/alphahu.json`。
- `CleanUpWhenUpdate`：`off`（默认）只覆盖 zip 里的文件、保留无关文件；
  `on` 先把整个目录删光再替换。

## 运行

```
糊糊爆破模式客户端更新器.exe            打开图形面板
糊糊爆破模式客户端更新器.exe --auto     静默：检查版本，有更新则逐目录更新（供 PCL 启动前调用）
```

返回码：`0`=成功　`1`=出错　`2`=已最新　`3`=已取消(已还原)

## 从源码打包

```bash
python make_icon.py     # 生成 huhu_icon.ico（需要 Pillow）
python make_exe.py      # 用 PyInstaller 打包，产物在 dist/
```

运行本身只依赖 Python 标准库（`urllib`、`zipfile`、`configparser`、`tkinter`）。
