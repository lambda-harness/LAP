# 增值税发票识别 Agent

这是一个用于中国增值税发票图片和 PDF 的 LAP Local 0.1 Agent。Host 会暂存一个或
多个已授权的输入 Artifact；Agent 渲染 PDF 页面，调用 DeepSeek 视觉 API，校验已标准化
的发票字段，并输出一个 XLSX Artifact。

运行环境需要 Python 3.10+、`openpyxl`、`PyMuPDF`，以及显式授权给 Agent 的
`DEEPSEEK_API_KEY`。可选环境配置为 `DEEPSEEK_VISION_BASE_URL` 和
`DEEPSEEK_VISION_MODEL`。
