"""把旧的折叠批注框（[!note]-）升级成黄纸便签（[!便签]）+ 已解决复选框。

用法:
    python convert_boxes.py --dir "<笔记目录>"          # 预演
    python convert_boxes.py --dir "<笔记目录>" --apply  # 真写

前后对照：
    旧：> [!note]- ✍️ 批注｜P30 填空(2)
        > - 卡在哪：
    新：> [!便签] ✍️ 批注｜P30 填空(2)
        > - [ ] 已解决
        > - 卡在哪：

已经升级过的块会跳过，可反复跑。
"""
import argparse
import os
import re

OLD_HEAD = re.compile(r"^>\s*\[!note\]-\s*✍️\s*批注｜(.+?)\s*$")
NEW_HEAD = re.compile(r"^>\s*\[!便签\]\s*✍️\s*批注｜(.+?)\s*$")


def convert(path, apply):
    lines = open(path, encoding="utf-8").read().split("\n")
    out, changed = [], 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = OLD_HEAD.match(ln)
        if m:
            title = m.group(1)
            out.append("> [!便签] ✍️ 批注｜%s" % title)
            # 看下一行是不是已经有复选框（防止重复升级）
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not re.match(r"^>\s*-\s*\[[ xX]\]\s*已解决", nxt):
                out.append("> - [ ] 已解决")
            changed += 1
            i += 1
            continue
        out.append(ln)
        i += 1
    if changed and apply:
        open(path, "w", encoding="utf-8").write("\n".join(out))
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    total = 0
    for root, dirs, files in os.walk(a.dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))]
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            p = os.path.join(root, f)
            n = convert(p, a.apply)
            if n:
                rel = os.path.relpath(p, a.dir)
                print("%-46s 升级 %2d 个 %s" % (rel, n, "已写入" if a.apply else ""))
                total += n
    print("\n合计 %d 个%s" % (total, "" if a.apply else "（预演，加 --apply 生效）"))


if __name__ == "__main__":
    main()