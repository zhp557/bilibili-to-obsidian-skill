# -*- coding: utf-8 -*-
"""离线测试：只覆盖纯函数与「仓库卫生」守卫，不碰网络。

    python -m pytest tests/          # 或者 python tests/test_common.py

设计原则：守卫测试用「模式」而不是「具体值」。
把真实用户名或路径写成断言，等于把要防的东西又写回仓库一遍。
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

import bili_notes.common as C  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 盘符 + Users/Documents，或盘符 + 非 ASCII 目录名（中文路径）。
_ABS_PATH = re.compile(r"[A-Za-z]:\\\\(?:Users|Documents)\\\\|[A-Za-z]:\\\\[^\x00-\x7F]")
_BV = re.compile(r"BV[0-9A-Za-z]{10}")
_UID = re.compile(r"(?<!\d)UID[=:]\s*(\d{6,12})(?!\d)")


# ---------------------------------------------------------------- 纯函数

def test_mmss():
    assert C.mmss(0) == "00:00"
    assert C.mmss(59) == "00:59"
    assert C.mmss(60) == "01:00"
    assert C.mmss(3725) == "62:05"
    assert C.mmss(2253) == "37:33"


def test_wbi_signed_is_stable_and_deterministic():
    url = C.wbi_signed("/x/player/wbi/v2", {"aid": 1, "cid": 2, "wts": 1700000000}, "k" * 32)
    assert url.startswith("https://api.bilibili.com/x/player/wbi/v2?")
    assert "w_rid=" in url
    rid = url.split("w_rid=")[1].split("&")[0]
    assert len(rid) == 32
    again = C.wbi_signed(
        "/x/player/wbi/v2", {"aid": 1, "cid": 2, "wts": 1700000000}, "k" * 32)
    assert rid == again.split("w_rid=")[1].split("&")[0]


def test_wbi_signed_sorts_params():
    """参数顺序不同、内容相同 → 签名必须一致。"""
    assert C.wbi_signed("/x", {"b": 2, "a": 1}, "k" * 32) == \
        C.wbi_signed("/x", {"a": 1, "b": 2}, "k" * 32)


def test_cookie_header_missing_file_returns_empty():
    old = C.COOKIE_PATH
    try:
        C.COOKIE_PATH = os.path.join(tempfile.gettempdir(), "definitely-not-here.json")
        assert C.cookie_header() == ""
    finally:
        C.COOKIE_PATH = old


def test_cookie_header_reads_json():
    old = C.COOKIE_PATH
    fd, p = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write('{"SESSDATA": "a", "bili_jct": "b"}')
        C.COOKIE_PATH = p
        assert C.cookie_header() == "SESSDATA=a; bili_jct=b"
    finally:
        C.COOKIE_PATH = old
        os.unlink(p)


def test_workdir_defaults_to_cwd_subdir():
    """默认工作目录必须是 <cwd>/work —— 不来自任何硬编码路径。"""
    env = os.environ.get("BILI_NOTES_WORKDIR")
    if env:
        assert C.WORKDIR == env, C.WORKDIR
    else:
        assert C.WORKDIR == os.path.join(os.getcwd(), "work"), C.WORKDIR


def test_find_ffmpeg_respects_env():
    old = os.environ.get("BILI_NOTES_FFMPEG")
    try:
        os.environ["BILI_NOTES_FFMPEG"] = "/custom/ffmpeg"
        assert C.find_ffmpeg() == "/custom/ffmpeg"
    finally:
        if old is None:
            os.environ.pop("BILI_NOTES_FFMPEG", None)
        else:
            os.environ["BILI_NOTES_FFMPEG"] = old


# ---------------------------------------------------------------- 仓库卫生

def _iter_sources(exts):
    for dp, dns, fns in os.walk(REPO):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "work", "node_modules")]
        for fn in sorted(fns):
            if fn.endswith(exts):
                yield os.path.join(dp, fn)


def test_repo_has_no_absolute_paths():
    """源码与文档里不许出现本机绝对路径。"""
    bad = []
    for p in _iter_sources((".py", ".md", ".toml", ".example", ".gitignore")):
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if _ABS_PATH.search(line):
                    bad.append("%s:%d" % (os.path.relpath(p, REPO), i))
    assert not bad, "发现硬编码绝对路径: %s" % bad


def test_no_real_bv_id():
    """只允许占位 BV（后 10 位含 x 或全同字符），不许出现可访问的真实 BV 号。"""
    bad = []
    for p in _iter_sources((".py", ".md")):
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for m in _BV.finditer(line):
                    tail = m.group(0)[2:]
                    if len(set(tail)) == 1 or "x" in tail.lower():
                        continue
                    bad.append("%s:%d %s" % (os.path.relpath(p, REPO), i, m.group(0)))
    assert not bad, "发现疑似真实 BV 号: %s" % bad


def test_no_hardcoded_uid():
    """不许出现「UID 等于一串具体数字」的写法（易被当成真实账号）。"""
    bad = []
    for p in _iter_sources((".py", ".md")):
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if _UID.search(line):
                    bad.append("%s:%d" % (os.path.relpath(p, REPO), i))
    assert not bad, "发现疑似真实 UID: %s" % bad


def test_gitignore_covers_credentials():
    """凭据文件的忽略规则必须存在，否则一次 git add . 就泄露。"""
    with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as f:
        t = f.read()
    for key in ("cookies", ".env", "__pycache__"):
        assert key in t, "`.gitignore` 缺少 %s 相关规则" % key
    assert ("*.pyc" in t or "*.py[cod]" in t), "`.gitignore` 缺少 .pyc 相关规则"


# ---------------------------------------------------------------- 入口

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   " + name)
            except AssertionError as e:
                fails += 1
                print("FAIL %s  %s" % (name, e))
    print("\n失败 %d 项" % fails)
    sys.exit(1 if fails else 0)
