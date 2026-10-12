# Arena正式在线教师首批续接验收（2026-10-12）

在线采集入口、预算内真实教师运行、正式Agent诊断配对、独立发布与DataEngine回读完成。**合格示范未达成：两次完整物理预算运行均未成功、零接触。** 原生启动额度已耗尽并关闭；本阶段不继续推理、原生运行、抖动研究、TacJev训练或扩大采集。

本目录保留原始数据、失败和负结果。最终机器可读验收见[phase_acceptance.json](phase_acceptance.json)，检查记录见[validation/checks.json](validation/checks.json)。仓库实现与任务记录在`bingsheng`；运行时源码各自在`attempt-a/code/`、`attempt-b/code/`及其`code_receipt.json`中固定，最后发布修复另存`publication_code/`。提交收据见[closure_receipt.json](closure_receipt.json)。

## 实际在线证据

服务目录查询HTTP200，实际三图预检及两个在线运行均固定请求/响应声明`gpt-6.1-sol`、`chat_completions`协议、温度0。预检返回合法`MV_FWD`。这验证服务接受真实三图请求并返回合法token；响应型号仍是服务声明，未独立认证后端权重。[教师身份](teacher_identity.json)、[预检](teacher_inference_preflight/inference.json)。

教师只看到场景图、腕部图、双指触觉拼图、完整任务和最近最多五个已执行移动token。精确状态用于控制与审计，未传给教师。每个决策保存决策前图像、实际JSON请求、脱敏响应和原响应哈希、合法token、HTTP前后冻结状态及实际执行区间；独立读取验证场景/目标计时器/动作历史冻结与唯一执行。离线记录保持原身份。

- **A：25mm／hold5原基线**。50决策、52推理请求（两次35秒超时后同请求重试成功）、250控制帧／5秒。原生未成功、无接触。[报告](attempt-a/report.json)、[全帧视频](attempt-a/rollout_h264.mp4)、[决策目录](attempt-a/decisions/)、[逐帧数据](attempt-a/native/frames/)、[运行日志](attempt-a/runtime.log)。
- **B：120mm／hold5未校准候选**。50决策、50请求、250控制帧／5秒。原生未成功、无接触；区别于研究的120mm／hold1。[报告](attempt-b/report.json)、[全帧视频](attempt-b/rollout_h264.mp4)、[决策目录](attempt-b/decisions/)、[逐帧数据](attempt-b/native/frames/)、[运行日志](attempt-b/runtime.log)。

每次均保留原生判定、触觉/RGB/state/action、执行计数和可解码视频。[独立核验](independent_verification.json)35项通过，共500帧完整解码；不是原生成功或触觉合格证明。

## 正式诊断对照与选择

B启动前保存[诊断v2](diagnosis_before_b_v2.json)，依据A推进不足联动改变步长/限幅、hold5不变，预声明完整前向执行区间投影中位至少提高2倍。v1草稿的跨轴计算和计数曾有误，修正发生在B预留/启动前；[原草稿](diagnosis_before_b.json)原字节保留，执行依据是v2。两次实际开局16字段及目标逐值一致；教师、提示、视角、采样、原生预算一致。实际`native_run`及控制源码一致，父入口许可检查和发布代码的版本区别在[开局检查](initial_pair_check.json)披露。

[比较](comparison.json)显示前向中位8.687→35.334mm，通过事前17.374mm阈值；共同前10次前移的跨轴中位0.927→10.311mm。**A的3次DOWN全部反向，B的18次中17次反向**，对应请求方向投影中位−5.639→−38.678mm。两个方案已有反向响应，候选未解决且偏移更大，故不采纳为整体改善，不改25mm／hold5默认基线。正式案例验收完成，结论限于一个开发开局及步长/限幅联动；没有唯一根因、统计提升、通用校准或训练收益证明。

B第11号决策在55–60帧执行`GRASP`时，TCP距方块675.9mm、零接触/零力，是过早空闭合。[事实审计](empty_close_audit.json)和[独立错误收据](known_error_receipt.json)关联原token/观测/finish，不覆盖原件，不推断教师内部意图。

## 发布与回读

[正式v2数据集](../../../datasets/unified/tacjev-online-first-20261012T014737Z-v2/manifest.json)包含两条诊断episode、100条因果样本、**0正示范／0训练样本**，保留并排除1条已知错误。[发布结果](publication_result_v2.json)、[DataEngine实际回读](dataengine_readback.json)核对正常目录发现、真实目录/曲线接口、视频分段读取、500帧时间轴及每帧state/action。历史fixture的全局血缘不属于本次；新采集没有学生checkpoint/评测/campaign血缘。

首次独立发布因工具导入路径失败，[失败收据](publication_failure_001.json)及部分目录保留。修复后使用新v2目录，未覆盖失败目录或原始在线记录。

## 闭合预算与原件保护

[续接台账](budget_ledger.json)继承历史4/6次启动、0/300请求、1848.098秒，历史台账哈希不变。本次新增2启动、103请求（预检1＋A52＋B50）。累计**6/6启动、103/300请求、4209.569/7200秒（70.159/120分钟）**；历史1848.098秒加恢复后连续2361.471秒，包含HTTP等待/重试、两次运行、运行间诊断及结束保存。开发和封存研究未合入运行窗口。

原生启动上限耗尽时关闭，剩余197请求和墙钟余量不构成继续授权。关闭后的只读回读、CPU测试、审查和证据整理没有新增教师请求/原生启动。[保护起点](preservation_start.json)固定三份历史台账及封存`research/arena-jitter`分支；[收尾检查](validation/checks.json)核对保持不变。未跟踪用户PDF/HTML原件未提交、未覆盖。

## 测试、审查与尚缺证据

相关回归[134项通过](validation/pytest_targeted.log)，[7文件类型检查通过](validation/mypy.log)。全仓CPU检查仅运行一次：[2663通过、3项历史失败、1项环境导入收集错误](validation/pytest_full.log)；未宣称全仓通过。该次全仓检查早于最后独立CLI路径修复，修复随后由新增公开CLI回归、134项相关测试及真实发布回读验证。[Standards/Spec审查](validation/code_review.md)发现已修复，复查无剩余问题。

本地任务04的在线入口和05的正式诊断案例已结项。仍缺合格在线触觉示范、可靠九token方向/幅度校准、跨开局泛化与学生能力证据。额度已尽，停止条件保持；训练与扩大采集不属本次交付。
