# modarchitect

独立的模型设计器与研究服务项目。目标包含对外 HTTP API、独立 PostgreSQL 研究库和 DolphinScheduler 调度。

- [项目迁移需求与验收](coding/model-designer-migration.md)
- [首批研究设计服务的逻辑与结构](coding/design-service.md)
- [模型设计器演示与验收](coding/model-designer-demo.md)
- [模型成果连接与验收](coding/model-composition.md)
- [研究运行、模型保存与预测验收](coding/research-execution.md)
- [通用运行、节点用途与非训练分析验收](coding/runtime-generalization.md)
- [Figma 分步设计器实现与真实界面验收](coding/figma-designer-implementation.md)
- [设计器易用性与节点规划报告](coding/model-designer-usability-report.md)
- [成熟建模产品对照研究](coding/modeling-usability-product-research.md)
- [组件开发模板与复跑方式](components/README.md)
- [249 部署与验收记录](coding/deployments/modarchitect-249/README.md)
- [前端对接：curl](docs/frontend-integration.md)
- [业务接入、数据库字段与重试：curl](docs/business-api-integration.md)
- [模型设计器API入口与完整闭环流程图](docs/model-designer-api-flow.md)
- [生物所SR850部署与验收](coding/deployments/modarchitect-biology/README.md)
- [初始化设计](coding/project-bootstrap.md)
- [Codex 项目规则](AGENTS.md)

## 安装与运行

需要 Python 3.11 或更高版本。以下命令在项目根目录的 PowerShell 运行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn modarchitect.api:app --host 127.0.0.1 --port 8000
```

运行后打开空白研究工作区，从系统指标库采用准确变量和来源、设置研究目标，再从目录选择计算模型。已登记指标和模型允许设计组合；未接通的来源、资料或参数可明确保留待配置，实际运行另行检查取数与制品。`/health` 提供存活检查，`/docs` 提供版本化 API 文档。运行安装可用 `python -m pip install .`。 [本机设计器](http://127.0.0.1:8000/designer/) · [249 设计器](http://192.168.3.249:18925/designer/)

## 在 249 使用研究与预测

打开 [多变量研究](http://192.168.3.249:18925/designer/?research=multivariable) 或 [串联研究](http://192.168.3.249:18925/designer/?research=chain)。样例会保存到当前浏览器的个人工作区。可编辑方案、修改观测或上传同格式 JSON，再点击“运行研究”。运行成功后点击“保存为模型”，填写新的日期及因子并“开始预测”。多变量样例同时输出株高和叶面积；串联样例先用历史生长模型生成因子，再合并其他变量预测株高。

默认界面按公开原型分为“选择模型 → 模型配置 → 检查与确认”。配置页依次设置基础信息、输入与建模关系、数据来源、计算与评价、结果与版本。指标从系统目录选择，用途表与实际模型参数同步；完成后可训练、保存候选模型并输入新因素预测。数据配对的含义与规则有单独说明；点击“查看组件与连线”仍可编辑准确拓扑、版本和节点设置，按依赖自动整理后从左到右读取。

方案、观测、运行及训练状态均持久化在研究库。刷新后可从三个选择框重开方案、运行与模型。当前个人工作区使用签名 Cookie，需在同一浏览器保留该工作区；企业身份接口仍按原授权协议接入。示例为合成数据，预测结果用于工程闭环验证。

界面逻辑与 DOM 交互测试使用 Node.js 24.13 或更高版本，执行 `npm ci --ignore-scripts`、`npm test`。运行依赖仍由 Python 制品提供，Node 测试依赖不进入服务镜像。

## 在独立 PostgreSQL 库启用方案保存

1. 准备空研究库和两个数据库角色。迁移角色管理表结构，应用角色使用原生登录、无表所有权及 `BYPASSRLS` 权限。
2. 用迁移角色设置 `MODARCHITECT_MIGRATION_DATABASE_URL` 并运行 `modarchitect-db`，或运行 `python -m modarchitect.persistence.migrate`。连接串格式为 `postgresql+psycopg://用户:密码@地址/研究库`。
3. 用数据库管理员为已创建的应用登录角色授权。下面以 `modarchitect_app` 为例，并假定应用已有该库的连接权限。

执行[应用角色授权](coding/deployments/modarchitect-249/app-grants.sql)，按实际角色名替换`modarchitect_app`。当前迁移为0011，已包含不可变保存回执及新增基础回归合同；应用角色不能修改或删除回执。

4. 配置应用连接 `MODARCHITECT_DATABASE_URL`。设置 `MODARCHITECT_API_KEY`，默认`MODARCHITECT_AUTH_MODE=api_key`。企业范围由业务后端传`provider_name/company_id`；不调用用户登录身份端。启用选地时另配置 `MODARCHITECT_SELECTION_URL`、`MODARCHITECT_SELECTION_AUDIENCE`、`MODARCHITECT_SELECTION_KEY`。两个业务端点使用 HTTPS 和既有身份及选地协议。配置后重新启动应用。

## 通过 HTTP 复跑设计闭环

研究路径以 `/api/v1/research` 开头，传 `X-Modarchitect-Api-Key`。私有资源请求还需同一企业范围`?provider_name=来源代码&company_id=正整数`；新保存入口也可在正文传这两个字段。下面用 [V4 样例](coding/model-designer-fixtures/research-fit-v4.json) 作为输入。

| 操作 | 请求 |
| --- | --- |
| 读准确组件 | `GET /api/v1/model-center/components/logistic_growth_curve?revision=4` |
| 导入并检查 | 将完整文件发给 `POST /configurations/import`。将返回的 `definition` 发给 `POST /configurations/draft`，再将生成的草稿文件发给 `POST /configurations/check`。 |
| 草稿暂存与重开（兼容接口） | 将草稿文件发给 `POST /design-drafts`，带 `Idempotency-Key`。用 `GET /design-drafts/{design_id}` 重开。修改时用 `PUT`，请求体包含 `expected_revision` 和新的 `configuration`。正式提交使用下一行的`design-saves`，不能把暂存成功当作完整设计校验通过。 |
| 业务关联保存 | 新接入使用`POST /design-saves`，响应只有方案ID、修订、配置摘要；`GET /design-saves/{request_id}`恢复原回执。业务关联失败不重复创建方案。见[接入文档](docs/business-api-integration.md)。 |
| 发布与导出 | 向 `POST /design-drafts/{design_id}/publish` 发送 `{"expected_revision": 1}`，修订取最新草稿响应值。用 `GET /design-versions/{design_version_id}/configuration` 导出。 |
| 采集点 | 方案保存 `sampling_selection` 后，写入及新版本发布会在线核验每块地的授权点位。用户可先调用 `POST /field-selections/resolve` 查看候选。 |

[V3 样例](coding/model-designer-fixtures/research-fit-v3.json)用于核对原版本和文件摘要。已采用的新设计入口使用 V4。数据库行为回归在独立库上运行。完成迁移、授权后，将低权限测试连接设为 `MODARCHITECT_TEST_DATABASE_URL` 并执行 `python -m pytest -q`。
