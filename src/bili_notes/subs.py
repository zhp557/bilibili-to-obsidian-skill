"""B 站 AI 字幕：先扫可用性，再下载。

**优先走这条路，不要一上来就跑 ASR。** 教学类视频大多带 ai-zh 字幕，
转写质量够用，几秒拿完一集，而 ASR 要几分钟。

用法:
    python subs.py scan  <bvid>            # 全部分 P
    python subs.py scan  <bvid> 1-4        # 只扫 1~4
    python subs.py fetch <bvid>            # 下载 avail.tsv 里全部有字幕的 P
    python subs.py fetch <bvid> 1,2,4      # 只下指定 P

产物:
    <WORKDIR>\\subs_<bvid>\\avail.tsv      page / cid / lan / has(1|0) / url / part
    <WORKDIR>\\subs_<bvid>\\pNNN.json      原始字幕（body 里带 from/to/content）
    <WORKDIR>\\subs_<bvid>\\pNNN.txt       [mm:ss] content 逐行，直接读这个
"""
import json
import os
import sys

import common as C

OUT = None


def api_dir(bvid):
    global OUT
    OUT = os.path.join(C.WORKDIR, "subs_" + bvid)
    os.makedirs(OUT, exist_ok=True)
    return OUT


def scan(bvid, rng=None):
    d = api_dir(bvid)
    data = C.view(bvid)
    aid = data["aid"]
    key = C.wbi_key()
    pages = data["pages"]
    if rng:
        a, b = (int(x) for x in rng.split("-"))
        pages = [p for p in pages if a <= p["page"] <= b]

    rows = []
    for p in pages:
        url = C.wbi_signed("/x/player/wbi/v2",
                           {"aid": aid, "cid": str(p["cid"]), "wts": C.wts()}, key)
        r = C.api(url)
        subs = ((r.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        lan = subs[0]["lan"] if subs else ""
        surl = subs[0]["subtitle_url"] if subs else ""
        rows.append("\t".join([str(p["page"]), str(p["cid"]), lan,
                               "1" if subs else "0", surl, p["part"]]))

    path = os.path.join(OUT, "avail.tsv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))
    n = sum(1 for r in rows if r.split("\t")[3] == "1")
    print("scan DONE total=%d with_sub=%d -> %s" % (len(rows), n, path))
    if n == 0:
        print("!! 一个都没有：多半是没登录（ai-zh 字幕要登录态才返回）。")
        print("   把 SESSDATA / bili_jct / DedeUserID 存成 JSON 到 %s" % C.COOKIE_PATH)
        print("   格式见 docs/cookies.md；这个文件不会被提交。")
    return path


def load_avail(bvid):
    path = os.path.join(api_dir(bvid), "avail.tsv")
    if not os.path.exists(path):
        scan(bvid)
    avail = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            fields = line.rstrip("\n").split("\t")
            if len(fields) >= 5 and fields[3] == "1":
                avail[int(fields[0])] = (fields[4], fields[5])
    return avail


def fetch(bvid, targets=None):
    d = api_dir(bvid)
    avail = load_avail(bvid)
    if not avail:
        print("no subtitles available, fall back to ASR: python asr.py %s <pages>" % bvid)
        return
    pages = targets or sorted(avail)
    for page in pages:
        if page not in avail:
            print("P%03d no sub" % page)
            continue
        surl = avail[page][0]
        if surl.startswith("//"):
            surl = "https:" + surl
        # 字幕地址来自接口返回值和本地 avail.tsv，两者都不是我们控制的。
        # 所以：只走 https、只接受 B 站域名，而且**一律匿名** —— 绝不把登录态发给它。
        if not surl.startswith("https://") or not C.host_allowed(surl):
            print("P%03d skip: 不可信的字幕地址 %s" % (page, surl[:50]))
            continue
        raw = C.get_raw(surl, cookie="", allowed_hosts=C.BILI_HOSTS)
        try:
            j = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print("P%03d parse fail %s" % (page, e))
            continue
        body = j.get("body") or []
        with open(os.path.join(d, "p%03d.json" % page), "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False)
        lines = ["[%s] %s" % (C.mmss(b["from"]), b["content"].strip()) for b in body]
        with open(os.path.join(d, "p%03d.txt" % page), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("P%03d %-34s lines=%d chars=%d" % (
            page, avail[page][1][:34], len(body), sum(len(b["content"]) for b in body)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, bvid = sys.argv[1], sys.argv[2]
    if cmd == "scan":
        scan(bvid, sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "fetch":
        arg = sys.argv[3] if len(sys.argv) > 3 else ""
        tgt = [int(x) for x in arg.split(",") if x.strip()] if arg and arg != "all" else None
        fetch(bvid, tgt)
    else:
        raise SystemExit(__doc__)