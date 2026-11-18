"""跨篇汇总：把所有批注按「🟡 未解决 / ✅ 已解决」两区列出来。

用法:
    python collect_notes.py --dir "<笔记目录>"           # 只列写过的
    python collect_notes.py --dir "<笔记目录>" --all      # 连空框也列

产物: <dir>\\我的批注汇总.md

和 boards.py 用同一套解析（boards.parse），所以单篇看板与总汇总永远一致：
- 未解决 / 已解决 的判定 = 批注框里的「已解决」复选框
- 摘要 = 框内第一行正文

给谁用：
- 你自己复习：一眼看到还欠哪些题
- 给我（AI）优化笔记：先读这一份，用户写「卡在哪」的地方就是该补的地方
"""
import argparse
import datetime
import os

import boards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--all", action="store_true", help="连没动笔的框也列出来")
    ap.add_argument("--out", default=None)
    ap.add_argument("--subject", default="",
                    help="写进 frontmatter 的学科名；留空则不写该字段")
    a = ap.parse_args()

    targets = []
    for root, dirs, fs in os.walk(a.dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))]
        for f in sorted(fs):
            if f.endswith(".md") and not f.startswith(("00", "我的批注汇总", "AGENTS")):
                targets.append(os.path.relpath(os.path.join(root, f), a.dir))
    targets.sort()

    total = done_n = written = 0
    todo_sec, done_sec = [], []
    for rel in targets:
        items, _ = boards.parse(os.path.join(a.dir, rel))
        if not items:
            continue
        label = rel.replace("\\", " / ")[:-3]
        todo_rows, done_rows = [], []
        for x in items:
            total += 1
            has = bool(x["text"])
            written += 1 if has else 0
            if x["done"]:
                done_n += 1
            if not has and not a.all:
                continue
            row = (x["title"], has, boards.brief(x["text"][0], 60) if has else "")
            (done_rows if x["done"] else todo_rows).append(row)
        if todo_rows:
            todo_sec.append((label, todo_rows))
        if done_rows:
            done_sec.append((label, done_rows))

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    open_n = total - done_n
    lines = [
        "---",
        "类型: 复习清单",
        "状态: 自动生成",
        "学科: %s" % a.subject,
        "创建日期: %s" % now[:10],
        "---",
        "",
        "# 我的批注汇总",
        "",
        "> 由 `collect_notes.py` 生成（%s）" % now,
        "> 共 %d 个批注：**未解决 %d** ｜ 已解决 %d ｜ 已动笔 %d" % (total, open_n, done_n, written),
        "> 这一页是自动生成的，别手改；勾选框请回笔记里点，再跑一次脚本。",
        "",
    ]

    def render(head, sections, empty_hint):
        lines.append("## %s" % head)
        lines.append("")
        if not sections:
            lines.append("> %s" % empty_hint)
            lines.append("")
            return
        for label, rows in sections:
            lines.append("### %s" % label)
            lines.append("")
            for title, has, text in rows:
                lines.append("- **%s**%s" % (title, ("　—— " + text) if has else "　（还没写）"))
            lines.append("")

    render("🟡 未解决（%d）" % open_n, todo_sec, "全部勾完了。")
    render("✅ 已解决（%d）" % done_n, done_sec, "还没有勾掉的条目。")

    out = a.out or os.path.join(a.dir, "我的批注汇总.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("批注 %d 个（未解决 %d / 已解决 %d，已动笔 %d）-> %s"
          % (total, open_n, done_n, written, out))


if __name__ == "__main__":
    main()