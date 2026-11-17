# 生物所设计器工作区配置修复

2026-11-16。用户直接访问`/designer/#select`，页面显示`Workspace identity is not configured`。

## 已复现与原因

全新HTTP客户端调用`GET /api/v1/workspace/session`得到503及同一错误。线上Nomad模板与运行变量均缺少workspace_key。设计器research.js初始化、采用模板和保存使用独立浏览器工作区；业务API-Key只负责业务系统接口，不能代替工作区签名。空浏览器也失败，排除旧Cookie损坏。

## 修复边界

用户要求直接使用本系统设计器，按已有浏览器工作区合同启用它：独立随机签名密钥保存在Nomad变量`nomad/jobs/modarchitect-api`的workspace_key，模板注入`MODARCHITECT_WORKSPACE_KEY`。已有值不得轮换或复用业务Key；浏览器只取得HttpOnly签名Cookie，业务Key不下发页面。

页面工作区按既有`modarchitect_workspace`范围及独立随机主体隔离，不授予任何企业范围。业务接口仍验证原`X-Modarchitect-Api-Key`与企业声明。当前修复不改变Python业务规则、数据库结构或海豚Worker。

## 验收

先保留503失败证据，再只修改缺失配置。验证新会话200、签名Cookie可复用、错误签名拒绝。真实线上DOM完成模板浏览、载入、编辑、保存、刷新重开与配置下载，不能只检查静态HTML或/health。增加既有验收脚本的仅设计保存模式以跳过本轮未部署的研究计算，不使用网络替身。修复后核对Nomad模板/运行Job一致、Consul passing、业务Key和既有企业方案保持不变。


## 完成结果

17:31北京时间：API Job版本3，deployment successful、Consul passing。业务Key及原企业方案摘要保持不变，Worker仍为版本36；未修改Python产品代码、数据库结构或镜像。

复现命令首先报出与用户一致的Workspace identity is not configured；补齐配置后同一命令通过，另起Node进程带原Cookie重开并导出再导入成功。34项前端测试通过。用新工作区读他人方案404、错误签名401、Cookie不能替代业务Key401均通过。

```powershell
node scripts/verify_designer_ui.mjs --base-url http://172.16.1.122:18925 --design-only --session-file .ops/designer-workspace-fix/private/session.json --output .ops/designer-workspace-fix/ui-created.json
# 从上一步输出读取design_id，作为--reopen-study传入：
node scripts/verify_designer_ui.mjs --base-url http://172.16.1.122:18925 --design-only --reopen-study <design_id> --session-file .ops/designer-workspace-fix/private/session.json --output .ops/designer-workspace-fix/ui-reopened.json
npm test
node --check scripts/verify_designer_ui.mjs
```

[验收记录](deployments/modarchitect-biology/designer-workspace-fix-20261116.json)。Cookie仅保存于忽略的私有验收文件，不进入公开报告。浏览器研究空间与业务企业空间隔离，业务Key不下发页面。
