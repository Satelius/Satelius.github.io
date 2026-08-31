# Asset ledger v3 integrity evidence — 2026-08-31

这份记录区分两件事：账本代码和所有活动写入口已经按 v3 内容契约 fail closed；仓库里既有的
162 份账本则尚未因此自动变成合格数据。没有通过改 `schema_version`、猜 stable pose 或把 catalog
来源字符串伪装成物理 run id 来消除债务。

## 现在由什么构成一份有效账本

- `representations[].files` 是规范排序、无重复的实际依赖闭包，不是“作者愿意列出的几个文件”。
  validator 会解析 URDF、OBJ/MTL、glTF/GLB、DAE 和 USDA 的下游引用，并逐文件复核 SHA-256 与
  bytes；越根引用、网络/绝对引用、缺文件、格式混淆、文件或任一父目录 symlink 都拒绝。
- collision-bearing representation 必须有明确 `collision_meta`。v3 已删除的 `size_bytes`、
  `runtime_default_kg` 和 `runtime_default_basis` 不再因为文档自称 v3 而被放过。
- stable pose 必须带 `measured_against`；verification receipt 必须是结构化的 backend/check/verdict、
  canonical timestamp、非空 run id，并绑定当前 `asset-representation-set.v2` 摘要。这个摘要覆盖目标
  backend 的全部非 snapshot representation、完整 files、几何/坐标系/collision metadata，而不是只
  哈希一个顶层 mesh。
- `ledger_writes.py` 是活动写入口共享的提交边界：先构造完整闭包，再用 `check_files=True` 验证，
  最后原子写入或追加 digest-bound receipt。materialize、runtime sweep、articulated validation、
  backfill、migration、fragment、retire、relativize、rescale、settle repair 和 writeback 都已接入或在
  发布前使用同一严格契约。
- 锁和发布同样属于证据边界：lock final component 用 `O_NOFOLLOW` 打开；read/validate/compare/write
  在同一锁内完成。空 backend 不能生成 representation digest，同一 producer identity 的相异 receipt
  是冲突而不是幂等。批迁移、backfill manifest+ledger、rescale 和 retire 都有异常回滚；路径段、父目录
  symlink、发布前目录换靶与 gate 后字节漂移均 fail closed。

generated admission 仍把确定性生成器的 `generation_qc` 作为 analytic provenance receipt，而不是
SAPIEN settle；admission report 继续写 `physical_qualification=pending_settle`。后续真实 settle 或
runtime receipt 可以保留并且不妨碍同一生成资产复用，但原始 generation-QC、输入 provenance、目录
manifest 或非 verification 内容只要变化，复用就会拒绝。`ledger.lock` 只是锁文件，不进入 payload
身份。

## 代码回归

资产子项目需要显式包含其本地 OpenXSim source root；使用这个真实入口运行完整测试得到：

```text
637 passed, 2 skipped
```

两个 skip 只因为该单元测试解释器没有 SAPIEN。`ledger.py`、`ledger_writes.py` 与
`writer_paths.py` 合计 1,255 statements / 706 branches，全部 100% 覆盖。Harness 独立回归得到
`1,311 passed, 18 skipped`，唯一额外失败是 checked-in compile qualification 正确检测到本切片修改了
`assets.py`；该资格会在实现提交后由固定三轮 generator 重新出具，不手改哈希。攻击测试覆盖闭包
缺失/篡改/symlink/opaque 格式、stale/冲突/空-backend receipt、共享依赖删除、路径逃逸、lock symlink、
并发 CAS、gate 后变更、批处理/mesh/retire 回滚、后续合法 receipt 复用、原始 generation-QC 篡改和
无物理证据等反例。

## 既有数据的 RED 基线

对活动 asset library 65 份和 upstream ledgers 97 份做只读审计：`162/162` 均被新门拒绝，共
`4,082` 条 violation：

| 类别 | 数量 |
| --- | ---: |
| deleted field | 1,915 |
| required field missing | 1,757 |
| stable pose `measured_against` missing | 410 |

字段层包括：1,101 个旧 `size_bytes`、1,101 个缺 `files`、563 个 collision representation 缺
`collision_meta`、407+407 个旧 runtime-default 字段、93 个缺 `external_ids.env_gen`，以及 410 个
pose provenance 缺失。完整 audit JSON 因体量不提交；upstream report 为 679,892 bytes / SHA-256
`881d2f8485f15be48be8ceef0a06337359b76a98377b7a107aa283b3437b8a98`，library report 为
133,108 bytes / SHA-256 `52592a69f173017acd6bd0b4a040ae266c5db21754b0fa345bae2a47cc2dea37`。

本切片修改既有 ledger 数据文件数为 0。能从现有 bytes 无损证明的字段可以由 migrator 补；不能
证明闭包或真实 settle 的项目会输出 typed debt 并拒绝写盘。剩余 pose debt 必须关联已有可信
receipt 或执行真实 replay，不能用迁移日期、source commit 或任意字符串补齐。

因此状态是 `implementation_pass_data_debt_open`：新写入和复用不会再制造表面 v3，旧数据也不会被
错误宣告健康。
