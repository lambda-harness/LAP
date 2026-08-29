# LAP Node.js 外部编排 Agent

这个可运行的 `lap-local/0.1` 包是一个无依赖 Node.js 参考实现，用于演示有界的外部工作流
编排 Agent。它读取 Host 持有的 `io.github.dongrv.lap.workflow.orchestrator` Context Packet
扩展，并返回一条标准派遣提议。

它刻意不包含目标 Agent 名称、capability、凭据、Host 路径、租户标识或授权逻辑。为了让示例
可重复，它选择 Host 提供的第一个目标及其第一个允许的 capability。生产级规划器可以选择不同
目标，但 Host 仍会在启动子运行前校验每一条提议。

```text
Host 工作流范围 -> Context Packet 扩展 -> 外部规划器提议
                                         -> Host 校验 -> 子运行
```

## 包内容

- `agent.json`：带有 `plan.dispatch` capability 和已发布 dispatch 输出 schema 形状的
  可移植包清单，并声明 `lap-local/0.1` 与 `lap-workflow/0.1`。
- `orchestrator_agent.js`：无依赖的 stdin/stdout 协议循环。

清单通过 `node orchestrator_agent.js` 运行它，需要 Node.js 18 或更高版本。Host 在激活前
必须显式允许经过审核的 `node` 可执行文件。profile 声明可支持发现和工作流预检；它不授予
权限，也不能替代每次运行前必需的握手。

## 通过 Host 试运行

1. 将此目录复制到 Host 受管理的 LAP 包目录，例如 Lambda Harness 运行目录中的
   `lap_agents/orchestrator-agent-node`。
2. 在 Host 的 Agent 管理界面审核并显式激活该包。仅发现目录中的包不得执行它。
3. 创建一个 `orchestrated` 工作流，其根节点使用
   `org.lap.orchestrator-agent-node` 和 `plan.dispatch` capability。
4. 使用当前 Host 和租户已准入的 Agent ID 与 capability 填写 `allowed_agent_ids` 和
   `allowed_capabilities`。
5. 运行工作流。Host 会在 Context Packet 中提供精确范围；此示例从该范围中返回一条提议。

## 验证示例

在仓库根目录执行：

```bash
node --check examples/echo-agent-node/echo_agent.js
node --check examples/orchestrator-agent-node/orchestrator_agent.js
python -m unittest discover -s tests -p "test_examples.py" -v
```

测试会发送真实的 `agent.hello` 和 `run.start` 交换，校验每一个返回 envelope，并确认提议
严格反映 Host 提供的 Context Packet。规范性契约见
[Workflow Profile](../../profiles/workflow.md) 和
[LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md)。
