# LAP Conformance Kit

本目录提供稳定、机器可读的 LAP 0.1 互操作检查材料。它刻意保持精简：套件验证公开
线协议，而每个 Host 仍需用实现本地测试证明自己的策略、存储、隔离和监管行为。

## 可移植内容

`local-stdio-roundtrip.json` 是标准 `lap-local/0.1` 交换。它包含成功运行的 Host
帧与预期 Agent 消息序列。兼容的本地 Agent 可以接收相同 Host 帧，并验证向量中记录的
不变字段。其 Context Packet 包含带摘要的 `lap://run/input/...` artifact 引用；该向量
验证公开引用形态，而不是 Host 的私有暂存目录。

仓库测试会根据 Core schema 验证该向量，并用它运行 Python、Go 和 Rust 参考 Echo Agent。
这能以独立 Host 或 Agent 作者可复现的形式发现协议漂移。

`tools/lap_local_probe.py` 允许 Agent 作者直接驱动包中声明的 `lap-local` 命令。它会将公开
Host 帧形态适配为一个已选择的声明 capability 和 JSON 输入，随后验证成功握手、有序 Agent
帧、运行身份、终态结果和已声明输出契约。它绝不安装该包或授予其权限，机器可读报告也有意
排除原始输入、Agent 输出、命令参数和包路径。该探测器是 Agent 实现的证据，而不是 Host
conformance 认证。

`host-metering.json` 是确定性的 `lap-host-metering/0.1` 算术向量。它涵盖最坏情况
预留、提供方报告的缓存用量，以及用量缺失时必需的完整预留回退。它不证明 Host 的私有
提供方集成或价格校准；这些属于实现本地 conformance 义务。

`model-relay.json` 是 `lap-model-relay/0.1` 的草案治理向量。它固定 Local Profile
协商、有界路由上下文、请求/响应 payload、幂等重放和 provider 调用前拒绝条件。它不让
该 Profile 变得可声明：已发布的 Core 尚未注册 relay 帧类型，真实 Host 仍需证明提供方
适配器和部署隔离。

`tools/lap_model_relay_probe.py` 会通过确定性的 stdin/stdout 交换驱动已发布的 Python
Relay 参考实现。它验证草案 Profile 握手、路由上下文、幂等键、关联响应和终态输出契约，
不会调用提供方。它是 Agent 侧的草案证据，不是 Host 计量或沙箱认证。

`workflow-release-admission.json` 定义排空外部发布的 Host 私有根作用域：精确的租户、
会话、根运行和发布集合。它列出可继续执行的匹配子任务，以及不得启动目标 Agent 的跨
作用域、已关闭和伪造 admission 情形。admission token 本身刻意不出现在任何 LAP
envelope 中；实现通过本地生命周期测试证明私有注册表行为。

`workflow-capability-scopes.json` 定义 `lap-workflow/0.2` 的 capability 收窄动态
派遣。它区分一个可接受的 Agent-capability 对，以及不得启动目标 Agent 的三类拒绝：
不在不可变 allow-list 的 Agent、Agent 已声明但不在其 scope 内的 capability、以及未声明
的 capability。它还包含缺少或多出 scope key 的文档，要求 Host 在 JSON Schema 之外进行
语义校验。

`workflow-orchestrator-context.json` 定义 Host 提供给外部 `orchestrator` 节点的精确
Context Packet 扩展。它验证稳定排序的 Agent-capability 规划视图、可复用的派遣输出 schema
以及独立的 A2A JSON data part 映射；同时列出私有字段泄漏、scope 越界和 A2A 缺失 JSON 输入
支持时必须在外部任务或目标 Agent 启动前发生的拒绝。对于 Local 外部编排器，它同时记录
`agent.json.profiles` 预检声明、声明 `FLOW-16` 的 Host 可选执行的激活探测，以及独立的实时
`agent.hello` / `agent.welcome` 证明。workflow Profile 缺失会以 `LAP-204` 在工作开始前
失败；激活探测失败会使候选发布保持 inactive 和 unverified，但每次调用仍必须完成实时证明。

`a2a-inline-inputs.json` 是确定性的 `lap-a2a-inline-inputs/0.2` 准入向量。它验证
清单 opt-in、Host 策略和所选 Skill MIME 三道门；精确的 A2A `FilePart.bytes` 映射；
以及安全元数据。它有意不证明远程 Agent 的保留或删除行为；那仍是管理员信任决策，
而不是 conformance 声明。

## 一个声明必须包含什么

conformance 声明是符合
[`../schemas/conformance-report.schema.json`](../schemas/conformance-report.schema.json)
的 JSON 文档。它标识实现、版本、profile、精确命令、套件版本、执行时间，以及每个
已声明断言的结果。

报告是证据，不是自我签发的认证。`not_applicable` 仅在断言不属于声明 profile 时有效。
`passed` 断言必须包含简明、可复现的证据引用。

## 运行已发布检查

```bash
python -m pip install -e ".[dev]"
python -m pytest

# 对一个包入口运行有界的 Agent 侧 Local 线协议探测。
python tools/lap_local_probe.py --package /path/to/my-agent \
  --capability task.run \
  --input '{"task":"verify the release"}'
```

该命令会验证全部已发布示例、schema、报告示例和 Python 本地往返流程。若 Go 和 Rust
可用，它还会使用相同向量驱动这两个参考实现；公共 CI 保证三条路径。Host 在声明
`CONFORMANCE.md` 中的条目前，应补充生命周期竞争、租户隔离、策略和存储恢复的
实现专属覆盖。
