# LAP Go 外部编排 Agent

这个可运行的 `lap-local/0.1` 包是一个有界外部工作流编排器的 Go 实现。它使用公开的
[Go Agent SDK](../../sdk/go/README.zh-CN.md) 读取 Host 持有的
`io.github.dongrv.lap.workflow.orchestrator` Context Packet 扩展，并返回一条标准派遣提议。

它刻意不包含目标 Agent 名称、capability、凭据、Host 路径、租户标识或授权逻辑。为了让
示例可重复，它选择 Host 提供的第一个目标及其第一个允许的 capability。生产级规划器可用
自己的推理或策略在同一份有界列表中做选择。

```text
Host 工作流范围 -> Context Packet 扩展 -> 外部 Go 规划器提议
                                            -> Host 校验 -> 子运行
```

规划器永远不会自行创建子运行。Host 仍会在启动任何目标前解析发布、检查租户准入、
capability 范围、预算、截止时间、审批和环路。

## 包内容

- `agent.json`：带有 `plan.dispatch` capability 和已发布 dispatch 输出 schema 形状的
  可移植包清单，并声明 `lap-local/0.1` 与 `lap-workflow/0.1`。
- `main.go`：基于 Go SDK 的无依赖 Agent 实现。
- `go.mod`：本地 SDK replacement，使仓库示例无需下载变动依赖即可构建。

源码清单通过 `go run .` 运行，使 conformance 套件可在支持的平台上执行同一份源码。
Host 在激活前仍必须显式允许 Go 可执行文件。该声明支持工作流预检，但 Host 仍会在每次运行
的握手中证明 workflow profile。

## 通过 Host 试运行

1. 将此目录复制到 Host 受管理的 LAP 包目录，例如 Lambda Harness 运行目录中的
   `lap_agents/orchestrator-agent-go`。
2. 在 Host 的 Agent 管理界面审核并显式激活该包。仅发现目录中的包不得执行它。
3. 创建一个 `orchestrated` 工作流，其根节点使用
   `org.lap.go-orchestrator-agent` 和 `plan.dispatch` capability。
4. 使用当前 Host 和租户已准入的 Agent ID 与 capability 填写 `allowed_agent_ids` 和
   `allowed_capabilities`。
5. 运行工作流。Host 会在 Context Packet 中提供精确范围；此示例从该范围中返回一条提议。

根节点形状示例：

```json
{
  "id": "plan",
  "type": "orchestrator",
  "agent": {
    "id": "org.lap.go-orchestrator-agent",
    "capability": "plan.dispatch"
  },
  "allowed_agent_ids": ["com.example.inspector"],
  "allowed_capabilities": {
    "com.example.inspector": ["repo.inspect"]
  }
}
```

请将示意的下游 ID 与 capability 替换为 Host 当前 Agent 目录中的条目；它们不由此包配置。

## 构建二进制包

在包内构建平台特定的可执行文件，然后将清单命令改为包内相对二进制路径：

```powershell
New-Item -ItemType Directory -Force bin
go build -o bin\lap-go-orchestrator.exe .
# agent.json: "command": ["bin/lap-go-orchestrator.exe"]
```

在 POSIX 平台使用 `go build -o bin/lap-go-orchestrator .`，并在清单中使用匹配的斜杠路径。
`bin/` 目录不会提交。包审核、激活、内容校验和任何发布者签名仍发生在 Host 边界。

## 验证示例

在仓库根目录执行：

```bash
go test ./sdk/go/...
python -m unittest discover -s tests -p "test_examples.py" -v
```

测试会发送一次真实的 `agent.hello` 和 `run.start` 交换，校验每一个返回 envelope，并检查
精确的 Host 作用域提议及范围缺失时带类型的 `LAP-201` 响应。规范性契约见
[Workflow Profile](../../profiles/workflow.md) 和
[LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md)。
