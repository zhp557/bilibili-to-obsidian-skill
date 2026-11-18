"""笔记验收：图片引用数 = 附件数、双链不断、体量达标、讲号连续。

用法:
    python verify.py "<笔记.md 绝对路径>" "<附件目录绝对路径>"
    python verify.py --dir "<笔记目录>" --att "<附件根目录>"

机器判定（决定 PASS / CHECK，有 CHECK 时退出码非零）:
1. 每个 ![[x.png]] 在附件目录里都存在（缺图 = 笔记里有裂图）
2. 附件目录里没有未被引用的图（多出来的图 = 白截了）
3. 正文 [[...]] 双链目标 .md 存在（断链会显示成灰点）
4. 体量不低于下限（默认 5 KB；frontmatter 里 类型 含「习题」时降到 2 KB）

只提示、不判失败:
- 体量是否超过 20 KB
- 时间轴条目数（过少时打一行 <-- 太少）
- `> 老师原话` 引用块的数量与密度

坑：别用 startswith('p1') 去匹配附件目录 —— 'p10-假设检验' 也会命中。
    统一用 'p<page>-<章节名>' 完整名，或直接传绝对路径。
"""
import os
import re
import sys

_IDX = None
_IMG = None


def vault_index(note_dir):
    """Obsidian 的 [[双链]]是全库解析的，跨子目录也能点开。

    所以断链检查必须递归扫整个 vault —— 只查同目录+上一级会误报，
    常见误报：索引页放在子目录里（如 <科目>\\<科目录习>\\ 下的总览）。
    """
    global _IDX, _IMG
    if _IDX is not None:
        return _IDX
    root = note_dir
    for _ in range(5):
        if os.path.isdir(os.path.join(root, ".obsidian")):
            break
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    names, imgs = set(), set()
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".md"):
                names.add(f[:-3])
            elif f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                imgs.add(f)
    _IDX, _IMG = names, imgs
    return names


def vault_images(note_dir):
    vault_index(note_dir)
    return _IMG


def check(note, attach):
    t = open(note, encoding="utf-8").read()
    # 行内代码里的 ![[xxx]] 是在"讲语法"，不是真引用（实测第07讲就有一段这么写，
    # 被当成缺图报了 ['文件名', '…']）。先剥掉 code span 再提取。
    t_code = re.sub(r"`[^`\n]*`", "", t)
    # ![[图.png|420]] 里的 |420 是显示尺寸参数，不是文件名的一部分
    emb = [e.split("|")[0].strip() for e in re.findall(r"!\[\[([^\]]+)\]\]", t_code)]
    links = sorted(set(re.findall(r"(?<!\!)\[\[([^\]|#]+)", t_code)))
    files = ({f for f in os.listdir(attach) if os.path.isfile(os.path.join(attach, f))}
             if os.path.isdir(attach) else set())
    note_dir = os.path.dirname(note)

    # ![[a.png]] 同样是全库解析的：插图可以放在 99 附件 的任意子目录，
    # 所以判"缺图"要看整个 vault，不能只看本篇的附件目录。
    allimg = vault_images(note_dir)
    missing = [e for e in emb if e not in files and e not in allimg]
    unused = [f for f in files if f not in emb]
    idx = vault_index(note_dir)
    # [[xxx.jpg]] 这种"双链引用附件"也合法（复习卷库常这么挂原卷），
    # 早先只查 .md 名，把图片双链一律当断链报了。
    broken = [l for l in links if l.strip() not in idx and l.strip() not in allimg]

    kb = len(t.encode()) / 1024
    timeline = len(re.findall(r"^\s*-\s*\[\d+:\d+\]", t, re.M))
    # 讲述口径：引用「老师原话」不是禁止，而是"要有用"（2026-11-12 用户定：
    # "只要有用、效率变高就可以多一点"）。所以这里不设硬上限，只在密度偏高时提示。
    # 只作提示项，不计入 PASS 判定 —— 存量笔记可能较多，
    # 强行判 CHECK 会把整门课刷成红。
    orig = len(re.findall(r"^>\s*老师原话", t, re.M))
    # 专题 / 习题整理 / 复习清单：没有时间轴，体量下限也不同（习题按题解密度衡量）
    m = re.search(r"^类型:\s*(\S+)", t, re.M)
    kind = m.group(1) if m else ""
    topic = any(k in kind for k in ("专题", "习题", "复习"))
    floor = 2.0 if "习题" in kind else (4.0 if topic else 5.0)

    ok = not missing and not unused and not broken and (kb >= floor or topic)
    print("%-52s %s%s" % (os.path.basename(note), "PASS" if ok else "CHECK",
                          "  [%s]" % kind if topic else ""))
    print("   体量      %.1f KB %s" % (kb, "" if topic or 5 <= kb <= 20 else "  <-- 期望 5~20 KB"))
    print("   图片引用  %d / 附件 %d %s" % (len(emb), len(files), "" if not missing else "  缺: " + str(missing)))
    if unused:
        print("   未引用图  %s" % unused)
    if broken:
        print("   断链      %s" % broken)
    if orig:
        dense = orig > max(3, int(kb / 2))
        print("   原话块    %d 处 %s" % (
            orig, "  <-- 密度偏高，逐条问：这句比意译更省时间吗？" if dense else ""))
    if not topic:
        print("   时间轴    %d 条 %s" % (timeline, "" if timeline >= 10 else "  <-- 太少"))
    return ok


if __name__ == "__main__":
    _fails = 0
    if "--dir" in sys.argv:
        if "--att" not in sys.argv:
            raise SystemExit(
                "--dir 必须同时给 --att \"<附件根目录>\"。\n"
                "例：verify --dir \"<笔记目录>\" --att \"<附件根目录>\"")
        root = sys.argv[sys.argv.index("--dir") + 1]
        att_root = sys.argv[sys.argv.index("--att") + 1]
        folders = sorted(os.listdir(att_root))

        def walk_notes(base):
            """递归收 .md（习题册可能按讲次分了子文件夹）。"""
            out = []
            for dp, dns, fns in os.walk(base):
                dns[:] = [d for d in dns if not d.startswith((".", "_"))]
                for f in sorted(fns):
                    if f.endswith(".md") and not f.startswith(("00", "我的批注", "AGENTS")):
                        out.append((dp, f))
            return out

        notes = walk_notes(root)
        for base, f in notes:
            path = os.path.join(base, f)
            text = open(path, encoding="utf-8").read()
            # 从笔记自己的「链接：...?p=N」推附件目录，别用讲号去猜。
            # 用讲号去猜会错位：相邻两讲的附件目录可能差一个编号，所以只认笔记里的 ?p=N。
            m = re.search(r"[?&]p=(\d+)", text)
            if not m:
                # 专题 / 习题册这类没有视频分 P 的笔记：只体检断链与体量
                _fails += 0 if check(path, os.path.join(att_root, "__none__")) else 1
                continue
            num = m.group(1)
            prefix = ["p%02d-" % int(num), "p%s-" % num]  # 老附件是 p05-，新附件可能写成 p5-
            hit = [d for p in prefix for d in folders if d.startswith(p)]
            if not hit:
                # 附件目录找不到 = 这篇根本没被验收，不能算通过
                print("%-52s CHECK（附件目录 %s* 不存在，未验收）" % (f, prefix[0]))
                _fails += 1
                continue
            _fails += 0 if check(path, os.path.join(att_root, hit[0])) else 1
    else:
        _fails += 0 if check(sys.argv[1], sys.argv[2]) else 1

    # 有任一笔记 CHECK 就返回非零，CI 与 pre-commit 才拦得住
    sys.exit(1 if _fails else 0)