# 怎么拿 B 站 cookie（只存本地）

有些接口（尤其是 AI 字幕列表）只在登录态下返回数据。匿名访问时 `subs scan` 会报 `with_sub=0`。

## 需要的三个值

| 键 | 作用 | 备注 |
|---|---|---|
| `SESSDATA` | 登录会话 | URL 编码形态，有效期可达数月 |
| `bili_jct` | CSRF token | 32 位十六进制 |
| `DedeUserID` | 你的 UID | 10 位数字 |

## 怎么取

1. 浏览器登录 bilibili.com。
2. F12 → Application（应用）→ Cookies → `https://www.bilibili.com`。
3. 找到上面三个键，复制它们的值。

## 存成什么格式

`work/cookies.json`（`BILI_NOTES_COOKIE` 可以改路径）：

```json
{
  "SESSDATA": "xxxx%2Cxxxx%2Cxxxx",
  "bili_jct": "0123456789abcdef0123456789abcdef",
  "DedeUserID": "1234567890"
}
```

脚本只做一件事：拼成 `k=v; k=v` 塞进请求头的 `Cookie` 字段。不发往任何第三方。

## 安全边界

- **这个文件等同于你的密码。** 它在 `.gitignore` 里，但你还应确认 `git status` 里看不到它。
- 不要贴进 issue、截图、聊天记录。
- 用它抓到的字幕/截图，版权归原作者；cookie 只解决「能不能访问」，不解决「能不能转载」。
- cookie 会过期。`subs scan` 报 `with_sub=0` 时先怀疑它失效，而不是怀疑代码坏了。

## 不想用 cookie？

可以。不带 cookie 也能跑 `probe`、`capture`（清晰度低一档）、`verify`，只是字幕接口可能不返回 `ai-zh`。这时候改走云端 ASR 路线即可。
