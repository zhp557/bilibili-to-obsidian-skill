"""按时间点从 B 站 DASH 流截帧（板书截图）。

用法:
    python capture.py <bvid> <page> 0 120 240          # 指定秒数
    python capture.py <bvid> <page> 0:1700:120         # start:end:step 批量
    python capture.py <bvid> <page> 0:1700:120 1755    # 两种写法可混用

产物: <WORKDIR>\\frames\\p<page>\\t%04d.png
       已存在且 >1KB 的帧会跳过，可反复增量补帧。

要点:
- 源最高常常只有 852x480（教学视频老课），追 1080P 没意义，笔记附件也是这个尺寸。
- 优先 480P 的 H.264（codecid 7），兼容性好；4K/AV1 反而容易解不出来。
"""
import os
import subprocess
import sys

import common as C

bvid = sys.argv[1]
page = int(sys.argv[2])

data = C.view(bvid)
p = next((x for x in data["pages"] if x["page"] == page), None)
if p is None:
    raise SystemExit("page %d not found (total %d)" % (page, len(data["pages"])))

pu = C.playurl(bvid, p["cid"])
videos = (((pu.get("data") or {}).get("dash")) or {}).get("video") or []
if not videos:
    raise SystemExit("no video stream: %s" % pu.get("message"))

# 优先 H.264（codecid 7）里最高的那档。
# 实测：匿名请求只给到 480P(id=32)，带上登录 cookie 后同一分 P 会给 720P(id=64)，
# 所以本地 cookie 有效时板书截图能比老笔记（852x480）更清楚。
cand = [v for v in videos if v.get("codecid") == 7] or videos
v = sorted(cand, key=lambda x: (x.get("height") or 0, x.get("bandwidth") or 0))[-1]
url = v.get("baseUrl") or v.get("base_url")
print("[stream] id=%s codec=%s %sx%s" % (v["id"], v["codecid"], v["width"], v["height"]), flush=True)

outdir = os.path.join(C.WORKDIR, "frames", bvid, "p%d" % page)
os.makedirs(outdir, exist_ok=True)

times = []
for a in sys.argv[3:]:
    if ":" in a:
        s, e, st = (int(x) for x in a.split(":"))
        times.extend(range(s, e + 1, st))
    else:
        times.append(int(a))

for t in times:
    out = os.path.join(outdir, "t%04d.png" % t)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("[%4ds] SKIP (exists)" % t, flush=True)
        continue
    r = subprocess.run(
        [C.FFMPEG, "-y", "-v", "error",
         "-user_agent", C.UA,
         "-headers", "Referer: https://www.bilibili.com/\r\n",
         "-ss", str(t), "-i", url,
         "-frames:v", "1", "-q:v", "2", out],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    size = os.path.getsize(out) if os.path.exists(out) else 0
    detail = "" if ok else (r.stderr or "")[-160:].replace("\n", " ")
    print("[%4ds] %s %8d bytes %s" % (t, "OK  " if ok else "FAIL", size, detail), flush=True)

print("frames ->", outdir)