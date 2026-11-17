# 生物所“浏览、设计、保存”上线评估

2026-11-16更新。生物所实际部署结果以[SR850部署验收](deployments/modarchitect-biology/README.md)为准。用户进一步明确改为仅验证本项目API-Key，信任业务后端传入企业范围，不再接用户登录身份端。下文为此前接口范围及验收基线。

| 功能 | 接口 | 当前结果 |
| --- | --- | --- |
| 组件与准确版本 | `/api/v1/model-center/components`、`/{code}?revision=...` | 已验证 |
| 指标库与变量采用 | `/api/v1/model-center/research-inputs`、`/configure` | 已验证；未绑定来源明确拒绝 |
| 公共研究模板及详情 | `/api/v1/research/study-templates`、`/{id}` | 新增企业入口，不依赖工作区Cookie |
| 已训练模型列表及详情 | `/api/v1/research/models`、`/{id}` | 新增企业入口，复用既有主体隔离 |
| 配置文件生成、检查和导入 | `/api/v1/research/configurations/draft`、`/check`、`/import` | 已验证往返 |
| 保存与确认 | `POST /api/v1/research/design-saves`、`GET .../{request_id}` | 原子保存及不可变回执；仅返回ID、修订、摘要 |
| 我的方案、重开与修改 | `/api/v1/research/design-drafts`、`/{id}`；修改走`design-saves` | 已验证；旧修订409，重放不重复创建 |

22个当前采用组件、65项系统指标、20份研究模板。65项指标中35项可按准确绑定配置，30项仍明确拒绝；可配置不代表真实取数已经接通。

## 保存职责

本系统保存完整方案和发布版本。业务系统保存业务关联与方案引用。发送前暂存原请求，确认业务关联提交后清理；这用于中断恢复，不作为第二份权威方案。

真实curl已验证：发送前业务进程退出后恢复；本系统提交后业务关联回滚，再查询原回执完成关联；同键重放无重复；修改后旧回执保持原修订；并发旧修订不能覆盖新内容。

## 真实验收

- Python：125通过、0跳过，独立PostgreSQL17及低权限应用角色。
- 前端逻辑与DOM：34通过、0跳过。
- Alembic：新库升级0010，元数据无差异。
- 回执：强制行级安全；应用仅SELECT/INSERT；表所有者修改也被触发器拒绝；已有回执时迁移回退被拒绝且结构保持0010。
- 研究写入：实际流式正文超过8,000,000字节返回413，不进入保存流程。
- Ruff与本次10个Python文件头检查通过。
- wheel在源码目录外安装，确认新接口、0010迁移、20模板和API启动正常。

[curl证据](deployments/modarchitect-249/business-curl-acceptance-20261116.json) · [数据库约束证据](deployments/modarchitect-249/business-save-migration-acceptance-20261116.json)

## 生物所仍需完成

1. 部署新包，迁移至0010并执行应用角色授权。
2. 业务后端传入准确企业范围并添加本项目API-Key，落实业务关联及临时待发送记录；用户登录与用户权限留在业务系统；采样点方案另接地块资料。
3. 新前端按文档调用企业API。现有`/designer/`样例页面仍使用个人工作区，不能直接作为企业账号页面交付。
4. 用两个真实账号验证保存、刷新重开、权限隔离、冲突及中断恢复。

[前端curl](../docs/frontend-integration.md) · [业务curl与数据库字段](../docs/business-api-integration.md)

本次身份端为HTTP合同适配替身，业务关联为隔离SQLite事务；未写入生物所业务库。249历史验收不能替代本次生产联验；本轮未更新249运行版本。
