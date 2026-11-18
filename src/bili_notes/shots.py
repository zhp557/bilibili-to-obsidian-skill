"""把挑好的帧按「时间点:目标文件名」复制进笔记的附件目录。

用法:
    python shots.py <页> "<附件目录>" "0:01-本讲标题.png" "120:02-例题1.png" ...
    python shots.py 4 --dry "0:01-本讲标题.png"          # 预演，零写入
    python shots.py --bvid BVxxx 4 "<附件目录>" ...       # 多个视频都有该页时
    python shots.py 4 plan.json

    plan.json 的样子:
    {
      "dir": "<附件目录>",
      "items": [[0, "01-本讲标题.png"], [120, "02-例题1.png"]]
    }

命名约定:
    附件目录  p<分P>-<章节名>        例:p04-示例章节名
    图片名    NN-<题型或小节>.png     例:02-例题1-题目.png
    第一张通常叫 01-本讲标题.png，对应 t=0 的开场封面。

只复制、不移动，源帧留着可反复重挑。
目标同名文件已存在时默认跳过，加 --overwrite 才覆盖 —— 附件目录常常是全库共享的，
静默覆盖会改掉别的笔记里的图。
"""
import json
import os
import re
import shutil
import sys

import common as C

argv = sys.argv[1:]
dry = "--dry" in argv
overwrite = "--overwrite" in argv
bvid = None
if "--bvid" in argv:
    i = argv.index("--bvid")
    if i + 1 < len(argv):
        bvid = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

pos = [a for a in argv if not a.startswith("--")]
if not pos:
    raise SystemExit(__doc__)

page = int(re.sub(r"^[pP]", "", pos[0]))
rest = pos[1:]

if len(rest) == 1 and rest[0].lower().endswith(".json"):
    with open(rest[0], encoding="utf-8") as f:
        plan = json.load(f)
    outdir = plan["dir"]
    items = [(int(t), n) for t, n in plan["items"]]
else:
    if not rest:
        raise SystemExit(__doc__)
    outdir = rest[0]
    items = []
    for a in rest[1:]:
        t, name = a.split(":", 1)
        items.append((int(t), name))

if not items:
    raise SystemExit(
        "没有要复制的帧。\n"
        "用法：shots <页> \"<附件目录>\" \"秒:文件名\" [\"秒:文件名\" ...]\n"
        "        shots 4 \"attachments/p04-章节名\" \"0:01-本讲标题.png\" \"120:02-例题1.png\"\n"
        "        shots 4 --dry \"0:01-本讲标题.png\"    # 只想预演")

src_dir = C.frames_dir(page, bvid)
if not dry:
    os.makedirs(outdir, exist_ok=True)

ok = miss = skipped = 0
for t, name in items:
    src = os.path.join(src_dir, "t%04d.png" % t)
    if not os.path.exists(src):
        print("MISSING t%04d.png（先跑 capture 补这一帧）" % t)
        miss += 1
        continue
    size = os.path.getsize(src)
    if size < 1000:
        print("SUSPECT t%04d.png 只有 %d 字节（黑帧/坏帧，别用）" % (t, size))
        miss += 1
        continue
    dst = os.path.join(outdir, name)
    if os.path.exists(dst) and not overwrite:
        print("EXISTS %s（同名附件已存在，跳过；要覆盖加 --overwrite）" % name)
        skipped += 1
        continue
    if dry:
        print("[dry] t%04d -> %s" % (t, name))
    else:
        shutil.copy2(src, dst)
    ok += 1

where = "(dry run，未写入任何文件)" if dry else outdir
print("copied %d, skipped %d, missing %d -> %s" % (ok, skipped, miss, where))
