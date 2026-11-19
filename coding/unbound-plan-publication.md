# 未绑定地块的研究方案发布

2026-11-19。业务端调用 `POST /api/v1/research/design-drafts/{design_id}/publish`，点位采样方案返回 `Select business fields before saving a sampling-point plan`。

## 事实与边界

正式保存 `design-saves` 已按设计阶段约定跳过实际选地；发布却无条件调用 `business.check_sampling`。因此同一份合法方案可以正式保存，却不能固定版本，与本期设计和版本文档中“应用时绑定对象”的约定冲突。旧暂存草稿和直接发布接口对显式绑定业务范围的历史校验已有回归，不整体取消。

当前实际应用 `BusinessStudyStart` 已要求受权地块并校验所选点位归属；点位方案还要求非空点位。但是多个地块仅选第一块的点位时，尚缺逐地块覆盖检查。发布放开未绑定范围之前，补齐该应用边界。

## 最小改动

- `ResearchDesigns.publish`：继续执行准确合同、来源采用及修订检查。没有 `sampling_selection` 时允许固定通用方案；已经显式绑定选地的历史草稿仍重新核验原范围，不改变冻结正文和摘要。
- `ResearchStudies.create`：保留可信业务网关、观察期、点位归属与跨企业隔离；需要点位的方案必须为每个应用地块选择至少一个授权点位。实际应用上下文固定后，现有执行前证据复核继续生效。
- 不增加路由、请求字段、依赖或数据库迁移，不修改科学采样尺度、不编造地块或点位。不修改用户未完成的点尺度取数及计算组件工作。
- 迁移计划明确正式设计保存/发布与旧绑定接口的边界；前端及业务文档补充修复后的发布与应用规则。

## 验收

通过实际 HTTP 和独立 PostgreSQL：正式保存含点位采样要求但未选地的方案，修改并发布，读回及重复发布一致；同时覆盖服务 Key 企业范围和旧委托身份。应用时缺地块、缺点位、越权点位、漏选地块点位必须拒绝；全部覆盖时创建成功，跨企业读取拒绝。保留旧显式选地发布时重新核权、修订冲突、固定版本及历史合同回归。记录真实命令及结果，所有本次 Python 文件执行 Ruff 与文件头检查。

## 已执行结果

- `.venv/Scripts/python.exe .ops/verify_local_database.py` 以 `MODARCHITECT_PYTEST_ARGS` 指定新增发布用例，在独立 PostgreSQL 的新库及低权限角色复现三个失败，发布响应与业务端一致。只调整发布后，两种身份路径通过，应用反例发现漏选点位仍错误返回 201；补齐应用检查后通过。
- `.venv/Scripts/python.exe .ops/run_remote_tests.py` 选跑 `test_publish_sampling_scope`、`test_design_api`、`test_versioned_studies`、`test_api_design_loop` 和 `test_research_inspection`，34 项通过；包含原有显式选地发布重新核权用例。
- 本次三个 Python 文件 Ruff 与文件头检查通过；数据库迁移检查无新增结构差异。准确发布制品及部署回读结果随 v0.2.2 发布记录保存。
