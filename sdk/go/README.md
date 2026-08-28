# LAP Local Go SDK

This dependency-free Go package implements the **Agent side** of the
[`lap-local/0.1`](../../profiles/local-stdio.md) stdio profile. It lets an
author of a local binary, including a Windows `coding-agent.exe`, focus on a
capability handler instead of reimplementing JSON Lines framing, ordered
messages, cancellation, and terminal-result races.

It is a reference SDK for the LAP `0.1` draft, not a Host Runtime and not a
conformance certification.

## Scope

The SDK provides:

- `agent.hello` / `agent.welcome` negotiation and ordered Agent envelopes;
- accepted-run sequencing, progress and artifact events, and one terminal
  `run.result` per accepted run;
- bounded input frames, declared capability and concurrency checks;
- a cancellation-aware Go `context.Context`; and
- graceful shutdown that drains work for a configurable period.

The SDK does **not** authenticate users, assign tenants, validate or activate
packages, authorize effects, stage files, supervise child processes, enforce
resource limits, or persist audit state. Those are Host responsibilities under
the LAP Core and Local profiles.

## Install

The protocol is pre-release. Pin an immutable commit or a future tagged
version in production rather than tracking a moving branch.

```bash
go get github.com/dongrv/LAP/sdk/go@main
```

The module requires Go 1.21 or newer.

## Minimal Agent

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "os"

    laplocal "github.com/dongrv/LAP/sdk/go"
)

type echoInput struct {
    Text string `json:"text"`
}

func main() {
    server, err := laplocal.New(laplocal.Config{
        AgentID: "com.example.echo",
        Version: "1.0.0",
        MaxConcurrency: 1,
        Capabilities: []string{"text.echo"},
    }, func(ctx context.Context, request laplocal.Request, reporter laplocal.Reporter) (laplocal.Result, error) {
        var input echoInput
        if err := json.Unmarshal(request.Input, &input); err != nil {
            return laplocal.Failed("failed", "Input is invalid.", "LAP-201", "Expected {text} input.", false), nil
        }
        if err := reporter.Progress("tool", "Preparing echo output."); err != nil {
            return laplocal.Result{}, err
        }
        select {
        case <-ctx.Done():
            return laplocal.Failed("cancelled", "Run cancelled.", "LAP-401", "Cancellation requested by the Host.", false), nil
        default:
        }
        return laplocal.Succeeded("Echo complete.", map[string]any{"text": input.Text}), nil
    })
    if err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(2)
    }
    if err := server.Serve(os.Stdin, os.Stdout); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(2)
    }
}
```

`Server.Serve` writes protocol frames only to its output writer. Applications
should write diagnostics to stderr. The Host must still compare the welcome
identity, version, profile, and concurrency with the validated `agent.json`
manifest before it activates a process.

## Handler Contract

`Request.Input` and `Request.Context` preserve the Host-provided JSON values
as `json.RawMessage`. A handler should validate only the contract for the
capability it owns. It can call:

```go
reporter.Progress("file", "Wrote report.json")
reporter.Artifact(laplocal.Artifact{
    ID: "report-01", Name: "report.json",
    MediaType: "application/json", URI: "lap://run/output/report.json",
})
```

Progress must describe observable work, such as a tool call or file operation;
it must not expose private model reasoning. A handler must return promptly when
`ctx.Done()` is closed. A returned Go error becomes a typed `LAP-500` result
without exposing implementation-error text on the protocol stream.

For an accepted run the SDK emits `run.accepted` before invoking the handler,
serializes Agent output with a strictly increasing `seq`, and makes the first
terminal result win. Progress or artifacts attempted after cancellation or a
terminal result return `laplocal.ErrRunClosed`.

## Limits And Shutdown

`Config.MaxFrameBytes` defaults to 1 MiB, `MaxConcurrency` defaults to one,
and `ShutdownTimeout` defaults to ten seconds. A Host `agent.shutdown` stops
new work and lets active handlers drain until that timeout; remaining runs are
cancelled with a typed terminal result. The Host remains responsible for a
hard process timeout if a handler ignores cancellation.

Run the SDK checks locally with:

```bash
go test ./...
go vet ./...
```

The [Go echo Agent](../../examples/echo-agent-go/README.md) is a complete,
runnable use of this SDK against the shared LAP local round-trip vector.
