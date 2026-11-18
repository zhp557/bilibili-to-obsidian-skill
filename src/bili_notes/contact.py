"""把某个分 P 的帧拼成联系表，一眼看全集结构。

用法:
    python contact.py p4                 # -> <WORKDIR>/contact_p4.png
    python contact.py 4                  # 等价写法
    python contact.py p1 p2 p4           # 一次拼多张
    python contact.py --bvid BVxxx p4    # 多个视频都有 P4 时必须指定
    python contact.py <帧目录> -o x.png

为什么先拼联系表：直接开单帧会盲；拼成一张 3 列网格，按时间标签就能
立刻划出「开场 / 例题 / 解答 / 下一题」的段落，再去挑精帧。
"""
import glob
import os
import re
import sys

from PIL import Image, ImageDraw

import common as C

argv = sys.argv[1:]
bvid = None
if "--bvid" in argv:
    i = argv.index("--bvid")
    if i + 1 < len(argv):
        bvid = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

args = [a for a in argv if not a.startswith("-")]
out_opt = None
if "-o" in argv:
    out_opt = argv[argv.index("-o") + 1]
    args = [a for a in args if a != out_opt]

COLS = 3
THUMB_W, THUMB_H = 426, 240
LABEL_H = 22


def sheet(frames_dir, out_path):
    files = sorted(
        glob.glob(os.path.join(frames_dir, "t*.png")),
        key=lambda p: int(re.search(r"t(\d+)\.png$", p).group(1)),
    )
    if not files:
        print("no frames in", frames_dir)
        return
    rows = (len(files) + COLS - 1) // COLS
    img = Image.new("RGB", (COLS * THUMB_W, rows * (THUMB_H + LABEL_H)), "white")
    draw = ImageDraw.Draw(img)
    for idx, path in enumerate(files):
        t = int(re.search(r"t(\d+)\.png$", path).group(1))
        thumb = Image.open(path).convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS)
        col, row = idx % COLS, idx // COLS
        x, y = col * THUMB_W, row * (THUMB_H + LABEL_H)
        img.paste(thumb, (x, y))
        draw.rectangle([x, y + THUMB_H, x + THUMB_W, y + THUMB_H + LABEL_H], fill="black")
        draw.text((x + 6, y + THUMB_H + 4), "%02d:%02d  (%ds)" % (t // 60, t % 60, t), fill="white")
    img.save(out_path, "PNG")
    print("frame count: %-4d sheet: %s %s" % (len(files), out_path, img.size))


for name in args:
    if os.path.isdir(name):
        d = name
        bv = bvid or ""
    else:
        page = int(re.sub(r"^[pP]", "", name))
        d = C.frames_dir(page, bvid)
        parent = os.path.basename(os.path.dirname(d.rstrip("\\/")))
        bv = bvid or (parent if parent and parent != "frames" else "")
    base = os.path.basename(d.rstrip("\\/"))
    # 文件名带 BV：两个视频都有 P4 时，联系表不会互相覆盖
    fname = "contact_%s_%s.png" % (bv, base) if bv else "contact_%s.png" % base
    out = out_opt if (out_opt and len(args) == 1) else os.path.join(C.WORKDIR, fname)
    sheet(d, out)