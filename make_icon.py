# -*- coding: utf-8 -*-
"""生成更新器 .ico 图标（多尺寸），供 PyInstaller --icon 使用。
用法：python make_icon.py  →  输出 huhu_icon.ico
绘制：圆角方块（蓝底渐变）+ 白色向下的“更新/下载”箭头。
"""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "huhu_icon.ico")
SIZES = [16, 32, 48, 64, 128, 256]


def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = float(size)
    # 圆角方块（底图，带圆角遮罩）
    pad = s * 0.06
    box = [pad, pad, s - pad, s - pad]
    radius = s * 0.22
    # 竖向渐变蓝
    top, bottom = (42, 125, 225), (18, 82, 156)
    for y in range(int(pad), int(s - pad)):
        t = (y - pad) / max(1.0, (s - 2 * pad))
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        d.line([pad, y, s - pad, y], fill=(r, g, b, 255))
    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle(box, radius=radius, fill=255)
    img.putalpha(mask)

    d2 = ImageDraw.Draw(img)
    # 白色向下箭头（更新/下载）
    white = (255, 255, 255, 255)
    ax = s * 0.30   # 箭头边界
    cx = s * 0.50   # 水平中心
    # 箭杆
    d2.rectangle([cx - s * 0.11, s * 0.38, cx + s * 0.11, s * 0.48], fill=white)
    # 箭头三角（顶在杆底）
    head_bottom = s * 0.70
    d2.polygon([(cx - s * 0.22, s * 0.48),
                (cx + s * 0.22, s * 0.48),
                (cx, head_bottom)], fill=white)
    # 底座横线（表示“落地/载入”）
    d2.rounded_rectangle([cx - s * 0.20, s * 0.72,
                          cx + s * 0.20, s * 0.76], radius=s * 0.02, fill=(255, 255, 255, 200))
    # 顶部两笔（从杆顶往上的“拉把”，示意刷新/更新）
    d2.line([cx - s * 0.09, s * 0.30, cx - s * 0.09, s * 0.38], fill=white, width=max(1, int(s * 0.05)))
    d2.line([cx + s * 0.09, s * 0.30, cx + s * 0.09, s * 0.38], fill=white, width=max(1, int(s * 0.05)))

    # 顶部高光
    d2.ellipse([s * 0.16, s * 0.10, s * 0.34, s * 0.26], fill=(255, 255, 255, 70))

    # 圆角重新收紧（避免渐变角溢出）
    m2 = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m2).rounded_rectangle(box, radius=radius, fill=255)
    img.putalpha(m2)
    return img


if __name__ == "__main__":
    # 以最大尺寸绘制一张，再由 Pillow 内部缩放输出全尺寸
    img = draw_icon(max(SIZES))
    img.save(OUT, format="ICO", sizes=[(sz, sz) for sz in SIZES])
    print("ICON_SAVED:", OUT, os.path.getsize(OUT), "bytes")
