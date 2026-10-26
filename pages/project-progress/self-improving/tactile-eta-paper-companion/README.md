# Tactile-ETA 逐页论文伴读

发布于2026-10-26：[在线实测](https://satelius.github.io/pages/project-progress/self-improving/tactile-eta-paper-companion/online/) · [论文伴读](https://satelius.github.io/pages/project-progress/self-improving/tactile-eta-paper-companion/) · [复现总览](https://satelius.github.io/pages/project-progress/self-improving/tactile-eta-paper-companion/overview/) · [项目进展](https://satelius.github.io/pages/project-progress/)。沿用项目进展页的访问方式；首次访问并输入 PIN 后返回相应页面。既有其他项目入口及顺序保持。

## 阅读方式

- 左侧为24页原始PDF，滚动、页码输入、目录与右侧中文解释同步。
- 73项解释与55条问题索引覆盖领域、动机、相关工作、选帧、模型输入输出、消融、TacHarness接入及TacJev蒸馏。
- p.5可操作阈值与并列峰值示例；p.9可查看官方示范中的左右触觉图片。
- 可定位具体解释，例如`#page=5&note=selection`和`#page=21&note=distillation`。窄屏可切换原文与讲解。

## 事实与方案的边界

页面以“论文事实”“代码核验”“接入方案”“阅读边界”标识依据。这里的峰值指动作段内相邻触觉图像之间的变化分数峰值，不等于运动幅度最大的动作。作者框架将动作对齐的触觉经验放入冻结模型的上下文；不更新模型权重。

TacJev接入与蒸馏属于本项目提出的工程方案，尚未完成学生训练或闭环验收。当前三图、任务与最近最多五个已执行移动token的输入约束、九token动作接口和闭源模型可见性限制，另见页面的项目合同说明。

10月26日已在固定作者源码上跑通真实Codex0.164.0／作者MCP／原生仿真在线循环，取得一次Insert Tube原生成功：6段模型动作、14控制步、15采样帧与6份动作后触觉历史。另保留5段动作的原生提前终止试跑。两个运行均使用gpt-6-astra（服务自报）及两条官方示范，动作预算不同、初始化状态也不完全相同，不能合并成成功率或视为配对消融。

`online/`提供真实四视图视频、精确视频时间戳逐帧播放、逐动作指令／实际步数／触觉选帧，以及六次尝试的脱敏时间线；原视频未插帧。模型思考时物理暂停，这不是连续实时力控性能验证。论文所报仿真与真机成功率、触觉经验的因果收益、TacJev训练均未独立复现。`overview/#reproduction`与`evidence/`保留10月21日历史快照；不含服务器原始日志或私有配置。

## 来源与依赖

- [Tactile-ETA论文v1](https://arxiv.org/abs/2610.27613v1)：原始24页PDF，论文HTML声明CC BY 4.0。PDF未编辑，SHA-256为`5e68144ec4ded63f9adb1642283047c6dde3ff7dddcdb3b1921213267dba5d04`。
- [作者代码固定提交](https://github.com/No-518/Tactile-ETA/tree/e7e5efbd42d3be7532ff5eb940a3cb015c2f7818)：示范触觉帧及方法核验依据。
- Mozilla PDF.js `pdfjs-dist@4.10.38`：原样发行件与Apache-2.0许可证位于`assets/vendor/`。论文渲染不依赖外部CDN。
- [公开资产哈希清单](evidence/artifact-manifest.json)：记录本发布包的文件摘要；不收集访问者数据。

通过HTTP访问本目录；无需模型服务、GPU或仿真环境。
