# -*- coding: utf-8 -*-
"""ASCII 打包脚本：在 Python 内部处理中文 exe 名，避免命令行编码问题。
用法：python make_exe.py
"""
import os
import sys

import PyInstaller.__main__

os.chdir(os.path.dirname(os.path.abspath(__file__)))
for folder in ("build", "dist"):
    import shutil
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
for ext in (".spec",):
    if os.path.isfile("糊糊爆破模式客户端更新器" + ext):
        os.remove("糊糊爆破模式客户端更新器" + ext)

icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "huhu_icon.ico")

PyInstaller.__main__.run([
    "--onefile",
    "--noconsole",
    "--icon", icon,
    "--name", "糊糊爆破模式客户端更新器",
    "updater_main.py",
])

out = os.path.join("dist", "糊糊爆破模式客户端更新器.exe")
print("BUILD OK:", out, os.path.getsize(out) if os.path.isfile(out) else "MISSING")
