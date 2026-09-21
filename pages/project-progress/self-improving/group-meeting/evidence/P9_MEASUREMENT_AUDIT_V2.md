# P9 v2 测量与解释只读审计

日期：2026-09-21。范围：P9 B1/B2 evaluator、staged runner、请求遥测、矩阵 provenance 与离线汇总。审计期间 v2 正在运行；本审计不改变运行代码、配置、provider、GPU 状态或冻结实验。行号指审计时源码，后续以函数名定位。

## 结论与证据边界

- **verified（静态源码）**：未发现上述测量路径替换 RoboLab 原生成功判定。P9 `ranking_sort_key` 的排序顺序符合冻结合同。
- **inference**：下面问题主要影响次级阶段指标、可复核性和报告解释；仅据此次静态审计，没有充分理由中断已启动的 v2。是否满足发布条件仍须检查完整运行产物。
- **unknown**：本审计未检查 v2 全部 episode，不声明其真值覆盖完整、任务结果正确或 provider 已恢复稳定。
- 测量修复须区分离线派生结果与下一次运行版本，不能静默改写原始 summary/steps/requests。保留原始产物，记录修订算法、版本和受影响 episode。

## 发现

### 1. 高：有效抓取、搬运和释放采用代理条件，掉落不撤销持物状态

**verified**：`core/sim/staged_evaluator.py:248–272` 用 CLOSE 命令及 GRASP 后物体升高至少 3 cm 标记有效抓取，没有使用实际接触；`:274–313` 用后续 XY 位移至少 2 cm 标记搬运，只有 RELEASE/auto-release 清除当前 `_valid_grasp`。掉落本身不清除它。

**影响（inference）**：被碰起的物体可能满足抓取代理条件；曾抬起后掉落的物体随后滑动、被推或空手释放，也可能被计为 carry/release。此问题不改变原生 success，但会影响同成功数的次级排名。

**处理**：本轮以“GRASP 后抬升代理事件”准确标注，并复核所有达到 valid_grasp/carry/release 的原始轨迹和关键帧。可离线派生掉落提示，但现有 centroid 数据不足以独立证明真实接触/持续持物；无法判明时标 unknown。下一版本分开记录“曾达到抬升阈值”和“当前仍持物”，预先声明新增规则；未经预注册不得用临时新规则重排本轮结果。

### 2. 高：真值不可用时，阶段缺事件仍被写作 false

**verified**：evaluator `:333–345` 对缺事件统一输出 false，即使 truth coverage 为 0；`scripts/robolab/summarize_model_benchmark.py:615–626` 将 false 转为 0，`:1195–1199` 纳入次级排序。`:180–181` 的 available 只统计物体 centroid，不代表目标 centroid 或完整 episode 时序均可用。

**影响**：unknown 可能被解释为观察到的失败；已有少量覆盖也可能掩盖缺测区间。

**处理**：离线核查逐步 object/target 覆盖、initial snapshot、缺口位置，单独发布coverage。真值相关事件缺测时标unknown，不把未知补零；命令事件可独立保留。下一版本加入按指标定义的可观测性。v2 不具备完整所需覆盖时暂停阶段排名，原生成功结果仍可独立报告。

### 3. 中：planner 日志 profile token预算不等于实际请求预算

**verified**：`scripts/run_robolab_staged.py:275` 设置 planner override（默认4096）；`plugins/subgoal/agent.py:127` 以 override 调用，`:256` 存在 diagnostics；runner `:928` 写出的 descriptor 却由 `:91–98` 读取 client.max_tokens，`:106–121` 的 telemetry allowlist 不保留 diagnostics.max_tokens。

**影响**：仅查看 requests.model.max_tokens 会误判 planner 截断预算。

**处理**：本轮根据冻结调用链/配置注明“重建的实际planner预算”，不要声称日志已直接记录线上的每次请求预算。下一版本记录 actual_request_max_tokens、字段名及profile预算，必要时区分补救子请求。actor 路径也应核对实际 override。

### 4. 中：关键帧引入额外渲染，step loop计时未覆盖

**verified**：runner `:1217–1221` 的阶段关键帧与 `:815–822` 的恢复关键帧调用 `_images`；`:1088–1089` 进入 `core/sim/calibrated_wrist.py:34–36`，执行三次render。`:1207` 的 loop_s 已在阶段关键帧采集前记录。上述调用没有直接执行物理step。

**影响（inference）**：墙钟、吞吐、900秒预算含部分诊断开销；loop_s不完整包含此开销。不能把P8与P9墙钟差异全部归因模型或控制能力。

**处理**：本轮明确计时口径和未单独测量的诊断开销；后续版本固定相同采集策略。下一测量版本增加采集耗时，或复用既有画面，作为测量变更登记。不要离线猜测并扣减固定耗时。

### 5. 中：source hashes未覆盖全部实际依赖

**verified**：`scripts/robolab/benchmark_models.py:135–165` 的列表缺少 staged_evaluator.py、visual_recovery.py、calibrated_wrist.py及选定overlay继承的visual_recovery/openrouter配置等模块。`:185` 另存Git commit，但文件哈希策略不能发现同HEAD下这些文件的未提交修改。

**影响**：resume fingerprint不足以独立证明全部行为依赖未变。

**处理**：本轮核查运行时commit及关键依赖的变更证据；保存补充文件hash清单，并明确它是补充快照，不能追溯证明未观察的时段。下一版本哈希完整配置继承链和实际执行依赖。运行期间避免编辑任何冻结依赖。

### 6. 中：汇总未消费新 evaluator 的物体运动字段

**verified**：summarizer `:381–386` 读取顶层 object/target；实际runner记录在 evaluator_truth。`:567–595` 的summary候选路径未包含 stage_progress.object_motion。

**影响**：已有物体位置、距离、抬升证据可能仍显示null。

**处理**：可在运行结束后用新版本离线汇总器读取显式新schema，保留旧汇总及输入hash，不需重跑。centroid到bowl的距离不是左右/前后关系任务的完整完成度，发布时须标作诊断量。

### 7. 中：逻辑失败与HTTP尝试失败混入同一errors计数

**verified**：summarizer `:229–231` 加逻辑error，`:263–268` 又把 attempt_error_counts 加到同一counter。

**影响**：最终失败请求可能重复计算，已恢复重试也混入errors；errors之和不能直接当逻辑失败数。

**处理**：可离线分别汇总logical_errors、http_attempt_errors、recovered_retry_requests及episode infrastructure failures，保留attempt coverage。若原始日志不足则明确unknown，不通过总数相减猜测。

### 8. 低：排名解释与报告分母残留P7

**verified**：summarizer `:1190–1205` 的P9实际排序正确；`:1143–1159` ranking_components仍展示P7旧指标且缺direction_switch；`:1672–1676` Markdown分母硬编码45/15/12。当前请求汇总没有finish_reason/truncated/output_protocol专门统计。

**处理**：可离线修复matrix特定解释、采用expected分母33/11/0，并补充截断/协议/补救覆盖统计。发布前以P9合同逐项核对排序解释与完整episode表，不需重跑。

### 9. 待实施：跨版本严格配对比较

**verified（当前范围）**：现有summarizer提供单矩阵聚合，没有上一版本输入及 configuration/task/seed 的严格配对比较路径。

**影响**：基线阶段可以独立发布；首次功能实验后若仅比较总数，不能完成已承诺的同格配对归因。

**处理**：首次功能实验前实现离线配对工具，拒绝缺失、重复和任务seed不一致，显示每格变化与覆盖；预先固定比较规则，不增加实验运行。

### 10. 中：requests日志扫描不足以独立证明实际出站请求无真值

**verified**：runner `_actor_decision:958–973` 传入任务、子目标、历史、夹爪状态、两视角和恢复上下文，proprio=None；`_log_step:1160–1201` 独立采样并写 evaluator_truth。requests记录是选定遥测字段，不是完整序列化HTTP body。

**影响**：在requests日志里未找到truth字段，只能证明该日志未包含这些字段，不能单独证明provider实际收到的内容无泄漏。静态调用链隔离提供支持，但不等价于完整运行期出站验证。

**处理**：将此前“日志未发现真值”保持为窄结论，并注明静态调用链支持隔离。下一测量版本可在序列化边界做内存中的结构/内容断言，持久化仅布尔结论、边界版本及非敏感摘要，避免写入密钥、完整base64或私密文本。v2不得补造不存在的出站审计记录。

### 11. 低：首次下降的口径需精确展示

**verified**：evaluator `:216–220` 仅将执行 MV_DOWN 且该次TCP z下降至少6 mm计为首次下降。

**影响**：不是任意实际下降，也不是多步累计下降；小步动作或伴随动作的下降不会计入。

**处理**：保持冻结定义，报告写明“单次MV_DOWN实测下降≥6 mm”。后续若引入自适应细步长，需预先处理定义可比性，不能沿用含糊的“未下降”解释。

## v2发布门禁

- [ ] 验证33个唯一 runnable cell、11配置、三个原task/seed、冻结预算及模型effort；基础设施失败与原生失败分开。
- [ ] 核查每条原生success的来源与证据；不以阶段proxy代替任务成功。
- [ ] 核查object/target逐步覆盖及initial snapshot；缺测保持unknown，不能据缺测进行阶段排名。
- [ ] 复核所有valid_grasp/carry/release候选，报告代理定义、掉落疑点及无法判明的情况。
- [ ] 明确profile预算与实际planner override、输出协议、截断及日志覆盖；不把推断预算伪装成实际请求采样。
- [ ] 拆分逻辑失败、HTTP尝试失败、已恢复重试和episode基础设施失败。
- [ ] 以正确新schema导出物体运动；修正P9分母与排名解释，保存离线派生版本和输入hash。
- [ ] 说明额外render和计时边界；保留原始时延，不估算扣除未知开销。
- [ ] 记录冻结依赖检查及provenance缺口；补充快照不追溯声称全程已审计。
- [ ] 对provider无真值泄漏使用准确证据表述：日志扫描 + 静态调用链支持，缺少完整出站独立验证。
- [ ] 原始产物只读保留；发布修订说明与未解决问题。首次功能实验前完成严格配对工具。

以上门禁均为待核查事项，不表示已经执行通过。
