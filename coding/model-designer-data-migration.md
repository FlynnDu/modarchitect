# 独立研究库迁移清单

2026-11-11。本文件留存旧库 `feature_store` 关系及早期迁移设想，供后续实现核对字段和状态语义。当前 249 部署以独立 PostgreSQL 空库为起点，初始化方式和验收范围以[迁移计划](model-designer-migration.md)为准。

## 表和引用顺序

| 次序 | 源表 | 目标处理及校验 |
| --- | --- | --- |
| 1 | `resource_scopes` | 首批导入研究所引用的资源范围。保留 UUID、`kind`、`company_source`、`company_id`，核对企业组合唯一和平台范围约束。未知范围、同一企业对应多个 UUID 或同 UUID 对应多个企业须定位并处理。 |
| 2 | `model_component_definitions`、`research_variable_definitions` | 首批导入当前参考版本及历史方案引用的准确目录行。保留主键、代码、版本、合同 JSON 和摘要，按权威目录补齐当前采用项。组件 `(code, revision)` 相同而摘要不同视为冲突。 |
| 3 | `research_variable_sources`、`research_variable_source_policies` | 来源绑定引用变量定义和组件定义。来源策略引用准确来源绑定。导入首批所需及历史方案所引用的版本，保留版本、来源代码、摘要、方法和观测性质，确保冻结方案可解析。 |
| 4 | `research_designs`、`research_design_drafts`、`research_design_versions`、`research_design_components` | 首批导入方案根、草稿、不可变版本及节点绑定。根引用范围并保留主体和创建幂等键。草稿以 `design_id` 为主键，保留修订、初始及当前配置摘要。版本引用根，保留版本 UUID、修订、定义和摘要。节点以版本及节点代码定位，强引用准确组件定义。 |
| 5 | `research_studies`、`research_study_changes`、`research_observation_revisions` | 研究实例引用准确方案版本，保留 `study_id`、上下文、状态、截止时间、修订及 `(design_version_id, idempotency_key)` 和请求摘要。变更按实例和修订追溯。观测按实例、来源系统、来源记录编号、修订保留原始载荷和摘要，保留更正、撤回及时间证据。 |
| 6 | `research_study_runs`、`research_execution_attempts` | 运行引用实例，保留 `run_id`、`(study_id, input_sha256)`、输入与结果、状态、租约、错误和旧 `workflow_code`。尝试强引用运行。运行行当前 `attempt_id` 与到期时间成对保存，回迁核验当前指针归属与尝试史。旧 `workflow_code` 只保留为定义编号。 |
| 7 | `research_study_outbox` | 采集规则、运行投递和报告共用实例外键及 `(study_id, topic, event_key)` 唯一约束。保留事件 UUID、载荷与摘要、高水位、可发送时间、尝试次数、回执与隔离原因。事件可能引用运行或报告证据，按主题核对 JSON 引用。交接待发事件前先核对旧端投递及在途归属。 |
| 8 | `research_model_publications`、`research_model_routes`、`research_model_route_changes` | 科研发布引用生产与独立评价运行及准确输出，并可引用前一发布，按版本链导入。路由与历史变更引用方案根和准确发布，保留变更修订、审批主体及理由。核对发布清单摘要、评价门槛与同一研究归属。 |
| 候选 | `component_package_submissions`、`component_package_reviews`、`model_component_package_bindings` | 旧工作区 `aef295e079d6` 的供方候选、审核证据和准确版本绑定。作为未来上传设计依据，由平台组件治理决定候选数据归属。研究库首批读取已采用版本和所需制品证据。 |

旧链路涉及 `ef7978dd3535` 的企业范围、`5db385010534` 的组件和方案、`f1561346e191` 的研究生命周期、`6d585cb36e97` 的执行尝试、`8ed4a62254b8` 的草稿与科研发布、`35e5767e0374` 的有界调度发现、`9ed1c915d83b` 的变量与来源、`d164cb66545b` 的平台指定来源策略。独立库维护自己的 Alembic 入口，从研究元数据和必要约束生成、审查迁移，记录源库实际 `alembic_version` 与导入批次。旧数据库完整迁移链供比对。 [迁移与权限记录](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/deployments/20261105-research-workflow-249.md>) · [源码与迁移指纹](model-designer-fixtures/source-fingerprints.json)

## 跨服务引用

| 外部权威 | 独立研究库保存 | 通过什么核验 |
| --- | --- | --- |
| 企业授权与用户主体 | 企业组合到本地范围 UUID 的映射、所有者主体和审计事实。 | 通过可信身份端验企业、主体、受众和时效。研究入口复核项目权限。以同一主体跨企业、同企业不同主体、项目撤权、伪造企业字段及身份端失联验证。 [身份入口](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/security/research_designs.py>) |
| 业务项目、地块、样点及种植季 | `project_ref`、`field_ref`、`unit_ref`、父子单位关系、种植季、边界版本或冻结引用，必要时保存选地授权证据。 | 业务选地和上下文接口验证主体、范围、作物、时效及完整地块，逐地块核对点位。业务地图瓦片是浏览辅助，业务候选服务提供实际可选对象。旧农业权属、地块、观测主表留在业务侧。 [选地合同](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/research-launch-api.md>) |
| 作物标准 | 研究所用作物代码和版本或来源证据。 | 旧服务读 `wofost_crops`，可用旧 `GET /api/crops` 做集成对照。新服务通过受信目录接口或经批准的版本化制品校验注册情况。品种参数库由权威平台提供。 [作物接口](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/routers/crop.py>) |
| 组件、变量、方法、来源和标准产物 | 可追溯的准确版本、合同和制品摘要，冻结方案所需本地行。 | 平台组件和标准目录提供权威数据，研究服务维护研究采用规则。旧测试依赖时序目录、特征定义及采样指标表，迁移按用例补齐相同版本的合同投影。验收同版本不同摘要拒绝，历史方案只按原绑定解读。 |
| 业务观测与采集/报告接收端 | 源系统、记录及修订、资格与单位、可用时间、封存输入，规则与报告事件、回执和高水位。 | 观测按准确上下文、方案摘要及边界引用拉取。事件按原 `event_id` 和摘要重投，回执按二者验证。联验跨租户伪造、分页、撤销、重复与乱序回执、错误摘要及业务拒绝。株高与 NDVI 另用真实点位、时间及影像证据验收。 [业务适配实现](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/mlgrowth_enterprise/research_business.py>) |
| DolphinScheduler 和 Worker 制品 | 调度项目、定义编号、实际实例 ID、提交关联键、研究运行和领取尝试关系，以及封存输入和成果身份。历史资料保留原有字段。 | 通过真实海豚接口和 Worker 控制面核验接受、排队、执行、停止和迟到结果。没有已证实的旧实例 ID 时保留未知状态。 [真实调度验收](model-designer-dolphin-acceptance.md) |

## 导入验收

1. 空目标库先验证数据库版本和 `uuidv7()` 等函数，按需核对 PostGIS 依赖。使用迁移角色部署表、外键、约束、不可变触发器和 RLS。用原生低权限连接运行应用。调度发现启用时复刻受限函数的权限和返回范围，使用事务局部范围与主体读写。迁移角色与应用角色独立。
2. 从同一旧库快照导出，记录源库版本、表行数、主键集合、摘要、关系、待发事件及脱敏对账报告。按依赖导入，保留原 UUID、版本、键和时间。注意旧 JSON 和 JSONB 的持久化差异，用准确合同代码重新核验摘要。重复导入同一批次无额外行，身份或摘要冲突须可定位且回滚该批次。
3. 以已授权所有者、同企业其他主体、不同企业及项目已撤权四种身份复核查询和写入。核对 `FORCE ROW LEVEL SECURITY`、连接归池后主体清理、已发布版本防修改、事件与结果历史。使用真实授权另跑业务查询与撤权用例。
4. 切换前停止旧端新增研究写入和派发，明确已提交实例仍由原端回传，处理旧端待发和回执后对账。目标运行前不得主动重放已确认交付的事件或抢占旧租约。恢复演练保留快照、前向迁移和新写入对账，验收见迁移计划第四阶段。
