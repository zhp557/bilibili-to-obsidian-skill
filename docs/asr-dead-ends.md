# 云端 ASR 踩坑记录：哪些路走不通

先说适用范围，免得你照着排查走错方向：

> 下面 8 条「死路」是在**某类 OpenAI 兼容中转网关**上实测的，不是 DashScope 官方文档的行为。
> 中转网关往往只实现了官方 API 的一个子集，路由 404、协议不认、对象 ACL 不同都很常见。
> 换成官方端点或另一家网关，结论可能完全不同——遇到新网关时，把这张表当成「先别浪费时间试这些」的清单，而不是「一定不行」的定论。

## HTTP 路线（推荐，`http_asr.py` 走这条）

```http
POST <base>/api/v1/services/aigc/multimodal-generation/generation
Content-Type: application/json
Authorization: Bearer <key>

{
  "model": "qwen3-asr-flash",
  "input": {
    "messages": [
      {"role": "user", "content": [{"audio": "data:audio/wav;base64,..."}]}
    ]
  }
}
```

→ 200，**纯标准库即可，不需要 websockets**。一段 120 秒音频约 9 秒返回，带标点。

要点：
- 音频要先转成 16k / 单声道 / 16bit wav，再 base64 塞进 `data:` URL
- 每段 120 秒左右比较稳（base64 后约 5 MB，留足余量）
- 模型名会随服务商版本变化，用 `<base>/models` 查一下当前可用的是哪个

## 实测走不通的路（针对中转网关）

| 尝试 | 结果 |
|---|---|
| `POST /compatible-mode/v1/audio/transcriptions` | 404，网关没实现该路由 |
| `POST /audio/translations` | 404 |
| ASR 异步接口 + `oss://` 直传 | 任务 `SERVER_ERROR`（网关不认 oss 协议） |
| ASR 异步接口 + 对象存储的 https 形式 | `FILE_403_FORBIDDEN`（对象是 private ACL，云端读不到） |
| ASR 异步接口 + `file://file-xxx`（先走 files 上传） | `DECODE_ERROR`（`purpose=file-extract` 存的是解析产物，不是原始音频） |
| `chat/completions` + `input_audio{data:base64}` | 400 / `provided URL does not appear to be valid`（把 data 当 URL 解析） |
| `chat/completions` + `input_audio{data:file://…}` | 400（通用聊天模型不吃 audio modal） |
| **B 站音频直链直接喂云端** | `FILE_403_FORBIDDEN`（CDN 防盗链，云端请求不带 Referer） |

最后一条值得单独强调：**音频必须先下载到本地再上传**。这不是网关的毛病，是 B 站 CDN 的防盗链——任何云端服务去拉那个 URL 都会被拒。

## 如果你确实需要流式进度（本仓库没包含）

有些服务商提供 `qwen3-asr-flash-realtime` 这类模型，走 OpenAI Realtime 协议（WebSocket）可以边推音频边出结果。它**不在这套工具里**，因为：

- 这个模型不是所有服务商都提供，别人 clone 下来未必跑得通；
- 实测同一条音频，WebSocket 路线比上面的 HTTP 路线慢约 5 倍。

真要用，协议要点是：

1. 用 **OpenAI Realtime 协议**，不是 DashScope 的 `run-task` 协议。发 `run-task` 会一路返回 `result-generated` 里带 `"param":"type"` 的错误帧。
2. 顺序必须是：收 `session.created` → 发 `session.update` → 收到 `session.updated` → **再**推音频。急着推音频会在 `send` 阶段被服务器超时关闭。
3. **不要发 `response.create`** —— 有的网关直接报 `Invalid value: 'response.create'`。只发 `input_audio_buffer.commit`，结果从 `conversation.item.input_audio_transcription.completed` 的 `transcript` 字段拿。
4. 分片推 PCM：16k / 单声道 / 16bit，每片 3200 字节（0.1 秒）最稳；整段 60 秒一个会话，兼顾上下文和超时。

## 判断某个网关有没有 ASR

```bash
curl -H "Authorization: Bearer $KEY" <base>/models | grep -Ei "audio|asr|whisper|paraformer"
```

有模型不代表能调通——上表前 7 行就是「模型在列表里，但路由不通」。先拿一段 3 分钟的音频试，别一上来就跑整集。
