# 企业方案保存与业务引用接入

2026-11-16。用户准备上线，要求本系统保存完整配置、业务系统保存引用；交付最少字段、直接curl和接入验证。本轮不操作旧mlgrowth或生物所生产库。

## 权威归属与入口

本系统唯一保存方案JSON、当前草稿修订和准确发布版本；业务库保存方案引用、业务关联和待完成保存请求。生物所按用户进一步确认改为默认API-Key模式：业务后端负责用户登录与权限，服务验证本项目Key后采用provider_name/company_id，固定business_api主体，同企业共享。原企业委托仅在显式delegation兼容模式核验；当前接入见docs/business-api-integration.md及coding/biology-nomad-deployment.md。业务库不在本项目中，本系统不能声称已经写入业务关联；成功回执证明本系统提交成功，业务提交仍由业务事务决定。

业务后端发送前持久化原请求ID、原正文及pending，以便POST尚未抵达时也能在进程重启后重发。收到确认后，引用回写、saved和正文清理在同一业务事务提交。待发送正文只作短期待办，不能作为另一份权威配置；409/413/422且查无回执时转failed，由用户修正或明确放弃，不自动覆盖。此业务库流程由对接方实现，本轮用隔离引用库模拟验收。

现有创建具备幂等、修改具备修订检查；修改响应丢失后再保存不能稳定识别原成功修订，创建重放还可能返回后来被改动的草稿。这不足以支撑可靠的两阶段关联。

新增 `POST /api/v1/research/design-saves` 与 `GET /api/v1/research/design-saves/{request_id}`。请求键使用UUID；新建只传configuration，修改增加design_id和expected_revision。返回严格三项design_id/revision/configuration_sha256。成功回执与草稿写入同一短事务，后续修改不改变旧回执。相同主体同键同内容重放，异内容409；并发修改仍检查修订，网络超时先按原请求ID查询/重放，不另造请求。

回执是保存确认，不是历史草稿JSON快照。业务记录以design_id打开当前草稿；需要固定供执行的方案时采用既有design_version_id。业务关联失败保留原请求与回执，重试关联，不回滚或覆盖用户方案。本系统不信任业务侧自报的“关联成功”，也不在响应添加虚构同步状态。

## 结构与兼容

- contracts/research/design_saves.py：最小输入和回执合同。
- persistence/design_save_store.py：不可变、按主体隔离的保存回执；不重复配置正文。
- designs.py：复用现有配置、来源、采样授权规则，编排一次保存与回执事务。
- routes.py：企业保存/查询、模板详情与已训练模型读取，使用既有业务身份。
- api.py：企业研究写入与现有工作区共用8,000,000字节流式正文预算，解析/核权/落库前超限返回413，不依赖Content-Length。
- 迁移0010：新增回执表、RLS及不可变约束；已有草稿、版本、模型和接口不变。
- docs/business-api-integration.md：前端/BFF调用及业务库最少字段，全部用curl。

现有POST/PUT草稿接口保留；新对接采用design-saves入口，不改变旧调用的重放语义。组件合同、来源适配器和科学运行不修改。前端仍由业务系统的服务端转接，业务Key不得下发浏览器。

## 验证

先用HTTP正反例验证回执稳定、重复/异载荷、并发更新、另一主体不可读、业务关联失败后的重放，以及新增企业目录不依赖工作区Cookie。使用本项目独立PostgreSQL与低权限角色验收迁移/autogenerate和事务。curl脚本启动真实本机HTTP服务，使用隔离业务身份端及独立研究库；明确区别本机接入验证与生物所生产联验。完成Python文件头、Ruff、相关回归与打包。

## 2026-11-16完成记录

- 真实curl经过本机HTTP与独立PostgreSQL：目录、变量配置、模板、配置往返、新建/更新、原回执恢复、旧修订409。隔离业务引用库在发送前关闭重开、关联事务回滚后均恢复；确认后清理临时正文，无重复方案。
- 整套Python行为测试125通过、0跳过；Node逻辑/DOM34通过、0跳过。
- 迁移0010实际autogenerate后补RLS及不可变约束；新库upgrade/check无差异；已存回执的downgrade拒绝且回滚保持0010；表所有者修改触发拒绝，应用仅SELECT/INSERT。
- 先复现企业写入超限503而未拦截，再扩展共用流式预算；新旧企业保存及配置生成超限均413。
- Ruff与10个本次Python文件头通过。wheel源码目录外独立安装后验证新接口、迁移及20模板。
- 两个只读审查分别复核规范和需求，修正export、导出当前配置、发送前中断恢复及413失败状态。
- 不新增运行依赖。原组件/历史合同/来源/模型计算回归通过；原草稿接口保留，新增入口保证原保存回执稳定。
- 未部署249或生物所；真实业务身份、业务数据库及业务BFF不在本项目内，须按对接文档联验。

实际命令：

```powershell
$env:PYTHONPATH='.'
$env:PYTHONIOENCODING='utf-8'
$env:MODARCHITECT_PYTEST_ARGS='["tests","-q","--maxfail=1"]'
.venv/Scripts/python.exe .ops/verify_local_database.py
npm test
.venv/Scripts/python.exe -m ruff check modarchitect tests/test_design_api.py .ops/verify_local_database.py
.venv/Scripts/python.exe E:/CodexData/home/skills/python-project-standards/scripts/check_python_headers.py modarchitect/api.py modarchitect/contracts/research/design_saves.py modarchitect/persistence/design_save_store.py modarchitect/designs.py modarchitect/routes.py modarchitect/persistence/design_store.py modarchitect/persistence/migrations/env.py modarchitect/persistence/migrations/versions/0010_design_save_receipts.py tests/test_design_api.py .ops/verify_local_database.py
.venv/Scripts/python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir .ops/business-release-20261116
```

[curl证据](deployments/modarchitect-249/business-curl-acceptance-20261116.json) · [迁移约束证据](deployments/modarchitect-249/business-save-migration-acceptance-20261116.json)

补充验收：对真实算法产生并保存的合成训练模型，通过企业模型列表和详情读回；跨企业、同企业另一主体的列表不出现该模型、详情404。修改后的API测试11通过、0跳过；生产代码与此前125项完整回归的版本相同。

交付包：`dist/business-design-20261116-795e45b0db08/`，wheel SHA-256 `795e45b0db08605f2f388038cada98a23c9af8da6d364dd05adee1ee415ad055`。包含wheel、两份curl文档、应用授权SQL及无密钥验收证据。
