"""统一入口：把散落的脚本收成一个命令。

    python -m bili_notes.cli probe   BV1xxxxxxxxx
    python -m bili_notes.cli subs    scan BV1xxxxxxxxx
    python -m bili_notes.cli subs    fetch BV1xxxxxxxxx 1,2,4
    python -m bili_notes.cli capture BV1xxxxxxxxx 4 0:1700:120
    python -m bili_notes.cli contact p4
    python -m bili_notes.cli verify  "<笔记.md>" "<附件目录>"

装成包之后也可以直接 `bili-notes subs scan BV...`。

每个子命令的参数和对应脚本完全一致（`bili-notes <cmd> --help` 看到的是脚本自己的说明），
所以这里只做转发，不改参数语义。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRAS = os.path.join(HERE, "extras")

# 子命令 → 脚本文件
CORE = {
    "probe": "probe.py",
    "subs": "subs.py",
    "capture": "capture.py",
    "contact": "contact.py",
    "shots": "shots.py",
    "verify": "verify.py",
    "extract": "extract.py",
    "asr": "asr.py",
    "http-asr": "http_asr.py",
}

# Obsidian 批注体系（可选，需要笔记里已有批注框）
BOXES = {
    "boxes": "add_boxes.py",
    "flatten-boxes": "flatten_boxes.py",
    "convert-boxes": "convert_boxes.py",
    "boards": "boards.py",
    "collect-notes": "collect_notes.py",
}

USAGE = """bili-notes —— B 站课程视频 → 结构化笔记

用法: bili-notes <命令> [参数...]

核心链路:
  probe      LIST       盘点多集：分 P、时长、最高清晰度
  subs       scan|fetch B 站 AI 字幕（首选，几秒一集）
  http-asr   BV PAGE    云端 ASR（没字幕时首选，需要 ASR key）
  asr        BV PAGE... 本地 whisper（断网兜底，需要 faster-whisper）
  capture    BV PAGE    按秒截帧，板书截图
  contact    pN         帧拼成联系表，先看结构再挑帧
  shots      PAGE       帧 → 中文命名附件（贴进 Obsidian）
  verify     笔记 附件  验收：引用数 / 断链 / 体量 / 时间轴

Obsidian 批注（可选）:
  boxes / flatten-boxes / convert-boxes / boards / collect-notes

示例:
  bili-notes probe BV1xxxxxxxxx
  bili-notes subs  scan BV1xxxxxxxxx 1-4
  bili-notes subs  fetch BV1xxxxxxxxx
  bili-notes capture BV1xxxxxxxxx 4 0:2000:120
  bili-notes contact p4
  bili-notes verify "notes/第03讲.md" "attachments/p04-章节名"

环境变量见 .env.example。
"""


def _run(script_path, argv):
    if not os.path.exists(script_path):
        raise SystemExit("脚本不存在: " + script_path)
    cmd = [sys.executable, script_path] + argv
    return subprocess.call(cmd)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    name, rest = argv[0], argv[1:]
    if name in CORE:
        return _run(os.path.join(HERE, CORE[name]), rest)
    if name in BOXES:
        return _run(os.path.join(EXTRAS, BOXES[name]), rest)

    near = [k for k in list(CORE) + list(BOXES) if k.startswith(name[:3])]
    tip = ("  你是不是想用: " + ", ".join(near)) if near else ""
    print("未知命令: %s\n%s\n" % (name, tip))
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
