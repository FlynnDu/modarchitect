# 首批设计闭环复跑用例

2026-11-11。首批以逻辑斯蒂参考组件贯通独立安装、目录、方案检查、草稿和不可变发布。另以两地块点位夹具验证业务选地。现有 HTTP 和真实 Worker 用例给后续运行迁移提供对照。

## 固定输入

| 文件 | 组件和用途 | 旧文件中的完整性摘要 |
| --- | --- | --- |
| [research-fit-v3.json](model-designer-fixtures/research-fit-v3.json) | 提交 `53d86cb` 的 `logistic_growth_curve@3`，用于历史导入与准确版本回放。 | `e856a15d2d3c0bc4b81a1717eaea8c3f616c12f2281c52f53cfb8391eb63e578` |
| [research-fit-v4.json](model-designer-fixtures/research-fit-v4.json) | 已核对的工作区 `logistic_growth_curve@4`，用于新方案闭环。 | `c345cd7ab5962e51b0be48ce2c611d9b4f80b2b8e2d7040a4dcbacb00ba5f68c` |

两个样例均为合成工程拟合，驱动轴 `driver` 用 day，目标 `height_cm` 用 cm，保存 `curve` 和 `fitted` 输出。[组件合同夹具](../modarchitect/contracts/logistic-growth-contracts-v1.json)保留 V1–V4 的定义及 V3、V4 引用的 V1 实现依赖。V3 在工作区 `history.json` 中与已提交定义一致，摘要为 `cea4471fde737c04e0ff5506a4cba78b40dba0c42c5b9e81d33b957254c993e6`。V4 在 `current.json` 及本次公开精确版本 GET 的摘要均为 `3b3d6282585fbbffd04aedd63a1af3368406f43422fd62166d632874101ffcc6`。

V1–V4 声明使用同一数值包 `mlgrowth-logistic-growth==1.0.0`，wheel SHA-256 为 `95bfa6671163804a392d7e6856c9e6baa0066cd5876a46529c62b1772fd716e9`，与历史 V2 的独立 wheel 验收记录一致。V3、V4 的实际执行绑定和候选文件入口须按准确目录、运行清单及安装制品复核。 [历史制品验收](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/coding/logistic-growth-verification-20261104.json>)

## 在批准的隔离批次复跑旧对照

使用批准的 249 批次副本和明确的 Python 入口。在副本核对[源码指纹](model-designer-fixtures/source-fingerprints.json)与所选用例。V3 使用提交版样例与准确目录。点位用例来自工作区，须同时带上匹配的目录、路由、服务及测试夹具。旧测试会写测试库并创建、授权或调整共享角色，运行前应确认专用 PostgreSQL/PostGIS 集群及串行使用。点位与草稿测试夹具要求端口 `55461` 且库名在 `test_research_study_database.py::engine` 的允许集合内，例如使用本批专用实例中的 `research_launch_test_20261105`。通过 `MLGROWTH_PGSQL_HOST/PORT/DB/USER/PASSWORD` 提供隔离连接，预先按旧批次引导 schema 和 PostGIS、升级所选迁移链并准备作物与目录。Worker 测试使用实际科学依赖、已校验的组件运行清单 `MLGROWTH_COMPONENT_RUNTIME_MANIFEST`。浏览器用例另外需要批次 Node、Playwright 及 `PLAYWRIGHT_MODULE`。

以下从批准的旧系统批次副本根目录执行。预先把 `BATCH_PYTHON` 指向该批次的 Python 可执行文件。

```bash
"${BATCH_PYTHON:?}" -m pytest -q \
  tests/model_center/test_research_drafts.py \
  tests/model_center/test_research_variable_library.py::test_old_configuration_and_template_sha_are_preserved \
  tests/model_center/test_research_launch.py::test_save_and_launch_require_business_points_in_each_selected_field \
  --junitxml=design-and-points.xml

"${BATCH_PYTHON:?}" -m pytest -q \
  tests/model_center/test_logistic_growth.py \
  tests/model_center/test_research_http_workflow.py \
  tests/model_center/test_research_run_database.py \
  tests/model_center/test_research_recovery.py \
  tests/model_center/test_research_publications_http.py \
  --junitxml=research-and-worker.xml

"${BATCH_PYTHON:?}" -m pytest -q \
  tests/model_center/test_research_launch.py::test_authenticated_browser_publishes_selects_and_queues_without_mocking_api \
  --junitxml=design-browser.xml
```

上述命令供隔离环境复跑。本次未运行旧系统有写入的回归。旧 HTTP 夹具使用真实应用端口、低权限数据库与 Worker CLI，业务身份、选地、上下文、观测、交付和调度仍使用替身。跳过浏览器或运行制品缺失应记入该批次结果。 [旧测试夹具](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/tests/model_center/research_http_fixture.py>) · [旧点位用例](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/tests/model_center/test_research_launch.py>)

## 对新服务的可观察判据

下面的路径使用旧合同便于对照。首个实现设计须写明哪些直接兼容，哪些经明确的版本化接入路径提供，并以原设计器和外部调用方请求复核。

| 用例 | 操作 | 通过条件 |
| --- | --- | --- |
| 组件模板与制品 | 用模板在干净环境构建参考组件，按冻结清单安装或解析受控制品，运行正例、应拒绝的输入和错误制品摘要。目录读取准确 V4 并验证连线和属性 Schema。 | 版本、制品和合同摘要均可追溯。Schema 或样例失败可定位至参数或端口。新增同协议组件可通过登记被发现，通用编排无需增加代码分支。参考组件可独立构建和复跑。 |
| 历史读入 | 使用准确目录导入 V3 文件，按 `revision=3` 读取已冻结定义。再篡改文件中的定义且保留原摘要重新导入。 | 历史样例按原准确版本和原文件摘要读回。篡改被拒。V3 的历史解释资格与新设计采用资格各自可查。 |
| V4 查询、校验、保存、重开、发布 | `GET /components/logistic_growth_curve?revision=4`，`POST /configurations/import` 导入文件，将 `definition` 传给 `POST /configurations/draft` 得到草稿信封。对该信封 `POST /configurations/check`，再用同一委托和 `Idempotency-Key` 创建草稿并重开。用当前 `expected_revision` 更新，再发布并从 `/design-versions/{version_id}/configuration` 导出。 | 首次创建 201，同键同原始内容 200 且为原 `design_id`，同键不同原始内容 409。过期修订的更新 409。发布成功返回准确版本，重复发布同一修订复用版本。导入文件摘要、草稿摘要、排除布局的科学摘要、数据库冻结版本摘要分别按对应合同对比。新库生成新方案 UUID，布局变化保留在文件里，科学摘要相同。 |
| V4 科学合同拒绝 | 使用同一 V4 定义，将轴单位从 day 改为 cm 或从观测配方移除 `height_cm`。重新生成草稿信封后检查及尝试发布。 | 检查响应 `valid=false`，能定位到 `method` 的 `observations` 及错误请求字段。格式有效的未完成草稿可按旧合同保存。拒绝发布，研究实例和投递队列无新增。 |
| 点位保存与启动 | 复用 `collection_plan(point_collection=True)` 和两个地块。先不选地，再给第一块添加授权点位而第二块为空。分别试草稿创建和旧直发路径。补齐第二块后创建、重开、发布。撤掉第二块授权点位，试更新、新版本发布和实际启动。补齐后重试。 | 无选地、任一地块缺点位、开关与单位冲突时 422。旧对照已覆盖缺点位的创建、直接发布、更新与启动。新版本发布另加「先保存、撤掉点位、首次发布或内容变化后发布」用例，预期拒绝且版本数不变。重复请求若只是返回已冻结版本，保留其幂等语义。两块补齐时保存、发布、启动通过。规则中点位要求只接收两块授权点位，整地块要求保留两个地块单位。 |
| 主体和企业隔离 | 所有者写入后，同企业另一主体、另一企业和已撤销项目授权的身份尝试相关读取与写入。用原生非特权数据库连接核查，再复用连接切换身份。 | 私有资源不可跨主体或企业读取与修改。项目撤权阻断实例、运行与成果访问及新工作。HTTP 层保持旧端适用的 401、403、404 或 503，数据库无越权写入或连接身份残留。 |
| 后续运行对照 | 从已发布方案建实例，先无数据，随后提供合格观测修订，冻结输入、派发、领取、回传、投递报告。固定截止时点重发，分别模拟错误回执、并发领取、尝试过期、取消和迟到回传。 | 无数据时只有采集事件，就绪后得到准确 `run_id` 和输入摘要。相同输入复用运行，重试保留输入。只接受有效尝试的结果和报告。逻辑斯蒂科学对照复用旧组件数值用例的期望与容差，合成成果标识保持原资格。新服务的真实调度通过标准见[调度验收](model-designer-dolphin-acceptance.md)。 |

真实业务联验补测委托过期或撤销、受众错误、跨企业地块、同企业不同主体、第二块点位撤权、观测撤回和重复交付。保留脱敏请求响应、库内行和回执证据。真实点位和 NDVI 取值另按冻结地点、时间、影像版本核对。

## 开工与验收条件

- 本地首批可据两份固定样例、目录摘要、迁移顺序和可观察判据编写实施设计。设计需锁定共享契约制品版本、历史目录的供给方式、组件模板及执行合同、旧 API 兼容路径和首个独立库迁移范围。当前选择 V4 用于新设计，V3 用于历史兼容。
- 进入隔离验收前，确认隔离库、原生低权限角色、冻结目录与运行制品均可用。产出空库升级、样例导入、重复导入、目录冲突及跨企业隔离的命令和结果。验收提交须记录准确源码与制品版本、实际命令、响应及摘要、迁移版本与约束证据。
- 首批通过需要组件模板与 V4 样例能在独立安装中复跑，V3 历史身份和摘要可追溯，设计器保存、重开、发布及点位正反例通过。真实授权、业务数据、真实 DolphinScheduler 和用户自助上传各自记录验收结论，完成相应联验后开放对应能力。

基线阶段本地存活用例 1 通过。两份固定 JSON 的完整性摘要已按旧规范 JSON 重新计算并与文件内值比对，84 项选定文件的本地源码指纹及文档链接检查通过。最新新库和接口结果见[首批设计服务](design-service.md)。Worker 运行、认证浏览器与真实调度待后续隔离复跑。
