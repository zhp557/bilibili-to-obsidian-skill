"""把转写 JSON 按固定窗口合并成可读文本（ASR 路线专用）。

用法:
    python extract.py 4                # -> 与输入同目录的 p4_transcript.txt，60 秒一段
    python extract.py 4 90             # 90 秒一段
    python extract.py --bvid BVxxx 4   # 多个视频都有 p4 时必须指定
    python extract.py <转写.json 路径>  # 直接指定文件

字幕路线不需要这个：subs.py 出来的 pNNN.txt 已经是 [mm:ss] 逐行格式。

查找顺序（不指定路径时）：bili_audio/<bvid>/pN_transcript.json → bili_audio/*/pN_transcript.json
→ <WORKDIR>/pN_transcript.json（旧布局）。
"""
import glob
import json
import os
import sys

import common as C

argv = sys.argv[1:]
bvid = None
if "--bvid" in argv:
    i = argv.index("--bvid")
    if i + 1 < len(argv):
        bvid = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

if not argv:
    raise SystemExit(__doc__)

first = argv[0]
window = int(argv[1]) if len(argv) > 1 else 60

if first.lower().endswith(".json"):
    src = first
else:
    page = first
    name = "p%s_transcript.json" % page
    if bvid:
        src = os.path.join(C.WORKDIR, "bili_audio", bvid, name)
    else:
        cands = [p for p in
                 sorted(glob.glob(os.path.join(C.WORKDIR, "bili_audio", "*", name)))
                 if os.path.exists(p)]
        legacy = os.path.join(C.WORKDIR, name)
        if os.path.exists(legacy):
            cands.append(legacy)
        if len(cands) > 1:
            raise SystemExit(
                "p%s 的转写在多个位置都有：\n  %s\n用 --bvid 指定其中一个。"
                % (page, "\n  ".join(cands)))
        src = cands[0] if cands else legacy
    if not os.path.exists(src):
        raise SystemExit("找不到转写文件：%s\n先跑 asr.py 生成它。" % src)

dst = src[:-5] + ".txt" if src.lower().endswith(".json") else src + ".txt"

with open(src, encoding="utf-8") as f:
    d = json.load(f)

# 窗口合并：从第一段的 start 起算，累计到超过 WINDOW 就切下一块（原逻辑，勿改）
blocks, cur, buf = [], None, []
for s in d.get("segments") or []:
    start = float(s.get("start") or 0)
    text = s.get("text") or ""
    if cur is None:
        cur, buf = start, [text]
    elif start - cur < window:
        buf.append(text)
    else:
        blocks.append((cur, "".join(buf)))
        cur, buf = start, [text]
if cur is not None:
    blocks.append((cur, "".join(buf)))

with open(dst, "w", encoding="utf-8") as f:
    f.write("\n".join("[%s] %s" % (C.mmss(t), txt) for t, txt in blocks))
print("src: %s\nblocks: %d chars: %d -> %s"
      % (src, len(blocks), sum(len(x[1]) for x in blocks), dst))
