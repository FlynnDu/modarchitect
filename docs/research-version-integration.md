# 研究方案版本与实例对接

本页适用于 v0.2.0。按[完整 API 流程图](model-designer-api-flow.md)进入。原 01–18 编号继续使用，本页补充 19–24。接口示例使用业务后端到平台的地址，前端经业务后端转接。

## 三个阶段

1. **保存方案**。09 生成配置 → 10 校验 → 11/12 保存 → 14 回读并展示可编辑流程。11/12 的 `version_name` 在请求体外层。创建时可留空。编辑时省略可保留尚未使用的候选名称，显式传 `null` 清空候选名称。名称最多 128 字符，使用单行可打印文本。
2. **保存为可应用版本**。用户确认时用 19 固定当前配置，保存响应的 `design_version_id`。`version_name` 用于显示，同一方案内唯一。自动名称按固定版本顺序分配，从 `1.0.0` 起并跳过已占用名称。由响应决定显示值。配置和候选名称均无变化时，重复确认返回已有版本。发布后的历史名称和配置随该 UUID 保存，后续调整名称通过下一版生效。
3. **应用版本**。从 20 选择版本，发起研究时再选地块、作物种植季、采集点和观察周期。23 创建、24 回查研究实例。一个版本可应用多次。原实例和已训练模型继续引用当时选定的 UUID。

14 的 `revision` 是草稿修订，用于 12 的并发校验和 19 的 `expected_revision`。19–21 的 `revision` 是固定版本序号。业务库可继续按原字段保存草稿回执；另外按版本记录 `design_id`、`design_version_id`，按应用记录 `study_id`、`design_version_id`，日报另保存返回的 `task_id`。`version_name` 可作为展示缓存；固定版本配置和原始训练证据由平台保存。

版本名冲突返回 HTTP 409，名称格式错误返回 422。按响应中的 `issues[].path` 定位版本名，保留编辑状态。草稿修订冲突时用 14 回读后人工处理。19 超时可先用 20 查固定版本；草稿修订仍相同则可重试同一请求。15 用于恢复 11/12 的保存回执。

以下 shell 示例共用服务配置。`KEY` 从业务服务环境变量或密钥配置读取，`SCOPE` 由登录态产生，示例 ID 需替换为本企业实际返回的值。

```sh
API=https://research.example.com
RESEARCH="$API/api/v1/research"
SCOPE='provider_name=your-provider&company_id=123'
```

## 19. 确认并保存为可应用版本

**POST /api/v1/research/design-drafts/{design_id}/publish**

请求体示例 `{"expected_revision":3}`。`3` 取自成功保存的草稿回执或 14 回读的当前修订。

```sh
curl -fsS -X POST "$RESEARCH/design-drafts/$DESIGN_ID/publish?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -H 'Content-Type: application/json' \
  --data '{"expected_revision":3}'
```

HTTP 200 响应关键字段如下，完整结构还包含 `contract_sha256`、`published_at`、`definition` 和 `plan`。

```json
{
  "design_id": "11111111-1111-4111-8111-111111111111",
  "design_version_id": "22222222-2222-4222-8222-222222222222",
  "version_name": "1.0.1",
  "revision": 2
}
```

用 `version_name` 显示确认成功的版本，保存 `design_version_id` 用于回读及应用。19 只固定方案，训练和日报有独立入口。

## 20. 查询某个方案的可应用版本

**GET /api/v1/research/design-drafts/{design_id}/versions**

请求传入路径 `design_id` 和企业范围，无请求体。

```sh
curl -fsS "$RESEARCH/design-drafts/$DESIGN_ID/versions?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
```

HTTP 200 返回 `items`，按固定版本序号倒序。版本下拉展示名称和确认时间，选项值使用 `design_version_id`。`items: []` 表示该方案暂无固定版本。

```json
{
  "items": [{
    "design_version_id": "22222222-2222-4222-8222-222222222222",
    "version_name": "1.0.1",
    "revision": 2,
    "contract_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "published_at": "2026-11-19T03:35:00Z"
  }]
}
```

## 21. 按版本 UUID 读取固定配置和流程

**GET /api/v1/research/design-versions/{version_id}**

请求路径的 `version_id` 使用 19/20/24 或模型详情返回的 `design_version_id`，无请求体。

```sh
curl -fsS "$RESEARCH/design-versions/$VERSION_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
```

HTTP 200 与 19 的结构一致。版本页用 `version_name` 显示名称，读取 `definition.research_plan` 展示该版本的输入和产物，使用 `definition.composition` 的节点与连线构图，节点详情按 06 查准确组件版本。查看已保存草稿仍用 14。

## 22. 导出指定版本的配置文件

**GET /api/v1/research/design-versions/{version_id}/configuration**

请求同 21，无请求体。

```sh
curl -fsS "$RESEARCH/design-versions/$VERSION_ID/configuration?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -o research-plan.json
```

HTTP 200 返回与 09 对应的配置文件。响应的 `format` 为 `research_plan`，`definition` 是完整方案，`sha256` 校验文件。原样下载，可由 18 校验并导入。文件来自固定版本，草稿配置由 14 查询。

## 23. 将可应用版本绑定到一次研究

**POST /api/v1/research/studies**

传入实际选定的 `design_version_id`、`observation_start`、`observation_end`、`fields`，按模型要求传 `point_refs`。`fields` 复用受权选地结果的条件和地块引用；平台复核完整地块、作物种植季、观察期和点位。示例请求文件 `study.json` 如下。

```json
{
  "design_version_id": "22222222-2222-4222-8222-222222222222",
  "observation_start": "2026-04-15",
  "observation_end": "2026-07-15",
  "fields": {
    "selection": {
      "geometry": {"type":"Polygon","coordinates":[[[116,39],[116.01,39],[116.01,39.01],[116,39.01],[116,39]]]},
      "crop_code": "potato",
      "season_start": "2026-04-01",
      "season_end": "2026-08-01"
    },
    "field_refs": ["field-42"]
  },
  "point_refs": ["point-7"]
}
```

```sh
curl -fsS -X POST "$RESEARCH/studies?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -H "Idempotency-Key: $REQUEST_ID" \
  -H 'Content-Type: application/json' --data-binary @study.json
```

HTTP 201 返回本次实例和固定范围。`study_id` 用于后续查看、取数、封存及运行。地块和样点名称由业务系统用相应引用展示。

```json
{
  "study_id": "33333333-3333-4333-8333-333333333333",
  "design_version_id": "22222222-2222-4222-8222-222222222222",
  "observation_start": "2026-04-15",
  "observation_end": "2026-07-15",
  "objects": [{"field_ref":"field-42","crop_code":"potato","season_ref":"season-2026"}],
  "sampling_points": [{"point_ref":"point-7","object":{"field_ref":"field-42","crop_code":"potato","season_ref":"season-2026"}}]
}
```

## 24. 查询实例及其绑定范围

**GET /api/v1/research/studies/{study_id}**

请求传 23 返回的 `study_id` 或日报返回的 `task_id`，无请求体。

```sh
curl -fsS "$RESEARCH/studies/$STUDY_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
```

HTTP 200 与 23 的响应结构一致。用 `objects`、`sampling_points` 和观察日期展示此次研究范围。用响应内的 `design_version_id` 调 21 查看其固定流程，即使方案已有新版，页面仍使用此 UUID。

## 日报和模型追溯

- **持续日报**走 `POST /api/v1/research/report-tasks`，传固定版本 UUID、授权地块及观察日期，沿用日报的 `Idempotency-Key`。它会创建自身的研究实例，`task_id` 同时是 `study_id`，无需先调 23。每天北京时间 02:00 处理前一天，结束日的数据次日处理。各批次与曲线使用日报接口查询。
- **单次研究**创建实例后，使用实例目录完成采集、封存和训练。保存模型后用 17 的 `design_version_id`、`study_id`、`dataset_snapshot_id` 回查原流程、对象和样本。老记录相关字段可能为空。取数、训练和模型保存路径见[业务对接说明](business-api-integration.md#采集封存训练与模型回查)。

上线验收已通过自定义及自动版本名、重名拦截、跨企业隔离、应用绑定和两个版本独立训练，旧版模型成功预测。真实调度联验使用合成资料。真实业务采样点取数及点尺度训练待联验。
