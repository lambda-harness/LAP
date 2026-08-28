# LAP: Lattice Agent Protocol

- **状态：** `0.1.0-draft`
- **许可证：** Apache-2.0
- **标语：** Orchestrate Any Agent. Connect Everything.

LAP 是一份开放的受管 Agent 互操作规范。它让 Agent 包、本地可执行文件、原生运行时
Agent 或远程 Agent 都能以同一个受监管单元的形式接入 Host Runtime。

LAP 有意保持边界清晰。它**不**取代已有标准：

- [MCP](https://modelcontextprotocol.io/) 连接模型和 Agent 与工具、资源及提示词。
- [A2A](https://a2a-protocol.org/latest/) 连接独立的远程 Agent。
- LAP 定义可安装、可治理 Agent 的生命周期和运行时契约，包括本地二进制 Agent 与
  A2A 支撑的 Agent。

## 为什么需要 LAP

Agent 不只是提示词或工具。一个可移植 Agent 需要身份、版本、声明的 capability、传输、
健康检查契约、作用域权限、可观测进度、取消、artifact 以及可靠的终态结果。没有这些
契约，“插件 Agent”就会退化为任意进程执行和不可靠的交接。

LAP 对这个缺失边界进行标准化。

```text
Agent package -> Registry -> Supervisor -> Adapter -> Agent implementation
                                      |-> policy / approval
                                      |-> events / audit / artifacts
```

## LAP 覆盖的内容

| 关注点 | LAP 的回答 |
|---|---|
| 发现和安装 | 版本化 `agent.json` 清单和包 profile。 |
| 运行本地二进制 | 通过受监管 stdin/stdout 使用 `lap-local` UTF-8 NDJSON。 |
| 调用远程 Agent | 使用协商 A2A 语义的 `lap-a2a-bridge`。 |
| 观察工作 | 有序的进度、artifact 和终态事件。 |
| 安全停止和重试 | 幂等键、截止时间、取消和不可变终态。 |
| 治理租户 | 运行时派生的租户身份和有作用域的 capability grant。 |
| 组合 Agent | 面向可信 supervisor 的父/子谱系与 Workflow Profile。 |

## 文档

- [Core Specification](SPEC.md)：术语、envelope、生命周期、治理和兼容规则。
- [Local Stdio Profile](profiles/local-stdio.md)：面向受监管外部 Agent 实现的规范性
  本地进程传输 profile。
- [A2A Bridge Profile](profiles/a2a-bridge.md)：受管远程 A2A Agent 的互操作规则。
- [A2A Inline Inputs Profile](profiles/a2a-inline-inputs.md)：将明确授予的小型 Host
  输入 artifact 以 A2A `FilePart.bytes` 有界传输给已准入 A2A Skill 的可选 profile。
- [Package Signing Profile](profiles/package-signing.md)：面向可移植 Agent Package 的
  可选 Ed25519 发布者来源证明。
- [Workflow Profile](profiles/workflow.md)：具有运行时强制分派边界、用户拥有的版本化
  Agent 图。
- [Host Metering Profile](profiles/host-metering.md)：面向可强制执行的工作流输入和成本
  预算的可选 Host 直连模型计量。
- [Go Agent SDK](sdk/go/README.zh-CN.md)：无依赖的本地 Profile Agent 侧辅助工具；它不是
  Host Runtime，也不是 conformance 认证。
- [Agent Manifest](schemas/agent-manifest.schema.json)、
  [Envelope](schemas/envelope.schema.json)、
  [Context Packet](schemas/context-packet.schema.json)、
  [Run Result](schemas/run-result.schema.json)、
  [Workflow](schemas/workflow.schema.json) 和
  [Package Signature](schemas/package-signature.schema.json) schema：机器可读契约。
- [Conformance Report](schemas/conformance-report.schema.json) schema：可复现、机器可读的
  实现声明。
- [Conformance](CONFORMANCE.md)：必需测试和 conformance 声明。
- [Conformance Kit](conformance/README.zh-CN.md)：可移植向量、报告示例和精确验证命令。
- [Governance](GOVERNANCE.md)：版本和变更流程。
- [LAP Enhancement Proposals](proposals/README.zh-CN.md)：规范性、兼容性和安全变更的
  公开设计记录。

## 最小本地包

```text
my-agent/
  agent.json
  bin/
    <agent-entrypoint>
  lap-signature.json  # optional, signed publisher provenance
```

运行时会验证清单、启动进程、协商 LAP，并且仅在此后将发布标记为 active。在磁盘上发现
二进制文件绝不代表可以执行它。

可参阅 [Echo Agent 示例](examples/echo-agent/README.zh-CN.md) 获得可运行的 Python 参考
对话；参阅 [Go Echo Agent 示例](examples/echo-agent-go/README.zh-CN.md) 获得使用同一
`lap-local` 交换的 Go 示例；参阅
[Rust Echo Agent 示例](examples/echo-agent-rust/README.zh-CN.md) 获得使用同一交换的
Rust 示例；参阅
[release-check.workflow.json](examples/release-check.workflow.json) 获得已验证工作流图。

## 设计原则

1. **兼容优先于替代。** 在各自领域复用 A2A 和 MCP，而不是创建竞争性线协议。
2. **运行时强制治理。** Agent 可以请求工作；只有 Host Runtime 可以授权、分派、审批、
   取消或结束它。
3. **无歧义热加载。** 新运行解析一个不可变发布；旧发布排空，不会在运行中任务下被替换。
4. **没有隐藏推理的可观测性。** 进度描述真实操作和结果，而不是私有 chain-of-thought。
5. **租户身份具有权威性。** 经认证的 Host 建立它；Agent 不能自行选择或扩大它。

## 状态与范围

`0.1.0-draft` 用于设计评审和参考实现，尚不是稳定兼容性承诺。实现者在生产依赖前，
应通过 issue 或 LAP Enhancement Proposal 报告缺口。

首个 conformance 目标是在 30 分钟内由独立 Host 集成本地可执行文件。已发布的 Python、
Go 和 Rust 参考实现使用相同向量，因此 Local Profile 不与单一语言运行时耦合。远程发现和
委派授权有意叠加在该目标之上。工作流图已在本草案中规定；生产参考 executor 将遵循
Local Profile。

## 验证草案

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

这些检查会验证已发布 schema、conformance 报告、可移植往返向量和通过真实 stdin/stdout
协议交换的本地 Echo Agent。若 Go 或 Cargo 位于 `PATH`，同一套件还会分别运行 Go 或 Rust
参考；公共 CI 使用固定 Go 1.21 job 覆盖 Go 路径。

## 贡献

请阅读 [GOVERNANCE.md](GOVERNANCE.md)。规范性文本、schema 或 profile 的变更需要版本化
提案和 conformance 影响分析。请从 [LEP template](proposals/LEP-template.md) 开始。
