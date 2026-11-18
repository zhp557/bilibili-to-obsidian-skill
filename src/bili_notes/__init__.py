"""bili_notes —— B 站课程视频 → 结构化笔记。

模块划分：
    common      公共常量、cookie、HTTP 层、wbi 签名
    probe       分 P / 时长 / 清晰度盘点
    subs        B 站 AI 字幕扫描与下载（首选路线）
    http_asr    云端 ASR（一次一段，纯标准库，需要 ASR key）
    asr         本地 whisper 兜底（需要 faster-whisper）
    capture     按时间点截帧
    contact     帧拼联系表
    shots       帧 → 中文命名附件
    verify      笔记验收（引用数 / 断链 / 体量 / 时间轴）
"""

__version__ = "0.1.0"
