# Tactile-ETA 逐页论文伴读

发布于2026-10-26：[论文伴读](https://satelius.github.io/pages/project-progress/self-improving/tactile-eta-paper-companion/) · [复现总览](https://satelius.github.io/pages/project-progress/self-improving/tactile-eta-paper-companion/overview/) · [项目进展](https://satelius.github.io/pages/project-progress/)。沿用项目进展页的访问方式。

## 阅读方式

- 左侧为24页原始PDF，滚动、页码输入、目录与右侧中文解释同步。
- 73项解释与55条问题索引覆盖领域、动机、相关工作、选帧、模型输入输出、消融、TacHarness接入及TacJev蒸馏。
- p.5可操作阈值与并列峰值示例；p.9可查看官方示范中的左右触觉图片。
- 可定位具体解释，例如`#page=5&note=selection`和`#page=21&note=distillation`。窄屏可切换原文与讲解。

## 事实与方案的边界

页面以“论文事实”“代码核验”“接入方案”“阅读边界”标识依据。这里的峰值指动作段内相邻触觉图像之间的变化分数峰值，不等于运动幅度最大的动作。作者框架将动作对齐的触觉经验放入冻结模型的上下文；不更新模型权重。

TacJev接入与蒸馏属于本项目提出的工程方案，尚未完成学生训练或闭环验收。当前三图、任务与最近最多五个已执行移动token的输入约束、九token动作接口和闭源模型可见性限制，另见页面的项目合同说明。

独立复现目前覆盖离线组件与方法核验。服务器尝试最远完成场景及双侧GelSight初始化，首次机器人reset仍失败；没有有效观测、模型决策、执行动作或成功episode。论文所报仿真与真机成功率没有独立复现。公开`evidence/`提供脱敏摘要，不含服务器原始日志或私有配置。

## 来源与依赖

- [Tactile-ETA论文v1](https://arxiv.org/abs/2610.27613v1)：原始24页PDF，论文HTML声明CC BY 4.0。PDF未编辑，SHA-256为`5e68144ec4ded63f9adb1642283047c6dde3ff7dddcdb3b1921213267dba5d04`。
- [作者代码固定提交](https://github.com/No-518/Tactile-ETA/tree/e7e5efbd42d3be7532ff5eb940a3cb015c2f7818)：示范触觉帧及方法核验依据。
- Mozilla PDF.js `pdfjs-dist@4.10.38`：原样发行件与Apache-2.0许可证位于`assets/vendor/`。论文渲染不依赖外部CDN。
- [公开资产哈希清单](evidence/artifact-manifest.json)：记录本发布包的文件摘要；不收集访问者数据。

通过HTTP访问本目录；无需模型服务、GPU或仿真环境。
