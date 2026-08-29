# LAP Node.js Echo Agent

这个无依赖的 Node.js 参考实现演示 `lap-local/0.1` 消息流。它刻意不是生产级沙箱或
授权系统。

请使用一个向 stdin 发送以换行分隔的 LAP envelope 的 Host 来运行它。Agent 只向 stdout
写入协议帧，诊断信息只会写入 stderr。

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

清单通过 `node echo_agent.js` 启动它，需要 Node.js 18 或更高版本。Host 在激活前必须
显式允许经过审核的 `node` 可执行文件。若将 Agent 与经过审核的运行时或编译后的可执行文件
一起打包，协议行为不会改变。

请将该夹具作为协议参考，而不是安全边界。
