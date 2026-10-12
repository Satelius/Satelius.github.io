# 术语表

| 术语 | 项目里的意思 | 延伸阅读 |
| --- | --- | --- |
| VTLA | Vision-Tactile-Language-Action；把视觉、触觉、语言、机器人状态和动作放进同一版本化合同 | [VTLA 服务边界](modules/vtla-contracts.md) |
| campaign | 跨采集、筛选、训练、服务、评测和门禁的耐久工作图，不等于一次 episode | [campaign 运行时](modules/agentic-runtime.md) |
| episode | 一个 task+seed 的有限环境交互；重试时 identity 不变，attempt 增加 | [smoke 评测导读](walkthroughs/one-real-run.md) |
| EvaluationRequest | 固定 episode、插件、指标、执行后端和输出身份的版本化评测请求 | [smoke 评测导读](walkthroughs/one-real-run.md) |
| attempt | 某个 episode 或 stage 的一次执行尝试，拥有独立进程/日志/证据边界 | [smoke 评测导读](walkthroughs/one-real-run.md) |
| provider | 外部环境、任务或研究栈的来源与兼容实现；源码存在不代表 end-to-end | [Provider 与成熟度](modules/providers.md) |
| adapter | 把 provider、硬件、触觉或模型的 native 类型转换为核心合同的窄边界 | [VTLA 服务边界](modules/vtla-contracts.md) |
| DataEngine | 只读的数据目录、血缘、证据和同步回放应用，与同名第三方项目无关 | [证据与回放](modules/evidence-and-data-engine.md) |
| registry | 保存内容寻址 artifact record 的目录；记录身份由内容摘要决定 | [证据与回放](modules/evidence-and-data-engine.md) |
| gate | 检查精确依赖证据并给出 pass/fail/blocked/waived 的机器结论 | [campaign 运行时](modules/agentic-runtime.md) |
| end-to-end | 真实资产/checkpoint/环境完成运行且证据被保留；高于声明、可导入和组件测试 | [Provider 与成熟度](modules/providers.md) |

## 采训推角色与轨迹

**编排 Agent（Agent Harness）**：由前沿模型驱动、组织采集、训练与评测实验的上层智能体，与直接选择机器人动作的策略模型分开。
_避免混称_：机器人策略、TacJev。

**TacJev**：接收多模态观测与任务信息、预测离散元动作的下层机器人策略模型。
_避免混称_：编排 Agent、整个采训推系统。

**在线多模态教师**：根据当前运行环境的多模态观测，在线选择机器人动作标签的模型。
_避免混称_：编排 Agent、源动作重放、几何脚本教师。

**几何脚本教师**：由程序根据几何状态与反馈选择任务动作的控制来源。现有 `ArenaLiftTeacher` 读取特权仿真状态、输出连续相对 IK 动作；`ArenaFeedbackMetaTeacher` 在执行前选择九 token，再由同一动作解释器执行，其[脚本研究参考验收](walkthroughs/arena-reference.md)与在线模型教师验收分开。
_避免混称_：在线多模态教师、学生 TacJev、只检查组件的固定元动作计划。

**元动作（meta action）**：策略选择的离散操作，由本体对应的动作解释器展开为机器人控制过程；一个元动作不必对应一个物理帧。
_避免混称_：物理帧、原生连续动作。

**控制来源**：一段轨迹中实际决定机器人动作的主体或参考，例如源轨迹、教师、学生策略或人工控制。
_避免混称_：编写采集代码的主体。

**执行时元动作标签**：执行前实际选定、经动作解释器落地的元动作标签，与决策前观测和实际执行过程关联。
_避免混称_：连续动作的事后离散化标签。

**配对案例验证**：在可比较的条件下，对原方案与一次证据驱动调整的运行结果作对照；结论限于所验证案例。
_避免混称_：统计成功率提升、多轮自进化验收。

**模型可见观测**：某次动作决策实际提供给模型的信息集合，与用于控制、审计和任务判定的信息分别声明。
_避免混称_：所有被记录的仿真信息。

**固定姿态保持**：本体控制维持预先声明的末端姿态，不由动作教师选择新的姿态。
_避免混称_：教师旋转决策、基于物体真值的姿态规划。

**开发与训练采集池**：用于采集开发、诊断、对照及生成训练候选数据的环境开局集合。
_避免混称_：持出评测集。

**迭代验证池**：用于后续候选模型选择的独立环境开局集合，其结果可反馈迭代。
_避免混称_：最终测试池。

**最终测试池**：预留给学生最终评测、未用于训练采集或迭代选择的环境开局集合。
_避免混称_：反复调试使用的开局。

**服务中断**：动作模型服务无法完成当前决策而终止一次采集尝试的结果，与原生任务判定分别记录。
_避免混称_：完整预算任务失败。

**训练采纳标记**：声明某条已保留记录是否进入特定训练视图的标记，保留实际动作及其依据。
_避免混称_：删除失败记录、事后替换正确动作。

角色、输入及验收边界见[rollout 与 TacJev 合同梳理](../docs/TACJEV_ROLLOUT_CONTRACT.md)。
