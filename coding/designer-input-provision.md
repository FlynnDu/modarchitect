# 设计器逐项展示输入来源

2026-11-16。入口：`/designer/#configure/inputs`、系统指标库弹窗。

## 事实与边界

- `GET /api/v1/model-center/research-inputs` 已返回 category/subcategory、source、execution。`configure` 返回 variable/requirement/entry；保存的 collection_requirements 保留 source/method/catalog_binding。
- 用途表没有消费这些来源信息。平台分析21项、物联网9项缺正式取数绑定；人工15项中11项的采样尺度未被当前日值表适配。不能通过取消禁用伪装接通。
- selectable 表示目录采用资格；当前设计器还要求 field_season。execution 是取数通道能力，data_available=null 不代表当次资料齐备。第三方已有通道也不能据此宣称生产环境已经完成真实取数。

## 实现

1. 来源说明使用一个纯展示模块。通过 catalog_binding 的 kind/code/definition_version/contract_sha256 准确解析目录，不按变量名称或代码猜来源，不在方案另存一份展示字段。
2. 用途表增加“数据提供方式”，显示二级来源类别、提供方、填写/导入或平台采集方式及已选土层/统计属性。未绑定、历史来源待核验分别提示。合成示例单独标识，不能暗示真实资料已经获取。
3. 指标库与用途表共用来源解析。保留服务端权威校验；待接入和尺度未适配按钮说明原因，不展示无效的用途选择。分类显示登记数与当前可添加数。
4. studio 复用启动时已读取的目录传给 wizard，无重复请求。既有角色、真实模型参数、配置文件合同、数据库和 Worker 均不改。

调用链：目录与方案绑定 → 纯来源说明 → 用途表/已选输入；指标采用 → 原 configure → 原 addSystemInput → 原保存。

## 验收

- 先用真实 DOM 回归复现用途表无来源列、待接入按钮不清晰；修复后人工/气象/土壤来源及属性准确。
- 历史绑定摘要或版本不匹配时不宣称当前来源已接通；无绑定不猜来源；合成示例明显标识。
- 保存并在新页面重开，新增指标、用途和来源绑定不丢。原前端回归通过，线上目录/配置合同不变。
- UI 静态包发布只滚动 API；不改计算协议与 Python 代码，不滚动 Worker，不执行数据库迁移。

## 验证结果

- 失败复现：`node --test --test-name-pattern='用途表逐项|未接通指标' tests/test_modeling.mjs` 初次2项失败，分别缺来源列及待接入提示；实现后2项通过。
- `npm test`：37项通过，包含新增土壤属性、准确绑定及历史版本反例。`node --check scripts/verify_designer_ui.mjs` 通过。
- API wheel对比已部署3805897175a1基线，仅input-provision.js/studio.js/system-inputs.js/wizard.js/wizard.css五项变化；全部计算代码、合同与数据库逻辑逐字节相同。新wheel摘要54f2fc90d02aba3d6c4a3299637163c986b0ed9d3f23bb0619c179f31f40f22f。
- 线上API安装包134个文件逐项摘要核对，差异0；上一API Job及模板已在新制品目录以0600备份，可单独回退API。
- `node scripts/verify_designer_ui.mjs --base-url https://research.example.com --design-only --verify-input-provision --session-file <私有目录>/session.json --output <证据路径>`通过；另起进程加`--reopen-study <研究方案ID>`通过。新增气温进入真实模型参数，来源绑定保存、重开、导出及导入均保留。
- 部署后的 API 健康检查通过。
- 发布辅助脚本 `.ops/input-provision-release/deploy.py` Ruff通过、文件头检查1项通过。无Python产品代码改动。
- 线上目录65项，当前UI可添加24项；平台分析未接入指标configure仍422。人工采集及Open-Meteo最低温的configure来源/方法字段在线核验。
- 原生浏览器工具无法初始化；已完成真实DOM与线上HTTP验收，未做像素布局验收。平台分析21项、物联网9项的正式取数接入及其科学尺度适配仍待后续实施，本次不授予可执行资格。

证据见部署记录、添加保存、新页面重开。
