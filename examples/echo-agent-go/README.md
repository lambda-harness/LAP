# LAP Go Echo Agent

This is a dependency-free Go implementation of the same `lap-local/0.1`
round trip as the Python echo Agent. It uses the public
[Go Agent SDK](../../sdk/go/README.md), demonstrating that a binary author can
implement a capability handler without hand-writing the protocol loop.

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

Run the source reference with:

```bash
go run .
```

For a Windows executable package, build it and change the manifest command to
the package-relative binary path:

```powershell
New-Item -ItemType Directory -Force bin
go build -o bin\lap-go-echo.exe .
# agent.json: "command": ["bin/lap-go-echo.exe"]
```

The source manifest intentionally uses `go run .` so the public conformance
suite can execute without checking a platform-specific binary into Git. A Host
must still explicitly allow the selected host executable before activation.
