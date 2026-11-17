# 模型设计器迁移基线

2026-11-11。旧系统来源为企业工作树 `E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth`。本次只读检查旧源码和记录，并向 249 的公开入口发送 GET 请求。

## 来源与适用范围

| 来源 | 已核实的标识和结果 | 迁移用途 |
| --- | --- | --- |
| 已提交源码 | `codex/enterprise-model-services`，提交 `53d86cb1a3359e279776ee8825e4366d066ea859`，静态解析的 Alembic 头为 `d164cb66545b`。原拟合样例引用 `logistic_growth_curve@3`。 | 追溯稳定路由、数据库约束和历史样例。用准确提交复原文件。 |
| 工作区候选 | 检查时 `git status --porcelain` 显示 99 项修改、11 项删除、140 项未跟踪路径（目录按默认规则折叠）。点位保存、目录采用字段、概览和报告有工作区改动。组件 JSON 从 `v1.json`…`v11.json` 改为 `current.json` 和 `history.json`，拟合样例改为 V4。另有未跟踪的组件包迁移 `aef295e079d6`。 | 逐文件采用已确认行为，按指纹核对素材。候选预检、包表和实验性组件范围按实际需要评审。 |
| 249 公开预览实测 | `18921` 的设计器 HTML 和两个目录 GET 为 200。组件 52 项，14 项可用于新设计。研究目录合同 `1.4`，54 项变量，`private_design_saving=false`、`online_submission=false`。私有 `/api/v1/research/studies` 和 `/openapi.json` 均为 404。逻辑斯蒂 V4 精确查询为 200，V3 为 404。 | 核对目录投影、入口和公开访问边界。正式历史导入需从准确历史目录恢复 V3。 |
| 249 既有隔离工程证据 | 11 月 4 日研究架构批次记录 306 通过、1 跳过，单独的全迁移链回归另有 1 通过。使用实际 PostGIS、原生低权限 HTTP 登录、真实 HTTP 与科学 Worker，身份、业务接口和海豚提交由替身提供。11 月 10 日的点位保存与目录合同批次分别记录 80 和 83 项通过。 | 复用用例和断言。各批次按自身源码、库和制品范围引用。 |

本次运行 `git rev-parse HEAD`、`git status --porcelain`，对 Alembic 文件静态解析修订关系，并对公开入口读取 `/ui/model-center/components.html`、`/api/v1/model-center/components?page_size=100`、`/api/v1/model-center/research-library`、`/api/v1/model-center/components/logistic_growth_curve?revision=3` 和 `revision=4`，以及上述两条 404 路径。复查限于 HTTP 响应。11 月 10 日发布记录所列的增量 SHA-256 为 `14d1e6025f0e516e102d2ce36ad25dfe8dfb023460115df736b03df7080f89a5`（点位保存）及 `3e718caa8f9967c169c9494bd54f0a111a94187441bbe891918c7f6ee67f9889`（目录合同）。批次档案、库和镜像摘要来自旧验收记录，制品字节需在隔离复跑前复核。 [公开预览与批次路径](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/deployments/20261109-research-interaction-preview-249.md>) · [隔离部署条件](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/deployments/20261105-research-workflow-249.md>) · [306 项回归日志](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/coding/deployments/research-architecture-20261105/research-final-regression.log>)

[源码指纹](model-designer-fixtures/source-fingerprints.json)记录首批涉及的选定源码、迁移、用例和静态 HTTP 合同。文件摘要按 CRLF 转 LF 后的 SHA-256 计算，`null` 表示该来源没有这个文件。使用 `git show <提交>:<路径>` 取已提交文件，对照批准的工作区增量或批次归档取候选文件。它记录的是本地快照的指纹。完整工作树和预览制品各以对应批次清单追溯。静态 OpenAPI 与实际路由一起核对，特别是组件包预检等候选接口。

## 入口、实现与回归

旧应用在启动时升级数据库、同步目录并按配置运行事件消费者。静态设计器挂载在 `/ui/model-center/`，同源调用 `/api/v1/model-center` 和 `/api/v1/research`。表中旧路径用于编制首批兼容用例。 [应用挂载和启动](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/main.py>) · [设计器 HTTP 调用](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/web/model_center/components.js>)

| 实际入口或调用方 | 旧实现与要保留的合同 | 旧回归 |
| --- | --- | --- |
| 设计器组件、变量、方法与连线，外部目录客户端 | `model_composition.py` 的 `/components`、准确版本与可连线端口、`/component-library`、`/research-library`、变量来源详情，调用 `model_components.py`、`research_variable_library.py` 与共享合同。新设计判定用 `available_for_new_design`，参数用 `research_contract.request_schema`，运行状态看 `execution`。 | `test_component_library.py`、`test_components.py`、`test_research_variable_library.py`、`test_components_browser.cjs` |
| 导入、检查、编辑、重开和发布 | `research_studies.py` 的 `/configurations/{draft,check,import}`、`/plans/validate` 和准确版本导出，`research_drafts.py` 的 `/design-drafts` 及子路径。旧调用方仍可走 `model_composition.py` 的 `/designs` 和版本路径。服务层由 `research_drafts.py`、`research_designs.py`、`research_plan_validation.py`、`research_input_bindings.py` 管理配置摘要、修订冲突及发布冻结。 | `test_research_drafts.py`、`test_research_templates.py`、`test_research_variable_library.py::test_real_api_contract_and_draft_roundtrip` |
| 浏览器选地、启动和外部研究接入 | `research-launch.js` 调用 `/launch-options`、`/configurations/launch-preview`、`/field-selections/resolve`、`/launches`。`research_launch.py` 核验作物、项目、地块边界、种植季和点位后，交给 `research_studies/collection.py` 绑定准确版本、建实例并生成规则。外部调用方也可用 `POST /studies`，经受信上下文校验。 | `test_research_launch.py`、`test_field_selection.py`、`test_research_launch_authenticated_browser.cjs` |
| 采集、观测、就绪和运行 | `research_studies.py` 的 `/studies/{id}`、`overview`、`collection`、`check`、`refresh`、`runs`、`commands`，以及 `/runs/{id}`、`cancel`、`retry`。业务通知走 `/api/internal/research/studies/{id}/coordinate`。事件消费者经 `runtime.py`、`coordinator.py`、`runs.py` 分别处理业务回执、输入封存、调度和恢复。 | `test_research_workflow.py`、`test_research_http_workflow.py`、`test_research_dispatch.py`、`test_research_recovery.py` |
| DolphinScheduler 与 Worker | `api/services/dolphin.py` 提交固定 Shell 入口，`pymlgrowth.research_models.remote` 走 `/api/internal/research/runs/{id}/{claim,heartbeat,result,failure}`。Worker 使用独立内部身份，领取准确运行并提交与租约绑定的结果。 | `test_research_http_workflow.py` 的真实 Worker CLI 和并发领取，`test_research_run_database.py` 的过期租约、重试与取消 |
| 报告及科研发布 | 结果经 `research_study_outbox` 投递业务报告，设计器概览与报告使用独立投影。科研版本和路由走 `research_publications.py` 的 `/model-publications`、`/model-routes/{design_id}`，分别绑定拟合与评价运行和准确成果。 | `test_research_http_workflow.py`、`test_research_publications_http.py`、候选 `test_research_report.py` |
| 组件开发者与后续供方 | 候选源码提供 `/component-packages/{schema,port-types,validate}`，校验清单、已登记端口和版本冲突。预检只读。候选提交、审核与准确版本绑定已有未提交数据模型与迁移，正式上传及执行需验收。 | `test_component_library.py::test_component_package_public_preflight_uses_registered_types`、候选 `test_package_storage_database.py` |

入口身份由 `X-Enterprise-Delegation` 向可信身份端验证，按企业来源编号映射 `resource_scope_id`，并在事务设置主体。外部业务 Key、企业用户委托、内部 Worker Key 各有验证入口。已有研究实例及成果还需逐次检查业务项目授权。调用方兼容以实际 HTTP 请求、状态码与读写结果验收。 [身份依赖](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/security/research_designs.py>) · [外部 HTTP 合同](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/research-workflow-api.md>) · [业务选地协议](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/research-launch-api.md>)
