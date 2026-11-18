"""为每篇笔记生成「批注看板」：🟡 未解决 / ✅ 已解决 两栏，条目可点回题目。

用法:
    python boards.py --dir "<笔记目录>"            # 预演
    python boards.py --dir "<笔记目录>" --apply     # 写入

它做三件事（幂等，可反复跑）：
1. 把已勾选的批注框同步成绿色 callout `[!success]`（复用 flatten_boxes 的逻辑）
2. 重建每篇末尾的 `<!-- BOARD-START -->…<!-- BOARD-END -->` 区块
3. 重建总汇总 `我的批注汇总.md`

看板长这样：
    ## 批注看板

    > [!warning] 🟡 未解决（5）
    > - [[#示例小节 3.2|示例小节 3.2]] —— 这里把公式抄错了一处符号

    > [!success] ✅ 已解决（2）
    > - [[#示例小节 4.1|示例小节 4.1]]

锚点用的是批注上方最近的 `##` / `###` 标题，所以点击会跳到那道题本身
（callout 自己的标题不能被 `[[#...]]` 链接）。
"""
import argparse
import os
import re

import flatten_boxes

HEAD = re.compile(r"^>\s*\[!(warning|success)\]\s*🖊️\s*批注｜(.+?)\s*$")
CHECK = re.compile(r"^>\s*-\s*\[([ xX])\]\s*已解决\s*$")
BOARD_START = "<!-- BOARD-START 由 boards.py 生成，手改会被覆盖 -->"
BOARD_END = "<!-- BOARD-END -->"
BOARD_TITLE = "## 批注看板"


def short(title, n=14):
    """把标题压成短名：全角空格 / 冒号之前的部分。

    标题里可能含 $...$ 公式，直接按字符截断会切出半个 $（渲染时公式坏掉），
    所以先去掉美元符再截断——别名只是纯文本，不需要公式语法。
    """
    s = re.split(r"[：:｜|　]", title)[0].strip()
    s = s.replace("$", "")
    if len(s) > n:
        # 超长时优先去掉末尾的页码括号（"习题4 · 3(1)（P88）" → "习题4 · 3(1)"）
        t = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", s)
        if t and len(t) <= n:
            return t
        return s[:n] + "…"
    return s


def brief(text, n=40):
    """摘要里别把 $…$ 公式截断（半截公式在 Obsidian 里渲染不出来），先换掉再截。

    批注正文里可能夹着内嵌图片 / wikilink（用户直接把截图贴在批注里），
    原样搬进看板会让 veriy 把它们当成"图片引用"、截断后又变成断链，
    所以整条剥掉，只留纯文字。
    """
    t = re.sub(r"\$[^$]{1,200}\$", "…", text)
    t = re.sub(r"!\[\[[^\]]*\]\]", "", t)      # ![[xxx.png]] 内嵌图片
    t = re.sub(r"\[\[[^\]]*\]\]", "", t)       # [[笔记]] 双链
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)  # ![alt](url) 普通图片
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n] + "…"


def parse(path):
    """返回 (批注列表, 是否已存在看板区块)。批注 = dict(title, anchor, done, text)。"""
    items = []
    cur_h2 = cur_h3 = ""
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m2 = re.match(r"^## (.+?)\s*$", line)
        m3 = re.match(r"^### (.+?)\s*$", line)
        if m2:
            cur_h2, cur_h3, cur = m2.group(1), "", None
            continue
        if m3:
            cur_h3, cur = m3.group(1), None
            continue
        h = HEAD.match(line)
        if h:
            cur = {"title": h.group(2), "done": h.group(1) == "success",
                   "anchor": cur_h3 or cur_h2, "text": []}
            items.append(cur)
            continue
        if cur is None:
            continue
        if not line.startswith(">"):
            cur = None
            continue
        c = CHECK.match(line)
        if c:
            cur["done"] = c.group(1).strip() != ""
            continue
        t = re.sub(r"^>\s?", "", line).strip()
        if t:
            cur["text"].append(t)
    return items, (BOARD_START in open(path, encoding="utf-8").read())


def render(items):
    todo = [x for x in items if not x["done"]]
    done = [x for x in items if x["done"]]
    lines = [BOARD_START, "", BOARD_TITLE, ""]

    def one(icon, tone, rows, empty):
        lines.append("> [!%s] %s（%d）" % (tone, icon, len(rows)))
        if not rows:
            lines.append("> %s" % empty)
        for x in rows:
            b = ""
            if x["text"]:
                b = " —— " + brief(x["text"][0])
            lines.append("> - [[#%s|%s]]%s" % (x["anchor"], short(x["title"]), b))
        lines.append("")

    one("🟡 未解决", "warning", todo, "全部勾完了。")
    one("✅ 已解决", "success", done, "还没有勾掉的条目。")
    lines.append(BOARD_END)
    return "\n".join(lines)


def splice(path, block, apply):
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    if BOARD_START in text:
        start = next(i for i, l in enumerate(lines) if l.strip() == BOARD_START)
        end = next(i for i, l in enumerate(lines) if l.strip() == BOARD_END)
        new = lines[:start] + block.split("\n") + lines[end + 1:]
    else:
        # 插在「## 关联」之前，没有就接在文末
        idx = next((i for i, l in enumerate(lines) if l.strip() == "## 关联"), None)
        if idx is None:
            new = lines + ["", block, ""]
        else:
            new = lines[:idx] + [block, ""] + lines[idx:]
    if apply:
        open(path, "w", encoding="utf-8").write("\n".join(new))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    files = []
    for root, dirs, fs in os.walk(a.dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))]
        for f in sorted(fs):
            if f.endswith(".md") and not f.startswith(("00", "我的批注汇总", "AGENTS")):
                files.append(os.path.join(root, f))

    grand = []
    for p in files:
        # 1) 先把勾选状态同步成颜色
        changed = flatten_boxes.flatten(p, a.apply)
        items, _ = parse(p)
        if not items:
            if changed:
                print("%-46s 只同步了颜色（%d）" % (os.path.relpath(p, a.dir), changed))
            continue
        block = render(items)
        splice(p, block, a.apply)
        todo = sum(1 for x in items if not x["done"])
        print("%-46s 未解决 %2d / 已解决 %2d %s"
              % (os.path.relpath(p, a.dir), todo, len(items) - todo,
                 "已写入" if a.apply else ""))
        grand.extend(items)

    n = len(grand)
    d = sum(1 for x in grand if x["done"])
    print("\n全部：%d 个批注，未解决 %d，已解决 %d %s"
          % (n, n - d, d, "" if a.apply else "（预演，加 --apply 生效）"))


if __name__ == "__main__":
    main()