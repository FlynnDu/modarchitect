# v0.2.2 点位方案发布修复

2026-11-19。修复正式保存后的点位采样方案发布时错误要求选择业务地块的问题。

## 问题与行为

业务端先使用 `POST /api/v1/research/design-saves` 保存未绑定地块的通用方案，再调用 `POST /api/v1/research/design-drafts/{design_id}/publish`，旧实现会返回 HTTP 422：`Select business fields before saving a sampling-point plan`。正式保存与固定版本发布对实际对象范围的要求不一致。

修复后，该发布接口允许尚无 `sampling_selection` 的方案固定版本，继续校验完整定义、准确组件、修订及保存摘要。业务端继续提交 `expected_revision`，无需为发布新增地块或点位字段；重复发布及版本读回保持原行为。

| 编号 | 改动项 | 对接方式 |
| --- | --- | --- |
| P1 | 未绑定地块的点位方案可以发布固定版本 | 正式保存后按原路径及修订发布，不补造业务地块，也不把点位指标改成地块尺度 |
| P2 | 实际应用时逐地块核验选中点位 | `POST /api/v1/research/studies` 传授权 `fields` 与 `point_refs`，每块应用地块至少选一个授权点位；目录中有点位但没有选中也会被拒绝 |
| P3 | 保留历史绑定与安全边界 | 已显式绑定选地的草稿发布仍重新核权；旧暂存草稿和直接发布入口保留原合同；企业隔离、版本摘要及来源资格保持 |

本批不增加接口、请求字段、依赖或数据库迁移。`inspection` 继续使用 v0.2.1 的统一六字段结构。发布版本表示固定方案，未完成本次应用及执行检查时仍不能显示可运行。

[前端接入](frontend-integration.md) · [业务后端接入](business-api-integration.md) · [修复设计与验收](../coding/unbound-plan-publication.md)
