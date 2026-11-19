# v0.3.0 发布冻结与独立新草稿

发布后冻结当前草稿。再次编辑必须明确从某个正式版本开启新草稿；方案 ID 保持，草稿 ID 更新。已发布版本、地块研究、数据快照和模型继续引用原来的正式版本。

| 改动项 | 实际行为 |
| --- | --- |
| 发布关闭草稿 | `publish` 与正式版本写入原子关闭草稿；同修订重复发布返回该草稿原来的版本 |
| 显式再次编辑 | 新增 26：`POST /api/v1/research/design-versions/{version_id}/drafts`，需要企业范围和 `Idempotency-Key` |
| 查询状态 | 13/14 增加 `draft_id`、`draft_state`、`base_version_id`、`published_version_id`；状态为 `draft` 或 `published` |
| 保存保护 | 12 和工作区保存拒绝写入关闭草稿，返回 409；原保存请求的幂等回执仍可查询与重放 |
| 独立版本 | 新草稿修订单调递增，发布生成新正式 UUID，即使配置未改也不复用旧版本；候选名称重新分配 |
| 前端 | 正式配置只读，显示“基于已发布版本编辑”；业务前端需转接新入口并依据状态控制编辑 |
| 迁移 0016 | 新增 `research_design_draft_sessions`；规范化识别历史配置状态，不改任何正式版本正文、摘要、UUID 或已有实例引用 |

已有未发布修改的历史草稿继续可编辑；与正式版本完整一致的草稿登记为已发布。首次保存仍返回原三字段 `design_id/revision/configuration_sha256`，其他接口继续沿用统一 `inspection`。历史直接发布合同仍只追加正式版本，不能改写旧版本。

部署须先备份并升级数据库到 0016，授予应用角色新表的 `SELECT, INSERT`、`UPDATE(published_version_id, closed_at)`，以及当前工作位的 `UPDATE(draft_id)`；其余权限沿用。迁移后的旧客户端不能继续直接编辑已发布草稿，应接入 26。回退旧镜像不能恢复旧编辑流程，应保留冻结保护并向前修复；数据库结构降级会移除草稿轮次记录，不能作为常规回退。

[完整对接](research-version-integration.md) · [功能设计与验收](../coding/published-plan-draft-lifecycle.md)
