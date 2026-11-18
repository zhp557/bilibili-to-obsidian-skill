"""把批注框压平：删掉「卡在哪 / 错因 / 二刷」三行，内容转自由文本，改用原生黄色 callout。

用法:
    python flatten_boxes.py --dir "<笔记目录>"           # 预演
    python flatten_boxes.py --dir "<笔记目录>" --apply    # 写入

改写前 -> 后：
    > [!便签] ✍️ 批注｜示例小节 3.2　某个公式的推导
    > - [ ] 已解决
    > - 卡在哪：
    > - 错因：这里把符号写反了
    > - 二刷：

    > [!warning] 🖊️ 批注｜示例小节 3.2　某个公式的推导
    > - [ ] 已解决
    >
    > 这里把符号写反了

要点：
- 槽位文字**一字不改**，只是从「行内字段」变成「自由正文」；空槽位直接丢掉
- [!warning] 是 Obsidian 原生黄色 callout，不依赖任何 CSS 片段
- 幂等：已经是新格式的块原样跳过
"""
import argparse
import os
import re

HEAD_OLD = re.compile(r"^>\s*\[!(?:便签|note)\]-?\s*(?:✍️|🖊️)\s*批注｜(.+?)\s*$")
HEAD_NEW = re.compile(r"^>\s*\[!(?:warning|success)\]\s*🖊️\s*批注｜(.+?)\s*$")
CHECK = re.compile(r"^>\s*-\s*\[([ xX])\]\s*已解决\s*$")
SLOT = re.compile(r"^>\s*-\s*[^：\[\]]+：\s*(.*)$")


def flatten(path, apply):
    lines = open(path, encoding="utf-8").read().split("\n")
    out = []
    i = 0
    changed = 0
    while i < len(lines):
        ln = lines[i]
        m = HEAD_OLD.match(ln) or HEAD_NEW.match(ln)
        if not m:
            out.append(ln)
            i += 1
            continue
        title = m.group(1)
        i += 1
        # 收集整块 callout 内容
        block = []
        while i < len(lines) and lines[i].startswith(">"):
            block.append(lines[i])
            i += 1

        checked = False
        body = []
        for b in block:
            c = CHECK.match(b)
            if c:
                checked = c.group(1).strip() != ""
                continue
            s = SLOT.match(b)
            if s:
                txt = s.group(1).strip()
                if txt:
                    body.append(txt)
                continue
            t = re.sub(r"^>\s?", "", b).rstrip()
            if t:
                body.append(t)

        new = ["> " + ("[!success]" if checked else "[!warning]") + " 🖊️ 批注｜" + title,
               "> - [%s] 已解决" % ("x" if checked else " "),
               ">"]
        for t in body:
            new.append("> " + t)
        out.extend(new)
        changed += 1
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
            n = flatten(p, a.apply)
            if n:
                print("%-46s %2d 个 batn %s" % (os.path.relpath(p, a.dir), n,
                                                "已写入" if a.apply else ""))
                total += n
    print("\n合计 %d 个框%s" % (total, "" if a.apply else "（预演，加 --apply 生效）"))


if __name__ == "__main__":
    main()