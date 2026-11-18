"""给课程笔记的每个题型 / 每道独立例题末尾插入「我的批注」折叠框。

用法:
    python add_boxes.py --dir "<笔记目录>"            # 预演，只报数量
    python add_boxes.py --dir "<笔记目录>" --apply     # 真写

规则:
- `## 题型 …` 末尾 1 个框
- `### 例 …` 末尾 1 个框（若下一节是"例 1 续/第 N 步"这类延续，不拆开）
- 已有 `[!note]- ✍️ 批注` 的块跳过，可反复跑

框体格式固定，方便 collect_notes.py 汇总：
    > [!note]- ✍️ 批注｜<小节标题>
    > - 卡在哪：
    > - 错因：
    > - 二刷：
"""
import argparse
import os
import re

MARK = "[!note]- ✍️ 批注"
SKIP_TITLES = ("本讲定位", "本讲小结", "时间轴", "关联", "书页原件",
               "一张总表", "记忆与易错", "笔记规范")


def split_blocks(lines):
    """切成 [(kind, title, start, end)]，end 为块内最后一个非空行下标（含）。"""
    heads = []
    for i, ln in enumerate(lines):
        m2 = re.match(r"^## (.+?)\s*$", ln)
        m3 = re.match(r"^### (.+?)\s*$", ln)
        if m2:
            heads.append(("##", m2.group(1), i))
        elif m3:
            heads.append(("###", m3.group(1), i))
    blocks = []
    for idx, (kind, title, start) in enumerate(heads):
        stop = heads[idx + 1][2] if idx + 1 < len(heads) else len(lines)
        end = start
        for j in range(stop - 1, start - 1, -1):
            if lines[j].strip():
                end = j
                break
        blocks.append([kind, title, start, end])
    return blocks


def want_box(kind, title, next_title, mode="course", parent_h2=""):
    """mode=course：题型级 + 例题级；mode=exercise：习题册每道题一级。"""
    if mode == "exercise":
        # 习题册：只有「## 收录题目」下面的每个 ### 才是题
        return kind == "###" and parent_h2.startswith("收录题目")

    if kind == "##":
        if not title.startswith("题型"):
            return False
    elif kind == "###":
        if "例" not in title[:6]:
            return False
        # "例 1 续：…"、"第二步：…" 这类是上一例的延续，不在中间打卡
        if next_title:
            stem = re.split(r"[：:（(]", title)[0].strip()
            if next_title.startswith(stem) and next_title != title:
                return False
    else:
        return False
    if re.split(r"[：:（(]", title)[0].strip() in SKIP_TITLES:
        return False
    return True


def box(title):
    return [
        "",
        "> " + MARK + "｜" + title,
        "> - 卡在哪：",
        "> - 错因：",
        "> - 二刷：",
        "",
    ]


def process(path, apply, mode="course"):
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    blocks = split_blocks(lines)
    plan = []
    cur_h2 = ""
    for i, (kind, title, start, end) in enumerate(blocks):
        if kind == "##":
            cur_h2 = title
        nxt = blocks[i + 1][1] if i + 1 < len(blocks) else None
        if not want_box(kind, title, nxt, mode, cur_h2):
            continue
        body = "\n".join(lines[start:end + 1])
        if MARK in body:
            continue
        # 插在块最后一行之后
        plan.append((end, title))
    if not plan:
        return 0, len(blocks)
    out = list(lines)
    for end, title in sorted(plan, reverse=True):   # 从后往前插，避免下标错位
        out[end + 1:end + 1] = box(title)
    if apply:
        open(path, "w", encoding="utf-8").write("\n".join(out))
    return len(plan), len(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--mode", choices=["course", "exercise"], default="course",
                    help="course=题型/例题；exercise=习题册每道题")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    targets = a.files or [f for f in sorted(os.listdir(a.dir))
                          if f.endswith(".md") and not f.startswith(("00", "我的批注"))]
    total = 0
    for f in targets:
        p = os.path.join(a.dir, f)
        if not os.path.exists(p):
            continue
        n, nb = process(p, a.apply, a.mode)
        print("%-46s 框 %2d / 块 %2d %s" % (f, n, nb, "已写入" if a.apply and n else ""))
        total += n
    print("\n合计 %d 个框 %s" % (total, "" if a.apply else "（预演，未写盘；加 --apply 生效）"))


if __name__ == "__main__":
    main()