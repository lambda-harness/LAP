# LAP: Lattice Agent Protocol

[![Verify LAP Draft](https://img.shields.io/github/actions/workflow/status/lambda-harness/LAP/verify.yml?branch=main&style=flat-square&label=verify)](https://github.com/lambda-harness/LAP/actions/workflows/verify.yml)
[![Protocol status](https://img.shields.io/badge/protocol-0.1.0--draft-5b7c99?style=flat-square)](SPEC.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-3da639?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square)](.github/workflows/verify.yml)

> **Orchestrate Any Agent. Connect Everything.**

多数 Agent 系统可以调用工具，却无法把独立开发的 Agent 安全地做成可安装、可识别、可
治理、可观测、可组合的单元。LAP 为 Host Runtime 提供一份可移植的生命周期契约，让已
准入的本地可执行文件、原生运行时 Agent 和远程 Agent 可以可靠协作，同时不牺牲租户边界
和运行控制权。

LAP 有意保持边界清晰。它**不**取代已有标准：

- [MCP](https://modelcontextprotocol.io/) 连接模型和 Agent 与工具、资源及提示词。
- [A2A](https://a2a-protocol.org/latest/) 连接独立的远程 Agent。
- LAP 定义可安装、可治理 Agent 的生命周期和运行时契约，包括本地二进制 Agent 与
  A2A 支撑的 Agent。

## 一份契约，多种 Agent 实现

<p align="center">
  <img src="assets/lap-architecture.png" alt="LAP 架构图：可信 Host Runtime 编排本地可执行、原生运行时和远程 Agent，并连接 MCP 工具与资源，统一治理身份、能力授权、监督、进度、交付物、取消与终态结果。" width="1200" />
</p>

LAP 治理 Agent 边界；MCP 仍是工具与资源边界；A2A 仍是远程 Agent 互操作边界。Host
Runtime 是控制点：它准入发布、授予 capability、监管运行并记录结果。

## 快速开始

LAP 是规范与 conformance 工具包。无需托管服务、API Key 或全局安装，即可验证 Local
Profile。

**前置条件：** Git 和 Python 3.11 或更高版本。仅运行 Node.js 参考 Agent 时需要 Node.js 18
或更高版本。公共 CI 验证 Python 3.11、3.12、3.13 以及 Node.js 22。

### 1. 克隆并准备环境

```bash
git clone https://github.com/lambda-harness/LAP.git
cd LAP
python -m venv .venv
```

Windows PowerShell 中激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS 或 Linux 的 POSIX shell 中激活环境：

```bash
source .venv/bin/activate
```

### 2. 安装检查依赖并运行已发布交换

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

该套件会验证已发布的 schema 和向量，随后通过真实 stdin/stdout LAP 交换驱动 Python
Echo Agent。若 `PATH` 中有 Node.js、Go 或 Cargo，还会运行相应语言的参考实现。

### 3. 探测外部 Agent 包

Agent 作者可以对任意包 `agent.json` 中声明的精确入口执行一次有界、机器可读的 Local
线协议探测：

```bash
python tools/lap_local_probe.py --package /path/to/my-agent
```

多 capability 包必须显式选择一个 capability，并提供符合其契约的 JSON 输入：

```bash
python tools/lap_local_probe.py --package /path/to/my-agent \
  --capability task.run \
  --input '{"task":"verify the release"}'
```

该探测器绝不通过 shell 启动命令。它会验证包清单、所选输入和成功输出契约、Local 握手
身份、有序 stdout 帧、关联 ID、运行身份以及唯一终态结果。它只执行包中已经声明的命令，
因此仅应对愿意实际执行的代码运行。其 JSON 报告有意不包含探测输入、原始 Agent 输出、
命令参数或包路径。它是 Agent 侧证据，不是 Host Runtime 认证或授权边界。

### 4. 选择下一条集成路径

- **构建本地 Agent：** 从可运行的
  [Python](examples/echo-agent/README.zh-CN.md)、
  [Node.js](examples/echo-agent-node/README.zh-CN.md)、
  [Go](examples/echo-agent-go/README.zh-CN.md) 或
  [Rust](examples/echo-agent-rust/README.zh-CN.md) Echo Agent 开始。要构建由 Host
  监管的多 Agent 工作流，请使用可运行的
  [Python](examples/orchestrator-agent/README.zh-CN.md)、
  [Node.js](examples/orchestrator-agent-node/README.zh-CN.md) 或
  [Go](examples/orchestrator-agent-go/README.zh-CN.md) 外部编排 Agent。
- **构建 Host Runtime：** 阅读 [Core Specification](SPEC.md)，再使用
  [Conformance](CONFORMANCE.md) 形成可复现的实现声明。
- **组合受治理的工作流：** 使用 [Workflow Profile](profiles/workflow.md) 与已经验证的
  [工作流示例](examples/release-check.workflow.json)。
- **验证草案 Model Relay：** 通过
  [参考 Agent](examples/model-relay-agent/README.zh-CN.md) 运行
  `python tools/lap_model_relay_probe.py --package examples/model-relay-agent`。
  它只验证确定性的草案交换，不对提供方、隔离、计量或 Host conformance 作出声明。

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
| 发现和安装 | 版本化 `agent.json` 清单、已声明 profile 和包 profile。 |
| 运行本地二进制 | 通过受监管 stdin/stdout 使用 `lap-local` UTF-8 NDJSON。 |
| 调用远程 Agent | 使用协商 A2A 语义的 `lap-a2a-bridge`。 |
| 观察工作 | 有序的进度、artifact 和终态事件。 |
| 安全停止和重试 | 幂等键、截止时间、取消和不可变终态。 |
| 治理租户 | 运行时派生的租户身份和有作用域的 capability grant。 |
| 组合 Agent | 面向可信 supervisor 的父/子谱系，以及不可变的 Agent 与 capability 作用域。 |

## 文档

- [Core Specification](SPEC.md)：术语、envelope、生命周期、治理和兼容规则。
- [Local Stdio Profile](profiles/local-stdio.md)：面向受监管外部 Agent 实现的规范性
  本地进程传输 profile。
- [A2A Bridge Profile](profiles/a2a-bridge.md)：受管远程 A2A Agent 的互操作规则。
- [A2A Inline Inputs Profile](profiles/a2a-inline-inputs.md)：将明确授予的小型 Host
  输入 artifact 以 A2A `FilePart.bytes` 有界传输给已准入 A2A Skill 的可选 profile。
- [Package Signing Profile](profiles/package-signing.md)：面向可移植 Agent Package 的
  可选 Ed25519 发布者来源证明。
- [Workflow Profile](profiles/workflow.md)：具有运行时强制分派边界与可移植外部编排器
  规划上下文、用户拥有的版本化 Agent 图。
- [Host Metering Profile](profiles/host-metering.md)：面向可强制执行的工作流输入和成本
  预算的可选 Host 直连模型计量。
- [Model Relay Profile（草案）](profiles/model-relay.md)：面向外部 Local Agent 的
  Host 可观测模型请求路径；在实现前不会放宽当前对外部预算的默认拒绝。
- [Model Relay Probe](tools/lap_model_relay_probe.py)：面向作者的、确定性的 Local
  stdio 草案请求/响应检查；它绝不调用提供方，也不认证 Host Runtime。
- [Go Agent SDK](sdk/go/README.zh-CN.md)：无依赖的本地 Profile Agent 侧辅助工具；它不是
  Host Runtime，也不是 conformance 认证。
- [Agent Manifest](schemas/agent-manifest.schema.json)、
  [Envelope](schemas/envelope.schema.json)、
  [Context Packet](schemas/context-packet.schema.json)、
  [Run Result](schemas/run-result.schema.json)、
  [Workflow](schemas/workflow.schema.json)、
  [Orchestrator Context](schemas/workflow-orchestrator-context.schema.json) 和
  [Orchestrator Output](schemas/workflow-orchestrator-output.schema.json) 以及
  [Package Signature](schemas/package-signature.schema.json) schema：机器可读契约。
- [Conformance Report](schemas/conformance-report.schema.json) schema：可复现、机器可读的
  实现声明。
- [Conformance](CONFORMANCE.md)：必需测试和 conformance 声明。
- [Conformance Kit](conformance/README.zh-CN.md)：可移植向量、报告示例和精确验证命令。
- [Local Agent Probe](tools/lap_local_probe.py)：无需 Host Runtime，对一个已声明
  `lap-local/0.1` capability 执行的 Agent 作者侧可执行检查。
- [Governance](GOVERNANCE.md)：版本和变更流程。
- [LAP Enhancement Proposals](proposals/README.zh-CN.md)：规范性、兼容性和安全变更的
  公开设计记录。

## 草案迁移

当前草案在 canonical `io.github.lambda-harness.lap.*` 命名空间下使用
`lap-workflow/0.2` 和 `lap-a2a-inline-inputs/0.2`。此前的 `0.1` profile 与键标识
仅是历史记录，不是别名。升级外部工作流 Agent 时，需要重新构建其包、更新已声明和协商的
profile，然后重新激活精确发布；Host 不会为了兼容性发送两份 Context Packet 键。请参阅
[LEP-0008](proposals/LEP-0008-canonical-profile-namespaces.md)。

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

Local 包声明 `profiles` 后，Host 可以在发现和工作流预检时展示其预期契约。该声明不授予
任何权限，也不能替代每次运行必需的 profile 协商。

Host 也可以在激活期间探测已声明的依赖 profile。成功的激活验证是绑定到精确已验证发布的
Host 本地证据；它不授予任何权限，也不能替代每次运行必需的 profile 协商。

可参阅 [Echo Agent 示例](examples/echo-agent/README.zh-CN.md) 获得可运行的 Python 参考
对话；参阅 [Node.js Echo Agent 示例](examples/echo-agent-node/README.zh-CN.md) 获得使用
同一 `lap-local` 交换的 Node.js 示例；参阅
[Go Echo Agent 示例](examples/echo-agent-go/README.zh-CN.md) 获得使用同一交换的 Go
示例；参阅 [Rust Echo Agent 示例](examples/echo-agent-rust/README.zh-CN.md) 获得使用同一
交换的 Rust 示例；参阅
[Node.js 外部编排 Agent 示例](examples/orchestrator-agent-node/README.zh-CN.md) 了解 Node.js
外部工作流规划器；参阅
[Go 外部编排 Agent 示例](examples/orchestrator-agent-go/README.zh-CN.md) 了解 Go 外部工作流
规划器；参阅 [release-check.workflow.json](examples/release-check.workflow.json) 获得已验证工作流图。

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
Node.js、Go 和 Rust 参考实现使用相同向量，因此 Local Profile 不与单一语言运行时耦合。
远程发现和委派授权有意叠加在该目标之上。工作流图已在本草案中规定；生产参考 executor
将遵循 Local Profile。

## 贡献

请阅读 [GOVERNANCE.md](GOVERNANCE.md)。规范性文本、schema 或 profile 的变更需要版本化
提案和 conformance 影响分析。请从 [LEP template](proposals/LEP-template.md) 开始。
