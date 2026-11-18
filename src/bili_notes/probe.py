"""列出某 BV 的全部分 P + 分辨率 + 是否疑似广告片尾。

用法:
    python probe.py <bvid>
    python probe.py <bvid> <page>          # 只看某 P，含 cid / 时长 / 视频流

输出示例:
    p1   1700s  1000000000  852x480  （一）第一节标题
    p3     34s  2000000000  852x480  <预览：疑似广告/片尾>
"""
import sys

import common as C

bvid = sys.argv[1]
only = int(sys.argv[2]) if len(sys.argv) > 2 else None

data = C.view(bvid)
pages = data["pages"]
print("TITLE:", data["title"])
print("OWNER:", data["owner"]["name"])
print("PAGES:", len(pages))
print()

for p in pages:
    if only and p["page"] != only:
        continue
    pu = C.playurl(bvid, p["cid"])
    dash = ((pu.get("data") or {}).get("dash")) or {}
    vids = dash.get("video") or []
    res = sorted({(v["width"], v["height"]) for v in vids if v.get("width")})
    best = "%dx%d" % res[-1] if res else "?"
    dur = p["duration"]
    tail = ""
    if dur < 90:
        tail = "  <预览：疑似广告/片尾，通常跳过>"
    print("p%-3d %5ds  %-12s %-9s %s%s" % (
        p["page"], dur, p["cid"], best, p["part"], tail))
    if only:
        print("  可用分辨率:", res)
        print("  视频流:", [(v["id"], v["codecid"]) for v in vids])
        print("  音频流:", [(a.get("id"), a.get("bandwidth")) for a in (dash.get("audio") or [])])