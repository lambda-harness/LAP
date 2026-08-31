# LAP Model Relay Agent（草案）

这个可运行的 Python Agent 演示拟议的 `lap-model-relay/0.1` 交换。它不包含提供方 URL、
API Key 或直连模型客户端，而是通过 LAP stdio 向 Host 请求一次有界模型响应。

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> model.request
model.response -> run.progress -> run.result
```

在仓库根目录运行确定性的草案探针：

```bash
python tools/lap_model_relay_probe.py --package examples/model-relay-agent
```

对于任意已声明 capability，请通过 `--capability` 与 `--input` 显式提供有效 JSON。

探针会模拟 Host 响应，并验证协议身份、Profile 协商、Context Packet 路由、请求幂等、关联
响应和已声明的 capability 输出。它不会调用模型提供方、证明部署出口隔离、安装该包或认证
Host Runtime。严格预算与隔离要求见 [LEP-0009](../../proposals/LEP-0009-host-model-relay.md)。
