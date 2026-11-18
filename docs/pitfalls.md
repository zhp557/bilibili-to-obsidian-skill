# 实测坑列表

这些都是跑真课踩出来的，按严重程度排。有些看起来像小事，但每一条都曾经让一整轮工作白做。

## 1. 不要一上来就跑本地 ASR

先 `subs scan`，有字幕几秒就完；没字幕也先试云端（`http-asr`，带标点），最后一个才轮到本机 whisper。**三级优先级别跳**——跳过一步的代价是 CPU 跑 10 分钟。

## 2. 匿名请求拿到的清晰度更低

同一个分 P：匿名只给 `852x480`（id=32），带登录 cookie 会给 `1280x720`（id=64）。`capture.py` 取 H.264 里的最高档，所以**板书想看清，先确认 cookie 有效**。这条直接决定后面截图能不能读。

## 3. AI 字幕会稳定地把专业词和数值听错

实测三处：`加奇减偶` → 「夹击减偶」；`5/8` → 「5%」；`0.25%` → 「0.54%」。

规矩：**结构、话术、思路按字幕写；具体数值一律看截图，读不准就写「以截图为准」**。不要拿字幕里的数字直接当答案。

## 4. `python -c` 里带中文路径会崩

报错形如 `can't open file 'D:\<乱码>'`。要么把代码写成 `.py` 文件再执行，要么给 shell 传 `workdir` 参数，别在命令行内联中文路径。

## 5. PowerShell 输出中文会乱码

每个会话先设：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
```

否则你会基于乱码做判断——这比报错更糟，因为它是静默的。

## 6. 验收脚本别用前缀匹配附件目录

`startswith('p1')` 会同时命中 `p10-假设检验`，导致「缺图」误报。用完整 `p<N>-` 名前缀或直接传绝对路径。

## 7. 别信第三方插件自带的 doctor

`spawnSync` 抓子进程输出在受限沙箱里会失败（命名管道被禁），误报「未找到 Python / ffmpeg」。用 `Test-Path` + 实际执行验证。

## 8. 别用 yt-dlp 下音频

个别分 P 报 `No video formats found!`。直接读 `playurl` 的 `dash.audio` 更稳，也是本仓库的做法。

## 9. PyAV 会坏

`av 19` 与 faster-whisper 的 `metadata_errors` 不兼容，降级又缺预编译包。`asr.py` 完全绕开 PyAV：ffmpeg 转 16k 单声道 wav → `wave` 读成 numpy 喂模型。

## 10. 附件目录编号补零到两位

`p05`…`p10` 与 `p4-` 两种风格并存时，排序乱、前缀匹配失效。统一 `p<两位>-`（`p04` / `p10`）。

## 11. 断链检查必须递归全库

`[[00 某科习题总览]]` 这类索引页常在子目录里，只查同目录会误报断链。`verify.py` 从笔记上溯到含 `.obsidian` 的 vault 根，再 walk 所有 `.md` 的 stem。

## 12. 相邻讲的反向链接容易漏

补完第 03 讲，别忘了把第 04 讲里那句纯文字「上一部分：…」改成 `[[第03讲 …]]`。写完一批用 `bili-notes verify --dir "<笔记目录>" --att "<附件根目录>"` 全量过一遍，比逐篇看快。
注意 `--att` 是必填的，只给 `--dir` 会直接报错。

## 13. 不要用脚本改 Obsidian 的 `appearance.json`

实测：往 `.obsidian/appearance.json` 写 `enabledCssSnippets`，Obsidian 会在几分钟后**整个重写**成 `{"theme": "moonstone"}` —— 加的字段没了，**连原来的 `cssTheme` 和 `accentColor` 一起被抹掉**。

后果：自定义 callout 的 CSS 片段从来没加载过，主题还可能掉回默认。结论：

- 想加样式，**只用 Obsidian 原生 callout**（`warning` 黄、`success` 绿、`tip` 青、`example` 紫…）
- CSS 片段只能让用户在 设置 → 外观 → CSS 片段 手动开
- 万一改了 `appearance.json`，事后提醒用户回设置里确认主题与强调色

## 14. 附件名要带分 P 前缀，且落盘前查重

附件目录是全库共享的，`01-本讲标题.png` 这种名字在别的讲里很可能已经存在，`Copy-Item` 会**静默覆盖**别人的图。落盘前先查：

```powershell
Get-ChildItem "<附件根>" -Recurse -File -Filter "*<你的文件名>*" | Select-Object FullName
```

稳的做法是整批文件名统一带 `p<两位>-` 前缀：`p04-02-题型1-例1题目.png`。

## 15. 「时间轴 0 条」是提示，不是失败

`verify.py` 的通过判据里**不包含时间轴**，它只用于打印 `<-- 太少`。别为了让这行告警消失去硬塞 10 条假时间轴——那是把验收做成了表演。

## 16. 字幕零命中的小节，在索引里写「待补」

课没讲到、或 AI 整段没识别出来的小节，不要在笔记里编内容。在章索引表里写一行 `| 第N节 | 课程未讲 | 待补 |`，注明「课程没讲，只能照课本另写」。

## 17. 合集不是分 P

合集里某一集的 `x/web-interface/view` 返回的 `pages` 只有 1 条，`probe` 会报 `PAGES: 1`——看着像「这视频只有一集」，实际是整个合集你只看到了一集。照这个结果往下做，会以为整门课只有 40 分钟。

全集在同一接口的 `ugc_season.sections[].episodes[]` 里，读它拿 `bvid` / `title` / `duration`。

## 18. `subs.py` 一次只吃一个 BV

入口是 `cmd, bvid = sys.argv[1], sys.argv[2]`，传多个 BV 会直接崩。多集只能逐个调，或者用 `bili-notes` 统一入口循环。
