# 前端API使用说明

覆盖浏览、设计、检查、保存、流程回读，以及可应用版本和研究实例。响应字段的界面用法与[业务系统 API 文档](business-api-integration.md)对应。

[查看完整闭环流程图（按 API 编号）](model-designer-api-flow.md)

## v0.2.0 前端改动

| 改哪里 | 界面与响应字段 | API |
| --- | --- | --- |
| 基础信息 | 增加可选的「方案版本名称」，允许留空。用 `version_name` 回填候选值，用 `latest_version.version_name` 展示最近确认版本。「来源模板」单独只读展示，自定义显示「自定义」。 | 11、12、14 |
| 检查与确认 | 用户保存方案后从 14 回读流程。用户确认「保存为可应用版本」后使用 19 返回的名称展示成功。409 重名或 422 格式错误按 `issues[].path` 定位，保留编辑状态。 | 09–12、14、19 |
| 历史版本与应用 | 20 的 `items` 用于版本选择，显示 `version_name`，以 `design_version_id` 作为选中值。应用时填写地块、种植季、点位和观察期，按 24 返回的对象与日期展示实例。 | 20–24 |
| 历史实例与模型 | 用实例或模型返回的 `design_version_id` 回读原版流程，按 `study_id` 展示原对象与周期。历史模型缺少实例引用时仍可展示原模型资料。 | 17、21、24 |
| 模板选择 | 初次进入直接显示已配置的输入、目标和成果。「查看本方案输入示例」只打开当前方案的预览；关闭后仍保留当前编辑配置与流程。 | 02、06、14 |

[19–24 请求、curl、响应及渲染字段](research-version-integration.md)

## 2026-11-18 前端配置流程修改

本节对应 2026-11-18 设计器版本。内置浏览器已验收从自定义方案到保存回读。已接好的 API 编号、路径、转接及保存回读顺序可以继续使用。

| 编号 | 改哪里 | 接口 |
| --- | --- | --- |
| F1 | 基础信息显示名称、负责人、研究目标、方案版本名称和模板来源。负责人写入可缺省的业务用户 ID 字符串。 | 02、09—12、14 |
| F2 | 指标配置分两页，共用目录。已选指标按 `variable.code` 跨页禁选。只读展示指标详情、来源和提供方式，已登记的待接入项仍可采用。 | 02—04、06 |
| F3 | 采用日尺度方法时按准确组件合同接入观测日期。用户无需在指标库补选天数。 | 05—08 |
| F4 | 「检查与确认」预览当前草稿，完整检查失败时定位到字段或节点，通过后再由用户正式保存。 | 09—12 |
| F5 | 移除保存前的采样计划确认及模型初始化。地块、样点和采样排程留给应用方案。 | 11/12 |
| F6 | 保存成功后回读数据库配置，核对修订，再按实际输入、计算、成果和依赖生成动态流程。 | 14、06 |

[本期对接修改清单及联调用例](model-designer-integration-changes-20261118.md)

## 调用与身份

浏览器只请求业务后端。业务后端为调用注入服务 Key，并为企业私有读写从登录态注入企业范围。平台默认方案的 01 和 02 只需服务 Key。下文 BFF 地址和用户登录头由业务项目实现。

| 项目 | 约定 |
| --- | --- |
| 本系统安全方案 | `ModarchitectApiKey`（`apiKey`） |
| 转发请求头 | `X-Modarchitect-Api-Key`，原值不加Bearer前缀 |
| 业务后端环境变量 | `MODARCHITECT_API_KEY` |
| 服务 Key | 业务后端从私有运行配置加载，与平台配置的服务 Key 相同。 |
| 企业范围 | 企业私有接口由业务后端从登录态注入 `provider_name/company_id` |
| 浏览器凭据 | 业务系统自己的登录凭据，本系统Key不下发浏览器 |

```sh
BFF=https://business.example.com/model-api
AUTH="Authorization: Bearer $USER_TOKEN"
```

下文curl访问BFF，前端正文不带企业字段。转接除注入身份范围外应保持请求/响应结构。业务后端负责持久化并管理保存请求ID，将`Idempotency-Key`转发给本系统；浏览器示例同名头只说明该次请求身份。

**“字段节选”用于解释，不能直接提交给校验/保存。** 完整定义和配置见[示例JSON](examples/model-designer.json)。

## 开始配置时的四项基本信息

自带独立设计器与业务系统登录不同：默认个人工作区通过浏览器签名Cookie识别，切换浏览器或无痕窗口会进入另一个空间，数据库记录不会丢失。18937本地单人验收已配置稳定工作区，新浏览器可重新读取同一批方案；该配置只允许回环入口，不作为正式企业登录方案。业务前端继续经业务后端访问本文API，不依赖自带页面的Cookie，也不把方案ID当访问凭据。

基本信息区按以下字段配置。

| 页面项 | 数据来源与使用 |
| --- | --- |
| 研究方案名称 | 用户填写，保存为`definition.name`。 |
| 负责人 | 业务系统提供用户ID，写入`definition.responsible_user_id`，本系统随方案保存并回读；成员列表与姓名由业务系统提供。 |
| 研究目标 | 用户填写，保存为`definition.question`；具体目标指标在后续指标配置中选择。 |
| 方案版本名称 | 14 的 `version_name` 是当前草稿候选名称。用 `latest_version.version_name` 展示最近固定的版本。用户可在新建或编辑时填写候选名称，放在 11/12 请求体外层。 |
| 模板来源 | 采用模板时按接口02的`id/revision/sha256`展示名称与版本，保留原有`definition.layout.study_template`中的`id/sha256`。重开时按原引用解析并只读显示。自定义方案显示“自定义”。 |

实际地块、样方点、作物、周期在发起具体研究时填写，指标来源尺度、模型操作和成果仍按后续配置校验。正式提交按09→10→11/12完成配置生成、检查与保存。

负责人只传业务用户ID字符串：`"responsible_user_id": "9007199254740993"`，放在完整`definition`中。长度1—128，不含空白；不传姓名或成员对象，不把数字ID转为JavaScript的Number。历史方案允许缺省，清空时删除此键。接口14通过`configuration.definition.responsible_user_id`回读，前端用业务系统成员信息显示姓名；这个ID不作为本系统登录或授权凭据。

## 确认可应用版本并启动研究

11/12 保存及 14 回查处理草稿编辑。用户点击「保存为可应用版本」时，业务后端用保存回执的 `revision` 调用 19，并使用响应的 `version_name` 显示名称。确认后用 `design_version_id` 选择版本。用户清空候选名称时发送 `version_name: null`。

创建研究实例时再收集地块、作物种植季、采集点和观察周期。`POST /studies` 的 `study_id` 用于该实例后续的采集、数据集和运行。展示已保存模型时可从 `study_id` 查看原对象和周期，从 `design_version_id` 查看原方案，从 `dataset_snapshot_id` 查看样本。历史数据缺少实例归属时显示「历史记录」，保留原运行版本。业务转接接口见 [固定版本与研究实例](business-api-integration.md#确认可应用版本并运行研究实例)。

## 分两步选择研究资料和目标指标

因素与指标不建立两套目录。页面按研究信息流分成两个独立步骤：“研究资料与候选因素”选择可提供的土壤、气象、遥感与作物观测资料；“目标指标与预期成果”选择关注的生长指标，基础模型确定后确认真实成果。两步统一采用系统定义；同一指标不能因用作因素或目标而复制定义，训练与应用用途以具体模型节点合同为准。

02与03添加互斥：按`items[].variable.code`关联已选变量，已选指标在两页均标明原用途并禁用添加，不只按entry.key去重。点击时先检查当前方案，调用04后写入配置前再防重复；需要改变用途时显式调整原选择，不能同时保留在两边。API10及11/12另检查同一模型的同一数据列不能既是训练输入又是目标，返回`input_target_overlap`并定位节点及参数字段。不同节点的合法用途、上游派生结果作为下游输入继续按准确端口合同解释，不作整个图的同名变量一刀切禁止。

处理、分组用途需要时再展开水平、对照或受管字典配置；普通预测或分析不强制配置分组。当前目录尚未完整登记截图中的灌溉处理、品种分组等定义，不能把界面合并理解为这些能力已实现，也不能用页面自由新增变量代替系统登记。

界面对研究者使用“模型输入”“预测输出”，以两个独立步骤及各自添加动作代替X/Y下拉。预测输出对应要预测的指标，训练与验证时仍需其实测记录；分析、模拟按准确基础模型展示实际成果。接口04继续传递已有`role`：模型输入为`covariate`（驱动仍按合同），实测预测输出为`target`；模型参数继续采用已有`features/targets`或准确Schema字段，不能仅改显示而不更新节点绑定。预测输出指标与`composition.outputs`中的模型文件、结果表等成果端口分别解释，不新增同名配置副本。

系统指标的名称、编码、类型、单位、来源尺度保持只读，编辑入口只展示合同允许配置的内容。截图中的处理水平CK/T1/T2、对照标记、实际处理量、分配和缺失策略尚无完整系统合同，不能直接增加表单字段后提交，或将其藏入layout冒充已校验设置。对照组不是验证集；处理与对照仅在已登记完整合同的相应研究中按需配置，不作为普通预测的必填步骤。

系统指标只提供「查看指标详情」。研究人员可调整在本方案中的采用、用途与来源合同允许选择的属性。1.5 配置按目录核验固定定义和科学值域，`minimum/maximum` 等字段保持 04 返回值。历史配置保留其原有合同。

只读详情复用接口03已返回的准确条目，无需增加详情查询接口：variable展示名称、编码、description、definition_version、value_type、unit、minimum/maximum；unit_kind展示观测尺度；source.name、binding.value_nature和method.instructions展示来源、数值性质与方法；execution展示接入状态和缺口。已有卡片只显示部分摘要，业务前端需据这些字段提供详情页或弹窗，不创建新的定义副本。

本期通用建模界面移除“处理水平与对照”，不为它新增通用表单或接口。它只对明确的处理效应试验有意义，不是指标采用、模型编排、训练和预测的前置条件。历史处理/分组合同保持解释能力，未来若纳入该业务，再以专门组件及完整科学合同接入。

## 方法需要日期驱动时如何配置

日期模型所需时间坐标由平台生成，不在03指标库中伪造“天数”指标，也不要求人工采集。自带设计器会自动连接`research_calendar_axis@1`；外部前端按06返回的准确组件合同生成同样的图，09只封装已编辑定义，不自动补图。

| 06返回字段 | 前端使用 |
| --- | --- |
| `definition.configuration.research_model.automatic_date_axis` | 识别平台自动日期变换，不作为用户手选的基础计算方法展示。 |
| 该声明的`input_port/output_port/output_field/variable` | 连接原始观测资料→日期变换→所选模型；按声明建立图内变量与输出参数，不新增外部采集要求。 |
| 准确请求Schema的`origin_date.const` | 原值写入日期变换参数，只读保留；不要按当前批次首日改写。 |
| 所选模型参数的`x-research-variables.roles=["driver"]`且`unit="day"` | 缺少合法驱动时采用日期变换输出；旧逻辑斯蒂准确合同由`axis_kind=elapsed_days`表示day轴。 |

页面只读显示“平台观测日期（自动使用）”；02显示“平台日期驱动”，不显示“未绑定来源”。外部指标仍由04采用，参数及连线经10、11/12复验。日期变量不能用作实测目标或上传外部数值。训练需要目标实测；纯时间模型预测可用`columns: []`、每行`values: {}`，对象与`business_date`仍必填。需要其他因素的方法按实际合同提交，不能统一清空预测列。

默认坐标来自实际观测日期，不表示播种后天数、定植后天数或积温。人工观测可间隔采集，卫星按有效场景日期，静态土壤参考也不等于每天重新实测；平台不为缺测日补造数据。日历规则随方案和模型保留，训练与预测使用同一时间语义。

## 每一步如何校验：当前能力

“下一步”不等于已请求服务端验证。自带设计器的普通下一步使用页面轻量检查；采用指标、应用计算方法及完整检查才调用相应服务。业务前端按下表接入，不依赖页面专用的`/designer/validate`。

| 环节 | 当前校验入口 | 能确认什么 |
| --- | --- | --- |
| 基本信息下一步 | 页面必填、长度与输入格式 | 本区表单完整性；不是一次完整API检查。 |
| 添加指标及来源属性 | 04 | 准确目录身份、来源属性与用途是否合法；不是整份图的校验。 |
| 配置基础模型与连接 | 06的request_schema生成表单，08辅助筛选端口 | 06/08属于读取合同与兼容候选，不代表参数、图和研究用途已整体通过。 |
| 已有完整草稿时检查 | 09生成当前配置后调用10 | 完整设计合同、参数、引用和连接，按issues.path定位错误。 |
| 正式保存 | 11/12服务端重新检查 | 不信任前端的“通过”标记；错误不作为正式方案保存。 |

「检查与确认」页使用当前编辑定义预览实际流程，检查失败按问题路径定位到配置区。点击「检查方案」只检查。点击「保存研究方案」时检查当前定义，通过后提交正式保存。保存后用 14 返回的 `configuration.definition` 还原已保存流程。地块、采样点、采样频率、执行时间及采样人员在发起研究时确定。

09只生成草稿文件及摘要，允许尚未完成，不能当成业务校验通过。10目前只支持整份设计，没有当前分区/scope/step参数。可在每次修改后调用10，但自定义方案尚未填写后续内容时，也会收到后续缺失错误，不能据此阻止当前正常配置；从完整模板开始时，10检查的仍是整份当前定义及模板默认值。前端可按path展示定位，不能忽略其他错误后宣称整份已通过。

如果业务要求“每一步都由API判定本步通过”，当前还不完整，需要在共用校验服务中增加领域范围的分段检查，区分未到步骤的待配置与真正非法配置，不机械新增每个UI步骤的独立接口。该能力尚未实现，不向现有10添加未声明参数。正式保存仍必须完整复验；设计通过也不表示来源、数据和执行制品已满足启动条件。

## 接口索引

| 编号 | 用途 | 方法 |
| --- | --- | --- |
| 01 | 查询公共研究方案列表 | GET |
| 02 | 查询公共方案详情并进入设计器 | GET |
| 03 | 查询系统指标库及两级分类 | GET |
| 04 | 采用指标并生成准确来源配置 | POST |
| 05 | 查询可采用的基础计算模型列表 | GET |
| 06 | 查询基础模型准确版本、端口和参数表单 | GET |
| 07 | 查询基础模型历史版本 | GET |
| 08 | 查询输出可连接的下游模型输入 | GET |
| 09 | 将编辑方案生成配置文件 | POST |
| 10 | 检查当前配置并定位错误 | POST |
| 11 | 正式保存一个新研究方案 | POST |
| 12 | 修改已保存研究方案 | POST |
| 13 | 查询企业已保存方案列表 | GET |
| 14 | 查询已保存方案并还原流程图 | GET |
| 15 | 按保存请求ID查询成功回执 | GET |
| 16 | 查询本企业已训练并保存的模型 | GET |
| 17 | 查询训练模型准确详情 | GET |
| 18 | 校验并导入配置文件 | POST |

## 01. 查询公共研究方案列表

**GET /api/v1/research/study-templates**

用途：展示可直接采用的公共方案卡片；这里返回模板，不是企业已保存方案。

请求：

无接口特定参数。

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/research/study-templates" \
  -H "$AUTH"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "items": [
    {
      "id": "crop-growth-prediction",
      "revision": 1,
      "title": "多因素作物生长指标预测",
      "summary": "研究冠层覆盖度、块茎干物质与叶面积指数、地上生物量的关系，并预测多个生长指标。",
      "operation": "train",
      "data_kind": "synthetic",
      "output_description": "可保存并继续预测的候选模型与验证结果",
      "limitations": [
        "示例数据用于说明研究流程，实际结论需用本研究对象的数据验证。"
      ],
      "input_policy": {
        "mode": "user_observations",
        "editable": [
          "records",
          "inputs",
          "factors",
          "targets"
        ]
      }
    }
  ]
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| items[].id | 模板标识 | 点击后作为接口02的template_id；不能当作design_id。 |
| items[].title / summary | 方案名称、研究问题 | 显示卡片标题和摘要。 |
| items[].revision / sha256 | 模板修订、准确摘要 | 保存模板来源；不当作设计修订或设计ID。 |
| items[].researcher.category / needed | 研究分类、所需资料 | 分类筛选和输入要求。 |
| items[].output_description / limitations | 预期成果、适用限制 | 显示成果说明和限制。 |
| items[].operation | 研究操作 | train训练、analyze分析、simulate模拟、calibrate标定、predict预测。按返回值显示。 |
| items[].data_kind | 示例资料性质 | synthetic显示合成示例，不能当作田间真实记录。 |
| items[].input_policy | 原模板的运行用数规则 | 说明原模板资料限制；不能据此禁用指标或基础模型的设计选择。 |

响应只有items，没有分页和total。空列表按items.length判断。

## 02. 查询公共方案详情并进入设计器

**GET /api/v1/research/study-templates/{template_id}**

用途：取得选中方案的完整定义，初始化研究设计页面。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| template_id（路径） | 必填string，接口01的id；示例crop-growth-prediction。 |
| sha256（查询） | 可选string，读取指定模板摘要；省略时读取当前采用版本。 |

请求体：无。

curl：

```sh
TEMPLATE_ID=crop-growth-prediction
curl -fsS "$BFF/api/v1/research/study-templates/$TEMPLATE_ID" \
  -H "$AUTH" -o template.json
```

响应：HTTP200（字段节选）。

```json
{
  "id": "crop-growth-prediction",
  "revision": 1,
  "title": "多因素作物生长指标预测",
  "sha256": "debcc0cb601db59523ace691d440aebfba5bfd18428a389873202e1550dbb76f",
  "input_policy": {
    "mode": "user_observations",
    "editable": [
      "records",
      "inputs",
      "factors",
      "targets"
    ]
  },
  "definition": {
    "schema_version": "1.4",
    "name": "多因素作物生长指标预测",
    "question": "研究冠层覆盖度、块茎干物质与叶面积指数、地上生物量的关系，并预测多个生长指标。",
    "objective": "prediction",
    "purpose": "train",
    "composition": {
      "schema_version": "1.0",
      "object_scope": "field_crop_season",
      "inputs": [
        {
          "code": "observations",
          "name": "系统标准人工记录",
          "role": "context",
          "data_type": {
            "semantic": "research_observation_table",
            "version": 1,
            "shape": "table",
            "unit": "column_definitions",
            "alignment": "business_date"
          }
        },
        {
          "code": "regression_config",
          "name": "多变量线性回归配置",
          "role": "parameter",
          "data_type": {
            "semantic": "multivariate_regression_request",
            "version": 1,
            "shape": "bundle",
            "unit": "native_contract",
            "alignment": "context"
          }
        }
      ],
      "nodes": [
        {
          "code": "regression",
          "component": {
            "code": "multivariate_linear_training",
            "revision": 1
          },
          "bindings": [
            {
              "port": "observations",
              "source": {
                "node": null,
                "port": "observations"
              }
            },
            {
              "port": "request",
              "source": {
                "node": null,
                "port": "regression_config"
              }
            }
          ],
          "selections": {}
        }
      ],
      "outputs": [
        {
          "code": "trained_model",
          "source": {
            "node": "regression",
            "port": "trained_model"
          }
        },
        {
          "code": "predictions",
          "source": {
            "node": "regression",
            "port": "predictions"
          }
        }
      ]
    },
    "input_recipes": {
      "observations": {
        "kind": "observations",
        "variable_codes": [
          "lai",
          "agb_kg_ha",
          "canopy_cover",
          "tuber_dm_kg_ha"
        ]
      },
      "regression_config": {
        "kind": "configuration",
        "value": {
          "features": [
            "canopy_cover",
            "tuber_dm_kg_ha"
          ],
          "targets": [
            "lai",
            "agb_kg_ha"
          ],
          "training_end": "2026-05-10"
        },
        "runtime_fields": {}
      }
    }
  }
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| definition.name / question | 研究名称、问题 | 填入基本信息；编辑definition，不是只改外层title。 |
| definition.objective / purpose | 研究目标、研究操作 | 恢复关联/预测/机理等目标和训练/探索/模拟等操作。 |
| definition.variables | 已采用指标 | 按code关联，显示name、unit；保留完整科学定义和版本。 |
| definition.collection_requirements | 指标来源与采集规则 | 按variable_code关联指标；展示来源、方法、采样尺度和取数属性。 |
| definition.composition / input_recipes | 节点连线、资料与参数 | 恢复流程图和参数面板，见本文末尾字段规则。 |
| input_requirements[].port / name / unit / kind / use / source | 指定资料的字段说明 | 按 `port` 匹配 `definition.composition.inputs[].code`，在对应资料卡列出指标或参数。`kind=target` 可同步展示在目标区。这个数组只在指定资料的详情返回。 |
| definition.composition.outputs[] | 方案公开的计算成果 | 沿 `source.node` 找节点和准确组件版本，用 `source.port` 匹配接口 06 的输出名称、说明。评价目标为空时照常显示模拟、分析和拟合成果。 |
| definition.evaluation / layout | 评价设置、界面信息 | 恢复评价条件并保留layout；node_labels可用作节点标题。 |
| observations / prediction_observations | 模板可提供的示例记录，可能为null | 独立于definition；本次设计保存不把示例记录塞入definition。 |

提取完整编辑定义：

```sh
jq '.definition' template.json > definition.json
```
自定义入口使用[空白定义](../coding/api-design-loop-fixtures/blank.json)，不请求不存在的空白模板API；填写后仍调用接口10检查。

## 03. 查询系统指标库及两级分类

**GET /api/v1/model-center/research-inputs**

用途：填充指标选择弹窗，包括分类、名称、单位、具体来源和设计采用状态。

请求：

无接口特定参数。

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/model-center/research-inputs" \
  -H "$AUTH"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "version": "1.1.0",
  "categories": [
    {
      "code": "manual",
      "name": "人工采集",
      "count": 15,
      "children": [
        {
          "code": "manual_morphology",
          "name": "植株形态",
          "count": 6
        },
        {
          "code": "manual_leaf_cover",
          "name": "叶面积与冠层覆盖",
          "count": 3
        },
        {
          "code": "manual_biomass_yield",
          "name": "生物量与产量",
          "count": 6
        }
      ]
    },
    {
      "code": "third_party",
      "name": "第三方数据",
      "count": 20,
      "children": [
        {
          "code": "third_party_weather",
          "name": "气象数据",
          "count": 7
        },
        {
          "code": "third_party_soil",
          "name": "土壤数据",
          "count": 11
        },
        {
          "code": "third_party_satellite",
          "name": "卫星观测",
          "count": 2
        }
      ]
    },
    {
      "code": "platform_analysis",
      "name": "平台分析成果",
      "count": 21,
      "children": [
        {
          "code": "analysis_growth",
          "name": "长势分析",
          "count": 21
        },
        {
          "code": "analysis_3d_phenotype",
          "name": "三维表型",
          "count": 0
        }
      ]
    },
    {
      "code": "iot_platform",
      "name": "物联网监测",
      "count": 9,
      "children": [
        {
          "code": "iot_greenhouse",
          "name": "棚内环境监测",
          "count": 5
        },
        {
          "code": "iot_root_water",
          "name": "根区水分监测",
          "count": 1
        },
        {
          "code": "iot_water_weighing",
          "name": "水肥与称重监测",
          "count": 3
        }
      ]
    }
  ],
  "items": [
    {
      "key": "variable_source:temperature_mean_daily@1.0.0",
      "variable": {
        "code": "temperature_mean_daily",
        "definition_version": "1.0.0",
        "name": "日平均气温",
        "description": "研究变量：日平均气温。变量定义独立于提供方；跨来源比较须核对日界、空间支撑及测量方法。",
        "value_type": "number",
        "unit": "celsius",
        "role": "covariate",
        "minimum": null,
        "maximum": null
      },
      "category": "third_party",
      "subcategory": "third_party_weather",
      "unit_kind": "field_season",
      "selectable": true,
      "source": {
        "code": "openmeteo_weather",
        "name": "Open-Meteo 天气",
        "selection_schema": {
          "type": "object",
          "properties": {},
          "required": [],
          "additionalProperties": false
        }
      },
      "execution": {
        "available": true,
        "reason": null,
        "channel": "source_snapshot"
      },
      "data_available": null
    }
  ],
  "total": 65
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| categories[].code / name / count | 一级分类代码、名称、数量 | 生成一级分类按钮，如第三方数据。 |
| categories[].children[].code / name / count | 二级分类 | 生成气象、土壤、卫星等子分类。 |
| items[].category / subcategory | 指标所属分类 | 按code与两级分类匹配，前端筛选。 |
| items[].key | 准确选择标识 | 添加时传给接口04，不能只传variable.code。 |
| items[].variable.name / description / unit | 名称、解释、科学单位 | 显示指标卡片和单位；celsius可显示℃，提交仍保持原值。 |
| items[].unit_kind | 指标代表的采样尺度 | field_season地块种植季、point点位、plant单株、quadrat样方、soil_layer土层、report_area报告范围。 |
| items[].source.name | 具体来源名称 | 显示Open-Meteo气象等提供方，不能只显示第三方。 |
| items[].source.selection_schema | 来源采用属性Schema | 根据properties/required/enum生成土层、统计方式等选择框。 |
| items[].source.binding.value_nature | 数值性质 | observed实测、estimated估计等；估计来源不能作为实测标签。 |
| items[].selectable | 设计采用资格 | 控制加入按钮，当前65项全部开放设计。 |
| items[].execution.available / reason / channel | 接入状态、原因、取数渠道 | 显示已接通或待接入；false不能禁用设计。source_snapshot为平台采集后引用快照，workspace_manual_entry为标准人工记录。 |
| items[].data_available | 本次数据是否已有 | null表示尚未核实，不能显示已有数据。 |
| total / version / sha256 | 目录总数、版本、摘要 | 显示总数，保留版本信息，不硬编码数量。 |

当前无分页、搜索或分类查询参数；前端按返回内容筛选和搜索。未接通来源可参与设计，不代表已有取数通道或当次数据。

## 04. 采用指标并生成准确来源配置

**POST /api/v1/model-center/research-inputs/configure**

用途：将选择的指标、角色和来源属性转换为可保存定义；本接口不实际获取数据。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| key | 必填string，接口03的准确key。 |
| role | 可选string，默认covariate；枚举treatment/group/covariate/driver/target/validation/parameter；常用target实测目标、covariate已知因素、driver驱动。 |
| selectors | 可选object，默认{}；必须满足selection_schema，不能猜土层或统计方式。 |
| required_for | 可选操作数组，至少一项，默认["train"]；枚举explore/simulate/fit/train/predict/evaluate，表示在哪些研究操作中需要，不表示数据已存在。 |

请求体：

```json
{
  "key": "variable_source:temperature_mean_daily@1.0.0",
  "role": "covariate",
  "selectors": {}
}
```

curl：

```sh
curl -fsS -X POST "$BFF/api/v1/model-center/research-inputs/configure" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"key":"variable_source:temperature_mean_daily@1.0.0","role":"covariate","selectors":{}}' -o input.json
```

响应：HTTP200（字段节选）。

```json
{
  "variable": {
    "code": "temperature_mean_daily",
    "name": "日平均气温",
    "definition_version": "1.0.0",
    "description": "研究变量：日平均气温。变量定义独立于提供方；跨来源比较须核对日界、空间支撑及测量方法。",
    "value_type": "number",
    "unit": "celsius",
    "role": "covariate",
    "minimum": null,
    "maximum": null,
    "categories": []
  },
  "requirement": {
    "code": "temperature_mean_daily",
    "variable_code": "temperature_mean_daily",
    "source": "third_party",
    "unit_kind": "field_season",
    "required_for": [
      "train"
    ],
    "catalog_binding": {
      "kind": "variable_source",
      "code": "openmeteo_weather_temperature_mean_daily",
      "definition_version": "1.0.0",
      "contract_sha256": "27b6e8044804d85c4a5ef2ba3dbeb47e567a9e28bc027414e7ef033ac9bed7a1",
      "value_nature": "estimated",
      "source_system": "openmeteo_weather",
      "selectors": {}
    },
    "method": {
      "protocol_code": "openmeteo_daily_records",
      "protocol_version": "1.0.0",
      "method_code": "openmeteo_daily_standard_record",
      "instructions": "由平台Open-Meteo数据链提供，保留Asia/Shanghai业务日、实际到达时刻及逐变量质量与来源证据；不生成人工采集任务。",
      "evidence_required": true
    }
  },
  "entry": {
    "key": "variable_source:temperature_mean_daily@1.0.0",
    "category": "third_party",
    "subcategory": "third_party_weather",
    "source": {
      "name": "Open-Meteo 天气"
    },
    "execution": {
      "available": true,
      "reason": null,
      "channel": "source_snapshot"
    }
  }
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| variable | 权威变量定义 | 按code加入/替换definition.variables；name、unit、definition_version不任意重写。 |
| requirement | 准确来源及采集要求 | 加入/替换definition.collection_requirements，按variable_code关联。 |
| requirement.catalog_binding | 来源身份、版本、摘要和属性 | 完整保留；kind=planned_source显示待接入。 |
| requirement.catalog_binding.selectors | 本次采用的来源属性 | 显示土层、统计方式；改变属性须重新调用本接口。 |
| requirement.method.instructions | 资料如何提供 | 显示取数/人工采集说明。 |
| entry.category / subcategory / source.name | 分类与具体提供方 | 匹配目录分类名称后显示完整来源，不只显示第三方/平台。 |
| entry.execution | 取数实现状态 | 显示接入说明，不能误当作设计采用资格。 |

土壤容重请求示例：

```json
{
  "key": "variable_source:soil_bdod@1.0.0",
  "role": "covariate",
  "selectors": {
    "depth": "0-5cm",
    "statistic": "mean"
  }
}
```
target或validation要求observed来源，不能把第三方估计值当实测目标。采用指标后还须同步观测配方variable_codes和模型参数，接口不会自动改图。

## 05. 查询可采用的基础计算模型列表

**GET /api/v1/model-center/components**

用途：填充基础模型/计算方法选择器；它与已经训练完成的模型列表是两个接口。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| page（查询） | 可选integer≥1，默认1。 |
| page_size（查询） | 可选integer，1—100，默认20。 |

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/model-center/components?page=1&page_size=100" \
  -H "$AUTH"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "items": [
    {
      "definition": {
        "code": "multivariate_linear_training",
        "revision": 1,
        "name": "多变量线性模型训练",
        "summary": "用多个已知因子预测一个或多个数值目标。",
        "category": "training",
        "composable": true
      },
      "available_for_new_design": true,
      "research_contract": {
        "execution": {
          "status": "available",
          "profile": "offline_cpu"
        }
      }
    }
  ],
  "total": 28,
  "page": 1,
  "page_size": 100
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| items[].definition.code / revision | 准确组件身份 | 采用后写入composition.nodes[].component，不只保存显示名称。 |
| items[].definition.name / summary | 模型名称、用途 | 显示模型卡片标题和说明。 |
| items[].definition.category | 计算组件分类 | 用于模型筛选，与指标来源分类分别管理。 |
| items[].available_for_new_design / definition.composable | 新设计采用资格、是否可组合 | 符合时允许新增组合节点。 |
| items[].research_contract.execution.status | 实际执行状态 | available/design_only/unavailable用于说明，不禁用设计选择。 |
| items[].research_contract.request_schema | 参数表单Schema | 按接口06解释；null不表示禁止设计。 |
| total / page / page_size | 分页信息 | 控制总数和翻页，本批28项不能硬编码在前端。 |

支持选择并配置或明确保留待配置步骤；未实现取数、制品或操作适配不作为本次设计禁用理由。最终组合仍须通过接口10。

## 06. 查询基础模型准确版本、端口和参数表单

**GET /api/v1/model-center/components/{code}**

用途：选择方法或重开节点时，读取准确版本的输入输出和参数合同。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| code（路径） | 必填string，基础模型代码，不是节点code。 |
| revision（查询） | 可选integer≥1；重开必须传保存的准确revision，不静默换成最新版本。 |

请求体：无。

curl：

```sh
COMPONENT_CODE=multivariate_linear_training
curl -fsS "$BFF/api/v1/model-center/components/$COMPONENT_CODE?revision=1" \
  -H "$AUTH"
```

响应：HTTP200（字段节选）。

```json
{
  "definition": {
    "code": "multivariate_linear_training",
    "revision": 1,
    "name": "多变量线性模型训练",
    "summary": "用多个已知因子预测一个或多个数值目标。",
    "category": "training",
    "composable": true,
    "inputs": [
      {
        "code": "observations",
        "name": "观测输入",
        "required": true,
        "data_type": {
          "semantic": "research_observation_table",
          "version": 1,
          "shape": "table",
          "unit": "column_definitions",
          "alignment": "business_date"
        }
      },
      {
        "code": "request",
        "name": "组件配置",
        "required": true,
        "data_type": {
          "semantic": "multivariate_regression_request",
          "version": 1,
          "shape": "bundle",
          "unit": "native_contract",
          "alignment": "context"
        }
      }
    ],
    "outputs": [
      {
        "code": "trained_model",
        "name": "训练后的模型",
        "data_type": {
          "semantic": "multivariate_linear_model",
          "version": 2,
          "shape": "bundle",
          "unit": "native_contract",
          "alignment": "context"
        }
      },
      {
        "code": "predictions",
        "name": "预测结果表",
        "data_type": {
          "semantic": "research_prediction_table",
          "version": 1,
          "shape": "table",
          "unit": "column_definitions",
          "alignment": "business_date"
        }
      }
    ]
  },
  "research_contract": {
    "request_schema": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "features": {
          "title": "输入变量",
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]{0,95}$"
          },
          "x-research-variables": {
            "table_port": "observations",
            "roles": [
              "covariate",
              "driver"
            ]
          }
        },
        "targets": {
          "title": "预测目标",
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]{0,95}$"
          },
          "x-research-variables": {
            "table_port": "observations",
            "roles": [
              "target"
            ],
            "observed": true,
            "evaluation_target": true
          }
        },
        "training_end": {
          "title": "训练截止日期",
          "type": "string",
          "format": "date",
          "description": "使用截至当天的记录训练，对之后日期的已知因子计算预测值。"
        }
      },
      "required": [
        "features",
        "targets",
        "training_end"
      ]
    },
    "execution": {
      "status": "available",
      "profile": "offline_cpu"
    }
  }
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| definition.inputs[].code / name / required | 输入端口标识、名称、必需性 | 绘制输入点；连线终点bindings[].port用code。 |
| definition.outputs[].code / name | 输出端口标识、名称 | 绘制输出点及成果名称，后续连接用code。 |
| definition.selection_options | 模型明确提供的选择项 | 非空时生成选项，选择结果写入节点selections；不能自行添加Schema未定义的开关。 |
| inputs/outputs[].data_type | 端口数据合同 | 同时比较semantic/version/shape/unit/alignment，不能只按名称或shape接线。 |
| research_contract.request_schema.properties | 参数字段Schema | title作标签、description作帮助；type/enum/format/default决定控件及初值。 |
| request_schema.required / additionalProperties | 必填及额外字段规则 | 用于表单检查，没有Schema时允许明确待配置，不编造字段。 |
| properties.<参数>.x-research-variables | 参数中的变量用途 | 按table_port、roles、observed筛选因素/标签，绑定features、targets等真实参数。 |
| research_contract.input_uses / capabilities | 操作和变量用途合同 | 有值时解释训练/应用及标签/因素；null时保留待配置，不强套通用回归。 |
| definition.requirements / limitations | 条件与限制 | 显示方法适用说明。 |
| contract_sha256 / available_for_new_design | 合同摘要、新采用状态 | 保留准确身份，历史节点按原版本解释。 |

本例参数为features/targets/training_end，写入对应request输入配方的configuration.value；不是每个模型都有这些参数。未确定时可在编辑草稿保留{"kind":"deferred"}，输入data_type和参数角色保持原合同；必需request参数待配置时，10返回incomplete_configuration，11/12拒绝正式保存。已配置参数且只缺数据接入的typed deferred资料，仍允许设计检查与保存，实际运行单独拒绝缺失适配。

## 07. 查询基础模型历史版本

**GET /api/v1/model-center/components/{code}/versions**

用途：显示同一基础模型的版本选项，解释方案已有的历史引用。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| code（路径） | 必填string，基础模型代码。 |

请求体：无。

curl：

```sh
COMPONENT_CODE=multivariate_linear_training
curl -fsS "$BFF/api/v1/model-center/components/$COMPONENT_CODE/versions" \
  -H "$AUTH"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "items": [
    {
      "definition": {
        "code": "multivariate_linear_training",
        "revision": 1,
        "name": "多变量线性模型训练",
        "summary": "用多个已知因子预测一个或多个数值目标。",
        "category": "training",
        "composable": true
      },
      "available_for_new_design": true,
      "research_contract": {
        "execution": {
          "status": "available",
          "profile": "offline_cpu"
        }
      }
    }
  ],
  "total": 1
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| items[].definition.revision | 版本号 | 显示版本选项；名称和端口读取该项definition。 |
| items[].available_for_new_design | 当前新采用资格 | 历史可读不等于允许新采用；已有节点不自动升级。 |
| total | 该模型版本数 | 与组件列表total分别解释。 |

## 08. 查询输出可连接的下游模型输入

**GET /api/v1/model-center/components/{code}/outputs/{output}/compatible-inputs**

用途：拖出连线时，按准确数据合同返回下游模型与输入端口候选。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| code / output（路径） | 必填string，上游组件代码及输出端口code。 |
| revision（查询） | 可选integer≥1，使用上游节点准确版本。 |

请求体：无。

curl：

```sh
COMPONENT_CODE=multivariate_linear_training
OUTPUT_CODE=trained_model
curl -fsS "$BFF/api/v1/model-center/components/$COMPONENT_CODE/outputs/$OUTPUT_CODE/compatible-inputs?revision=1" \
  -H "$AUTH"
```

响应：HTTP200。

```json
{
  "source": {
    "code": "multivariate_linear_training",
    "revision": 1,
    "output": "trained_model"
  },
  "items": [
    {
      "code": "multivariate_linear_predict",
      "revision": 1,
      "input": "model"
    }
  ],
  "total": 1
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| source | 上游组件和端口身份 | 确认候选列表对应当前输出。 |
| items[].code / revision | 下游组件及准确版本 | 通过接口06取得名称和完整合同。 |
| items[].input | 可接收的下游输入端口 | 写入下游节点bindings[].port。 |
| total | 兼容端口数量 | 0表示无直接兼容端口，不能强行用普通表替代。 |

只证明端口数据合同相等，不代表变量和参数或整个研究已通过检查；最终仍调用接口10。同一上游输出可连接多个下游节点形成分支。

## 09. 将编辑方案生成配置文件

**POST /api/v1/research/configurations/draft**

用途：把完整definition包装成带摘要的configuration；不落库，也不代表方案已通过设计检查。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| 请求体整体 | 完整definition，不再套definition或configuration外壳。 |
| name / question | 研究名称、问题；正式检查时必需。 |
| objective | 研究目标：association/prediction/treatment_effect/mechanistic。 |
| purpose | 研究操作：explore/simulate/fit/train/predict/evaluate；与模板外层operation分开，采用模板时保留原definition.purpose。 |
| variables / collection_requirements | 准确指标定义和来源，来自接口04。 |
| composition / input_recipes / evaluation | 节点连线、输入配方、参数和评价要求。 |
| schema_version / layout | 新自定义定义用1.5，旧方案保留原版本及layout。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "schema_version": "1.4",
  "name": "多因素作物生长指标预测",
  "question": "研究冠层覆盖度、块茎干物质与叶面积指数、地上生物量的关系，并预测多个生长指标。",
  "objective": "prediction",
  "purpose": "train",
  "composition": {
    "schema_version": "1.0",
    "object_scope": "field_crop_season",
    "inputs": [
      {
        "code": "observations",
        "name": "系统标准人工记录",
        "role": "context",
        "data_type": {
          "semantic": "research_observation_table",
          "version": 1,
          "shape": "table",
          "unit": "column_definitions",
          "alignment": "business_date"
        }
      },
      {
        "code": "regression_config",
        "name": "多变量线性回归配置",
        "role": "parameter",
        "data_type": {
          "semantic": "multivariate_regression_request",
          "version": 1,
          "shape": "bundle",
          "unit": "native_contract",
          "alignment": "context"
        }
      }
    ],
    "nodes": [
      {
        "code": "regression",
        "component": {
          "code": "multivariate_linear_training",
          "revision": 1
        },
        "bindings": [
          {
            "port": "observations",
            "source": {
              "node": null,
              "port": "observations"
            }
          },
          {
            "port": "request",
            "source": {
              "node": null,
              "port": "regression_config"
            }
          }
        ],
        "selections": {}
      }
    ],
    "outputs": [
      {
        "code": "trained_model",
        "source": {
          "node": "regression",
          "port": "trained_model"
        }
      },
      {
        "code": "predictions",
        "source": {
          "node": "regression",
          "port": "predictions"
        }
      }
    ]
  },
  "input_recipes": {
    "observations": {
      "kind": "observations",
      "variable_codes": [
        "lai",
        "agb_kg_ha",
        "canopy_cover",
        "tuber_dm_kg_ha"
      ]
    },
    "regression_config": {
      "kind": "configuration",
      "value": {
        "features": [
          "canopy_cover",
          "tuber_dm_kg_ha"
        ],
        "targets": [
          "lai",
          "agb_kg_ha"
        ],
        "training_end": "2026-05-10"
      },
      "runtime_fields": {}
    }
  }
}
```

curl：

```sh
curl -fsS -X POST "$BFF/api/v1/research/configurations/draft" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  --data-binary @definition.json -o configuration.json
```

响应：HTTP200（字段节选）。

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| format | 文件格式 | 通常为research_plan_draft，保留原值。 |
| definition | 完整可编辑方案 | 后续编辑此正文；修改后重新请求本接口。 |
| sha256 | 完整文件摘要 | 与format/definition一起原样传递，不手动改写。 |

完整definition来自接口02或[完整示例JSON](examples/model-designer.json)的definition。响应完整保留到configuration.json；本文节选不能直接作为后续提交正文。

## 10. 检查当前配置并定位错误

**POST /api/v1/research/configurations/check**

用途：保存前检查结构、变量、来源、参数与连线，不取数、不计算、不落库。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| format / definition / sha256 | 原样提交接口09返回的完整configuration；改正文须重新生成文件摘要。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
}
```

curl：

```sh
curl -fsS -X POST "$BFF/api/v1/research/configurations/check" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  --data-binary @configuration.json -o check.json
```

响应：HTTP200（字段节选）。

```json
{
  "valid": true,
  "compiled": {
    "validation_scope": "design_contract",
    "compiler_version": "1.0.0",
    "order": [
      "regression"
    ]
  },
  "issues": []
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| valid | 设计检查结果 | HTTP200且valid=true才允许正式保存。 |
| issues[].path | 错误字段路径 | 定位表单/节点，数字为数组下标。 |
| issues[].node / port | 出错节点及端口 | 存在时高亮；不是每个错误都含这两个字段。 |
| issues[].type / message | 类型和具体说明 | 按type映射中文提示并保留message；未知类型也显示。 |
| compiled.order | 节点依赖顺序 | 可辅助排列，不是实际运行记录。 |
| compiled.validation_scope | 检查范围 | design_contract表示设计合同检查，不能显示运行成功。 |

`incomplete_configuration`定位到`input_recipes[输入code]`，同时给出`node`和`port=request`。引导用户回到“计算与评价”完成参数，不能忽略该错误或把待配置步骤显示成已检查通过。空名称、纯空格名称、空研究问题、缺模型/成果和不合法参数也不得显示检查成功。合法模板已含预置配置时，无需用户重复填写；检查的是当前整份定义。

02 按真实资料形态展示。普通 `observations` 列按节点用途显示。`artifact` 和 `deferred` 资料从 `composition.inputs` 和 `input_recipes` 列出名称、来源状态和使用它的节点。指定资料明细按 `input_requirements[].port` 显示到对应资料卡。已保存方案的 `layout.study_template` 含模板 ID 和 SHA-256，可用接口 02 读取准确版本的明细。尚未采用的候选指标标为“尚未用于计算”。03 从 `composition.outputs` 关联接口 06 的准确输出端口，显示预期成果。样例目标可由 `kind=target` 提供。

设计检查失败通常仍返回HTTP200：

```json
{
  "valid": false,
  "issues": [
    {
      "path": [
        "composition",
        "nodes",
        0,
        "bindings"
      ],
      "type": "missing_input",
      "message": "Required input bindings are missing: regression.observations,request",
      "node": "regression",
      "port": "observations"
    }
  ]
}
```
摘要或请求格式错误可能返回HTTP422；不能只凭HTTP状态判断设计通过。

## 11. 正式保存一个新研究方案

**POST /api/v1/research/design-saves**

用途：再次检查配置，将方案与成功回执原子写入本系统数据库；随后业务系统保存业务关联。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| Idempotency-Key（请求头） | 必填UUID，发送前持久化；重试保持原ID和原正文。 |
| configuration | 必填object，接口09生成且接口10检查通过的完整配置。 |
| version_name | 可选单行字符串，如「春季基线」。留空在确认可应用版本时分配名称。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
  }
}
```

curl：

```sh
REQUEST_ID=$(uuidgen)
jq '{configuration:.}' configuration.json > save-create.json
curl -fsS -X POST "$BFF/api/v1/research/design-saves" \
  -H "$AUTH" -H "Idempotency-Key: $REQUEST_ID" -H 'Content-Type: application/json' \
  --data-binary @save-create.json -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
  "revision": 1,
  "configuration_sha256": "f9f66d773dc142c10f812d3c9d08f1a8447c8c26319aea489cb0d4aaef767525"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| design_id | 本系统已保存方案ID | 存入业务关联和前端路由，接口14用它查询。 |
| revision | 准确保存修订 | 更新时作为expected_revision，不自行加一提交。 |
| configuration_sha256 | 持久化配置摘要 | 业务库保留回执原值，与configuration内部sha256不同。 |

成功HTTP200表示本系统数据库已提交。不要用暂存草稿的POST/PUT design-drafts替代正式保存。非法设计返回HTTP422，不创建方案或成功回执：

```json
{
  "detail": "Research design validation failed",
  "issues": [
    {
      "path": [
        "composition",
        "nodes",
        0,
        "bindings"
      ],
      "type": "missing_input",
      "message": "Required input bindings are missing: regression.observations,request",
      "node": "regression",
      "port": "observations"
    }
  ]
}
```


## 12. 修改已保存研究方案

**POST /api/v1/research/design-saves**

用途：核对当前修订后更新同一方案，防止旧页面覆盖较新修改。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| configuration | 编辑后重新通过接口09、10的完整配置。 |
| design_id | 必填UUID，接口14返回的方案ID。 |
| expected_revision | 必填integer≥1，与design_id成对提供，取接口14返回的revision。 |
| version_name | 可选候选名称，已确认版本中的名称按方案唯一。 |
| Idempotency-Key（请求头） | 每次新的保存生成新UUID，该次重试保留原值。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
  },
  "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
  "expected_revision": 1
}
```

curl：

```sh
DESIGN_ID=$(jq -r '.design_id' saved.json)
REVISION=$(jq '.revision' saved.json)
REQUEST_ID=$(uuidgen)
jq --arg id "$DESIGN_ID" --argjson revision "$REVISION" '{configuration:.,design_id:$id,expected_revision:$revision}' configuration.json > save-update.json
curl -fsS -X POST "$BFF/api/v1/research/design-saves" \
  -H "$AUTH" -H "Idempotency-Key: $REQUEST_ID" -H 'Content-Type: application/json' \
  --data-binary @save-update.json -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
  "revision": 1,
  "configuration_sha256": "f9f66d773dc142c10f812d3c9d08f1a8447c8c26319aea489cb0d4aaef767525"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| design_id | 原方案ID | 保持当前页面和业务关联，不新增一份方案。 |
| revision | 服务端确认修订 | 替换前端当前修订，内容变化时推进；完全相同配置可能保持不变。 |
| configuration_sha256 | 更新结果摘要 | 更新业务关联，随后接口14重查。 |

本节响应展示同配置重放的回执，不承诺每次调用都加一。409时保留用户修改，重读最新方案并提示处理冲突，不自动改expected_revision覆盖。

## 13. 查询企业已保存方案列表

**GET /api/v1/research/design-drafts**

用途：显示本企业已经保存的可编辑研究方案，与接口01的公共模板目录分开。

请求：

无接口特定参数。

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/research/design-drafts" \
  -H "$AUTH"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "items": [
    {
      "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
      "revision": 1,
      "configuration_sha256": "f9f66d773dc142c10f812d3c9d08f1a8447c8c26319aea489cb0d4aaef767525",
      "updated_at": "2026-11-16T21:38:09.945171+08:00",
      "configuration": {
        "format": "research_plan_draft",
        "definition": {
          "name": "多因素作物生长指标预测"
        },
        "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
      }
    }
  ]
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| items[].design_id | 方案唯一ID | 作为列表唯一键和打开方案参数。 |
| items[].configuration.definition.name / question | 保存后的名称、问题 | 显示标题、摘要；没有单独title字段。 |
| items[].revision / updated_at | 修订、更新时间 | 显示版本和最近保存时间，日期按时区格式化。 |
| items[].configuration | 完整配置 | 可用于预览，正式编辑前用接口14重查。 |
| items[].configuration_sha256 | 持久化摘要 | 核对一致性，卡片不必显示长摘要。 |

当前最多返回最近100项，按更新时间倒序；无total、分页或搜索参数。items=[]显示尚未保存方案，不是接口失败。

## 14. 查询已保存方案并还原流程图

**GET /api/v1/research/design-drafts/{design_id}**

用途：从本系统数据库重新读取保存结果，用查询结果展示流程图并继续编辑。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| design_id（路径） | 必填UUID，正式保存回执的design_id，不是模板id或模型id。 |

请求体：无。

curl：

```sh
DESIGN_ID=$(jq -r '.design_id' receipt.json)
curl -fsS "$BFF/api/v1/research/design-drafts/$DESIGN_ID" \
  -H "$AUTH" -o saved.json
```

响应：HTTP200（字段节选）。

```json
{
  "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
  "revision": 1,
  "version_name": null,
  "latest_version": {"design_version_id": "18d1001a-d86f-5827-8525-0466086c7499", "version_name": "1.0.0"},
  "configuration_sha256": "f9f66d773dc142c10f812d3c9d08f1a8447c8c26319aea489cb0d4aaef767525",
  "updated_at": "2026-11-16T21:38:09.945171+08:00",
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
  }
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| configuration.definition | 已持久化正文 | 完整恢复编辑状态，不只展示保存前的浏览器缓存。 |
| configuration.definition.composition | 节点、连线、成果 | 按本文流程图规则渲染。 |
| configuration.definition.variables / collection_requirements | 指标及来源 | 恢复名称、单位、提供方式及准确绑定。 |
| design_id / revision | 本次查询的ID与修订 | 供后续修改提交使用。 |
| version_name / latest_version | 候选名称及最近固定版本 | 候选填入基础信息。用 `latest_version.version_name` 显示最近固定版本，使用其中的 UUID 应用。 |
| configuration_sha256 / updated_at | 持久化摘要、更新时间 | 核对保存结果并显示更新时间。 |

404表示当前企业不可见或方案不存在，不能切换匿名空间读取。配置接口不返回当次真实观测或运行结果。

14 查询该方案当前修订。保存后用返回的 `revision` 和 `configuration_sha256` 对照保存回执。有并发更新时，页面标明当前显示的修订。

保存或确认版本时用 `issues[].path` 把错误定位到版本名称。409 表示该方案已用此名称，422 表示格式错误。保留编辑中的配置，用户改名后用新保存请求重试。

### 用已保存响应还原动态研究流程

卡片数量与依赖随方案变化，不能固定套用五栏，也不能向配置补写展示节点。自带页面采用黄色来源、绿色处理/计算、蓝色评价/成果，卡片底部展开明细；全屏、适应宽度与缩放不修改配置。

| 卡片 | 使用的数据 | 缺少实际证据时显示 |
| --- | --- | --- |
| 资料卡：每个实际外部输入一张 | 14的`configuration.definition.composition.inputs/input_recipes`，变量与`collection_requirements`关联03目录一级/二级分类；按06节点参数确定实际用途。`configuration`参数并入消费步骤，不单独成卡；原生资料包不能因端口叫request而隐藏 | 列出该输入内全部已选指标，区分参与计算与尚未使用；目录取数能力不等于本次已取数 |
| 数据划分卡：确有可解释的划分规则才出现 | 当次真实观测或已封存记录数；按准确训练截止与实际记录划分训练/时间留出 | “尚未提供数据”；不从日期跨度推算样本，不虚构数据集编号或独立测试集；未识别到规则时不追加此卡 |
| 计算卡：每个实际节点一张 | 14的`composition.nodes`与06准确版本、输入端口及参数；运行状态从对应步骤回执读取 | “待训练/待拟合/待分析”；自动日期变换单独标为平台资料处理；并行步骤同层，串联步骤按依赖展开 |
| 评价卡：实际评价节点、已识别的时间留出规则或真实评价结果 | 实际结果中的目标、配对行数、RMSE及已提供的MAE/R²；成果关联决定预测数据从哪里进入 | 无依据不额外补评价卡；有规则未运行时显示“尚无评价结果”；时间留出不叫独立地块验证，缺值不填0 |
| 成果卡：按公开输出的产生节点分组 | 14的`composition.outputs[].source`及06准确输出端口；实际成果与16/17已保存模型另行关联 | 列出该分支预期成果及“等待产出”；方案修订不是训练模型版本，不显示虚构发布版本 |

连线必须来自`composition.nodes[].bindings`与`composition.outputs[].source`，只连接真正依赖的卡片，不能因为相邻就补箭头。同一对卡片的多端口连接可以合并展示，保留端口明细；多个输入汇合、并行计算和各自产出分支都要保留。时间留出资料绕过训练进入评价，使用虚线；没有实测时标明计划或待补，不声称验证通过。

例如高温条件分析是“资料→分析→成果”3个环节；平台日期拟合是“资料→日期处理→曲线拟合→成果”4个环节；土壤、气象、卫星资料汇合计算时有3张来源卡。具体数量以返回配置为准。

14仅提供可复用设计，无法单独提供图中真实样本数、误差、地块覆盖和发布进度。业务前端须结合自己的实际数据及相应运行记录。当前自带页面复用工作区观测与运行结果展示统计，未新增专为卡片服务的API或数据库字段。

## 15. 按保存请求ID查询成功回执

**GET /api/v1/research/design-saves/{request_id}**

用途：保存响应超时、业务落库失败或重启后确认原保存结果，避免重复创建。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| request_id（路径） | 必填UUID，原Idempotency-Key，不是design_id。 |

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/research/design-saves/$REQUEST_ID" \
  -H "$AUTH" -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "d5abe113-2d68-56a9-b08f-a24ca8619fc8",
  "revision": 1,
  "configuration_sha256": "f9f66d773dc142c10f812d3c9d08f1a8447c8c26319aea489cb0d4aaef767525"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| design_id / revision / configuration_sha256 | 原保存的准确结果 | 用于恢复业务关联；方案后来又修改时，旧回执不代表最新修订。 |

200继续登记业务关联；404按原ID、原正文重发；超时保留pending。相同ID、不同正文返回409，不能自动换ID重复创建。

## 16. 查询本企业已训练并保存的模型

**GET /api/v1/research/models**

用途：显示训练成果模型列表。基础算法选择使用接口05；保存研究方案本身不会产生训练模型。

请求：

无接口特定参数。

请求体：无。

curl：

```sh
curl -fsS "$BFF/api/v1/research/models" \
  -H "$AUTH" -o models.json
```

响应：HTTP200。

```json
{
  "items": []
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| items[].model_id | 训练模型ID | 模型列表唯一键、接口17的查询参数。 |
| items[].name | 保存的模型名称 | 显示模型标题。 |
| items[].run_id | 模型来源训练运行 | 关联训练来源，不能当作研究方案ID。 |
| items[].model_sha256 | 准确模型内容摘要 | 保留模型身份，不当作设计修订。 |
| items[].created_at | 模型保存时间 | 显示保存时间，不能当作数据更新截止日期。 |

隔离设计验收企业的真实响应为items=[]，显示暂无已训练模型。有模型时索引字段示意（不是该企业实测记录）：

```json
{
  "items": [
    {
      "model_id": "11111111-1111-4111-8111-111111111111",
      "run_id": "22222222-2222-4222-8222-222222222222",
      "name": "作物生长指标预测模型",
      "model_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "created_at": "2026-11-16T14:00:00+00:00"
    }
  ]
}
```
最多100项、按created_at倒序，没有分页或total。

## 17. 查询训练模型准确详情

**GET /api/v1/research/models/{model_id}**

用途：读取本企业已保存训练模型及状态；不训练、不预测。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| model_id（路径） | 必填UUID，接口16返回的模型ID，须属于同一企业。 |

请求体：无。

curl：

```sh
MODEL_ID=$(jq -r '.items[0].model_id' models.json)
# 仅当列表有记录时调用；不要把null作为模型ID。
curl -fsS "$BFF/api/v1/research/models/$MODEL_ID" \
  -H "$AUTH"
```

响应：HTTP200（合同字段示意，非本企业实测记录）。

```json
{
  "model_id": "11111111-1111-4111-8111-111111111111",
  "run_id": "22222222-2222-4222-8222-222222222222",
  "name": "作物生长指标预测模型",
  "model_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "created_at": "2026-11-16T14:00:00+00:00"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| model_id / name / created_at | 模型身份、名称、保存时间 | 显示详情基本信息。 |
| run_id / model_sha256 | 训练来源、内容摘要 | 保留准确训练模型身份。 |
| design_version_id / study_id / dataset_snapshot_id | 训练绑定的固定版本、研究实例和样本快照 | 用 21 读取原方案流程，用 24 读取对象与观察期。缺少引用的历史记录继续显示自身可用信息。 |
| model_json | 版本化训练状态 | 算法间结构不同，完整保留；不能用作统一设计参数表或普通研究定义。 |

上方为合同字段示意，省略model_json；本次不为该企业新开训练任务补样例。不存在或企业不符返回404。模型实际发布、运行和预测不在本文范围。

## 18. 校验并导入配置文件

**POST /api/v1/research/configurations/import**

用途：校验导入文件格式与摘要，按准确版本恢复定义；不落库，不继承原企业访问权。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| 请求体整体 | 完整format/definition/sha256；本批推荐research_plan_draft格式。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
}
```

curl：

```sh
curl -fsS -X POST "$BFF/api/v1/research/configurations/import" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  --data-binary @configuration.json
```

响应：HTTP200（字段节选）。

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "b6cc93ca20884d35a5a8b8a51dabe99badd9b34fc2243bb5d9a512e70f18d517"
}
```

前端使用响应：

| 字段 | 含义 | 显示或后续使用 |
| --- | --- | --- |
| format / definition / sha256 | 校验后的完整配置 | 导入后恢复definition，正式保存仍调用接口10及11/12。 |

research_plan_draft核验文件身份；历史research_plan还会走对应完整合同适配，不保证未来待实现模型能按旧格式导入。导出直接下载完整configuration，不需要另一个导出API。

## 流程图与编辑状态

保存前用当前编辑的 `definition` 预览。保存后用接口 14 的 `configuration.definition` 恢复状态。两个页面按相同规则构图，按每个节点的 `component.code/revision` 通过 06 读取准确名称和端口。下面路径相对于 `definition`。

| 显示内容 | 字段或规则 | 前端处理 |
| --- | --- | --- |
| 指标名称与单位 | variables[].name / unit | 显示研究输入；按实际变量去重计数，不能把观测表数当指标数 |
| 来源与提供方式 | collection_requirements按variable_code关联变量 | 按catalog_binding的kind/code/definition_version/contract_sha256准确匹配目录source.binding，展示分类、具体source.name、method.instructions及selectors |
| 外部资料节点 | composition.inputs[] | code作节点身份、name作标题，data_type完整保留 |
| 模型节点 | composition.nodes[] | node.code作画布唯一键；component.code/revision找组件；标题取layout.node_labels[node.code]或组件definition.name |
| 外部输入连线 | bindings[].source.node=null | 起点为source.port对应的外部输入，终点为当前node.code和binding.port |
| 模型串联/分支 | bindings[].source.node非空 | 起点source.node+source.port，终点当前节点+binding.port；同一输出可被多个下游引用 |
| 成果节点 | composition.outputs[] | output.code作成果ID，source指定来源节点与输出端口，名称查组件输出name |
| 参数侧栏 | input_recipes[外部输入code].kind=configuration | value按对应request_schema填写；参数不用渲染成另一张数据表 |
| 待配置资料/参数 | input_recipes[输入code].kind=deferred | 显示待接入/待配置；保留准确data_type，不填假表或假参数 |
| 观测表所含指标 | input_recipes[输入code].variable_codes | 按variables查出每个名称；一张表可含多项输入指标 |
| 排列 | 依赖关系与layout | 从左到右按拓扑排列，保留已有layout；不假定接口返回x/y坐标 |

外部输入连线示例（从真实composition节选）：

```json
{
  "bindings": [
    {
      "port": "observations",
      "source": {
        "node": null,
        "port": "observations"
      }
    },
    {
      "port": "request",
      "source": {
        "node": null,
        "port": "regression_config"
      }
    }
  ]
}
```

下游模型使用上游训练结果的绑定示意：

```json
{
  "port": "model",
  "source": {
    "node": "regression",
    "port": "trained_model"
  }
}
```

regression是上游节点code，model必须是下游合同真实声明的输入端口，不能任意命名；最终调用接口10检查。

### 指标与模型编辑规则

- 采用指标须同时写入variable和requirement，避免variable.code重复；更换来源时替换整项准确绑定。
- 新增/删除指标须同步variables、collection_requirements、观测配方variable_codes和模型features/targets等真实参数，不能只增删界面行。
- 1.5方案的训练/应用、因素/标签用途按实际节点请求合同解释；修改全局variable.role不能让任意模型使用任意输入。多因素、多目标数组按Schema配置。
- 模型选择保留准确code/revision和端口合同。未接通实现可保留待配置；已经填写的参数仍须合法。
- 展示来源时，category/subcategory用于分类，source.name为具体提供方，method.instructions解释如何提供，execution.reason说明接入缺口。
- 历史绑定未匹配当前目录时保留原绑定、显示历史来源待核验；不能仅凭同名指标换来源或升级版本。
- 研究流程按同一配置的实际输入、计算节点、公开成果及依赖动态生成；设计接口不返回运行数量、资料齐备数量、训练曲线，不编造这些状态。

## 检查错误如何定位

| issues.path | 页面位置 |
| --- | --- |
| name / question | 基本信息 |
| variables / 下标 / 字段 | 指标定义、单位或角色 |
| collection_requirements / 下标 / 字段 | 来源、版本、尺度、土层或统计属性 |
| input_recipes / 输入code / value / 字段 | 模型参数表单 |
| composition / nodes / 下标 / bindings | 节点连线，配合node/port高亮 |
| composition / outputs | 成果选择 |
| configuration | 文件格式或摘要，提示重新生成配置 |

不是所有错误都有node/port；未知path/type也显示message。HTTP422请求解析错误可能使用rule而非type，path前的body/query/path表示请求层位置。409保留用户未保存编辑并提示重读，不能自动覆盖。

| `issues[].type` | 典型定位和处理 |
| --- | --- |
| `unregistered_indicator` | `collection_requirements / 下标 / catalog_binding`，返回资料或目标配置，从指标库重新采用。 |
| `invalid_indicator` | `variables / 下标 / 字段`，恢复目录中已登记的定义。 |
| `input_target_overlap` | `input_recipes / 输入code / value / 参数字段`，在对应模型参数中移除重复用作训练输入和目标的列。 |
| `incomplete_configuration` | `input_recipes / 输入code`，结合 `node/port` 回到计算与评价，补齐必需模型参数。 |

## 保存成功后的界面行为

前端提交→业务后端检查→本系统正式保存→业务后端保存关联→返回成功→接口14重查→从查询结果展示流程图。业务关联尚未提交时显示方案已保存、业务登记待完成，不显示整体保存完成。

configuration.sha256是文件摘要；回执configuration_sha256是持久化配置摘要；模板sha256、模型model_sha256分别表示模板和训练模型身份。模板revision、设计revision、组件revision分别管理。

本系统/designer/为个人工作区样例，业务前端使用企业转接接口和自己的页面路由。
