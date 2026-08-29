# LAP Enhancement Proposals

LAP Enhancement Proposal（LEP）是 LAP 规范性行为、schema、profile、兼容规则或
安全边界变化的长期公开记录。

## 发起提案

1. 使用 [LEP issue form](../.github/ISSUE_TEMPLATE/lep.yml) 发起讨论。
2. 将 [LEP-template.md](LEP-template.md) 复制到本目录，并按
   `LEP-XXXX-short-title.md` 命名，填写所有适用章节。
3. 通过 pull request 提交。维护者在提案进入正式评审时分配下一个四位编号。
4. 在接受、实施、拒绝、撤回或取代的整个过程中保持提案状态最新。

提案是决策记录。相应的规范、schema、profile、示例和 conformance 变更仍然是
可执行行为的来源。

## 何时必须有 LEP

只要一项变更影响下列任一领域，就必须创建 LEP：

- 必需或禁止的线协议行为、envelope 字段、错误、生命周期或传输规则；
- profile、schema、capability、扩展边界或 conformance 断言；
- 兼容性、版本、租户隔离、授权、包信任、审计、计量或安全行为；
- 移除或改变已经在先前 LEP 中接受的行为的发布。

不改变有效行为的编辑性修正和示例可以使用普通 pull request。请在该 pull request 中
说明为何不需要 LEP。

## 当前 LEP

| LEP | 状态 | 目标 | 摘要 |
|---|---|---|---|
| [LEP-0001](LEP-0001-a2a-inline-inputs.md) | Draft | `0.1.0-draft` | 可选、有界的 A2A 内联输入 artifact 传输。 |
| [LEP-0002](LEP-0002-scoped-workflow-release-admission.md) | Implemented | `0.1.0-draft` | 用于排空工作流发布的根作用域、Host 私有准入。 |
| [LEP-0003](LEP-0003-capability-scoped-orchestrator-dispatch.md) | Implemented | `0.1.0-draft` | 面向编排器派遣的可选、按 Agent 收窄的 capability 范围。 |
| [LEP-0004](LEP-0004-portable-orchestrator-context.md) | Implemented | `0.1.0-draft` | 面向外部编排器的可移植 Context Packet 规划视图。 |
| [LEP-0005](LEP-0005-local-workflow-profile-negotiation.md) | Implemented | `0.1.0-draft` | 外部 Agent 接收工作流编排上下文前的逐运行 Local 协商。 |
| [LEP-0006](LEP-0006-manifest-profile-declaration.md) | Implemented | `0.1.0-draft` | 可发现的包 Profile 声明，以及工作流预检和逐运行证明。 |
| [LEP-0007](LEP-0007-activation-verified-workflow-profile.md) | Implemented | `0.1.0-draft` | 已声明 Local Workflow Profile 的可选激活期证据，不削弱逐运行证明。 |
