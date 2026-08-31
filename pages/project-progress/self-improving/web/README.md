# ASPIRE × 仿真环境生成组会网站

这是一个无构建依赖的静态单页网站，内容基于本次 ASPIRE 研究及本项目已经冻结的实验结果。

## 打开方式

直接打开 `index.html` 即可；为了让浏览器稳定加载视频，也可以在 `web/` 目录启动任意静态文件服务：

```bash
python -m http.server 8765
```

然后访问 `http://127.0.0.1:8765/`。

## 文件说明

- `index.html`：页面内容与结构。
- `styles.css`：投屏和移动端样式。
- `app.js`：滚动进度、当前章节、投屏模式和图片放大。
- `assets/`：论文官方图片与本次研究的本地 SAPIEN 回放媒体。

页面内部的样式、脚本、图片、视频和章节链接均使用相对路径；外部一手资料保留官方网页地址。

## 证据边界

- 论文图片来自 ASPIRE 论文（CC BY 4.0）。
- 本地视频是本项目 can-on-plate seed 7 的一次 SAPIEN 物理门控回放，不是 ASPIRE 任务 rollout。
- E2 数值来自固定合成 contract proxy，不代表真实仿真物理或分布外泛化。

## 构建与资产回执（2026-08-31）

本次制作只新增 `web/`，没有创建分支，也没有修改现有研究或生产文件。为了让汇报可离线播放，
页面没有外部字体、前端框架或 CDN 依赖；内部链接、样式、脚本和媒体全部使用相对路径。

可见资产及来源：

| 页面资产 | 来源 | 在页面中说明什么 |
| --- | --- | --- |
| `assets/aspire-system.png` | arXiv HTML v1 的 `system_design.png` | coordinator、actors 与共享 skill library 的整体关系 |
| `assets/aspire-execution-engine.png` | arXiv HTML v1 的 `coding_dojo.png` | primitive trace 如何帮助定位而不是盲目重试 |
| `assets/aspire-skill-library.png` | arXiv HTML v1 的 `skill_library_update.png` | actor findings 经审计后才进入共享技能库 |
| `assets/replay-observer.mp4` | `self_improving/studies/ASPIRE/artifacts/real_replay_can_on_plate_seed7/observer_runtime.mp4` | 一次本项目 SAPIEN 物理门控回放；10 秒、12 fps、120 帧 |
| `assets/replay-rgb.png` | 同一 evidence bundle 的 `preview_head.png` | 头部 RGB 中 can-on-plate 的可见状态 |
| `assets/replay-segmentation.png` | 同一 evidence bundle 的 `preview_segmentation.png` | 源物体与目标物体的分割预览 |
| `assets/replay-world.png` | 同一 evidence bundle 的 `preview_world_left.png` | 场景整体关系与机器人工作区 |

选择这些素材的原因：官方仓库没有随代码发布论文原始 rollout；本次研究中唯一真实 SAPIEN 媒体是
can-on-plate seed 7。因此网站没有用该视频冒充 ASPIRE 机器人任务复现，也没有把合成 memory 实验
冒充物理提升。

最终验证记录：

- JavaScript 语法检查通过。
- 23 个 HTML `href/src/poster` 引用均可解析；没有缺失资源、根路径或越出 `web/` 的内部路径。
- MP4 为 H.264、320×240、12 fps、120 帧、10 秒。
- 干净 Chrome 会话中 7 张页面图片全部加载，视频 `readyState=4`、时长 10 秒，无控制台错误。
- 1440×1100 与 390×844 两种 viewport 均无横向溢出。
- 章节跳转停在 90 px sticky-header 留白；投屏模式和图片放大对话框的开/关路径均通过。
- `git diff --check -- web` 通过。

Repo-docs 同步判定为 `none`：这是独立汇报资产，不改变编译器、harness、validator 或运行时行为；
读者行为说明仍以现有 repo-docs 和研究报告为准。
