# LAP Echo Agent

这是一个小型参考实现，用于演示 `lap-local/0.1` 消息流。它刻意不是生产级
沙箱或授权系统。

请使用一个向 stdin 发送以换行分隔的 LAP envelope 的 Host 来运行它。Agent 只向
stdout 写入协议帧，不输出诊断信息。

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

清单通过 `python echo_agent.py` 启动它。在 Windows 上可以将其打包为 `.exe`；协议
行为不会改变。

请将该夹具作为协议参考，而不是安全边界。
