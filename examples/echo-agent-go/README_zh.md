# LAP Go Echo Agent

这是与 Python Echo Agent 相同 `lap-local/0.1` 往返流程的无依赖 Go 实现。它使用
公开的 [Go Agent SDK](../../sdk/go/README.md)，展示二进制作者如何实现能力处理器，
而无需手写协议循环。

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

使用下列命令运行源码参考实现：

```bash
go run .
```

如需 Windows 可执行包，请构建它并将清单命令改为包内相对二进制路径：

```powershell
New-Item -ItemType Directory -Force bin
go build -o bin\lap-go-echo.exe .
# agent.json: "command": ["bin/lap-go-echo.exe"]
```

源码清单特意使用 `go run .`，以便公共 conformance 套件无需将平台相关二进制提交到
Git 即可运行。Host 在激活前仍必须显式允许所选 Host 可执行文件。
