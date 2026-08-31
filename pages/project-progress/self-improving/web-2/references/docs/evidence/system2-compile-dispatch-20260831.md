# System 2 → compile dispatch trust boundary — 2026-08-31

## 结论

本切片把已经通过结构校验的 System 2 规划结果接到了一个应用拥有的
`text2env.compile` 调用边界。Dispatcher 不把 callable 交给模型，而是重新读取并校验
planner 的 prompt、原始回答、decision、终态 receipt、事件顺序、Skill card、当前
descriptor 与 qualification，再将模型给出的参数解析为公开的 typed input 后调用一次
`CompileApplication.invoke_typed()`。

终态会生成三个可重算对象：Harness `Invocation`、完整 `RunState`、以及把规划意图、
精确 Skill 实现、资格、运行结果和 supporting artifacts 串起来的
`TrustedToolReceipt`。成功 compile 只派生两个非物理事实：catalog 身份与 environment
package 身份；blocked/failed 结果不会发布事实，也不会为 preflight 阻断伪造
`Invocation`。

## 信任边界

- planner 的 prompt、decision、receipt 和所有事件必须在 dispatcher 自己的 CAS 中可读，
  且摘要、schema、call id、时间与阶段序列互相一致。
- Planner Skill card 必须与应用当前公开的 descriptor、实现摘要、qualification artifact、
  input/output schema 和重试上限完全一致。
- typed input 内每个 `ArtifactRef` 必须是同一 CAS 的
  `artifact://sha256/<digest>` 对象；外部 locator、foreign CAS、缺失或损坏对象均停止执行。
- 应用返回的 `RunState` 必须是终态，Skill 身份、typed output、artifact closure 和
  Registry 的 Invocation digest 必须可独立重算。
- `StateDelta` 自身带内容摘要；应用前会重验 retained world state 与 retained delta，避免
  Pydantic model 构造后被嵌套可变对象改写。
- compile/static validation 不能成为物理事实。回放、接触、稳定性、可见性和发布资格都
  仍需后续 replay/validate receipt。

## 验证

执行：

```text
python -m pytest -q \
  tests/self_improving/harness/test_system2_dispatcher.py \
  tests/self_improving/harness/test_system2_domain.py \
  --cov=self_improving.harness.system2.dispatcher \
  --cov=self_improving.harness.system2.domain \
  --cov-branch --cov-report=term-missing --cov-fail-under=100
```

结果：97 tests passed；`dispatcher.py` 348/348 statements、146/146 branches，
`domain.py` 196/196 statements、78/78 branches，均为 100%。Ruff、格式检查与
`git diff --check` 同时通过。

攻击测试覆盖 retained state/delta 改写、planner artifact 或事件漂移、Skill/qualification
错配、foreign/missing/corrupt CAS、参数 schema 绕过、应用 CAS 不同、Invocation digest
错配、非终态/矛盾 RunState、typed output 与 supporting artifact closure 漂移，以及失败
路径伪造事实。

## 诚实边界

这些是应用边界的 unit/integration tests，使用 synthetic application、qualification 和
Registry 结果 fixture；它们不是一次新的真实环境编译。当前 checked-in
`text2env.compile@1.0.0` qualification 已因并行收紧的 asset-admission、ledger 与 Registry
实现发生源码漂移，生产 application 必须 fail closed。只有共享实现冻结后重新生成并
复核 compile qualification，再用真实非空 catalog 执行 System 2 → Registry → compile，
才能声称“agent 驱动 compile 跑通”。

