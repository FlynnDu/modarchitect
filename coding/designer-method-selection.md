# 按合同选择计算方法

2026-11-16。用户发现“计算与评价”固定显示多变量线性模型，无法选择已整理的基础模型。

本记录保留首次选择入口批次。后续已接入标准表格随机森林、XGBoost、高斯过程的训练及预测，并启用线性训练；最新范围与真实运行见[基础回归方法接入](tabular-learning-methods.md)。

## 核实

- 引导页的方法横幅只有文本；buildInputModel固定采用multivariate_linear_training@1。模型组件目录与引导入口没有连通。
- 随机森林、XGBoost、高斯过程及LSTM/ConvLSTM当前是原生资料的方法评估组件，操作为analyze，无可复用训练状态；不能直接冒充任意观测表的多目标训练组件。
- 生物所已启用catalog_weather_conditions@1运行，其他目录组件目前为design_only。目录采用、适配当前研究、实际运行分别判断。

## 本次改动

1. 在“计算与评价”增加方法选择/配置入口，按现有组件目录与准确版本显示，不另建模型列表API或并行存储选中值。
2. 候选按实际操作、输入端口及下游连接解释适配条件。训练须有声明的训练状态与推理组件；原生/序列/网格资料不能当普通观测表。
3. 用户在独立草稿中设置候选参数，使用原Schema表单；应用前复用服务端结构检查，成功才修改实际图。失败保留原方案及数据。未启用运行允许设计保存，但明确提示，实际启动仍由既有预检拒绝。
4. 替换保留节点身份及已有科学输入；不静默断开下游。独立配置端口不覆盖其他节点的共享配置；公开成果按新组件声明更新。节点用途从合同推导，评价目标同步实际标签。所有节点支持声明时采用1.5节点用途合同。
5. 已批准原生资料方案不通过换方法解除资料限制。普通模板改为自定义方法时去掉模板展示标记，准确来源绑定和数据性质保持；不授予新的真实来源资格。
6. 建立按钮进入方法选择，不再把“已选版本”表示成运行已启用。既有直接/串联样例及历史合同保持。

本批交付选择入口与已有合同的配置，不新增算法、不把原生评估改成训练。通用随机森林等训练接入需要独立的准确组件、状态/推理合同、制品及正反例验收。

## 验收

真实DOM可打开目录、看到随机森林等方法及具体限制；修改兼容方法进入真实节点和参数，保存/重开保留。无匹配输入、不兼容下游及结构检查失败均保留原配置。前端回归、历史方案及生物所实际HTTP验证。

## 2026-11-16生物所结果

- `npm test`：40/40通过，包含方法替换、失败保留、校验期间修改参数、已有串联/来源/结果展示回归。`node --check scripts/verify_designer_ui.mjs`通过。
- 生物所真实HTTP/DOM：从合成工程样例采用多因素研究，打开方法目录，随机森林显示评估限制；切换历史生长曲线、服务端检查、保存、新进程重开，准确组件与配置摘要一致，HTTP错误0。此项只验证设计保存，没有启动训练或生成模型。
- `node scripts/verify_designer_ui.mjs --base-url http://172.16.1.122:18925 --methods-only --session-file .ops/method-selection/private/session.json --output coding/deployments/modarchitect-biology/method-selection-created.json`；新进程加`--reopen-study 01a1e436-5881-7d8d-ab27-11f40c579c63`重开。
- 原纯第三方研究新页面重查真实历史运行，报告和7点曲线正常。未重复提交调度任务。
- API Job版本8，SR850；部署successful，Consul 1 passing；安装包137个文件逐项摘要一致。只改8个界面文件，科学合同/Python执行代码不变；独立执行Job版本2、海豚Worker版本36不变。API密钥、工作区签名密钥和运行注册表保留，无数据库迁移。
- 私有发布工具rollout.py复用既有Nomad规划/并发更新入口；Ruff通过，Python文件头检查1个文件通过。原生浏览器运行环境未能初始化，没有像素布局验收。

[首次保存](deployments/modarchitect-biology/method-selection-created.json) · [新页面重开](deployments/modarchitect-biology/method-selection-reopened.json) · [气象结果回归](deployments/modarchitect-biology/method-selection-weather-regression.json) · [部署及准确包](deployments/modarchitect-biology/method-selection-deployment.json)。
