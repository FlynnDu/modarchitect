# Figma 原型对照：当前 API 能力事实清单

2026-11-12 · 只读评估，不含产品代码修改、数据库操作或新运行。本文按用户动作核对入口与执行行为，不以合同类、字段名称或未来计划代替已实现功能。

后续状态：当天已完成并部署[运行通用化首批改造](runtime-generalization.md#2026-11-12-实施与验收结果)。分析任务、1.5 节点用途及运行响应合同已扩展；下文保留改造前的只读核对基线，其余缺口不因此视为完成。

## 1. 核对范围与结论

当前 API 能支撑“目录选指标、编辑完整研究配置、保存重开、并发修订、发布准确版本、已有方法训练、查询最终结果、保存模型、后续预测”的闭环。它尚未完整承载本轮已读原型中的团队科研工作台、样方平均株高、多角色字段、随机森林、按组独立测试、采集任务、独立验证记录及模型生效规则。

本轮原型已读范围由主评估的浏览器核对提供：节点 `669:4523` 的“模型配置·作物水分响应研究”五步、科研工作台的部分统计与采集状态、科研助手的阶段报告和版本效果文字。控件可见不代表其交互已验证成功；本清单不推断未读画板具有哪些功能。

随后直接匿名复读，补充看到了模型选择中的非训练分析、直接识别、模拟/可选标定等入口。配置内的来源/评价/版本具体表单仍未成功导航到达，不能将侧栏标题视为已读完这些步骤。运行入口和执行器当前依赖训练/预测及可复用训练状态，尚不能仅凭登记新组件就覆盖所有模型类型。详见[复读记录](figma-public-prototype-observations.md)与[主评估补充](figma-ui-api-assessment.md#复读补充运行类型还不够通用)。

**本次实际只读核验：**

- 249 新项目 [OpenAPI](http://192.168.3.249:18925/openapi.json) 返回 HTTP 200，OpenAPI 3.1.0，应用版本 0.1.0，**40 个路径、48 个操作**；正文 SHA-256 为 `93fa2ccdd7b8420b505b2ce4123a99cce8397034b2147e7430eac48fa434d748`。
- 核对时点：`2026-11-12T03:49:27Z` 附近，即北京时间 11:49。随后重复读取路由，集合未变。
- 从当前 `routes.py`、`runtime/routes.py` 的装饰器及健康入口提取方法/路径，与线上 48 个操作逐项比较，`LOCAL_ONLY=[]`、`REMOTE_ONLY=[]`。这证明路由集合相同，不证明每份部署源码逐字节相同。
- 公开健康检查、组件目录、系统输入目录返回 200；无凭据访问个人方案列表、企业草稿列表均返回 401。没有新建工作区 Cookie、提供身份凭据或调用任何写操作。
- 本地工作目录没有可解析的 Git HEAD；本文以读取时的工作区、准确路径和线上 OpenAPI 摘要作为基线。
- 本次没有重跑行为测试；后文“测试”表示已核对测试源码及断言。历史部署结果另外引用已存在的[249 部署记录][D01]，不当作本次新验收。

另有两个实际挂载的页面辅助入口不在 OpenAPI：`POST /designer/validate`、`POST /designer/import`。它们是有界的无状态 JSON 操作，不能替代云端保存。[应用装配][S01]、[页面辅助入口][S02]

## 2. 先明确页面使用哪一套身份与资源

| 入口组 | 实际身份与能力 | 当前边界 |
|---|---|---|
| `/api/v1/model-center` 的公开目录 | 无需私有身份即可查询定义与兼容端口 | 定义可见不等于执行或数据授权。包预检属于受保护兼容路由。 |
| `/api/v1/workspace` | 服务器签名的 `modarchitect_workspace` Cookie，标识同一浏览器的个人空间；非 GET 请求还要求 `X-Workspace-Request: 1` | 没有账号注册、登录、退出、找回、跨设备恢复或团队共享接口。只授予工作区自有数据权限。 |
| `/api/v1/research`、受保护的 `/api/v1/model-center/designs...` | `X-MLGrowth-Business-Key` 加 `X-Enterprise-Delegation`，调用受信业务身份/选地适配 | 业务接入 Key 不应下发浏览器。存在适配代码不证明 249 企业身份、点位服务已完成联验；本次未提供凭据核实。 |
| `/internal/v1/research` | Worker 专用身份、准确运行及执行尝试 | 供调度和 Worker 领取/回传，不应由普通 UI 直接调用。 |

依据：[个人工作区身份][S03]、[企业路由依赖][S04]、[业务身份与选地][S05]、[运行路由][S06]、[事务主体隔离][S07]。

OpenAPI 当前没有把这些全部表达为 `securitySchemes/security`。企业头在 Schema 中可显示为非必填，但代码会按配置拒绝缺少凭据的操作；工作区 Cookie 与写请求头由 `Request` 读取，未作为普通参数完整展示。前端或生成的 SDK 不能因 `security` 为空就把接口当匿名入口。

个人方案与企业方案共用底层服务，但权限来源、列表和发布入口不同。若原型需要“团队模型”，应先确定正式账号、企业主体及共享策略，不能简单把个人 Cookie 的列表改成团队列表。

## 3. 按用户动作核对现有入口

表中的“缺口”是在本次源码与线上路由中未找到相应能力，不代表必须给每个按钮单独新增接口。能够由已有 API 安全组合完成的动作，会单独标明。

### 3.1 目录检索、分类和系统指标

| 用户动作 | 实际方法/路径 | 已有字段和行为 | 缺口或限制 |
|---|---|---|---|
| 浏览计算组件 | `GET /api/v1/model-center/components` | `page`、`page_size≤100`；响应含 `items/total/page/page_size`，条目有 `definition`、`contract_sha256`、`available_for_new_design`、参数 Schema 与执行标记 | 无 `q/category/group/tag/sort` 服务端筛选。少量条目可由 UI 在完整取回后筛选，不能称已有目录搜索接口。 |
| 查看组件详情 | `GET /api/v1/model-center/components/{code}?revision=...` | 不传 revision 取当前采用版，传入时读准确版本 | 属于计算定义，不是已训练模型详情。 |
| 查看组件历史 | `GET /api/v1/model-center/components/{code}/versions` | 准确合同历史与版本资格 | 组件版本与研究方案版本、训练模型身份不同。 |
| 选择可连接下游 | `GET /api/v1/model-center/components/{code}/outputs/{output}/compatible-inputs` | 根据完整 `DataType` 相等列候选输入 | 只证明端口合同兼容，不证明实验语义、数据来源或模型效果成立。 |
| 浏览四类输入 | `GET /api/v1/model-center/research-inputs` | `version/sha256/categories/items/total`；条目含固定变量、来源、科学对象、属性 Schema、`execution`、`data_available` | 无检索参数；当前项目是否有数据不能由目录判断。 |
| 选择指标/角色/土层 | `POST /api/v1/model-center/research-inputs/configure` | 请求 `key/selectors/role`；返回 `variable/requirement/entry`，按准确合同校验 | 不能改代码、名称、单位、来源、方法；第三方不能作为实测目标；待绑定来源不准选入。 |

**249 目录实读：**新设计组件共 8 项，其中 5 项标记 `offline_cpu` 执行可用：`historical_logistic_training@1`、`historical_logistic_predict@1`、`research_forecast_feature_join@1`、`multivariate_linear_training@1`、`multivariate_linear_predict@1`。其余 3 项为 `design_only`：`logistic_growth_curve@4`、`historical_logistic_forecast@1`、`multivariate_linear_regression@1`。不能把 8 项都写成可执行算法，更不能把旧迁移库的 55 份定义当作本项目当前可运行目录。

输入目录 63 项，人工 15、第三方 18、平台分析 21、物联网 9；当前只有 `agb_kg_ha/canopy_cover/lai/tuber_dm_kg_ha` 四项具备工作区标准人工记录通道，全部条目的 `data_available` 仍为 null。固定来源、取数通道与项目数据就绪分别呈现。[目录路由][S04]、[组件目录投影][S08]、[系统输入权威模块][S09]、[输入目录测试][T01]

### 3.2 方案列表、详情、重命名、复制、删除、版本及发布

| 用户动作 | 实际方法/路径 | 可用行为 | 缺口或限制 |
|---|---|---|---|
| 个人方案列表 | `GET /api/v1/workspace/plans` | `items` 内有 `design_id/revision/configuration/configuration_sha256/updated_at` | 最多最近 100 项；没有服务端搜索、筛选、分页参数，也没有团队/收藏/文件夹字段。 |
| 新建个人方案 | `POST /api/v1/workspace/plans` | `Idempotency-Key`；`SavePlan{definition,expected_revision?,observations?,data_kind?}` | 普通输入须有完整系统绑定，合成演示另行标注。 |
| 读取个人方案 | `GET /api/v1/workspace/plans/{design_id}` | 返回草稿，并附保存的 `observations/data_kind` | 没有单独数据集引用；每方案保存最新一份观测表。 |
| 保存/重命名个人方案 | `PUT /api/v1/workspace/plans/{design_id}` | 用完整 definition 修改 `name`，携带 `expected_revision` | 可实现重命名，但没有单独 rename/PATCH；不会改写历史发布名。 |
| 企业草稿新建/列表/详情/更新 | `POST /api/v1/research/design-drafts`；`GET /api/v1/research/design-drafts`；`GET/PUT /api/v1/research/design-drafts/{design_id}` | 输入/输出为带摘要的草稿信封；更新体 `expected_revision/configuration`，列表最多 100 项 | 不是工作区 Cookie 入口。 |
| 检查并发布企业草稿 | `POST /api/v1/research/design-drafts/{design_id}/check`；`POST /api/v1/research/design-drafts/{design_id}/publish` | 发布体 `expected_revision`；返回准确版本身份与合同摘要 | 工作区没有对应独立发布路由，工作区训练流程内部会调用同一发布服务。 |
| 读取准确配置文件 | `GET /api/v1/research/design-versions/{version_id}/configuration` | 导出准确方案版本的旧配置格式及摘要 | 需要企业身份，不能直接供匿名分享。 |
| 兼容直接创建/追加版本 | `POST /api/v1/model-center/designs`；`POST /api/v1/model-center/designs/{design_id}/versions` | `DesignPublication{name,description,revision,composition,research_plan?}`；新建要求幂等键 | 这是版本发布，不是运行、部署服务或发布到公开市场。 |
| 已发布列表/详情/历史 | `GET /api/v1/model-center/designs`；`GET /api/v1/model-center/designs/{design_id}`；`GET /api/v1/model-center/designs/{design_id}/versions`；`GET /api/v1/model-center/designs/{design_id}/versions/{revision}` | 已发布列表有 `page/page_size≤50`；历史准确版不可变 | 全部受企业及主体边界控制；个人 UI 暂无独立版本列表入口。 |
| 复制 | 没有专用 clone 路由 | UI 可以读取 definition 后，以新幂等键创建新方案；也可复制已授权观测 | 无服务器复制来源关系、模板实例化、团队复制授权或副本追溯合同。 |
| 删除/归档/恢复 | **没有对应入口** | — | 没有 DELETE、软删除、归档或回收站 API；不能用前端隐藏伪装持久删除。 |

依据：[草稿和发布路由][S04]、[工作区路由][S06]、[方案服务与响应字段][S10]、[草稿并发存储][S11]。相关回归：[企业草稿并发、发布及隔离][T02]、[旧版直接发布历史][T03]、[工作区保存训练预测][T04]。

### 3.3 画布节点、连线、参数、草稿与并发保存

| 用户动作 | 实际入口/载荷 | 已实现 | 未实现或不能推断 |
|---|---|---|---|
| 校验端口和依赖 | `POST /api/v1/model-center/compositions/validate`，体为 `Composition` | 拓扑、准确组件、端口绑定等检查 | 不执行节点，不提供每节点科学验证成功标记。 |
| 检查完整研究 | `POST /api/v1/research/plans/validate` | `plan_sha256/compiled/collection_requirements` | 完整合同通过不等于有数据、授权或可执行制品。 |
| 生成/检查/导入草稿文件 | `POST /api/v1/research/configurations/draft`、`/check`、`/import` | 有界 JSON、摘要验证；检查返回 `valid/issues`，问题可定位字段、节点与端口 | 无服务器草稿历史逐次快照或协同编辑；云端持久化仍需 save/create。 |
| 页面内检查/导入 | `POST /designer/validate`、`POST /designer/import` | 无状态辅助，返回配置与检查结果，限制 JSON 约 1 MiB | `include_in_schema=false`；新 UI 不应只按 OpenAPI 生成客户端后遗漏它们。 |
| 增删节点、连线、参数、位置 | 保存完整 `definition.composition/input_recipes/layout` | 节点含 `code/component{code,revision}/bindings/selections`；连线通过 `source{node?,port}`；参数值在 `input_recipes[].value`；画布布局在 `layout` | 没有逐节点 CRUD、参数 PATCH、连接独立资源、WebSocket/CRDT 协作或服务器撤销重做。普通 UI 可以本地编辑后整体保存。 |
| 并发编辑 | 更新体 `expected_revision` | 陈旧修订返回 409；观测变化也推进共同修订，防止旧页面覆盖 | 没有自动合并冲突、多人在线状态或字段锁。 |

图合同当前最多 64 个节点、64 个输出、128 个外部输入，每节点最多 32 条绑定；输入观测列和行还有独立限制。不能对 UI 承诺没有任何规模约束。[组合合同][S12]、[编译规则][S13]、[草稿持久化][S11]、[页面辅助路由][S02]、[画布与错误定位测试][T05]

### 3.4 数据来源、采集任务和输入就绪

| 用户动作 | 已有入口 | 实际边界 |
|---|---|---|
| 查看来源与当前阻断原因 | `GET /api/v1/workspace/plans/{design_id}/input-readiness` | 返回每输入的 `variable_code/source_name/category/unit_kind/selectors/execution/data_available`。主要判断已登记通道与适配，不是检查每周采集完成率或逐日缺口的服务。 |
| 解析真实授权地块/点位 | `POST /api/v1/research/field-selections/resolve` | 通过受信业务端解析对象；企业/地块授权代码存在，本次未联验该外部服务。它不是项目或科研地块管理 CRUD。 |
| 配置采样规则 | `ResearchPlan.collection_requirements` 中有方法、用途、对象类型、窗口、间隔、最低记录与独立单位数 | 可在方案中保存规则，不能据此认为当前运行已执行采集排程、最低样本门禁或缺口跟踪。 |
| 人工数据接入 | 工作区保存/训练请求内嵌 `ObservationTable` | 当前只提供标准人工 JSON 数据通道，保留主体、来源和数据摘要。未接业务表单自动同步。 |
| 第三方/平台分析/物联网取数 | 目录有定义或候选；**没有对应受权取数运行入口** | 缺适配明确拒绝，不能上传自填天气/NDVI 数值冒充系统接通。 |
| 按周采集、逾期采集、待办、提醒、记录审核、逐次采集进度 | **没有本项目对应资源或操作入口** | 原型统计和状态暂不能用 `input-readiness` 凑成真实业务数据。 |

依据：[系统输入配置、阻断与封存][S09]、[方案采集字段][S14]、[业务选地适配][S05]、[来源校验与拒绝测试][T01]。旧库的采集工作流及研究实例服务没有因为保留了合同类就自动接入新项目。

### 3.5 数据集、训练、运行状态、节点成果、日志与控制

| 用户动作 | 实际方法/路径 | 已有字段或行为 | 缺口 |
|---|---|---|---|
| 保存并重读观测 | `POST/PUT /api/v1/workspace/plans...`、`GET /api/v1/workspace/plans/{design_id}` | 方案附一份最新观测 JSON；内容摘要和 `data_kind` 持久化 | 无独立 `/datasets` 列表、详情、版本、上传文件、文件解析、预览分页或批量治理接口。浏览器目前导入 JSON，不是 CSV/Excel 文件服务。 |
| 开始训练 | `POST /api/v1/workspace/runs` | 体 `design_id/expected_revision/observations/data_kind`，要求幂等键；编译、来源封存、准确方案版本、任务入队 | “runs”当前是训练请求，不是可选择任意 purpose 的通用研究实例启动 API。 |
| 运行列表与详情 | `GET /api/v1/workspace/runs`、`GET /api/v1/workspace/runs/{run_id}` | 列表最多 100 项；详情含 `run_id/design_id/design_version_id/kind/status/attempt_id/scheduler_id/input_sha256/result_json/result_sha256/error/created_at/updated_at` | 无分页筛选参数、百分比、当前节点、节点状态数组、预计剩余时间、SSE 或 WebSocket。 |
| 查看最终模型计算结果 | 同一运行详情的 `result_json` | `outputs/metrics/receipts/pipeline/data_kind/input_sources`；receipts 保留节点、准确执行组件、镜像和每端口输入输出摘要 | 完成后可追溯；执行过程中没有逐节点可视化结果流。中间节点未选为最终输出时，不具备通用中间表浏览 API。 |
| 日志 | **没有公开日志读取入口** | 容器失败日志写入服务日志，用户仅取得有界 `error` | 没有日志检索、下载、尾随或按节点日志 API；不能把错误文字当完整日志。 |
| 取消 | **没有对应入口** | — | 没有取消状态、任务停止确认或取消后成果处置合同。 |
| 重试/恢复 | **没有同一运行重试入口** | 新幂等键可以创建新运行；相同键重放既有运行 | 失败运行不能据此称已恢复同一 attempt；提交未知状态的自动对账仍缺。 |

当前整体状态仅 `queued/dispatching/submitted/running/succeeded/failed/uncertain`。`uncertain` 表示调度结果待核对，不宜显示为计算失败或成功。租约过期会受控失败，但不是自动恢复计算。

数据约束：最多 256 列、5000 行，必须完整有限数值，列代码唯一、完整对象与业务日唯一；工作区/内部写请求正文限 8 MB。当前普通数值适配仅 `field_season`，没有 point/plant/quadrat 的运行适配。[输入请求合同][S15]、[运行服务][S16]、[运行响应与存储][S17]、[执行器][S18]、[容器日志][S19]、[HTTP 正文限制][S01]

内部已有 5 个调度操作，但它们不是补齐用户操作的捷径：

| 内部入口 | 用途 |
|---|---|
| `POST /internal/v1/research/dispatch/next` | 调度消费者领取待投递任务 |
| `POST /internal/v1/research/runs/{run_id}/dispatch` | 登记准确海豚实例或提交未知 |
| `POST /internal/v1/research/claim` | Worker 凭单运行身份领取封存输入 |
| `POST /internal/v1/research/runs/{run_id}/heartbeat` | 当前执行尝试续租 |
| `POST /internal/v1/research/runs/{run_id}/complete` | 当前尝试回传结果或失败 |

### 3.6 模型管理、预测与发布为服务

| 用户动作 | 实际方法/路径 | 已有能力 | 缺口 |
|---|---|---|---|
| 保存训练模型 | `POST /api/v1/workspace/models` | 请求 `run_id/name`；只接收已成功训练运行，每运行幂等登记一个不可变模型 | 不强制通过独立评价门槛。重复用同一 run_id 传新名字返回原模型，不是重命名。 |
| 模型列表 | `GET /api/v1/workspace/models` | 最多 100 项，含 `model_id/run_id/name/model_sha256/created_at` | 无搜索、标签、所属团队、效果排序、版本家族、上线状态等列表字段。 |
| 模型详情 | `GET /api/v1/workspace/models/{model_id}` | 准确 `model_json` 与摘要，内含原方案、执行制品、训练状态、训练来源及切分日期 | 无模型元信息更新、删除、归档、共享和版本晋升入口。 |
| 用模型预测 | `POST /api/v1/workspace/predictions` | `model_id/observations/data_kind` 加幂等键；复用准确状态，生成异步运行，用运行详情查询 | 没有低延迟同步 serving 路由；非完整工作区身份下不能凭公开模型 URL 调用。 |
| 发布在线服务/设当前生效版/回滚/停用 | **没有对应入口** | — | 没有服务资源、稳定服务 URL、版本路由、调用权限、流量或生效条件管理。保存模型和方案发布都不能解释为服务上线。 |

依据：[模型请求字段][S15]、[模型存储][S17]、[模型推理编排][S16]、[状态复用执行][S18]。相关测试：[保存、重开、预测不重训及隔离][T04]、[准确来源保留][T06]。

### 3.7 账号、企业权限及团队共享

| 用户动作 | 当前事实 |
|---|---|
| 恢复个人空间 | `GET /api/v1/workspace/session` 可签发/恢复同一浏览器的 Cookie；返回 `workspace/data_scope/persistent`。本次只读核对没有调用它创建新身份。 |
| 企业委托接入 | HTTP 依赖会向部署指定的可信业务身份端核验企业、主体、有效期；没有本项目用户密码登录 API。 |
| 用户/团队/成员/角色管理 | 没有对应 API；`VerifiedPrincipal` 类型不代表已具备产品账号管理。 |
| 团队可见、邀请、授权分享、公开链接 | 没有对应 API。当前持久化按企业范围与主体隔离；测试明确同企业同事也不能读取私有草稿。 |
| 科研地块管理 | 只存在授权候选解析和选择核验，没有地块列表/详情/创建/修改/采集点管理工作台 API。 |

依据：[工作区身份][S03]、[业务网关][S05]、[数据库事务范围][S07]、[私有方案隔离测试][T02]。本次 249 的无身份请求只证明入口关闭，不证明真实企业账号、团队共享或上游地块系统已接通。

### 3.8 用户上传自定义组件

| 入口 | 实际能力 |
|---|---|
| `GET /api/v1/model-center/component-packages/schema` | 清单 JSON Schema。 |
| `GET /api/v1/model-center/component-packages/port-types` | 当前目录允许申报的准确端口类型。 |
| `POST /api/v1/model-center/component-packages/validate` | 核验 manifest、封闭参数 Schema、离线引用、版本递增及已登记端口；返回候选身份、清单摘要，**`execution_authorized=false`**。 |

不存在文件/镜像上传、候选仓、审批、隔离验收任务、验收结果查询、批准采用或动态加入运行 profiles 的用户 API。目录读取安装包中的已审定定义；运行只使用部署配置中的准确制品。`ComponentPackageManifest` 的存在不能视为上传流程已完成。[预检实现][S20]、[预检响应合同][S21]、[预检测试][T07]

## 4. 对已读五步原型的科学与产品断点

| 已读原型内容 | 当前合同/执行事实 | 适配程度 |
|---|---|---|
| “同一字段可承担多个明确角色” | `Variable.role` 是一个枚举字符串，不是 roles 数组；变量代码在方案内要求唯一 | **需扩展研究语义**。复制同一物理字段造多个私有代码会破坏准确来源及语义一致性，不能作为正式替代。 |
| “每个输入关联目标输出” | 候选回归有 `features[]/targets[]`，一组 features 对全部 targets；图可通过多个候选节点安排不同输入集合 | **部分支持**。已有组件依赖，不存在独立的每目标因素关系、角色用途与阶段映射资源。 |
| 表格分别指定训练时/应用时使用 | 输入配方和采集 `required_for` 有用途字段；预测组件可省略实测目标，复用模型状态 | **部分支持**。没有统一的每字段 train/apply 用途合同；不能把 required_for 枚举直接当完整运行行为。 |
| “样方在指定日期的平均株高 cm” | `height_cm` 固定 point、`plant_height` 固定 plant；工作区实际仅 field_season 日观测；没有样方均值聚合标准/执行适配 | **当前真实运行阻断**。需明确样方身份、取哪些株/点、平均方法、时间配对及来源证据。 |
| 土壤含水率、NDVI、LAI、日均温共同输入 | LAI 有人工通道；天气和 SoilGrids 定义有固定来源但通道未接；长势 NDVI 待绑定；SoilGrids 持水量不是当天实测土壤含水率 | **不能作为已接通组合**。指标相近不代表含义和时空支撑相同。 |
| 随机森林回归（模板示例） | 249 当前 8 项新设计组件不含随机森林 | **无对应本项目可运行方法**。若只作为原型占位应明确；正式训练需组件及准确运行制品。 |
| 灌溉处理、品种分组和独立测试 | 合同有 treatment/group、ScientificUnit.assignments、EvaluationPolicy.split_unit/holdout_unit_refs；工作区表只有地块/作物/季节/日/数值，当前训练与评价主要按训练截止日划分 | **合同存在，执行不足**。未找到按处理/品种/地块组执行独立切分的当前运行规则；分类数据适配也受限。 |
| 独立测试 MAE | executor 对预测日期晚于训练边界的、同对象同日实测计算 MAE/RMSE/bias/coverage | **已有时间后段评价的一部分**。没有独立测试数据集资源、可引用独立评价快照 ID 或前瞻采样验证流程。 |
| “D03·T-027·已关联独立验证记录” | 当前模型绑定 run_id，有准确输入来源和摘要；没有实验编号/独立验证记录资源及其关联 API | **不能用当前模型摘要替代该记录**。 |
| “V2 MAE 改善/R²” | 方案有准确版本；结果有每次运行 MAE 等，但 executor 不计算 R²，也没有版本比较或提升幅度 API | **需补评价比较语义**。前端可以在条件一致时比较已有 MAE，不能自动宣称独立改善或可比。 |
| “结果与版本规则/生效条件” | EvaluationPolicy 有 maximum_error、最低覆盖/样本、update_policy 等字段；当前保存模型仅检查运行成功，未据这些门槛执行晋升/生效 | **有声明，未形成生效控制**。阶段报告、独立评价、科研发布和服务部署还需分别落地。 |
| 科研工作台的团队模型、地块、本月/逾期采集、按周采集 | 当前个人模型列表、授权地块解析及静态来源阻断可用；没有相关业务聚合与采集任务 API | **缺后台事实来源**。不能由列表长度和 data_available=null 推算这些统计。 |
| 科研助手阶段报告 | 当前 `compile_plan` 拒绝非空 `report`，已有结果是结构化运行输出 | **没有对应报告/助手生成链路**。合同包含 ReportOptions 不代表已启用。 |

依据：[Variable 与科学单位][S22]、[方案和评价字段][S14]、[数值评价门槛合同][S23]、[实际编译限制][S13]、[回归实际算法][S24]、[实际评价与最终输出][S18]、[模型登记条件][S17]、[系统输入规则][S09]。这些是原型需求与当前实现的差距，不把尚未实现的合同能力写成现网故障。

## 5. 接 UI 前应补齐的共同合同

以下为建议，未在本轮实现：

1. 先确定工作台的正式身份和归属：个人、企业与团队共享如何衔接，再统一方案、模型、数据和版本列表的查询合同。
2. 以已读研究问题完善“观测字段—角色用途—目标关系—训练/应用阶段—科学单位”的合同，并为样方平均株高及实际因素建立可验证的来源适配。
3. 把评价口径、准确独立验证数据/修订、比较范围和版本生效条件实现为可查询、可拒绝错误状态的业务行为；不要仅保存 success_criteria 文本。
4. 运行 UI 先使用真实整体状态和完成后成果；若产品需要节点进度、取消、重试与日志，应补服务端状态及控制，不由前端定时器模拟。
5. 为长期前端接入补齐明确的响应 DTO、认证说明、列表筛选分页及错误合同。多数现有响应仍是泛化 `dict`，OpenAPI 能生成请求结构，但不能完整生成结果、来源目录和画布问题的类型。

## 6. 已核对的测试证据与本次验证边界

| 源码测试 | 证明的范围 | 不能代替 |
|---|---|---|
| [test_design_api.py:237][T02] | 幂等创建、陈旧修订冲突、准确发布、导出、同企业同事/跨企业隔离 | 团队共享、实时协作、真实企业身份服务联验 |
| [test_design_api.py:357][T03] | 兼容直接发布与准确版本历史 | 模型 serving 发布和版本流量控制 |
| [test_designer_demo.py:14][T05] | 页面辅助校验、JSON 往返、大小限制、合同问题定位 | 原型五步全部业务能力或浏览器视觉验收 |
| [test_research_runtime.py:122][T04] | 方案保存、训练、重开、模型预测不重训及隔离 | 本次 249 新运行；随机森林、组间独立验证 |
| [test_research_runtime.py:388][T06] | 标准输入来源随运行及模型保留，预测形成新来源 | 第三方/平台分析/物联网取数接通 |
| [test_research_runtime.py:252][T08] | 实测性质、单位与覆盖分母的评价边界 | 独立验证快照、R²、版本生效门槛 |
| [test_system_inputs.py:28][T01] | 四类63项、33项有绑定、仅四项当前通道、属性及来源拒绝 | 63项都有实时项目数据 |
| [test_design_api.py:109][T07] | manifest 预检、未知端口/远程 Schema 拒绝，execution_authorized=false | 上传、审批和第三方执行安全验收 |
| [test_modeling.mjs:213][T09] | 标准输入建模、实际 DOM 选择、属性与模板补列等逻辑 | 原生布局引擎、全部 Figma 交互、五步业务完整性 |

本次执行了：只读 HTTP GET、线上 Schema 解析、AST 路由集合比对、源码/调用方/测试断言追踪。没有发起训练、预测、发布、组件验证或写接口，没有新建业务数据，也未读取密钥或连接旧库。

## 证据路径

[S01]: E:/python/modarchitect/modarchitect/api.py:65
[S02]: E:/python/modarchitect/modarchitect/designer.py:17
[S03]: E:/python/modarchitect/modarchitect/runtime/workspace.py:19
[S04]: E:/python/modarchitect/modarchitect/routes.py:94
[S05]: E:/python/modarchitect/modarchitect/business.py:131
[S06]: E:/python/modarchitect/modarchitect/runtime/routes.py:28
[S07]: E:/python/modarchitect/modarchitect/persistence/design_store.py:71
[S08]: E:/python/modarchitect/modarchitect/catalog.py:28
[S09]: E:/python/modarchitect/modarchitect/system_inputs.py:100
[S10]: E:/python/modarchitect/modarchitect/designs.py:23
[S11]: E:/python/modarchitect/modarchitect/persistence/design_store.py:169
[S12]: E:/python/modarchitect/modarchitect/contracts/model_center/components.py:181
[S13]: E:/python/modarchitect/modarchitect/validation.py:101
[S14]: E:/python/modarchitect/modarchitect/contracts/research/plans.py:42
[S15]: E:/python/modarchitect/modarchitect/runtime/contracts.py:18
[S16]: E:/python/modarchitect/modarchitect/runtime/service.py:80
[S17]: E:/python/modarchitect/modarchitect/runtime/store.py:116
[S18]: E:/python/modarchitect/modarchitect/runtime/executor.py:70
[S19]: E:/python/modarchitect/modarchitect/runtime/containers.py:158
[S20]: E:/python/modarchitect/modarchitect/package_preflight.py:99
[S21]: E:/python/modarchitect/modarchitect/contracts/model_center/component_packages.py:82
[S22]: E:/python/modarchitect/modarchitect/contracts/research/variables.py:15
[S23]: E:/python/modarchitect/modarchitect/contracts/research/evaluation.py:16
[S24]: E:/python/modarchitect/components/multivariate_regression/component.py:58
[T01]: E:/python/modarchitect/tests/test_system_inputs.py:28
[T02]: E:/python/modarchitect/tests/test_design_api.py:237
[T03]: E:/python/modarchitect/tests/test_design_api.py:357
[T04]: E:/python/modarchitect/tests/test_research_runtime.py:122
[T05]: E:/python/modarchitect/tests/test_designer_demo.py:14
[T06]: E:/python/modarchitect/tests/test_research_runtime.py:388
[T07]: E:/python/modarchitect/tests/test_design_api.py:109
[T08]: E:/python/modarchitect/tests/test_research_runtime.py:252
[T09]: E:/python/modarchitect/tests/test_modeling.mjs:213
[D01]: E:/python/modarchitect/coding/deployments/modarchitect-249/README.md:150
