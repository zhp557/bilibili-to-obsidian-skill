"""bili_notes 公共常量与网络小工具。

所有路径都能用环境变量覆盖，默认值一律落在当前工作目录下，**不含任何绝对路径**，
所以 clone 到任何机器都能直接跑：

    BILI_NOTES_WORKDIR   中间产物目录（字幕/帧/音频）   默认 <cwd>/work
    BILI_NOTES_VAULT     Obsidian vault 路径           默认空；当前版本不读取，供扩展
    BILI_NOTES_COOKIE    B 站 cookie json 路径          默认 <WORKDIR>/cookies.json
    BILI_NOTES_FFMPEG    ffmpeg 可执行文件              默认从 PATH 找
    BILI_NOTES_HTTP      HTTP 后端 auto|urllib|curl      默认 auto

.env 在**导入时**就读进来，保证下面这些常量看到的是最终值 ——
否则「.env 里设了 ASR_HTTP_ENDPOINT 却不生效」这种坑会一直存在。
"""
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request


def load_dotenv(path=None):
    """把一个 .env 读进 os.environ（已存在的变量不覆盖）。不依赖 python-dotenv。"""
    p = path or os.path.join(os.getcwd(), ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


# 必须在任何 os.environ.get 常量之前执行
load_dotenv()

WORKDIR = os.environ.get(
    "BILI_NOTES_WORKDIR") or os.path.join(os.getcwd(), "work")
VAULT = os.environ.get("BILI_NOTES_VAULT", "")
COOKIE_PATH = os.environ.get(
    "BILI_NOTES_COOKIE") or os.path.join(WORKDIR, "cookies.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

REFERER = "https://www.bilibili.com/"

# B 站 wbi 签名用的混淆表（固定 64 长）
MIXIN = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

# 允许携带登录凭据的域名后缀。任何不在这个列表里的地址，一律匿名访问。
BILI_HOSTS = ("bilibili.com", "biliapi.net", "hdslb.com", "bilivideo.com",
              "biliimg.com", "bstarstatic.com")


def api_key(names=("ASR_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY")):
    """按顺序从环境变量 / .env 取 key。绝不读仓库外的私有文件。"""
    load_dotenv()
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    raise SystemExit(
        "找不到 ASR key。二选一：\n"
        "  1) 在仓库根目录建 .env，写一行 ASR_API_KEY=你的key（参考 .env.example）\n"
        "  2) set ASR_API_KEY=你的key（Linux: export ASR_API_KEY=...）")


def host_of(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def host_allowed(url, suffixes=BILI_HOSTS):
    """url 的主机是否落在允许列表里。用于决定要不要附带登录凭据。"""
    h = host_of(url)
    if not h:
        return False
    return any(h == s or h.endswith("." + s) for s in suffixes)


def find_ffmpeg():
    """环境变量 → PATH。找不到就返回裸名，让调用方在 subprocess 阶段报错。"""
    p = os.environ.get("BILI_NOTES_FFMPEG")
    if p:
        return p
    return shutil.which("ffmpeg") or "ffmpeg"


FFMPEG = find_ffmpeg()


def ensure_workdir(sub=""):
    """建好 WORKDIR（或它的子目录）并返回路径。"""
    d = os.path.join(WORKDIR, sub) if sub else WORKDIR
    os.makedirs(d, exist_ok=True)
    return d


def frames_dir(page, bvid=None):
    """帧目录：frames/<bvid>/pN（按视频隔离），旧布局 frames/pN 仍然兼容。

    不给 bvid 时按唯一匹配猜；匹配到多个直接报错，绝不静默挑一个 ——
    两个视频都有 P4 时，猜错就是拿别人的板书截图写进笔记。
    """
    base = os.path.join(WORKDIR, "frames")
    if bvid:
        return os.path.join(base, bvid, "p%d" % page)
    hits = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            d = os.path.join(base, name, "p%d" % page)
            if os.path.isdir(d):
                hits.append(d)
        legacy = os.path.join(base, "p%d" % page)
        if os.path.isdir(legacy):
            hits.append(legacy)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(
            "p%d 的帧在多个视频下都存在：\n  %s\n用 --bvid 指定其中一个。"
            % (page, "\n  ".join(hits)))
    return os.path.join(base, "p%d" % page)


def vault_path():
    if not VAULT:
        raise SystemExit(
            "未设置 BILI_NOTES_VAULT。用环境变量指定 Obsidian vault 路径。")
    return VAULT


def cookie_header():
    """读 cookie json → 'k=v; k=v'。没有文件就返回空串（免登录接口仍可用）。"""
    if not os.path.exists(COOKIE_PATH):
        return ""
    with open(COOKIE_PATH, encoding="utf-8") as f:
        ck = json.load(f)
    return "; ".join("%s=%s" % (k, v) for k, v in ck.items())


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """跨源重定向时丢掉敏感头。

    urllib 默认会把原请求的 headers 复制给重定向后的请求，于是 302 到第三方域时
    Cookie / Authorization 会跟着走。这里按主机名判断，跨源就剥掉这两个头。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        if host_of(req.full_url) != host_of(newurl):
            for k in list(new.headers):
                if k.lower() in ("cookie", "authorization"):
                    del new.headers[k]
        return new


_OPENER = urllib.request.build_opener(_SafeRedirect)


def _get_urllib(url, ck, timeout):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", REFERER)
    if ck:
        req.add_header("Cookie", ck)
    with _OPENER.open(req, timeout=timeout) as r:
        return r.read()


def _get_curl(url, ck, timeout):
    exe = shutil.which("curl")
    if not exe:
        raise SystemExit(
            "urllib 请求失败，且系统里没有 curl。"
            "如果你在受限网络下，装个 curl 或改 BILI_NOTES_HTTP=urllib 重试。")
    cmd = [exe, "-sS", "--max-time", str(timeout), "-A", UA, "-e", REFERER]
    stdin = None
    if ck:
        # 控制字符能破坏 curl config 的语法，损坏或伪造的 cookies.json 会变成注入面
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in ck):
            raise SystemExit(
                "Cookie 里含控制字符，拒绝发送。检查 %s 是不是被改坏了。" % COOKIE_PATH)
        # Cookie 走 --config -（stdin），不出现在进程命令行里，ps/tasklist 看不到
        cmd += ["--config", "-"]
        safe = ck.replace("\\", "\\\\").replace('"', '\\"')
        stdin = ('header = "Cookie: %s"\n' % safe).encode("utf-8")
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, input=stdin)
    return p.stdout


def get_raw(url, cookie=None, timeout=30, force_curl=False, allowed_hosts=None):
    """B 站接口统一走这里。

    cookie 传 None 表示带上本地 cookie；传 "" 表示匿名。
    allowed_hosts 给了 suffixes 时，主机不匹配就自动降级为匿名 ——
    避免把登录态发给接口返回值里的任意地址。
    默认 urllib（跨平台、无外部依赖）；命中 -352 风控时由 api() 自动回退 curl。
    """
    ck = cookie_header() if cookie is None else cookie
    if ck and allowed_hosts is not None and not host_allowed(url, allowed_hosts):
        ck = ""
    backend = os.environ.get("BILI_NOTES_HTTP", "auto").lower()
    if not force_curl and backend in ("auto", "urllib"):
        try:
            return _get_urllib(url, ck, timeout)
        except Exception:  # noqa: BLE001
            if backend == "urllib":
                raise
    return _get_curl(url, ck, timeout)


def api(url, cookie=None, timeout=30):
    raw = get_raw(url, cookie=cookie, timeout=timeout, allowed_hosts=BILI_HOSTS)
    try:
        d = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {"code": -1,
                "message": "decode failed: " + raw[:200].decode("utf-8", "replace")}
    # -352 是 B 站的风控码。urllib 偶尔会被盯上，换 curl 重试一次。
    if d.get("code") == -352 and os.environ.get("BILI_NOTES_HTTP", "auto") == "auto":
        raw = get_raw(url, cookie=cookie, timeout=timeout, force_curl=True,
                      allowed_hosts=BILI_HOSTS)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return d


def view(bvid):
    d = api("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
    if d.get("code") != 0:
        raise SystemExit("view 失败: %s" % d)
    return d["data"]


def playurl(bvid, cid):
    return api(
        "https://api.bilibili.com/x/player/playurl"
        "?bvid=%s&cid=%s&fnval=16&fourk=1" % (bvid, cid)
    )


def wbi_key():
    """nav 接口拿 img_key/sub_key，按固定 MIXIN 重排取前 32 位。不需要登录。"""
    nav = api("https://api.bilibili.com/x/web-interface/nav", cookie="")
    w = nav["data"]["wbi_img"]
    raw = w["img_url"].rsplit("/", 1)[1].split(".")[0] + \
        w["sub_url"].rsplit("/", 1)[1].split(".")[0]
    return "".join(raw[i] for i in MIXIN)[:32]


def wbi_signed(path, params, key):
    params = dict(sorted(params.items()))
    q = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((q + key).encode()).hexdigest()
    return "https://api.bilibili.com" + path + "?" + urllib.parse.urlencode(params)


def wts():
    return int(time.time())


def mmss(sec):
    sec = int(sec)
    return "%02d:%02d" % (sec // 60, sec % 60)
