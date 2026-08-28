# LAP 外部编排 Agent

这个可运行的 `lap-local/0.1` 包演示了最小但完整的外部工作流编排 Agent。它读取
Host 持有的 `io.github.dongrv.lap.workflow.orchestrator` Context Packet 扩展，并返回一条
标准派遣提议。

它刻意不包含目标 Agent 名称、capability、凭据、Host 路径、租户标识或授权逻辑。为了让
示例可重复，它选择 Host 提供的第一个目标及其第一个允许的 capability。生产级规划器可用
自己的推理或策略在同一份有界列表中做选择。

```text
Host 工作流范围 -> Context Packet 扩展 -> 外部规划器提议
                                         -> Host 校验 -> 子运行
```

规划器永远不会自行创建子运行。Host 仍会在启动任何目标前解析发布、检查租户准入、
capability 范围、预算、截止时间、审批和环路。

## 包内容

- `agent.json`：带有 `plan.dispatch` capability 和已发布 dispatch 输出 schema 形状的
  可移植包清单，并声明 `lap-local/0.1` 与 `lap-workflow/0.1`。
- `orchestrator_agent.py`：无依赖的 stdin/stdout 协议循环。

清单通过 `python orchestrator_agent.py` 运行它。将其打包为 Windows 可执行文件或改用其他
语言，不会改变线协议契约。该声明可让 Host 提前拒绝不兼容的工作流，但不能替代每次运行前
必需的 workflow profile 握手。

## 通过 Host 试运行

1. 将此目录复制到 Host 受管理的 LAP 包目录，例如 Lambda Harness 运行目录中的
   `lap_agents/orchestrator-agent`。
2. 在 Host 的 Agent 管理界面审核并显式激活该包。仅发现目录中的包不得执行它。
3. 创建一个 `orchestrated` 工作流，其根节点使用
   `org.lap.orchestrator-agent` 和 `plan.dispatch` capability。
4. 使用当前 Host 和租户已准入的 Agent ID 与 capability 填写 `allowed_agent_ids` 和
   `allowed_capabilities`。
5. 运行工作流。Host 会在 Context Packet 中提供精确范围；此示例从该范围中返回一条提议。

根节点形状示例：

```json
{
  "id": "plan",
  "type": "orchestrator",
  "agent": {
    "id": "org.lap.orchestrator-agent",
    "capability": "plan.dispatch"
  },
  "allowed_agent_ids": ["com.example.inspector"],
  "allowed_capabilities": {
    "com.example.inspector": ["repo.inspect"]
  }
}
```

请将示意的下游 ID 与 capability 替换为 Host 当前 Agent 目录中的条目；它们不由此包配置。

## 验证示例

在仓库根目录执行：

```bash
python -m unittest discover -s tests -p "test_examples.py" -v
```

测试会发送一次真实的 `agent.hello` 和 `run.start` 交换，校验每一个返回 envelope，并确认
提议严格反映 Host 提供的 Context Packet。规范性契约见
[Workflow Profile](../../profiles/workflow.md) 和
[LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md)。
