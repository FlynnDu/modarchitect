# 统一研究资料、计算与规则响应

2026-11-19。以 v0.2.0 的合同为基线，统一设计器消费的业务事实，保留准确历史定义和既有接口字段。

## 目标与验收

前端不按算法代码决定资料、参数、用途和规则的显示。新增同协议组件时，服务端按准确合同投影，前端使用相同的资料卡、Schema 表单、输出清单和检查结果。配置完整、操作兼容、当次执行检查分别表达，未检查不能视为通过。

## 现状与设计

已有目录提供端口、request_schema 和执行能力；input_usages 解释节点用途；check_definition 检查设计；compile_execution 检查实际运行。复用这些权威入口，不在投影中重新实现科学规则。

- 新增 `contracts/research/inspection.py`：版本化响应及统一问题/检查类型。
- 新增 `inspection.py`：纯只读投影 materials、nodes、outputs、checks。参数保留 Schema，资料保留准确类型、来源与原采样尺度，原生封存输入只返回公开元数据。
- `execution_contracts.py` 提取共用操作兼容校验，投影和执行均调用；无能力声明属于未接入执行，不阻止计划设计。
- 无状态配置检查、设计器检查、模板详情及已保存草稿/版本详情附加 `inspection`，旧字段、摘要及持久化正文保持。新增有类型的 inspection 入口供自定义前端检查任意编辑草稿。
- 执行检查附加相同 checks 类型，旧 can_execute/issues 保持。只有实际执行准备通过才能返回 execution=passed。
- 设计器使用通用投影展示资料、节点用途、参数与规则；编辑继续写入同一份 definition。变更后清除旧事实，异步返回按请求代次和定义摘要核对，迟到结果不得覆盖当前草稿。旧服务未提供投影时保留旧页面兼容。

## 边界与兼容

只读投影不取数、不访问数据库或调度，不赋予已登记来源实际运行资格。配置可保存与操作不兼容分别返回，避免破坏现有计划设计。接口不返回颜色、页面步骤或运行凭据。既有科学成果负载继续保持各自版本化类型，不强行改成同一数值表。来源授权、封存、调度和计算算法不变。

## 验证

通过真实 HTTP 检查训练、分析、无执行声明、待配置、错误草稿和混合操作；核对既有响应和保存读回兼容。DOM 验证同一渲染入口显示不同方法、服务端用途及统一问题、编辑写回、请求乱序和失败清除。运行相关 Python/JS 回归、Ruff、全部本次 Python 文件头检查；数据库回归使用项目已确认的本地隔离验收容器。

## 实现与验收结果

- 发布、版本读回及旧版发布入口均从 `designs._version_view` 生成同一投影，避免只在 GET 增加字段导致发布/读回响应不等。草稿及模板详情只附加只读投影，存储正文和摘要不变。
- `inspection-view.js` 统一展示资料类型、服务端用途、Schema 参数、声明成果及三类检查。资料页采用服务端用途；历史服务未提供 inspection 时保留旧入口。核对失败可重试，切换方案即清除旧控件，连续编辑保留焦点，迟到响应不能覆盖当前定义。实际执行检查遇到编辑变化时要求重新核对。
- 接口文档：[统一响应与字段合同](../docs/research-inspection-api.md)。无新增依赖；JS 验收入口加入 package.json，Python 沿用 pyproject.toml 的 tests 自动发现。
- `npm test`：125/125 通过，新增测试直接读取 Python 实际生成的投影验证跨端合同。
- 首轮通过 `.venv/Scripts/python.exe .ops/verify_local_database.py` 在新隔离库及非特权角色运行 11 个相关测试文件，共 82 场景，81 通过，发现 1 处发布/版本读回响应差异。修复后用 `PYTHONPATH=.`、`MODARCHITECT_PYTEST_ARGS` 指定 api_design_loop、design_api、versioned_studies、research_inspection 四个文件，运行 `.venv/Scripts/python.exe .ops/run_remote_tests.py`，31/31 通过；覆盖了上述失败场景。
- 最终对检查响应空值字段和执行预检重新运行 research_inspection 的数据库读回用例与 platform_rules，10/10 通过。上述相关 Python 场景并集 82 项均已通过；没有用跳过数据库的结果代替联验。迁移检查无新增结构差异。
- 对全部 12 个本次自有 Python 文件执行 Ruff 及 `check_python_headers.py`，全部通过；`git diff --check` 通过。早期直接 pytest 遇到系统临时目录访问失败，后续使用项目隔离验收目录与标准数据库入口完成验证。
- 未部署，未进行浏览器像素布局验收或真实 DolphinScheduler 联验；本次验证覆盖 HTTP、实际隔离数据库、DOM 行为及既有计算回归。
