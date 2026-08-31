# LAP Local Go SDK

这个无依赖 Go 包实现
[`lap-local/0.1`](../../profiles/local-stdio.md) stdio profile 的 **Agent 侧**。它让本地
Agent 实现作者专注于 capability handler，而不必重复实现 JSON Lines framing、有序消息、
取消和终态结果竞争处理。

它是 LAP `0.1` 草案的参考 SDK，不是 Host Runtime，也不是 conformance 认证。

## 范围

SDK 提供：

- `agent.hello` / `agent.welcome` 协商和有序 Agent envelope；
- 已接受运行的顺序、进度和 artifact 事件，以及每次已接受运行的一条终态 `run.result`；
- 有界输入帧、声明 capability 和并发检查；
- 支持取消的 Go `context.Context`；
- 可选外部编排器工作流范围的类型化解析；以及
- 在可配置时间内排空工作的优雅关闭。

SDK **不**认证用户、分配租户、验证或激活包、授权效果、暂存文件、监管子进程、强制资源
限制或持久化审计状态。这些均是 LAP Core 和 Local profile 下 Host 的职责。

## 安装

协议尚未发布稳定版。生产环境应固定不可变 commit 或未来 tag 版本，而不是跟踪变动分支。

```bash
go get github.com/lambda-harness/LAP/sdk/go@main
```

该模块要求 Go 1.21 或更高版本。

## 最小 Agent

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "os"

    laplocal "github.com/lambda-harness/LAP/sdk/go"
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

`Server.Serve` 只向其 output writer 写入协议帧。应用应将诊断输出写到 stderr。Host 在
激活进程前仍必须将 welcome 中的身份、版本、profile 和并发信息与已验证的 `agent.json`
清单进行比较。

## Handler 契约

`Request.Input` 与 `Request.Context` 以 `json.RawMessage` 保留 Host 提供的 JSON 值。handler
只应验证它所拥有 capability 的契约。它可以调用：

```go
reporter.Progress("file", "Wrote report.json")
reporter.Artifact(laplocal.Artifact{
    ID: "report-01", Name: "report.json",
    MediaType: "application/json", URI: "lap://run/output/report.json",
})
```

进度必须描述可观察工作，如工具调用或文件操作；它不得暴露私有模型推理。`ctx.Done()`
关闭后 handler 必须及时返回。返回的 Go error 会变成带类型的 `LAP-500` 结果，不会在协议流
中暴露实现错误文本。

对于已接受的运行，SDK 在调用 handler 前发出 `run.accepted`，以严格递增的 `seq` 序列化
Agent 输出，并让第一条终态结果胜出。取消或终态结果之后试图发送进度或 artifact 会返回
`laplocal.ErrRunClosed`。

## 外部编排器上下文

被 Workflow Profile `orchestrator` 节点选中的 Agent 可以读取其不可变规划范围，无需手写
JSON 遍历：

```go
server, err := laplocal.New(laplocal.Config{
    AgentID: "com.example.workflow-planner",
    Version: "1.0.0",
    Capabilities: []string{"plan.dispatch"},
    AdditionalProfiles: []string{laplocal.WorkflowProfile},
}, planDispatch)
```

`AdditionalProfiles` 仅声明该可执行文件理解工作流契约，并不授予派遣权限。若 Local Agent 被
用作 `orchestrator` 节点，符合规范的 Host 会在 `agent.hello` 中请求
`lap-workflow/0.2`，在 `agent.welcome` 中确认它；缺失时不会发送 `run.start`。普通 Local
运行仍可只使用 `lap-local/0.1` 保持兼容。

```go
scope, found, err := request.WorkflowOrchestratorContext()
if err != nil || !found {
    return laplocal.Failed(
        "failed", "Workflow context is invalid.", "LAP-201",
        "A valid Host-scoped orchestrator context is required.", false,
    ), nil
}

target := scope.AllowedDispatches[0]
proposal := map[string]any{
    "dispatch": []map[string]any{{
        "agent_id": target.AgentID,
        "capability": target.Capabilities[0],
        "input": json.RawMessage(request.Input),
    }},
}
return laplocal.Succeeded("Proposed one Host-constrained dispatch.", proposal), nil
```

`found == false` 对普通 Agent 节点是正常情况。扩展存在时，
`WorkflowOrchestratorContext` 会严格校验 LEP-0008 / Workflow Profile `0.2` 形状：精确的
扩展字段、版本、合法 ID、非空目标，以及规范的目标/capability 排序。它不授予调度权限；
Host 在启动子 Agent 前仍会校验每条提议。请参阅可运行的[外部编排器 Agent 示例](../../examples/orchestrator-agent/README.zh-CN.md)
和[Workflow Profile](../../profiles/workflow.md#33-external-orchestrator-context)。

## 限制与关闭

`Config.MaxFrameBytes` 默认 1 MiB，`MaxConcurrency` 默认一，`ShutdownTimeout` 默认十秒。
Host 的 `agent.shutdown` 停止新工作，并让活动 handler 排空到该超时；剩余运行以带类型的
终态结果取消。如果 handler 忽略取消，Host 仍负责硬进程超时。

可在本地运行 SDK 检查：

```bash
go test ./...
go vet ./...
```

[Go Echo Agent](../../examples/echo-agent-go/README.zh-CN.md) 是该 SDK 针对共享 LAP 本地
往返向量的完整可运行用法。
