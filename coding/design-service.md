# 首批研究设计服务

## 逻辑

首批沿用已确认的 V4 新方案和 V3 历史样例，交付组件目录、导入检查、草稿与不可变方案版本。设计阶段只编译配置和核验业务对象授权。真实调度、研究实例、报告和用户上传入口按后续阶段推进。

1. 目录按准确代码和版本读取冻结定义。检查导入摘要后，使用旧纯合同验证方案、连线和输入配方。科学摘要排除布局。历史导入保留原组件版本，新方案发布检查当前采用资格。
2. 私有接口通过固定业务身份端验证委托与受众。要求点位的草稿在新增、修改和新增方案版本前通过固定选地端核验授权。选地请求由平台签发。授权失败停止写入，外部网络请求在写事务外完成。
3. PostgreSQL 事务绑定企业来源编号和主体。创建以企业范围、主体和幂等键唯一。保存和发布对草稿修订做比较，锁定草稿后复核，提交后响应。重复发布同一定义返回同一版本，已发布版本与节点绑定不可变。读取准确历史版本保留原身份。

## 结构与依赖

| 模块 | 职责 |
| --- | --- |
| `contracts/` | 移入首批实际调用的旧纯合同，保留 JSON 格式、图编译、科学单位及摘要规则。共享规则按安装包版本复用。 |
| `catalog.py`、`validation.py` | 目录负责准确版本与新设计采用。验证负责组合、参数 Schema 和观测列检查。 |
| `business.py` | 调用固定身份和选地端，验证受众、租户、主体、时效、查询摘要和候选关系。 |
| `designs.py` | 编排草稿、检查和发布。数据库读写及行锁集中在 `persistence/`。 |
| `api.py`、`routes.py` | 装配 FastAPI，声明版本化 HTTP 入口与协议错误。 |
| `components/template/` | 组件提交结构及复跑命令示例。逻辑斯蒂沿用准确数值制品，以同一清单、输入输出和摘要规则验收。 |

依赖方向为 HTTP → 方案动作 → 纯合同、固定业务适配和存储。存储以独立数据库为部署边界，迁移与运行角色分离。业务规则和科学计算分别由合同模块和计算制品承载。首批接受冻结目录内的组件，未知来源、未接入报告、制品适配和无法验证的科学绑定拒绝进入发布。数据库在方案根和关联表启用强制行级安全，应用在事务内设置范围和主体，角色只获得必要读写权限。 [PostgreSQL 行级安全](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)

## 用法与验收

沿用旧 API 前缀和旧草稿及准确版本路径。运行使用 `modarchitect.api:app`，数据库使用 `modarchitect-db` 升级。组件开发者使用本地文件执行模板及清单预检接口。纯合同和目录随应用 wheel 交付，逻辑斯蒂数值包独立构建和安装。 [运行和 HTTP 用法](../README.md) · [组件开发用法](../components/README.md)

### 2026-11-11 工程验收记录

| 验收 | 实际命令和结果 |
| --- | --- |
| HTTP 设计闭环 | 在新建的本机 PostgreSQL 18.4 容器内运行迁移，使用原生低权限测试角色。设置 `MODARCHITECT_TEST_DATABASE_URL` 后执行 `python -m pytest -q`，7 项通过。覆盖准确 V3/V4 导入、篡改拒绝、科学摘要、清单预检、并发幂等、版本追加、跨企业和主体隔离、点位撤权。业务身份和选地使用 HTTP 协议替身。 |
| 独立库和安装 | 执行 `python -m pip wheel --no-deps .` 后在源码目录外安装，`modarchitect-db`、存活接口、V3 准确目录和 OpenAPI 通过。最终应用 wheel SHA-256 为 `aac788c62d0c2a4f456fd6efda2c54115c89de4a965740dbd8cef4d69e66a483`。隔离空库完成升降级及再次升级，`alembic.command.check` 无待升级结构。已保存方案的测试库拒绝降级，冻结版本拒绝更新。 |
| 组件模板 | 执行 `python components/template/verify.py`，成功、记录不足和篡改三例通过。用 `docker buildx build` 导出并加载 OCI 镜像，`verify.py --image modarchitect-component-template:design-test` 复跑三例通过。实际镜像 manifest 摘要为 `sha256:24ee7514586a62cdcbc2027ca58d0041fac5d62190908fa65583e4d3cb6d0d3d`，带该摘要的清单通过 API 预检。 |
| 逻辑斯蒂数值 | 独立 Python 3.12 环境构建并从 wheel 安装，执行 `python -I components/logistic_growth/verify.py --expected-wheel-sha256 <本次制品摘要>`。恢复参数 100、0.1、50，常量序列按预期拒绝。工程 wheel SHA-256 为 `f2bafdbbfa5eea4e7f29f034a54ca9241172e13269a2b23a1d1dbd6b6a99f16c`，历史绑定继续使用原封存摘要。 |
| 静态检查 | 38 个本次新增或修改的 Python 文件通过文件头检查，Ruff 通过。数值核心与原逻辑斯蒂源码字节一致。 |

249 已从独立 PostgreSQL 空库初始化，API、低权限数据库连接和 V3/V4 文件校验通过。原冻结运行制品、真实业务授权与点位、原设计器页面、研究实例与海豚闭环、正式自助上传按后续阶段验收。 [249 部署记录](deployments/modarchitect-249/README.md) · [首批验收用例](model-designer-first-batch-acceptance.md)
