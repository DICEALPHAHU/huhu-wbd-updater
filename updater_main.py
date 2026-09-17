# -*- coding: utf-8 -*-
"""
糊糊爆破模式客户端 更新器（图形交互面板）
================================================
作者：糊糊     QQ：2387629002

工作方式
--------
1) 版本检查：启动时取服务器上的 version.json（格式 {"version": "版本号"}），
   与本地 HuhuUpdate/version.json 比对：
     · 相同 → 显示“目前已经是最新版本：<版本号>”，更新按钮置灰不可点
     · 不同（或本地没有，例如首次运行）→ 显示有新版本，可点“检查/应用更新”
2) 应用更新：点“检查/应用更新”后
     · 下载 note.json（更新公告）→ 隔离保存到 HuhuUpdate/note.json 并显示在面板
     · 下载 alphahu.json（文件更新清单）→ 只放临时目录，按它更新文件，
       更新完立即删除（防止暴露文件原始地址）
     · 更新成功后把服务器版本号写回本地 version.json

服务器地址
----------
配置 [Server] DownloadServer 只填到端口（如 http://110.42.109.54:8080），
程序自动补全 /version.json、/note.json、/alphahu.json。
界面上“更新检查服务器”可选“默认”（预设）或“自定义”（输入后写回 ini）。

两种更新方式
------------
  方式一（默认）逐目录：mods / config / tacz / resourcepacks 各自独立版本，
    只下版本变化了的目录；没变的不下载、不覆盖、不备份。
  方式二 全量：下载整包覆盖整个客户端根目录（需要清单里带 full_url）。

更新清单 alphahu.json 格式
--------------------------
  {
    "full_url": "https://直链地址/full.zip",        // 方式二 全量包（可省）
    "mods":   { "version": "1.0", "url": "https://直链地址/mods.zip" },
    "config": { "version": "1.0", "url": "https://直链地址/config.zip" },
    "tacz":   { "version": "1.0", "url": "https://直链地址/tacz.zip" },
    "resourcepacks": { "version": "1.0", "url": "https://直链地址/resourcepacks.zip" }
  }
  · full_url 供“方式二 全量更新”下载整包；不填则方式二不可用。
  · 每个目录 version 与本地记录一致 → 该目录跳过。
  · 不想更新某个目录 → 删掉那一项。
  · 兼容旧格式：只有 {version, url} 或一行纯直链时，四目录共享同一个包。

目录布局
--------
  糊糊爆破模式客户端/
    ├── 糊糊爆破模式客户端更新器.exe
    └── HuhuUpdate/
        ├── huhuwbdUpdater.ini     配置（首次运行自动生成）
        ├── version.json           本地已应用的版本号
        ├── note.json              更新公告（隔离保存；缺失时自动下载）
        ├── client_versions.json   各目录已应用版本记录
        └── 更新器日志-<时间戳>     仅当出错时才生成（日常不产生日志）

界面：进度条 / 下载速度 / 剩余时间；支持 暂停·继续（断点续传）与
  取消更新（已改动文件从更新前备份原样还原）。
返回码：0=成功  1=出错  2=已最新  3=已取消(已还原)。

运行参数
--------
  无参数          打开图形面板
  --auto / -auto  静默：检查版本，有更新则逐目录更新（供 PCL 启动前调用）

依赖：仅标准库（urllib、zipfile、configparser、tkinter），无第三方包。
"""
import sys
import os
import json
import shutil
import zipfile
import configparser
import tempfile
import datetime
import time
import threading
from urllib import request as _urlreq

# ---- 常量 ----
PROG_NAME = "糊糊爆破模式客户端更新器"
AUTHOR = "糊糊"
AUTHOR_QQ = "2387629002"
DEFAULT_SERVER = "http://110.42.109.54:8080"   # 预设更新检查服务器（默认）
UPDATER_DIR = "HuhuUpdate"             # 配置/日志所在子文件夹
CONFIG_NAME = "huhuwbdUpdater.ini"     # 配置文件
VERSION_FILE = "version.json"          # 本地记录：已应用的服务器版本号
NOTE_FILE = "note.json"                # 本地保存的更新公告（从服务器下载/隔离）
LOCAL_VER_FILE = "client_versions.json"    # 各目录已应用版本记录
LEGACY_VER_FILE = "client_version.txt"     # 旧整包版本文件（兼容读取）
POINTER_SAVE_NAME = "alphahu.json"         # 更新清单文件名（仅临时存放，用完即删）
LOG_PREFIX = "更新器日志-"                 # 出错才生成：更新器日志-<年月日时分秒>
FOUR_KEYS = ("mods", "config", "tacz", "resourcepacks")

_LOG_PATH = None        # 出错落盘后的日志路径（日常为 None，不产生日志文件）
_LOG_BUFFER = []        # 内存中累积的运行记录，出错时一次性写入日志文件
_DATA_DIR = None        # HuhuUpdate 目录（供出错时生成日志用）


# ---- 首次运行自动生成的默认文件内容 ----
DEFAULT_CONFIG_TEXT = r"""; ============================================================
;  糊糊爆破模式客户端 更新器 配置文件
;  本文件由程序首次运行时自动生成（也可手动放置）。
;  你不应该动这个文件夹（HuhuUpdate），除非你知道自己在干什么。
;  注意：保存时保持 UTF-8 编码（记事本默认即可）。
; ============================================================

[Server]
; 更新检查服务器地址（只填到域名/端口，不要带文件名）。
; 程序会自动去取下列三个文件：
;   {DownloadServer}/version.json   ← 版本号（用来判断是否有更新）
;   {DownloadServer}/note.json      ← 更新公告（显示在面板上）
;   {DownloadServer}/alphahu.json   ← 文件更新清单（临时下载，更新完即删）
DownloadServer = http://110.42.109.54:8080

[Files]
; 要更新的版本文件夹名。留空或填 auto = 自动取 .minecraft\versions 下唯一的一个文件夹
VersionsFolder = 1.20.1-Forge_47.4.23

; 备份目录（相对客户端根目录）。每次更新前会删除上一次备份再备份当前内容。
BackUpFolder = backups

[Overwrite]
; on = 更新前自动备份；off = 直接覆盖不备份
OverwriteFiles = on

; 清理多余文件：on = 更新该目录时先整个删光再替换（干净替换，连同非服务器里的文件）；
;                off = 只把服务器 zip 里的文件解压覆盖进去，不删目录里其他无关文件（默认，保守）
CleanUpWhenUpdate = off
"""


# ------------------------------------------------------------------------- #
# 日志 / 弹窗
# ------------------------------------------------------------------------- #
def _log(msg):
    """记录一条运行日志。日常只存在内存里，不产生文件；
    只有出错时由 enable_log_file() 一次性落盘成
    “更新器日志-年月日时分秒”。"""
    line = "[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    _LOG_BUFFER.append(line)
    if _LOG_PATH:
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def enable_log_file(data_dir=None):
    """出错时才把内存里的日志写入文件，文件名：更新器日志-YYYYMMDDHHMMSS。
    返回日志文件路径（已存在则直接返回）。"""
    global _LOG_PATH
    if _LOG_PATH:
        return _LOG_PATH
    d = data_dir or _DATA_DIR
    if not d:
        return None
    name = LOG_PREFIX + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    p = os.path.join(d, name)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(_LOG_BUFFER))
            f.write("\n")
        _LOG_PATH = p
        return p
    except Exception:
        return None


def _info_box(msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, PROG_NAME, 0x40)
    except Exception:
        print(msg)


def _fail_box(msg):
    """出错提示：同时生成日志文件，并在提示里告诉用户文件名。"""
    _log("错误：%s" % msg)
    lp = enable_log_file()
    text = msg
    if lp:
        text += "\n\n详细日志已保存为：\n%s" % os.path.basename(lp)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, PROG_NAME, 0x10)
    except Exception:
        print(text)


def fmt_time(sec):
    """把秒格式化成人可读的剩余时间（mm:ss 或 h:mm:ss）。"""
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


# ------------------------------------------------------------------------- #
# 目录与自动补全
# ------------------------------------------------------------------------- #
def app_dir_of(root):
    """返回 exe 所在(客户端根)目录下的 HuhuUpdate 子文件夹，不存在则创建。"""
    d = os.path.join(root, UPDATER_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def ensure_defaults(data_dir):
    """缺什么就生成什么：HuhuUpdate 不存在→建；配置文件缺失→写入默认模板。

    这样更新器不硬依赖预先放好的 ini：首次运行自动把 HuhuUpdate 建好并生成默认配置，
    之后每次启动“有就读取、没有就生成”。"""
    os.makedirs(data_dir, exist_ok=True)
    cfg_path = os.path.join(data_dir, CONFIG_NAME)
    if not os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_CONFIG_TEXT)
        except Exception:
            pass
    # 注意：alphahu.json（更新清单）不落地到 HuhuUpdate，只在临时目录用完即删，
    #       避免暴露其中记录的文件原始地址。


# ------------------------------------------------------------------------- #
# 配置读取
# ------------------------------------------------------------------------- #
def load_config(cfg_path):
    conf = configparser.ConfigParser()
    conf.optionxform = str
    conf.read(cfg_path, encoding="utf-8-sig")

    def get(section, key, default):
        try:
            v = conf.get(section, key).strip()
            return v if v else default
        except Exception:
            return default

    server = get("Server", "DownloadServer", "").strip()
    if not server:
        # 兼容旧配置：以前填的是完整指示文件地址（如 .../alphahu.json）
        legacy = get("Server", "DownloadURL", "").strip()
        if legacy:
            server = legacy
            if server.rstrip("/").lower().endswith(".json"):
                server = server.rstrip("/").rsplit("/", 1)[0]
    server = norm_server(server) or DEFAULT_SERVER

    return {
        "server": server,
        "version_folder": get("Files", "VersionsFolder", ""),
        "backup_dir": get("Files", "BackUpFolder", "backups"),
        "use_backup": get("Overwrite", "OverwriteFiles", "on").lower()
                      in ("on", "true", "1", "yes"),
        "clean_extra": get("Overwrite", "CleanUpWhenUpdate", "off").lower()
                       in ("on", "true", "1", "yes"),
    }


# ------------------------------------------------------------------------- #
# 本地版本记录读写（放 HuhuUpdate）
# ------------------------------------------------------------------------- #
def load_local_versions(data_dir):
    d = {}
    p = os.path.join(data_dir, LOCAL_VER_FILE)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                j = json.load(f)
            d = j if isinstance(j, dict) else {}
        except Exception:
            d = {}
    else:
        lp = os.path.join(data_dir, LEGACY_VER_FILE)
        if os.path.isfile(lp):
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    d["_overall"] = f.read().strip()
            except Exception:
                pass
    return d


def save_local_versions(data_dir, d):
    try:
        with open(os.path.join(data_dir, LOCAL_VER_FILE), "w",
                  encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------------------- #
# 服务器地址 / 版本号 / 更新公告
# ------------------------------------------------------------------------- #
def norm_server(s):
    """规范化服务器地址：去空白与结尾斜杠，缺协议则补 http://。"""
    s = (s or "").strip().strip('"').strip("'").rstrip("/")
    if not s:
        return ""
    if not s.lower().startswith(("http://", "https://")):
        s = "http://" + s
    return s


def srv_url_version(server):
    return norm_server(server) + "/version.json"


def srv_url_note(server):
    return norm_server(server) + "/note.json"


def srv_url_alpha(server):
    return norm_server(server) + "/alphahu.json"


def read_local_version(data_dir):
    """读取本地 HuhuUpdate/version.json 里的版本号；没有则返回空串。"""
    p = os.path.join(data_dir, VERSION_FILE)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            txt = f.read()
    except Exception:
        return ""
    try:
        j = json.loads(txt)
        if isinstance(j, dict):
            return str(j.get("version") or "").strip()
        return str(j).strip()
    except Exception:
        return txt.strip()


def write_local_version(data_dir, ver):
    """把已应用的版本号写入本地 HuhuUpdate/version.json。"""
    ver = str(ver or "").strip()
    if not ver:
        return
    try:
        with open(os.path.join(data_dir, VERSION_FILE), "w",
                  encoding="utf-8") as f:
            json.dump({"version": ver}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_remote_version(server, timeout=20):
    """取服务器 version.json 里的版本号。"""
    txt = http_text(srv_url_version(server), timeout=timeout)
    try:
        j = json.loads(txt)
        if isinstance(j, dict):
            return str(j.get("version") or "").strip()
        return str(j).strip()
    except Exception:
        return txt.strip()


def parse_note(text):
    """更新公告兼容解析：{'notes'|'note'|'content'|'text'} 或纯文本。"""
    text = text or ""
    try:
        j = json.loads(text)
    except Exception:
        return text.strip()
    if isinstance(j, dict):
        for k in ("notes", "note", "content", "text", "公告", "更新公告"):
            if k in j:
                return str(j[k])
        return ""
    return str(j)


def ensure_note(server, data_dir, force=False, timeout=20):
    """更新公告隔离保存在 HuhuUpdate/note.json。
    本地没有 note.json（或 force=True）时主动从服务器下载；失败则退回本地已有内容。"""
    p = os.path.join(data_dir, NOTE_FILE)
    if os.path.isfile(p) and not force:
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                return parse_note(f.read())
        except Exception:
            return ""
    try:
        txt = http_text(srv_url_note(server), timeout=timeout)
        with open(p, "w", encoding="utf-8") as f:
            f.write(txt)
        return parse_note(txt)
    except Exception:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    return parse_note(f.read())
            except Exception:
                pass
        return ""


def update_ini_server(cfg_path, server):
    """把 DownloadServer 写回 ini（保留原有注释与其它配置，尽量只改那一行）。"""
    line_new = "DownloadServer = %s" % norm_server(server)
    try:
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except Exception:
        lines = []
    out, in_server, replaced = [], False, False
    for ln in lines:
        st = ln.strip()
        if st.startswith("[") and st.endswith("]"):
            if in_server and not replaced:
                out.append(line_new)
                replaced = True
            in_server = (st[1:-1].strip().lower() == "server")
            out.append(ln)
            continue
        if in_server and not replaced:
            low = st.lower()
            if low.startswith("downloadserver") or low.startswith("downloadurl"):
                out.append(line_new)
                replaced = True
                continue
        out.append(ln)
    if in_server and not replaced:
        out.append(line_new)
        replaced = True
    if not replaced:
        out.append("")
        out.append("[Server]")
        out.append(line_new)
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return True
    except Exception:
        return False


# ------------------------------------------------------------------------- #
# 网络
# ------------------------------------------------------------------------- #
# 模拟浏览器的请求头：很多 OneDrive/网盘直链服务会 403 拒绝 Python 默认 UA
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0 Safari/537.36")


def _open_with_headers(url, timeout):
    from urllib.parse import urlparse
    p = urlparse(url)
    referer = ("%s://%s/" % (p.scheme, p.netloc)) if p.scheme and p.netloc else ""
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    req = _urlreq.Request(url, headers=headers)
    return _urlreq.urlopen(req, timeout=timeout)


def http_text(url, timeout=20):
    with _open_with_headers(url, timeout) as r:
        data = r.read()
    return data.decode("utf-8-sig", errors="replace")


# ---- 下载控制：暂停/继续（断点续传）、取消 ----
class DLControl:
    """跨线程下载控制。GUI 线程设置，下载线程读取。"""
    def __init__(self):
        self.cancel = False
        self._pause_flag = threading.Event()

    def request_cancel(self):
        self.cancel = True

    def request_pause(self):
        self._pause_flag.set()

    def pause_flag(self):
        return self._pause_flag.is_set()

    def resume(self):
        self._pause_flag.clear()

    def wait_resume(self):
        """阻塞直到“继续”或“取消”。返回 True=继续，False=已取消。"""
        while self._pause_flag.is_set() and not self.cancel:
            time.sleep(0.1)
        return not self.cancel


class _Cancelled(Exception):
    """更新被用户取消。"""


class _Paused(Exception):
    """下载被用户暂停（已保留残片，可断点续传）。"""


def _base_req_headers(url, extra=None):
    from urllib.parse import urlparse
    p = urlparse(url)
    referer = ("%s://%s/" % (p.scheme, p.netloc)) if p.scheme and p.netloc else ""
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    if extra:
        headers.update(extra)
    return headers


def _parse_total_from(r, status):
    if status == 206:
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:  # 形如 bytes 0-524287/5242880
            try:
                return int(cr.rsplit("/", 1)[1])
            except Exception:
                pass
        return 0
    try:
        return int(r.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def download_file(url, dest, timeout=300, progress=None, ctrl=None):
    """下载到 dest。支持：
      - progress(done, total, speed, eta) 实时回报进度/速度/剩余。
      - ctrl 为 DLControl 时支持 暂停/继续（断点续传，HTTP Range）与 取消。
        暂停抛 _Paused（保留残片）后内部等待继续并从断点续传；
        取消抛 _Cancelled 给外层（由 do_update 负责还原已改动文件）。
      - 无 ctrl 时等同普通下载（从头，不可中断）。
    """
    if ctrl is not None and os.path.isfile(dest):
        start = os.path.getsize(dest)      # 已有残片 → 断点续传
    elif os.path.isfile(dest):
        os.remove(dest)                    # 全新下载，清旧残片
        start = 0
    else:
        start = 0

    def _stream():
        """发起一次 HTTP 请求并写一段。分块边界检查暂停/取消。"""
        nonlocal start
        if os.path.isfile(dest):
            start = os.path.getsize(dest)
        had_range = start > 0
        extra = {"Range": "bytes=%d-" % start} if had_range else {}
        r = _urlreq.urlopen(
            _urlreq.Request(url, headers=_base_req_headers(url, extra)),
            timeout=timeout)
        try:
            status = r.status
            if had_range and status == 416:
                return True   # 残片已等于完整文件
            if had_range and status != 206:
                # 服务器不支持 Range → 从头重下
                if os.path.isfile(dest):
                    os.remove(dest)
                start = 0
                r.close()
                r = _urlreq.urlopen(
                    _urlreq.Request(url, headers=_base_req_headers(url)),
                    timeout=timeout)
                status = r.status
            had_range = (status == 206)
            total = _parse_total_from(r, status)
            done = start
            t0 = time.time()
            last_send = 0.0
            with open(dest, "ab" if had_range else "wb") as f:
                while True:
                    if ctrl is not None:
                        if ctrl.cancel:
                            raise _Cancelled()
                        if ctrl.pause_flag():
                            raise _Paused()
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress and time.time() - last_send >= 0.3:
                        elapsed = time.time() - t0
                        speed = (done / elapsed) if elapsed > 0 else 0
                        eta = (total - done) / speed if (speed > 0 and total > 0) else None
                        progress(done, total, speed, eta)
                        last_send = time.time()
            if progress:
                elapsed = time.time() - t0
                speed = (done / elapsed) if elapsed > 0 else 0
                eta = (total - done) / speed if (speed > 0 and total > 0) else None
                progress(done, total, speed, eta)
            return False
        finally:
            try:
                r.close()
            except Exception:
                pass

    while True:
        try:
            done_flag = _stream()
            if done_flag:
                break
            break   # 完整下载（或从头完成）结束
        except _Paused:
            if ctrl is None:
                break
            if not ctrl.wait_resume():
                raise _Cancelled()
            continue
    return dest


# ------------------------------------------------------------------------- #
# 拉取指示文件（并把内容保存到 HuhuUpdate/alphahu.json，同名覆盖）
# ------------------------------------------------------------------------- #
def parse_info(text):
    """把 alphahu.json（更新清单）文本解析成统一结构。"""
    text = text or ""
    result = {
        "overall": "", "notes": "", "full_url": "",
        "folders": {k: {"version": "", "url": ""} for k in FOUR_KEYS},
    }
    parsed = False
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            parsed = True
    except Exception:
        parsed = False

    if not parsed:  # 纯直链一行 → 四目录共享同一个包（回退整包行为）
        url = text.strip()
        for k in FOUR_KEYS:
            result["folders"][k] = {"version": "", "url": url}
        return result

    result["overall"] = str(data.get("overall_version")
                            or data.get("version") or "").strip()
    result["notes"] = str(data.get("notes") or "").strip()
    result["full_url"] = str(data.get("full_url") or "").strip()

    any_folder = False
    for k in FOUR_KEYS:
        e = data.get(k)
        if isinstance(e, dict):
            any_folder = True
            result["folders"][k] = {
                "version": str(e.get("version") or "").strip(),
                "url": str(e.get("url") or "").strip(),
            }
    if not any_folder and data.get("url"):
        shared_url = str(data.get("url") or "").strip()
        shared_ver = str(data.get("version") or "").strip()
        for k in FOUR_KEYS:
            result["folders"][k] = {"version": shared_ver, "url": shared_url}
    return result


def fetch_info(pointer_url, save_path=None):
    """下载更新清单并解析。save_path 给定时会把原文写过去（临时目录用）。"""
    text = http_text(pointer_url, timeout=20)
    if save_path:
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
    return parse_info(text)


# ------------------------------------------------------------------------- #
# 解压单个目录包到目标目录
# ------------------------------------------------------------------------- #
def apply_zip_to_folder(pkg, target_dir, key):
    with zipfile.ZipFile(pkg) as z:
        names = z.namelist()
        tops = {n.split("/", 1)[0] for n in names if n.split("/", 1)[0]}
        prefix = (key + "/") if key in tops else ""
        for n in names:
            if n.endswith("/"):
                continue
            if prefix and not n.startswith(prefix):
                continue
            rel = n[len(prefix):] if prefix else n
            if not rel:
                continue
            if ".." in rel.split("/"):
                _log("跳过可疑路径：%s" % rel)
                continue
            dest = os.path.join(target_dir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)


# ------------------------------------------------------------------------- #
# 方式二 全量覆盖根目录
# ------------------------------------------------------------------------- #
def apply_full(pkg, root, self_exe, ctrl=None):
    with zipfile.ZipFile(pkg) as z:
        for n in z.namelist():
            if ctrl is not None and ctrl.cancel:
                raise _Cancelled()
            if n.endswith("/"):
                continue
            if ".." in n.split("/"):
                _log("跳过可疑路径：%s" % n)
                continue
            dest = os.path.join(root, n.replace("/", os.sep))
            if os.path.abspath(dest) == os.path.abspath(self_exe):
                _log("跳过正在运行的更新器自身。")
                continue
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            except PermissionError as e:
                _log("整包覆盖跳过被占用文件：%s (%s)" % (dest, e))
            except Exception as e:
                _log("整包覆盖文件失败：%s (%s)" % (dest, e))


# ------------------------------------------------------------------------- #
# 备份
# ------------------------------------------------------------------------- #
def clear_backup(root, cfg):
    backup_base = os.path.join(root, cfg["backup_dir"])
    if os.path.isdir(backup_base):
        shutil.rmtree(backup_base, ignore_errors=True)
    os.makedirs(backup_base, exist_ok=True)
    return backup_base


def backup_folders(root, cfg, target_root, keys):
    clear_backup(root, cfg)
    for k in keys:
        src = os.path.join(target_root, k)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(root, cfg["backup_dir"], k))


def backup_full(root, cfg, self_exe):
    clear_backup(root, cfg)
    backup_base = os.path.join(root, cfg["backup_dir"])
    for entry in os.listdir(root):
        s = os.path.join(root, entry)
        if os.path.abspath(backup_base) == os.path.abspath(s):
            continue
        if os.path.abspath(self_exe) == os.path.abspath(s):
            continue
        try:
            if os.path.isdir(s) and not os.path.islink(s):
                shutil.copytree(s, os.path.join(backup_base, entry))
            elif os.path.isfile(s):
                shutil.copy2(s, os.path.join(backup_base, entry))
        except Exception as e:
            _log("备份跳过：%s (%s)" % (s, e))


def restore_backup_folders(root, cfg, target_root, keys):
    """取消更新时，把已改动的目录从备份里原样还原回去。"""
    backup_base = os.path.join(root, cfg["backup_dir"])
    for k in keys:
        src = os.path.join(backup_base, k)
        dst = os.path.join(target_root, k)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            try:
                shutil.copytree(src, dst)
            except Exception as e:
                _log("还原 %s 失败：%s" % (k, e))


def restore_backup_full(root, cfg):
    """取消全量更新时，把整个客户端从备份里还原回去。"""
    backup_base = os.path.join(root, cfg["backup_dir"])
    if not os.path.isdir(backup_base):
        return
    for entry in os.listdir(backup_base):
        s = os.path.join(backup_base, entry)
        d = os.path.join(root, entry)
        try:
            if os.path.isdir(s) and not os.path.islink(s):
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(s, d)
            elif os.path.isfile(s):
                shutil.copy2(s, d)
        except Exception as e:
            _log("整包还原 %s 失败：%s" % (entry, e))


# ------------------------------------------------------------------------- #
# 定位版本目录
# ------------------------------------------------------------------------- #
def resolve_target_root(root, cfg):
    versions_root = os.path.join(root, ".minecraft", "versions")
    if cfg["version_folder"] and cfg["version_folder"] != "auto":
        cand = os.path.join(versions_root, cfg["version_folder"])
        return cand if os.path.isdir(cand) else None
    if os.path.isdir(versions_root):
        subs = [d for d in os.listdir(versions_root)
                if os.path.isdir(os.path.join(versions_root, d))]
        if len(subs) == 1:
            return os.path.join(versions_root, subs[0])
    return None


# ------------------------------------------------------------------------- #
# 执行更新
#   mode: 'four' 逐目录增量 / 'full' 全量
#   返回: 0 成功 / 1 出错 / 2 已是最新(或无可更新)
# ------------------------------------------------------------------------- #
def do_update(mode, root_dir, data_dir, cfg, info, self_exe, log_path,
              progress=None, dl_progress=None, ctrl=None):
    """progress: 状态文本回调；dl_progress: 下载进度回调(done,total,speed,eta)；
       ctrl: DLControl，支持 暂停/继续/取消；取消时从备份还原已改动内容。
       返回: 0 成功 / 1 出错 / 2 已最新 / 3 已取消(已还原)。"""
    def say(msg):
        if progress:
            progress(msg)
        _log(msg)

    localv = load_local_versions(data_dir)

    if mode == "four":
        target_root = resolve_target_root(root_dir, cfg)
        if not target_root:
            say("错误：无法定位版本目录。")
            return 1
        changed = []
        status_list = []
        for k in FOUR_KEYS:
            e = info["folders"].get(k) or {}
            url = e.get("url", "").strip()
            ver = e.get("version", "").strip()
            if not url:
                status_list.append("%s(无包)" % k)
                continue
            if ver and ver == str(localv.get(k, "")):
                status_list.append("%s(已最新)" % k)
                continue
            changed.append(k)
            status_list.append("%s(待更新)" % k)
        say("目录状态：%s" % "  ".join(status_list))
        if not changed:
            say("无需更新。")
            return 2

        # 更新前先备份将被改动的目录（取消可原样还原；不依赖“自动备份”开关）
        say("正在备份（%s）……" % ", ".join(changed))
        backup_folders(root_dir, cfg, target_root, changed)
        say("备份完成。")

        applied = []
        try:
            # 阶段一：全部下载到临时目录（可暂停/续传/取消；此阶段不改动游戏目录）
            with tempfile.TemporaryDirectory() as tmp:
                pkgs = {}
                for k in changed:
                    url = info["folders"][k].get("url", "")
                    say("下载 %s <- %s" % (k, url))
                    pkg = os.path.join(tmp, k + ".zip")
                    download_file(url, pkg, timeout=300, progress=dl_progress,
                                  ctrl=ctrl)
                    pkgs[k] = pkg
                # 阶段二：逐个应用（此阶段才真正改动游戏目录）
                for k in changed:
                    if ctrl is not None and ctrl.cancel:
                        raise _Cancelled()
                    pkg = pkgs[k]
                    target_dir = os.path.join(target_root, k)
                    if cfg["clean_extra"]:
                        # 清理多余文件=on：整个目录删光再替换（连同无关文件）
                        if os.path.isdir(target_dir):
                            shutil.rmtree(target_dir, ignore_errors=True)
                        os.makedirs(target_dir, exist_ok=True)
                    else:
                        # 默认：保留无关文件，只解压覆盖 zip 里的文件
                        os.makedirs(target_dir, exist_ok=True)
                    apply_zip_to_folder(pkg, target_dir, k)
                    applied.append(k)
                    ver = info["folders"][k].get("version", "")
                    if ver:
                        localv[k] = ver
                    say("已更新 %s。" % k)
        except _Cancelled:
            if applied:
                say("检测到取消，正在把已改动的目录还原回原样……")
                restore_backup_folders(root_dir, cfg, target_root, applied)
                say("已还原（%s）。" % ", ".join(applied))
            else:
                say("在改动目录前已取消，游戏文件未被动过。")
            return 3
        except Exception as ex:
            say("更新失败：%s" % ex)
            return 1
        if info["overall"]:
            localv["_overall"] = info["overall"]
        save_local_versions(data_dir, localv)
        return 0

    # ---- mode == full ----
    if not info["full_url"]:
        say("错误：更新清单 alphahu.json 里没有全量包地址 full_url，无法用方式二。"
            "请改用方式一，或在服务器清单里补上 full_url。")
        return 1
    if info["overall"] and info["overall"] == str(localv.get("_overall", "")):
        say("已是最新（%s），无需更新。" % info["overall"])
        return 2
    # 更新前备份整个客户端（取消时可原样还原，不依赖“自动备份”开关）
    say("正在备份整个客户端……")
    backup_full(root_dir, cfg, self_exe)
    say("备份完成。")
    say("正在下载全量更新包……")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "full.zip")
            download_file(info["full_url"], pkg, timeout=300,
                          progress=dl_progress, ctrl=ctrl)
            say("下载完成，正在整套覆盖……")
            apply_full(pkg, root_dir, self_exe, ctrl=ctrl)
    except _Cancelled:
        say("检测到取消，正在把整个客户端还原回原样……")
        restore_backup_full(root_dir, cfg)
        say("已还原整个客户端。")
        return 3
    except Exception as ex:
        say("全量更新失败：%s" % ex)
        return 1
    if info["overall"]:
        localv["_overall"] = info["overall"]
    save_local_versions(data_dir, localv)
    say("全量更新完成。")
    return 0


# ========================================================================= #
# 图形交互面板（tkinter）
# ========================================================================= #
def run_gui(root_dir, data_dir, cfg, self_exe, log_path):
    global _LOG_PATH, _DATA_DIR
    _LOG_PATH = log_path            # 日常为 None：出错时才生成日志文件
    _DATA_DIR = data_dir            # 供 _fail_box 出错时落盘用

    import tkinter as tk
    from tkinter import messagebox, simpledialog
    from tkinter import ttk

    cfg_path = os.path.join(data_dir, CONFIG_NAME)
    state = {
        "server": norm_server(cfg.get("server")) or DEFAULT_SERVER,
        "server_ver": "",
        "local_ver": read_local_version(data_dir),
        "has_update": True,
        "info": None,
    }

    win = tk.Tk()
    win.title(PROG_NAME)
    win.geometry("760x680")
    win.minsize(680, 560)

    # ---------------- 顶部：更新检查服务器 ----------------
    srow = tk.Frame(win, padx=14, pady=10)
    srow.pack(fill="x")
    tk.Label(srow, text="更新检查服务器：", font=("", 10, "bold")).pack(side="left")
    server_var = tk.StringVar()
    server_box = ttk.Combobox(srow, textvariable=server_var, width=7,
                              state="readonly", values=("默认", "自定义"))
    server_box.pack(side="left")
    cur_server_var = tk.StringVar()
    tk.Label(srow, textvariable=cur_server_var, fg="#555").pack(side="left",
                                                               padx=(8, 0))
    about_btn = tk.Button(srow, text="关于", width=6)
    about_btn.pack(side="right")

    # ---------------- 版本状态 ----------------
    ver_var = tk.StringVar(value="正在检查更新……")
    ver_label = tk.Label(win, textvariable=ver_var, anchor="w",
                         font=("", 11, "bold"), fg="#555")
    ver_label.pack(fill="x", padx=14, pady=(0, 4))

    # ---------------- 更新方式 ----------------
    top = tk.Frame(win, padx=14)
    top.pack(fill="x")
    tk.Label(top, text="选择更新方式：", anchor="w",
             font=("", 10, "bold")).pack(anchor="w")
    mode_var = tk.StringVar(value="four")
    tk.Radiobutton(top, text="方式一 · 逐目录更新（默认）—— mods/config/tacz/resourcepacks 各自检测、只下变了的",
                   variable=mode_var, value="four", anchor="w").pack(anchor="w", pady=1)
    tk.Radiobutton(top, text="方式二 · 全量更新 —— 下载整包，覆盖整个客户端根目录",
                   variable=mode_var, value="full", anchor="w").pack(anchor="w", pady=1)

    dir_status_var = tk.StringVar(value="各目录状态：点“检查/应用更新”后显示")
    tk.Label(win, textvariable=dir_status_var, anchor="w",
             fg="#155724").pack(fill="x", padx=14, pady=(6, 0))

    # ---------------- 更新公告 ----------------
    tk.Label(win, text="更新公告：", anchor="w",
             font=("", 11, "bold")).pack(fill="x", padx=14, pady=(6, 0))
    notes_frame = tk.Frame(win)
    notes_frame.pack(fill="both", expand=True, padx=14, pady=4)
    notes_text = tk.Text(notes_frame, wrap="word", height=11, bg="#f6f6f6")
    notes_text.pack(side="left", fill="both", expand=True)
    sbar = tk.Scrollbar(notes_frame, command=notes_text.yview)
    sbar.pack(side="right", fill="y")
    notes_text.configure(yscrollcommand=sbar.set)

    def set_notes(txt):
        notes_text.config(state="normal")
        notes_text.delete("1.0", "end")
        notes_text.insert("1.0", txt if txt else "（暂无更新公告）")
        notes_text.config(state="disabled")

    set_notes("（正在获取更新公告……）")

    # ---------------- 进度条 + 速度 + 剩余时间 ----------------
    progress_bar = ttk.Progressbar(win, orient="horizontal", mode="determinate",
                                   maximum=100, value=0)
    progress_bar.pack(fill="x", padx=14, pady=(2, 0))
    dl_frame = tk.Frame(win, padx=14)
    dl_frame.pack(fill="x")
    pct_var = tk.StringVar(value="0%")
    speed_var = tk.StringVar(value="速度 --")
    eta_var = tk.StringVar(value="剩余 --")
    tk.Label(dl_frame, textvariable=pct_var, anchor="w").pack(side="left")
    tk.Label(dl_frame, textvariable=speed_var, anchor="center").pack(
        side="left", expand=True)
    tk.Label(dl_frame, textvariable=eta_var, anchor="e").pack(side="right")

    dl_state = {"done": 0, "total": 0, "speed": 0.0, "eta": None}

    def dl_cb(done, total, speed, eta):
        dl_state.update(done=done, total=total, speed=speed, eta=eta)

    def poll_progress():
        ds = dl_state
        total = ds["total"]
        if total > 0:
            pct = min(100.0, ds["done"] * 100.0 / total)
            progress_bar["value"] = pct
            pct_var.set("%.1f%%" % pct)
        elif ds["done"] > 0:
            progress_bar["value"] = 0
            pct_var.set("下载中…")
        else:
            progress_bar["value"] = 0
            pct_var.set("0%")
        speed_var.set("%.2f MB/s" % (ds["speed"] / 1048576.0)
                      if ds["speed"] > 0 else "速度 --")
        eta_var.set("剩余 %s" % fmt_time(ds["eta"])
                    if ds["eta"] is not None else "剩余 --")
        win.after(300, poll_progress)

    # ---------------- 底部状态与按钮 ----------------
    bottom = tk.Frame(win, padx=14, pady=10)
    bottom.pack(fill="x")
    status_var = tk.StringVar(value="准备就绪。")
    tk.Label(bottom, textvariable=status_var, anchor="w", fg="#333").pack(
        fill="x", pady=(0, 6))

    ctrl = DLControl()

    def refresh_server_label():
        cur_server_var.set("当前：" + state["server"])

    def apply_server(new_server, save=True):
        s = norm_server(new_server)
        if not s:
            return False
        state["server"] = s
        cfg["server"] = s
        if save:
            update_ini_server(cfg_path, s)
        refresh_server_label()
        return True

    # ---- 版本检查（后台线程）----
    def check_worker():
        try:
            sv = fetch_remote_version(state["server"])
        except Exception as e:
            win.after(0, lambda: check_done(None, str(e), None))
            return
        try:
            note = ensure_note(state["server"], data_dir, force=True)
        except Exception:
            note = None
        win.after(0, lambda: check_done(sv, None, note))

    def start_check():
        ver_var.set("正在检查更新……")
        ver_label.config(fg="#555")
        btn.config(state="disabled")
        threading.Thread(target=check_worker, daemon=True).start()

    def check_done(server_ver, err, note):
        if err:
            lp = enable_log_file(data_dir)
            ver_var.set("检查更新失败：%s" % err)
            ver_label.config(fg="#a00")
            btn.config(state="normal")
            status_var.set("无法连接更新检查服务器，可点“重新检查”或更换服务器。"
                           + ("（日志：%s）" % os.path.basename(lp) if lp else ""))
            return
        if note is not None:
            set_notes(note)
        state["server_ver"] = server_ver or ""
        state["local_ver"] = read_local_version(data_dir)
        if state["server_ver"] and state["server_ver"] == state["local_ver"]:
            state["has_update"] = False
            ver_var.set("目前已经是最新版本：%s" % state["server_ver"])
            ver_label.config(fg="#155724")
            btn.config(state="disabled")
            status_var.set("已是最新版本，无需更新。")
        else:
            state["has_update"] = True
            if state["local_ver"]:
                ver_var.set("发现新版本：%s（当前 %s）"
                            % (state["server_ver"] or "未知", state["local_ver"]))
            else:
                ver_var.set("发现新版本：%s" % (state["server_ver"] or "未知"))
            ver_label.config(fg="#b60")
            btn.config(state="normal")
            status_var.set("点“检查/应用更新”开始更新。")

    # ---- 更新（后台线程）----
    def show_dirs(info):
        state["info"] = info
        localv = load_local_versions(data_dir)
        segs = []
        for k in FOUR_KEYS:
            e = info["folders"].get(k) or {}
            url, ver = e.get("url", ""), e.get("version", "")
            if not url:
                segs.append("%s 无包" % k)
            elif ver and ver == str(localv.get(k, "")):
                segs.append("%s 已最新" % k)
            else:
                segs.append("%s 待更新" % k)
        dir_status_var.set("各目录状态：" + "   ".join(segs))

    def worker(mode):
        tmpdir = tempfile.mkdtemp(prefix="huhu_")
        try:
            alpha_path = os.path.join(tmpdir, POINTER_SAVE_NAME)
            info = fetch_info(srv_url_alpha(state["server"]), save_path=alpha_path)
            win.after(0, lambda: show_dirs(info))
            result = do_update(mode, root_dir, data_dir, cfg, info, self_exe,
                               log_path, dl_progress=dl_cb, ctrl=ctrl)
        except _Cancelled:
            result = 3
        except Exception as e:
            _log("更新异常：%s" % e)
            result = 1
        finally:
            # 更新清单只临时存放，用完立即删除（避免暴露文件原始地址）
            shutil.rmtree(tmpdir, ignore_errors=True)
        win.after(0, lambda: finish(result))

    def on_start():
        mode = mode_var.get()
        ctrl.cancel = False
        ctrl.resume()
        btn.config(state="disabled")
        check_btn.config(state="disabled")
        pause_btn.config(state="normal", text="暂停")
        cancel_btn.config(state="normal")
        progress_bar["value"] = 0
        pct_var.set("0%")
        speed_var.set("速度 --")
        eta_var.set("剩余 --")
        status_var.set("开始%s更新……" % ("逐目录" if mode == "four" else "全量"))
        win.after(0, poll_progress)
        threading.Thread(target=worker, args=(mode,), daemon=True).start()

    def on_pause_toggle():
        if ctrl.pause_flag():
            ctrl.resume()
            pause_btn.config(text="暂停")
            status_var.set("已继续，从断点续传……")
        else:
            ctrl.request_pause()
            pause_btn.config(text="继续")
            status_var.set("已暂停：点【继续】后从断点续传。")

    def on_cancel():
        if messagebox.askyesno(
                PROG_NAME,
                "确定取消本次更新吗？\n已改动的文件会原样还原回更新前的状态。"):
            ctrl.request_cancel()
            cancel_btn.config(state="disabled")
            pause_btn.config(state="disabled")
            status_var.set("正在取消并还原……")

    def finish(result):
        pause_btn.config(state="disabled", text="暂停")
        cancel_btn.config(state="disabled")
        check_btn.config(state="normal")
        if result == 0:
            if dl_state["total"] > 0:
                progress_bar["value"] = 100
                pct_var.set("100%")
            if state["server_ver"]:
                write_local_version(data_dir, state["server_ver"])
            state["local_ver"] = read_local_version(data_dir)
            state["has_update"] = False
            btn.config(state="disabled")
            ver_var.set("目前已经是最新版本：%s" % (state["local_ver"] or ""))
            ver_label.config(fg="#155724")
            status_var.set("更新完成。")
            messagebox.showinfo(PROG_NAME, "更新完成！")
        elif result == 2:
            if state["server_ver"]:
                write_local_version(data_dir, state["server_ver"])
            state["local_ver"] = read_local_version(data_dir)
            state["has_update"] = False
            btn.config(state="disabled")
            ver_var.set("目前已经是最新版本：%s" % (state["local_ver"] or ""))
            ver_label.config(fg="#155724")
            status_var.set("没有需要更新的内容。")
            messagebox.showinfo(PROG_NAME, "没有需要更新的内容。")
        elif result == 3:
            status_var.set("已取消更新，文件已还原回原样。")
            btn.config(state="normal")
            messagebox.showinfo(PROG_NAME, "已取消更新，已改动的文件已还原回原样。")
        else:
            lp = enable_log_file(data_dir)
            name = os.path.basename(lp) if lp else "（未能写入日志）"
            status_var.set("更新出错，日志：%s" % name)
            btn.config(state="normal")
            messagebox.showerror(PROG_NAME, "更新出错。\n\n详细日志：%s" % name)

    # ---- 服务器下拉 ----
    def on_server_choice(_evt=None):
        if server_var.get() == "默认":
            if state["server"] != DEFAULT_SERVER:
                apply_server(DEFAULT_SERVER)
            start_check()
        else:
            val = simpledialog.askstring(
                "自定义更新检查服务器",
                "请输入更新检查服务器地址（填到端口为止，不要带文件名）：\n"
                "例如：http://127.0.0.1:8080",
                initialvalue=state["server"], parent=win)
            if val and apply_server(val):
                start_check()
            else:
                server_var.set("默认" if state["server"] == DEFAULT_SERVER
                               else "自定义")

    def on_about():
        messagebox.showinfo(
            "关于",
            "%s\n\n作者：%s\nQQ：%s\n\n更新检查服务器：%s\n本地版本：%s"
            % (PROG_NAME, AUTHOR, AUTHOR_QQ, state["server"],
               state["local_ver"] or "（无）"))

    # 按钮行：暂停/继续、取消更新、重新检查、检查/应用更新
    btns = tk.Frame(bottom)
    btns.pack(anchor="e")
    pause_btn = tk.Button(btns, text="暂停", width=10, state="disabled",
                          command=on_pause_toggle)
    pause_btn.pack(side="left", padx=(0, 6))
    cancel_btn = tk.Button(btns, text="取消更新", width=10, state="disabled",
                           command=on_cancel)
    cancel_btn.pack(side="left", padx=(0, 6))
    check_btn = tk.Button(btns, text="重新检查", width=10, command=start_check)
    check_btn.pack(side="left", padx=(0, 6))
    btn = tk.Button(btns, text="检查/应用更新", width=16, height=2,
                    font=("", 11, "bold"), command=on_start)
    btn.pack(side="left")

    about_btn.config(command=on_about)
    server_box.bind("<<ComboboxSelected>>", on_server_choice)

    server_var.set("默认" if state["server"] == DEFAULT_SERVER else "自定义")
    refresh_server_label()

    win.after(200, start_check)
    win.mainloop()
    return 0


# ========================================================================= #
# 静默模式（--auto）：方式一 逐目录更新
# ========================================================================= #
def run_auto(root_dir, data_dir, cfg, self_exe, log_path):
    """静默模式：先比对 version.json，有更新才按 alphahu.json 逐目录更新。
    供 PCL 启动前 / .bat 调用，不弹面板。"""
    global _LOG_PATH, _DATA_DIR
    _LOG_PATH = log_path            # 日常为 None：出错时才生成日志文件
    _DATA_DIR = data_dir            # 供 _fail_box 出错时落盘用
    server = norm_server(cfg.get("server")) or DEFAULT_SERVER
    _log("静默模式：检查更新。服务器=%s" % server)

    try:
        server_ver = fetch_remote_version(server)
    except Exception as e:
        _fail_box("检查更新失败（无法连接 %s）：%s" % (server, e))
        return 1

    local_ver = read_local_version(data_dir)
    if server_ver and server_ver == local_ver:
        _log("已是最新版本：%s，无需更新。" % server_ver)
        return 2

    # 公告隔离保存：本地没有或版本有变时刷新
    ensure_note(server, data_dir, force=True)

    tmpdir = tempfile.mkdtemp(prefix="huhu_")
    try:
        alpha_path = os.path.join(tmpdir, POINTER_SAVE_NAME)
        info = fetch_info(srv_url_alpha(server), save_path=alpha_path)
        if not any((info["folders"][k].get("url")) for k in FOUR_KEYS):
            _fail_box("更新清单（alphahu.json）里没有可用的下载地址，无法更新。")
            return 1
        result = do_update("four", root_dir, data_dir, cfg, info, self_exe,
                           log_path)
    except Exception as e:
        _fail_box("更新失败：%s" % e)
        return 1
    finally:
        # 更新清单只临时存放，用完立即删除（避免暴露文件原始地址）
        shutil.rmtree(tmpdir, ignore_errors=True)

    if result in (0, 2) and server_ver:
        write_local_version(data_dir, server_ver)
    return result


# ------------------------------------------------------------------------- #
if __name__ == "__main__":
    # 模块级代码，_LOG_PATH/_DATA_DIR 已是全局，勿写 global
    root_dir = os.path.dirname(os.path.abspath(sys.argv[0])) or os.getcwd()
    data_dir = app_dir_of(root_dir)          # 不存在则创建 HuhuUpdate
    # 缺什么生成什么：首次运行自动补全配置文件（不硬依赖 ini）
    ensure_defaults(data_dir)
    _DATA_DIR = data_dir                     # 出错时用它生成日志文件
    cfg_path = os.path.join(data_dir, CONFIG_NAME)
    cfg = load_config(cfg_path)
    self_exe = os.path.abspath(sys.argv[0])

    auto = ("--auto" in sys.argv[1:]) or ("-auto" in sys.argv[1:])
    try:
        if auto:
            code = run_auto(root_dir, data_dir, cfg, self_exe, None)
        else:
            code = run_gui(root_dir, data_dir, cfg, self_exe, None)
    except SystemExit:
        raise
    except Exception as e:
        # 程序级异常 → 生成日志文件并在提示里告知
        _fail_box("发生异常：%s" % e)
        code = 1
    sys.exit(code)
