"""ASR 兜底：B 站没有 AI 字幕时才用。

**先跑 subs.py scan**，真有字幕就别用这个 —— 实测一集 34 分钟的课，
字幕几秒拿完，faster-whisper small 要跑好几分钟，而且同音错字更多。

用法:
    python asr.py <bvid> <page> [page...]
    set ASR_PROMPT=大学课程的课堂录音，涉及专业术语   # 可选：领域词提示，提高专有名词准确率

产物:
    <WORKDIR>/bili_audio/<bvid>/pN.m4a / pN_16k.wav
    <WORKDIR>/bili_audio/<bvid>/pN_transcript.json   （segments + text，给 extract.py 消费）

依赖:
    faster-whisper + numpy，建议 Python 3.9~3.12（更高版本可能还没有可用轮子）。
    单独建个 venv 最省事:

        py -3.12 -m venv .venv
        .venv\\Scripts\\python.exe -m pip install faster-whisper numpy
        .venv\\Scripts\\python.exe asr.py BVxxx 1

模型缓存:
    首次运行会把模型下到 <WORKDIR>/hf_home（small 约 460 MB）。之后复用，不必重复下载；
    想换位置就设 HF_HOME 环境变量。
"""
import json
import os
import shutil
import subprocess
import sys
import time
import wave

import common as C

HF_HOME = os.path.join(C.WORKDIR, "hf_home")
os.environ["HF_HOME"] = HF_HOME
os.environ["HF_HUB_CACHE"] = os.path.join(HF_HOME, "hub")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

try:
    import numpy as np
    from faster_whisper import WhisperModel
except ImportError as e:  # noqa: BLE001
    raise SystemExit(
        "缺少依赖: %s\n当前解释器: %s\n"
        "换 3.12 的 venv 跑，或先 pip install faster-whisper numpy。\n"
        "重建: py -3.12 -m venv .venv && .venv\\Scripts\\python.exe -m pip install faster-whisper numpy"
        % (e, sys.executable)
    )

bvid = sys.argv[1]
pages = [int(x) for x in sys.argv[2:]] or [1]

data = C.view(bvid)
page_map = {p["page"]: p for p in data["pages"]}
# 按 bvid 分目录：不同视频的同一分 P 绝不能共用音频缓存
audio_dir = os.path.join(C.WORKDIR, "bili_audio", bvid)
os.makedirs(audio_dir, exist_ok=True)


def download_audio(cid, dest):
    """直连 playurl 的 dash.audio，绕开 yt-dlp 的 B 站解析器。"""
    pu = C.playurl(bvid, cid)
    audios = (((pu.get("data") or {}).get("dash")) or {}).get("audio") or []
    if not audios:
        return False, "no dash audio (%s)" % pu.get("message")
    best = sorted(audios, key=lambda a: a.get("bandwidth", 0), reverse=True)[0]
    url = best.get("baseUrl") or best.get("base_url")
    if not url:
        return False, "no baseUrl"
    import urllib.request
    req = urllib.request.Request(
        url, headers={"User-Agent": C.UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return True, "%d bytes (bw=%s)" % (os.path.getsize(dest), best.get("bandwidth"))


model = None
for page in pages:
    try:
        target = page_map.get(page)
        if target is None:
            print("[skip] page %d not found (total %d)" % (page, len(data["pages"])))
            continue

        m4a = os.path.join(audio_dir, "p%d.m4a" % page)
        wav = os.path.join(audio_dir, "p%d_16k.wav" % page)

        if not os.path.exists(wav):
            if not os.path.exists(m4a):
                ok, info = download_audio(target["cid"], m4a)
                print("[dl]  p%d %s %s" % (page, "OK" if ok else "FAIL", info), flush=True)
                if not ok:
                    continue
            subprocess.run(
                [C.FFMPEG, "-y", "-v", "error", "-i", m4a, "-ar", "16000", "-ac", "1",
                 "-acodec", "pcm_s16le", wav],
                check=True,
            )

        with wave.open(wav, "rb") as w:
            n = w.getnframes()
            audio = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        print("[wav] p%d %.1fs" % (page, n / 16000), flush=True)

        if model is None:
            t0 = time.time()
            model = WhisperModel("small", device="cpu", compute_type="int8", download_root=HF_HOME)
            print("[asr] model ready in %.1fs" % (time.time() - t0), flush=True)

        t0 = time.time()
        segments, tinfo = model.transcribe(
            audio, language="zh", vad_filter=True, beam_size=5,
            initial_prompt=os.environ.get("ASR_PROMPT", "这是一段中文教学视频。"),
        )
        segs = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()}
                for s in segments]
        full = "".join(x["text"] for x in segs)
        out = os.path.join(audio_dir, "p%d_transcript.json" % page)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"meta": {
                "bvid": bvid, "page": page, "part": target["part"],
                "cid": target["cid"], "duration": target["duration"],
                "seriesTitle": data["title"], "owner": data["owner"]["name"],
            }, "model": "small", "duration": tinfo.duration,
                "segments": segs, "text": full}, f, ensure_ascii=False, indent=1)
        os.remove(wav)
        print("[asr] p%d DONE segs=%d chars=%d %.1fs -> %s"
              % (page, len(segs), len(full), time.time() - t0, out), flush=True)
    except Exception as e:  # noqa: BLE001
        print("[error] p%d %s: %s" % (page, type(e).__name__, str(e)[:200]), flush=True)

print("[all done]")