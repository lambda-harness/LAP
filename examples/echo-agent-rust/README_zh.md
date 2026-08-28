# LAP Rust Echo Agent

此参考实现与 Python、Go 示例执行相同的 `lap-local/0.1` 往返流程。它仅使用
`serde_json` 处理 UTF-8 NDJSON 帧；stdout 只输出协议 envelope。

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

使用下列命令运行源码参考实现：

```bash
cargo run --quiet
```

源码清单刻意通过 Cargo 启动，使 conformance 夹具无需将平台相关二进制提交到 Git 即可
运行。可发布包应构建可执行文件、将其放在包根目录内，并用该包内相对入口替换
`transport.command`。Host 在激活前仍必须显式准入选定的启动入口。

请将该夹具作为协议参考，而不是沙箱或授权边界。
