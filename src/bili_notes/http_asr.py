"""云端 ASR（HTTP 版）：千问百炼原生 multimodal-generation 接口。

优先级（本 skill 的文本获取三档）：
    1. B 站 AI 字幕        subs.py        —— 37 分钟一集约 3 秒，最省
    2. 云端 ASR（本脚本）  http_asr.py    —— 37 分钟一集约 3~5 分钟，要额度，带标点
    4. 本地 whisper        asr.py         —— 断网兜底，需要 Python 3.12 venv

为什么用这条路径（2026-10 实测）：
    POST /api/v1/services/aigc/multimodal-generation/generation
    body: {"model":"qwen3-asr-flash",
           "input":{"messages":[{"role":"user","content":[{"audio":"data:audio/wav;base64,..."}]}]}}
    → 200，纯标准库即可，不需要 websockets。

对照（这些路径实测都不可用，别再试）：
    /audio/transcriptions            → 404
    chat/completions + input_audio   → 400
    ASR 异步接口 + oss:// / https:// → SERVER_ERROR / FILE_403_FORBIDDEN

用法：
    python http_asr.py <bvid> <page>
    python http_asr.py <bvid> <page> --seconds 180      # 只转前 3 分钟，先验效果
    python http_asr.py <bvid> <page> --seg 120          # 每段 120 秒（默认 120）
    python http_asr.py --file xxx.wav                   # 直接转本地音频
    python http_asr.py <bvid> <page> --tag http         # 产物加后缀，避免覆盖

产物：
    <WORKDIR>/asr_http/<bvid>_p<N>.txt       [mm:ss] 逐段文本（与 subs.py 同格式）
    <WORKDIR>/asr_http/<bvid>_p<N>.raw.json  原始分段（含每段字符数/耗时）
"""
import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

# 默认打阿里云百炼（DashScope）官方端点；用别的网关时设 ASR_HTTP_ENDPOINT。
# 注意：这些值必须**运行时**读，不能在 import 时求值 —— 否则 .env 里的设置不生效。
DEFAULT_HTTP_ENDPOINT = (
    "https://dashscope.aliyuncs.com/api/v1/services/"
    "aigc/multimodal-generation/generation")
DEFAULT_MODEL_NAME = "qwen3-asr-flash"
SEG_SEC = 120          # 每段音频秒数（base64 后约 5MB，留足余量）
MAX_B64 = 12 * 1024 * 1024

# 官方百炼端点（精确匹配用；端口/路径不参与判断）
OFFICIAL_HOSTS = ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")


def api_endpoint():
    return os.environ.get("ASR_HTTP_ENDPOINT") or DEFAULT_HTTP_ENDPOINT


def default_model():
    return os.environ.get("ASR_MODEL") or DEFAULT_MODEL_NAME


def is_dashscope(ep=None):
    """精确按主机名判断。子串匹配会把 https://evil/?x=dashscope 也当成官方端点。"""
    return C.host_of(ep or api_endpoint()) in OFFICIAL_HOSTS


def api_key_for_endpoint():
    """key 必须与端点匹配。

    默认的百炼端点只接受百炼自己的 key（DASHSCOPE_API_KEY）或通用命名的 ASR_API_KEY；
    指向自定义网关时只认 ASR_API_KEY —— 避免把别家的 key 发给一个陌生 URL。
    """
    if is_dashscope():
        return C.api_key(("ASR_API_KEY", "DASHSCOPE_API_KEY"))
    return C.api_key(("ASR_API_KEY",))


def audio_wav(bvid, page, seconds=None):
    """playurl 取最高码率音频 → 16k 单声道 wav。"""
    data = C.view(bvid)
    p = next((x for x in data["pages"] if x["page"] == page), None)
    if p is None:
        raise SystemExit("page %d not found" % page)
    pu = C.playurl(bvid, p["cid"])
    audios = (((pu.get("data") or {}).get("dash")) or {}).get("audio") or []
    if not audios:
        raise SystemExit("no audio stream: %s" % pu.get("message"))
    best = sorted(audios, key=lambda a: a.get("bandwidth", 0), reverse=True)[0]
    url = best.get("baseUrl") or best.get("base_url")

    outdir = os.path.join(C.WORKDIR, "asr_http")
    os.makedirs(outdir, exist_ok=True)
    raw = os.path.join(outdir, "%s_p%d.m4s" % (bvid, page))
    wav = os.path.join(outdir, "%s_p%d_16k.wav" % (bvid, page))
    if not os.path.exists(raw) or os.path.getsize(raw) < 1000:
        # 用 common 的 HTTP 层（urllib 优先，必要时回退 curl），不依赖 curl.exe
        blob = C.get_raw(url, cookie="", timeout=120)
        if blob:
            with open(raw, "wb") as f:
                f.write(blob)
        if not os.path.exists(raw) or os.path.getsize(raw) < 1000:
            raise SystemExit("audio download failed")
    cmd = [C.FFMPEG, "-y", "-v", "error", "-i", raw, "-ar", "16000", "-ac", "1",
           "-acodec", "pcm_s16le"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd.append(wav)
    subprocess.run(cmd, check=True)
    return wav, p["part"], p["duration"]


def any_to_wav(path, seconds=None):
    """任意音频（mp3/m4a/flac/wav…）→ 16k 单声道 wav。

    已是 16k 单声道 wav 时直接返回，不重复转码。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as w:
                if w.getframerate() == 16000 and w.getnchannels() == 1:
                    return path
        except Exception:
            pass
    outdir = os.path.join(C.WORKDIR, "asr_http")
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    wav = os.path.join(outdir, stem + "_16k.wav")
    cmd = [C.FFMPEG, "-y", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
           "-acodec", "pcm_s16le"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd.append(wav)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise SystemExit("找不到 ffmpeg：%s\n非 wav 格式需要 ffmpeg 转码" % C.FFMPEG)
    except subprocess.CalledProcessError as e:
        raise SystemExit("ffmpeg 转码失败: %s" % (e.stderr or b"")[:200])
    if not os.path.exists(wav):
        raise SystemExit("转码产物不存在: %s" % wav)
    return wav


def split_wav(wav_path, seg_sec, overlap=2):
    """按秒切片，相邻段之间重叠 overlap 秒，避免切在句子中间。

    返回 [(起始秒, wav_bytes), ...]。
    """
    with wave.open(wav_path, "rb") as w:
        nch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        total = w.getnframes()
        per = seg_sec * rate
        ov = overlap * rate
        out = []
        start = 0
        while start < total:
            w.setpos(start)
            frames = w.readframes(min(per + ov, total - start))
            buf = io.BytesIO()
            with wave.open(buf, "wb") as o:
                o.setnchannels(nch)
                o.setsampwidth(width)
                o.setframerate(rate)
                o.writeframes(frames)
            out.append((start // rate, buf.getvalue()))
            start += per
    return out


_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]", re.U)


def _plain(s):
    return _PUNCT.sub("", s)


def cut_overlap(prev_text, cur_text, min_n=8, max_n=60):
    """若 cur 开头重复了 prev 结尾，去掉重复部分。

    两次识别同一段音频结果可能有个别字不同，所以按「去标点后比较」，
    找不到匹配就原样返回（宁可重复，不可丢内容）。
    """
    a, b = _plain(prev_text), _plain(cur_text)
    if not a or not b:
        return cur_text
    for n in range(min(len(a), len(b), max_n), min_n - 1, -1):
        if a[-n:] != b[:n]:
            continue
        # 在原文里定位第 n 个有效字符之后的位置
        cnt = 0
        for i, ch in enumerate(cur_text):
            if _PUNCT.match(ch) is None:
                cnt += 1
            if cnt == n:
                return cur_text[i + 1:].lstrip("，。、；：,.;: ")
    return cur_text


def transcribe(model, key, wav_bytes):
    """一次 HTTP 调用，返回该段文本。"""
    b64 = base64.b64encode(wav_bytes).decode()
    if len(b64) > MAX_B64:
        raise SystemExit("单段 base64 过大（%d），请调小 --seg" % len(b64))
    body = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [
            {"audio": "data:audio/wav;base64," + b64}]}]},
    }
    req = urllib.request.Request(
        api_endpoint(), data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:300]))
    except urllib.error.URLError as e:
        raise SystemExit("网络错误: %s" % e.reason)

    out = j.get("output") or {}
    if out.get("code"):
        raise SystemExit("上游错误: %s %s" % (out.get("code"), out.get("message")))
    content = None
    for ch in (out.get("choices") or []):
        content = (ch.get("message") or {}).get("content")
        if content:
            break
    if content is None:
        content = out.get("text") or ""
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c)
                          for c in content)
    return str(content or "").strip()


def main():
    ap = argparse.ArgumentParser(description="云端 ASR（HTTP 版，百炼 multimodal-generation）")
    ap.add_argument("bvid", nargs="?", help="BV 号")
    ap.add_argument("page", nargs="?", type=int, help="分 P 序号")
    ap.add_argument("--file", help="直接转本地音频（跳过 B 站下载）")
    ap.add_argument("--seconds", type=int, default=None, help="只转前 N 秒")
    ap.add_argument("--seg", type=int, default=SEG_SEC, help="每段秒数，默认 120")
    ap.add_argument("--overlap", type=int, default=2, help="相邻段重叠秒数，默认 2（0 关闭）")
    ap.add_argument("--model", default=None,
                    help="ASR 模型，默认取 ASR_MODEL 或 qwen3-asr-flash")
    ap.add_argument("--tag", default="", help="产物文件附加后缀，如 http")
    args = ap.parse_args()

    model = args.model or default_model()
    if (args.seg or 0) <= 0:
        raise SystemExit("--seg 必须大于 0（当前 %s）" % args.seg)
    if (args.overlap or 0) < 0 or (args.overlap or 0) >= args.seg:
        raise SystemExit("--overlap 必须 >= 0 且小于 --seg（当前 %s / %s）"
                         % (args.overlap, args.seg))

    key = api_key_for_endpoint()
    outdir = os.path.join(C.WORKDIR, "asr_http")
    os.makedirs(outdir, exist_ok=True)

    if args.file:
        if not os.path.exists(args.file):
            raise SystemExit("文件不存在: %s" % args.file)
        stem = os.path.splitext(os.path.basename(args.file))[0]
        wav, title, dur = any_to_wav(args.file, args.seconds), stem, None
    else:
        if not args.bvid or not args.page:
            raise SystemExit("用法: python http_asr.py <bvid> <page> 或 --file <音频>")
        wav, title, dur = audio_wav(args.bvid, args.page, args.seconds)
        stem = "%s_p%d" % (args.bvid, args.page)

    if args.seconds is None and not args.file:
        print("音频: %s  时长 %ss" % (title, dur))
    segs = split_wav(wav, args.seg, args.overlap)
    print("分 %d 段，每段 %ds（重叠 %ds），模型 %s" % (len(segs), args.seg,
                                                      args.overlap, args.model))

    lines, raw = [], []
    t0 = time.time()
    prev_text = ""
    for i, (offset, blob) in enumerate(segs, 1):
        ts = time.time()
        text = transcribe(args.model, key, blob)
        if prev_text:
            text = cut_overlap(prev_text, text)
        prev_text = text
        raw.append({"index": i, "offset_sec": offset, "chars": len(text),
                    "elapsed": round(time.time() - ts, 2), "text": text})
        print("  [%d/%d] %s (%d 字, %.1fs)" % (i, len(segs), C.mmss(offset), len(text),
                                               time.time() - ts))
        if text:
            lines.append("[%s] %s" % (C.mmss(offset), text))

    suffix = ("." + args.tag) if args.tag else ""
    txt = os.path.join(outdir, "%s%s.txt" % (stem, suffix))
    js = os.path.join(outdir, "%s%s.raw.json" % (stem, suffix))
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    print("\n完成，用时 %.1fs" % (time.time() - t0))
    print("文本: %s（%d 段有内容）" % (txt, len(lines)))
    print("分段: %s" % js)


if __name__ == "__main__":
    main()