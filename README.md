# bili-notes

把 B 站课程视频变成**可复习的结构化笔记**：字幕几秒拿完，没字幕就走云端 ASR，板书按时间点截帧贴进笔记，最后跑一遍验收脚本确认没有裂图、断链和漏讲。

写给两类人用：想整理网课笔记的人，和想把这套流程接给 AI agent 的人（`skills/bili-course-notes/SKILL.md` 是一份 agent 手册，可以用 `npx skills` 一条命令装进 Claude Code / Cursor 等支持 skills 规范的 agent）。

## 为什么不是「下载视频再转写」

实测一集 34 分钟的课，三条路线的耗时差一个数量级：

| 路线 | 手段 | 34 分钟一集（单次样本） | 产物质量 |
|---|---|---|---|
| 1 | **B 站 AI 字幕**（`subs`） | **约 3 秒** | `[mm:ss]` 短句，结构可信，数值要查板书 |
| 2 | 云端 ASR · HTTP（`http-asr`） | 约 3 分钟（19 段串行，每段约 9 秒） | `[mm:ss]` 整段，**带标点**，接近逐字稿 |
| 3 | 本地 whisper（`asr`） | 6~10 分钟 | 同音错字更多 |

结论很简单：**先扫字幕，没有字幕再花钱**。`subs` 扫一集只要一次接口调用，绝大多数教学视频都带 `ai-zh` 字幕。

> 这里只有一条云端路线。还有一种「WebSocket 流式」的做法能显示实时进度，但它依赖
> `qwen3-asr-flash-realtime` 这类只在特定服务商提供的模型，不是所有人都能复现，所以没有收进来。
> 需要的话按 `docs/asr-dead-ends.md` 的协议说明自己接。

同一条开场，字幕版会被切成好几片（`各位同学` / `我们接着讲下一个概念` / `第二部分`），而云端 ASR 输出的是一整句带标点的话——内容一样，可读性差一个量级。所以**字幕优先不是因为快，是因为够用**。

## 快速开始

### 装成 agent skill（一条命令）

```bash
npx skills add zhp557/bilibili-to-obsidian-skill --skill bili-course-notes
```

支持任意兼容 skills 规范的 agent（Claude Code、Cursor、OpenCode 等）。
这条命令只装**文档**——skill 里写的都是 `bili-notes` 命令，还得把 CLI 装上：

### 装 CLI

```bash
git clone https://github.com/zhp557/bilibili-to-obsidian-skill.git
cd bilibili-to-obsidian-skill
pip install -e .            # 只需要 Pillow；本地 whisper 是可选依赖
```

截帧需要 **ffmpeg** 在 PATH 里（Windows 可以 `winget install Gyan.FFmpeg`）：

```bash
ffmpeg -version      # 有输出就行
```

两个都装完，`bili-notes probe BV号` 就能跑了。只用 CLI 不想装 skill 的话，跳过第一步即可。

> 先说明边界：本工具到「拿到文本 + 截好图 + 验收」为止，**不生成最终 Markdown**。
> 把文本整理成笔记是人工步骤，或者交给能读文本的 agent。`skills/bili-course-notes/SKILL.md` 是给 agent 的那份手册。

### 只用字幕路线（不需要 API key）

```bash
bili-notes probe   BV1xxxxxxxxx        # 先看有几集、哪集是广告
bili-notes subs    scan  BV1xxxxxxxxx  # 扫哪些集有 AI 字幕
bili-notes subs    fetch BV1xxxxxxxxx  # 下载，产物在 work/subs_BV.../pNNN.txt
```

产物格式是 `[mm:ss] 内容`，可以直接读、也可以喂给任何模型整理成笔记。

> **但这条路通常需要登录 cookie。** 实测匿名调用 `subs scan` 会返回 `with_sub=0` ——
> `ai-zh` 字幕列表只在登录态下返回。cookie 免费，浏览器里就有，也不需要 API key。
> 把 `SESSDATA` / `bili_jct` / `DedeUserID` 三个值存成 `work/cookies.json`
> （格式见 `docs/cookies.md`），`subs` 会自动带上。
> **这个文件在 `.gitignore` 里，永远不要提交。**

### 加截图

```bash
bili-notes capture BV1xxxxxxxxx 4 0:2000:120   # 第 4 P，每 120 秒一帧（约 17 张）
bili-notes contact p4                          # 拼成一张联系表，先看结构
bili-notes shots   4 "<附件目录>" "0:01-本讲标题.png" "120:02-例题1.png"
```

**先粗扫再精挑**：一集 34 分钟、120 秒一帧约 17 张，一张联系表就能划出「开场 / 例题 / 解答 / 下一题」，再只为这些节点挑 8~12 张。不必每 30 秒都截。

产物按视频隔离：`work/frames/<BV号>/p4/t0000.png`。这样两门课都有 P4 时不会互相覆盖。

### 没有字幕才用云端 ASR

```bash
cp .env.example .env        # 填 ASR_API_KEY
bili-notes http-asr BV1xxxxxxxxx 4 --seconds 180   # 先转 3 分钟看效果
bili-notes http-asr BV1xxxxxxxxx 4                 # 满意了再跑整集
```

默认端点打阿里云百炼（DashScope）的 `multimodal-generation` 接口；换成别的网关时改 `ASR_HTTP_ENDPOINT`，
并使用该网关自己的 key（见 `docs/asr-dead-ends.md`——那里记了 8 条走不通的路，别重走）。

### 写完笔记跑验收

```bash
bili-notes verify "notes/第03讲 标题.md" "attachments/p04-章节名"
```

**机器判定**（`verify` 输出 `PASS` / `CHECK`，有 CHECK 就返回非零，CI 能拦）：
- 图片引用数 = 附件数（缺图 = 裂图，多图 = 白截）
- 双链无断链
- 体量不低于下限（默认 5 KB；`类型: 习题` 的笔记降到 2 KB）

**人工复核**（脚本不管，得自己看）：
- 体量是否明显超过 20 KB（写散了）
- 时间轴是否够密（脚本只在过少时打一行提示，不判失败）
- 讲号是否等于上一讲 +1、相邻讲的双向链接是否都对得上

## 命令一览

| 命令 | 作用 |
|---|---|
| `probe` | 分 P 列表、时长、最高清晰度、疑似广告片尾 |
| `subs scan\|fetch` | B 站 AI 字幕扫描 / 下载 |
| `http-asr` | 云端 ASR（HTTP，纯标准库，没字幕时首选） |
| `asr` | 本地 whisper（断网兜底） |
| `extract` | whisper JSON → 可读分段文本 |
| `capture` | 按秒 / 按 `start:end:step` 截帧，已存在的帧跳过 |
| `contact` | 帧拼 3 列联系表，带时间标签 |
| `shots` | 按「秒:文件名」把帧复制成附件，`--dry` 先预演 |
| `verify` | 笔记验收 |

`src/bili_notes/extras/` 里还有一套 Obsidian 批注工具：`boxes`（加框）、`flatten-boxes` / `convert-boxes`（旧格式迁移）、`boards`（重建看板）、`collect-notes`（汇总欠账）。需要笔记里先有批注框，可选。

## 配置

全部走环境变量或仓库根目录的 `.env`，**默认值只落在当前目录下，不含任何绝对路径**：

| 变量 | 默认 | 说明 |
|---|---|---|
| `BILI_NOTES_WORKDIR` | `./work` | 字幕、帧、音频等中间产物 |
| `BILI_NOTES_VAULT` | 空 | Obsidian vault 路径；核心 CLI 不使用，下游脚本可读取 |
| `BILI_NOTES_COOKIE` | `<WORKDIR>/cookies.json` | B 站 cookie |
| `BILI_NOTES_FFMPEG` | 从 PATH 找 | **截帧（capture）和本地 ASR 都需要**。不设就从 PATH 里找 ffmpeg |
| `BILI_NOTES_HTTP` | `auto` | `urllib` 优先，被风控（-352）时自动回退 `curl` |
| `ASR_API_KEY` | 空 | 云端 ASR 的 key；默认端点下也认 `DASHSCOPE_API_KEY` |

## 已知坑（都是踩出来的）

完整版共 18 条在 [`docs/pitfalls.md`](docs/pitfalls.md)，这里挑四个最容易中招的：

1. **匿名请求拿不到高清晰度**。同一个分 P，匿名只给 `852x480`，带上登录 cookie 才给 `1280x720`。板书想看清，先确认 cookie 有效。
2. **AI 字幕会把专业词和数值听错**。实测把「加奇减偶」听成「夹击减偶」、「5/8」听成「5%」、「0.25%」听成「0.54%」。规矩：**结构、话术按字幕写，具体数值一律看截图**，读不准就写「以截图为准」。
3. **附件目录别用前缀匹配**。`startswith('p1')` 会同时命中 `p10-假设检验`，验收时报一堆假「缺图」。统一用 `p<N>-` 完整名。
4. **合集不等于分 P**。合集里某一集的 `pages` 只有 1 条，`probe` 会报 `PAGES: 1`，看着像「只有一集」。全集在 `ugc_season.sections[].episodes[]` 里。

## 目录结构

```
bili-notes/
├── src/bili_notes/          核心脚本（每个都能单独 python xxx.py 跑）
│   └── extras/              Obsidian 批注工具（可选）
├── skills/
│   └── bili-course-notes/
│       └── SKILL.md         给 AI agent 的操作手册（npx skills 可识别）
├── docs/
│   ├── pitfalls.md          18 条实测坑
│   ├── asr-dead-ends.md     云端 ASR 的 8 条死路
│   └── cookies.md           怎么拿 B 站 cookie（只存本地）
├── examples/output-sample.md 产出长什么样
└── tests/                   离线测试 + 仓库卫生守卫（11 项，不联网）
```

## 合规与边界

- 本工具**只处理你自己有权访问的内容**，不绕过任何付费墙或权限校验。
- 产物（字幕文本、板书截图）的版权属于原作者。**自用复习可以，二次发布请自行确认授权**。
- `cookies.json` 是你账号的登录态，等同于密码。它和 `.env` 都在 `.gitignore` 里，任何情况下不要提交、不要贴进 issue。
- 请控制请求频率。这是给个人整理笔记用的工具，不是爬虫框架。

## License

MIT，见 [LICENSE](LICENSE)。
