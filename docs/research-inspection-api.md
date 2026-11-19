# 统一研究资料与规则响应

2026-11-19。新增 `inspection` 是只读业务投影，不进入方案正文、配置摘要或已冻结版本。前端按资料类型、参数 Schema、操作与规则结果渲染，无需按算法名称分支。

## 读取入口

| 入口 | 返回位置 |
| --- | --- |
| `POST /api/v1/research/definitions/inspect` | 直接返回投影；正文是当前 `definition`，使用现有服务 Key |
| `POST /api/v1/research/configurations/check` | 保留 `valid/compiled/issues`，附加 `inspection` |
| `POST /api/v1/research/design-drafts/{id}/check` | 同一检查响应 |
| `GET /api/v1/research/study-templates/{id}` | 详情附加 `inspection` |
| `GET /api/v1/research/design-drafts/{id}` | 详情附加 `inspection`，沿用企业授权 |
| `GET /api/v1/research/design-versions/{id}` | 详情附加 `inspection`；仅含旧组合而无完整研究方案的历史版本返回 null |
| 工作区模板详情、方案详情 | 同样附加 `inspection`，沿用工作区授权 |
| `POST /designer/validate`、`/designer/import` | 保留 `configuration/check`，附加同级 `inspection` |

直接检查接口的响应类型公开在 OpenAPI 的 `ResearchInspection`。错误草稿仍返回该形状；配置无法解析时资料和节点为空，问题位于 `checks.configuration.issues`，不能保留上一份草稿的通过状态。

## 固定结构

| 字段 | 含义及消费方式 |
| --- | --- |
| `schema_version` | 当前为 `1.0`，指投影协议版本，与方案版本分开 |
| `operation` | 当前方案要求的 train/predict/analyze/simulate/calibrate；无法解析时为 null |
| `materials[]` | 非参数外部资料的 code/name/kind/data_type/variable_codes；保留原始资料类型和采样尺度 |
| `materials[].sources[]` | 来源、取数属性、观测单位和通道状态；`data_available=null` 表示未核验本次数据 |
| `materials[].indicators[]` | 指定原生资料的公开字段、单位、用途与来源；没有原始数值、凭据或受限原文 |
| `nodes[]` | 准确组件身份、支持操作、输入绑定、请求配方身份、参数 Schema/当前值/运行上下文字段、节点用途及声明输出 |
| `nodes[].input_usages[]` | 复用权威用途推导；role/phases 表示指标在准确节点的用途，不修改变量自身单位或来源 |
| `outputs[]` | 方案选择的公开成果引用及准确端口定义，区别于组件全部声明输出 |
| `checks` | 分别表达配置完整、操作兼容与本次实际执行条件 |

前端依据 `parameter_schema` 生成表单，将编辑结果写回 `input_recipes[request_input].value`。`runtime_fields` 中的字段由可信运行上下文提供，不能作为静态用户参数覆盖。原生制品参数值未公开时 `parameters=null`，不得补造数值。

## 相同的检查类型

```json
{
  "configuration": {"status": "passed", "issues": []},
  "operation": {
    "status": "blocked",
    "issues": [{
      "code": "operation_incompatible",
      "path": ["composition", "nodes", 1],
      "node": "summary",
      "port": null,
      "message": "Component does not support research operation train: research_descriptive_statistics@1"
    }]
  },
  "execution": {"status": "not_checked", "issues": []}
}
```

- `passed`：对应检查已完成并通过。
- `blocked`：当前条件明确不满足，按 issues 显示问题和位置。
- `unsupported`：准确组件尚无执行能力声明，可保留计划设计，不能显示已可执行。
- `not_checked`：尚未检查，不能视为通过或运行成功。

`code/path/node/port/message` 在规范化检查中保持一致。旧的 `issues[].type` 和 `issues[].rule` 保留，旧客户端不必立即迁移。未知 code 也应显示 message 并保留定位；前端可按稳定 code 做中文展示。

实际 `POST /api/v1/workspace/check-execution` 响应保留 `can_execute/issues`，另返回同型 `checks`；其 execution 才代表本次输入和执行准备的结果，其他未单独检查的项目保持 not_checked。改变方案、数据或来源后清除旧结果。组件目录的 `execution.status=available` 只表示登记制品，不替代方案检查。

## 兼容

允许计划来源、未启用制品及组合继续设计保存；操作不兼容独立返回，不改变历史 valid 的含义。运行沿用原授权、来源核验、输入封存和同一操作校验。新增同协议方法不增加前端算法分支；新增资料/成果类型时扩展对应类型的通用控件。不同科学成果仍保留各自的版本化负载，统一响应保留表格、时序、网格与模型制品的差异。

前端修改后重新请求投影，通过代次和当前定义校验拒绝迟到响应；请求失败清除旧资料说明并显示提示。接口不执行取数、数据库写入或调度。
