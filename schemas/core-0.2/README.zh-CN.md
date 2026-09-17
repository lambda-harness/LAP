# Core 0.2 Schema 基础

这些 Schema 是已接受 LEP-0010 的草案材料，不构成已发布的 Core 0.2
conformance 声明。Core 0.1 的 Schema 与运行时行为保持不变。

- `envelope.schema.json` 校验版本化流身份、显式发送方角色、必填的
  Run/关联/幂等字段，以及通过稳定 `$defs` 片段定义的全部 Core payload。
- `message-registry.json` 校验注册表结构，并要求每个消息条目指向其 payload
  片段。
- `registry.json` 记录发送方、关键性、payload 片段、状态机位置和实现状态。
- `state-machine.json` 固定激活、Run 与流事件的合法状态。
- `../../conformance/core-0.2-wire.json` 为全部 19 类消息提供正向案例，并为
  发送方、幂等性、Artifact、输入、终态结果和 ACK 约束提供反向案例。

payload 契约已完整定义为草案材料。只有 Host 用正反向向量和运行时 conformance
证据实现后，对应条目才可从 `draft` 标为 `implemented`。Schema 校验本身不能证明
传输对端身份、epoch fencing、持久 ACK、重放、授权或终态正确性。

`sender` 字段使预期协议角色可被机器校验，但它不是授权声明：传输适配器必须在
应用帧之前，将其与已认证或已协商的对端进行比对。

ACK 消息不得请求 ACK。其关键性只表示它传递了持久水位，而不是让对端形成
ACK-of-ACK 循环。
