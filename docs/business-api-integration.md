# 业务系统API对接

范围：方案、指标、基础模型查询，设计校验、正式保存、重查及流程图。不包含取数、调度、训练和预测API。每个接口单独说明请求、curl和响应。

[查看完整闭环流程图（按 API 编号）](model-designer-api-flow.md)

## API-Key接入约定

| 项目 | 固定约定 |
| --- | --- |
| 服务地址 | `http://172.16.1.122:18925` |
| OpenAPI安全方案 | `ModarchitectApiKey`，类型`apiKey` |
| 传递位置、请求头 | `in: header`，`X-Modarchitect-Api-Key` |
| 请求头值 | 本项目Key原值，不加`Bearer `前缀 |
| 已部署Key | [Nomad变量modarchitect-api](http://172.16.1.124:4646/ui/variables/var/nomad/jobs/modarchitect-api@default)中的`api_key` |
| 业务后端配置 | 环境变量`MODARCHITECT_API_KEY`，复制上述同一个值 |
| 本系统配置 | Nomad模板自动将`api_key`注入本系统`MODARCHITECT_API_KEY` |

Key部署时已生成，无需重建；仅在后端配置，不写文档、方案或浏览器代码。本项目不使用`X-MLGrowth-Business-Key`。业务系统负责用户登录、权限和业务库；本系统验证服务Key和企业范围。

```sh
API=http://172.16.1.122:18925
: "${MODARCHITECT_API_KEY:?请先配置Nomad中的api_key原值}"
KEY="$MODARCHITECT_API_KEY"
PROVIDER=biology-institute
COMPANY_ID=1
SCOPE="provider_name=$PROVIDER&company_id=$COMPANY_ID"
```

企业方案、保存回执及训练模型接口的企业范围由业务登录态确定。GET通过查询传入；正式保存可以在正文传入，两处同时出现必须一致。配置生成、检查和导入只检查JSON，不要求企业范围，但仍需服务Key。不要把企业字段放入definition。公共model-center目录不含企业私有数据，当前可不带Key，示例统一带Key便于转接。

**标记“字段节选”的JSON仅解释字段，不能直接提交；curl读取和保存的是完整正文。** 长配置见[完整示例JSON](examples/model-designer.json)。示例ID属于隔离验收企业，不继承访问权；对接时使用本企业的API返回值。

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

| 字段 | 要求及含义 |
| --- | --- |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
curl -fsS "$API/api/v1/research/study-templates?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| items[].id | 模板标识；点击后作为接口02的template_id；不能当作design_id。 |
| items[].title / summary | 方案名称、研究问题；显示卡片标题和摘要。 |
| items[].revision / sha256 | 模板修订、准确摘要；保存模板来源；不当作设计修订或设计ID。 |
| items[].researcher.category / needed | 研究分类、所需资料；分类筛选和输入要求。 |
| items[].output_description / limitations | 预期成果、适用限制；显示成果说明和限制。 |
| items[].operation | 研究操作；train训练、analyze分析、simulate模拟、calibrate标定、predict预测。按返回值显示。 |
| items[].data_kind | 示例资料性质；synthetic显示合成示例，不能当作田间真实记录。 |
| items[].input_policy | 原模板的运行用数规则；说明原模板资料限制；不能据此禁用指标或基础模型的设计选择。 |

响应只有items，没有分页和total。空列表按items.length判断。

## 02. 查询公共方案详情并进入设计器

**GET /api/v1/research/study-templates/{template_id}**

用途：取得选中方案的完整定义，初始化研究设计页面。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| template_id（路径） | 必填string，接口01的id；示例crop-growth-prediction。 |
| sha256（查询） | 可选string，读取指定模板摘要；省略时读取当前采用版本。 |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
TEMPLATE_ID=crop-growth-prediction
curl -fsS "$API/api/v1/research/study-templates/$TEMPLATE_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -o template.json
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| definition.name / question | 研究名称、问题；填入基本信息；编辑definition，不是只改外层title。 |
| definition.objective / purpose | 研究目标、研究操作；恢复关联/预测/机理等目标和训练/探索/模拟等操作。 |
| definition.variables | 已采用指标；按code关联，显示name、unit；保留完整科学定义和版本。 |
| definition.collection_requirements | 指标来源与采集规则；按variable_code关联指标；展示来源、方法、采样尺度和取数属性。 |
| definition.composition / input_recipes | 节点连线、资料与参数；恢复流程图和参数面板，见本文末尾字段规则。 |
| definition.evaluation / layout | 评价设置、界面信息；恢复评价条件并保留layout；node_labels可用作节点标题。 |
| observations / prediction_observations | 模板可提供的示例记录，可能为null；独立于definition；本次设计保存不把示例记录塞入definition。 |

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
curl -fsS "$API/api/v1/model-center/research-inputs" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| categories[].code / name / count | 一级分类代码、名称、数量；生成一级分类按钮，如第三方数据。 |
| categories[].children[].code / name / count | 二级分类；生成气象、土壤、卫星等子分类。 |
| items[].category / subcategory | 指标所属分类；按code与两级分类匹配，前端筛选。 |
| items[].key | 准确选择标识；添加时传给接口04，不能只传variable.code。 |
| items[].variable.name / description / unit | 名称、解释、科学单位；显示指标卡片和单位；celsius可显示℃，提交仍保持原值。 |
| items[].unit_kind | 指标代表的采样尺度；field_season地块种植季、point点位、plant单株、quadrat样方、soil_layer土层、report_area报告范围。 |
| items[].source.name | 具体来源名称；显示Open-Meteo气象等提供方，不能只显示第三方。 |
| items[].source.selection_schema | 来源采用属性Schema；根据properties/required/enum生成土层、统计方式等选择框。 |
| items[].source.binding.value_nature | 数值性质；observed实测、estimated估计等；估计来源不能作为实测标签。 |
| items[].selectable | 设计采用资格；控制加入按钮，当前65项全部开放设计。 |
| items[].execution.available / reason / channel | 接入状态、原因、取数渠道；显示已接通或待接入；false不能禁用设计。source_snapshot为平台采集后引用快照，workspace_manual_entry为标准人工记录。 |
| items[].data_available | 本次数据是否已有；null表示尚未核实，不能显示已有数据。 |
| total / version / sha256 | 目录总数、版本、摘要；显示总数，保留版本信息，不硬编码数量。 |

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
curl -fsS -X POST "$API/api/v1/model-center/research-inputs/configure" \
  -H "X-Modarchitect-Api-Key: $KEY" -H 'Content-Type: application/json' \
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| variable | 权威变量定义；按code加入/替换definition.variables；name、unit、definition_version不任意重写。 |
| requirement | 准确来源及采集要求；加入/替换definition.collection_requirements，按variable_code关联。 |
| requirement.catalog_binding | 来源身份、版本、摘要和属性；完整保留；kind=planned_source显示待接入。 |
| requirement.catalog_binding.selectors | 本次采用的来源属性；显示土层、统计方式；改变属性须重新调用本接口。 |
| requirement.method.instructions | 资料如何提供；显示取数/人工采集说明。 |
| entry.category / subcategory / source.name | 分类与具体提供方；匹配目录分类名称后显示完整来源，不只显示第三方/平台。 |
| entry.execution | 取数实现状态；显示接入说明，不能误当作设计采用资格。 |

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
curl -fsS "$API/api/v1/model-center/components?page=1&page_size=100" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| items[].definition.code / revision | 准确组件身份；采用后写入composition.nodes[].component，不只保存显示名称。 |
| items[].definition.name / summary | 模型名称、用途；显示模型卡片标题和说明。 |
| items[].definition.category | 计算组件分类；用于模型筛选，与指标来源分类分别管理。 |
| items[].available_for_new_design / definition.composable | 新设计采用资格、是否可组合；符合时允许新增组合节点。 |
| items[].research_contract.execution.status | 实际执行状态；available/design_only/unavailable用于说明，不禁用设计选择。 |
| items[].research_contract.request_schema | 参数表单Schema；按接口06解释；null不表示禁止设计。 |
| total / page / page_size | 分页信息；控制总数和翻页，本批28项不能硬编码在前端。 |

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
curl -fsS "$API/api/v1/model-center/components/$COMPONENT_CODE?revision=1" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| definition.inputs[].code / name / required | 输入端口标识、名称、必需性；绘制输入点；连线终点bindings[].port用code。 |
| definition.outputs[].code / name | 输出端口标识、名称；绘制输出点及成果名称，后续连接用code。 |
| definition.selection_options | 模型明确提供的选择项；非空时生成选项，选择结果写入节点selections；不能自行添加Schema未定义的开关。 |
| inputs/outputs[].data_type | 端口数据合同；同时比较semantic/version/shape/unit/alignment，不能只按名称或shape接线。 |
| research_contract.request_schema.properties | 参数字段Schema；title作标签、description作帮助；type/enum/format/default决定控件及初值。 |
| request_schema.required / additionalProperties | 必填及额外字段规则；用于表单检查，没有Schema时允许明确待配置，不编造字段。 |
| properties.<参数>.x-research-variables | 参数中的变量用途；按table_port、roles、observed筛选因素/标签，绑定features、targets等真实参数。 |
| research_contract.input_uses / capabilities | 操作和变量用途合同；有值时解释训练/应用及标签/因素；null时保留待配置，不强套通用回归。 |
| definition.requirements / limitations | 条件与限制；显示方法适用说明。 |
| contract_sha256 / available_for_new_design | 合同摘要、新采用状态；保留准确身份，历史节点按原版本解释。 |

本例参数为features/targets/training_end，写入对应request输入配方的configuration.value；不是每个模型都有这些参数。未确定时可保留{"kind":"deferred"}，但输入data_type和参数角色保持原合同。

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
curl -fsS "$API/api/v1/model-center/components/$COMPONENT_CODE/versions" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| items[].definition.revision | 版本号；显示版本选项；名称和端口读取该项definition。 |
| items[].available_for_new_design | 当前新采用资格；历史可读不等于允许新采用；已有节点不自动升级。 |
| total | 该模型版本数；与组件列表total分别解释。 |

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
curl -fsS "$API/api/v1/model-center/components/$COMPONENT_CODE/outputs/$OUTPUT_CODE/compatible-inputs?revision=1" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| source | 上游组件和端口身份；确认候选列表对应当前输出。 |
| items[].code / revision | 下游组件及准确版本；通过接口06取得名称和完整合同。 |
| items[].input | 可接收的下游输入端口；写入下游节点bindings[].port。 |
| total | 兼容端口数量；0表示无直接兼容端口，不能强行用普通表替代。 |

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
curl -fsS -X POST "$API/api/v1/research/configurations/draft" \
  -H "X-Modarchitect-Api-Key: $KEY" -H 'Content-Type: application/json' \
  --data-binary @definition.json -o configuration.json
```

响应：HTTP200（字段节选）。

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| format | 文件格式；通常为research_plan_draft，保留原值。 |
| definition | 完整可编辑方案；后续编辑此正文；修改后重新请求本接口。 |
| sha256 | 完整文件摘要；与format/definition一起原样传递，不手动改写。 |

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
  "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
}
```

curl：

```sh
curl -fsS -X POST "$API/api/v1/research/configurations/check" \
  -H "X-Modarchitect-Api-Key: $KEY" -H 'Content-Type: application/json' \
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| valid | 设计检查结果；HTTP200且valid=true才允许正式保存。 |
| issues[].path | 错误字段路径；定位表单/节点，数字为数组下标。 |
| issues[].node / port | 出错节点及端口；存在时高亮；不是每个错误都含这两个字段。 |
| issues[].type / message | 类型和具体说明；按type映射中文提示并保留message；未知类型也显示。 |
| compiled.order | 节点依赖顺序；可辅助排列，不是实际运行记录。 |
| compiled.validation_scope | 检查范围；design_contract表示设计合同检查，不能显示运行成功。 |

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
| provider_name / company_id | 业务后端从登录态注入的企业范围，不进入definition。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "provider_name": "modarchitect_design_loop",
  "company_id": 1,
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
  }
}
```

curl：

```sh
REQUEST_ID=$(uuidgen)
jq --arg provider "$PROVIDER" --argjson company "$COMPANY_ID" '{provider_name:$provider,company_id:$company,configuration:.}' configuration.json > save-create.json
curl -fsS -X POST "$API/api/v1/research/design-saves" \
  -H "X-Modarchitect-Api-Key: $KEY" -H "Idempotency-Key: $REQUEST_ID" -H 'Content-Type: application/json' \
  --data-binary @save-create.json -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
  "revision": 1,
  "configuration_sha256": "83a41a9d263bb3330a478c3f30932e3dfad3d3c02527e816e345c8e6e8977e18"
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| design_id | 本系统已保存方案ID；存入业务关联和前端路由，接口14用它查询。 |
| revision | 准确保存修订；更新时作为expected_revision，不自行加一提交。 |
| configuration_sha256 | 持久化配置摘要；业务库保留回执原值，与configuration内部sha256不同。 |

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
| Idempotency-Key（请求头） | 每次新的保存生成新UUID，该次重试保留原值。 |
| provider_name / company_id | 业务后端注入原企业范围。 |

请求体（字段节选；实际提交完整文件）：

```json
{
  "provider_name": "modarchitect_design_loop",
  "company_id": 1,
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
  },
  "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
  "expected_revision": 1
}
```

curl：

```sh
DESIGN_ID=$(jq -r '.design_id' saved.json)
REVISION=$(jq '.revision' saved.json)
REQUEST_ID=$(uuidgen)
jq --arg provider "$PROVIDER" --argjson company "$COMPANY_ID" --arg id "$DESIGN_ID" --argjson revision "$REVISION" '{provider_name:$provider,company_id:$company,configuration:.,design_id:$id,expected_revision:$revision}' configuration.json > save-update.json
curl -fsS -X POST "$API/api/v1/research/design-saves" \
  -H "X-Modarchitect-Api-Key: $KEY" -H "Idempotency-Key: $REQUEST_ID" -H 'Content-Type: application/json' \
  --data-binary @save-update.json -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
  "revision": 1,
  "configuration_sha256": "83a41a9d263bb3330a478c3f30932e3dfad3d3c02527e816e345c8e6e8977e18"
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| design_id | 原方案ID；保持当前页面和业务关联，不新增一份方案。 |
| revision | 服务端确认修订；替换前端当前修订，内容变化时推进；完全相同配置可能保持不变。 |
| configuration_sha256 | 更新结果摘要；更新业务关联，随后接口14重查。 |

本节响应展示同配置重放的回执，不承诺每次调用都加一。409时保留用户修改，重读最新方案并提示处理冲突，不自动改expected_revision覆盖。

## 13. 查询企业已保存方案列表

**GET /api/v1/research/design-drafts**

用途：显示本企业已经保存的可编辑研究方案，与接口01的公共模板目录分开。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
curl -fsS "$API/api/v1/research/design-drafts?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
```

响应：HTTP200（字段节选；列表仅展示一项）。

```json
{
  "items": [
    {
      "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
      "revision": 1,
      "configuration_sha256": "83a41a9d263bb3330a478c3f30932e3dfad3d3c02527e816e345c8e6e8977e18",
      "updated_at": "2026-11-16T21:38:09.945171+08:00",
      "configuration": {
        "format": "research_plan_draft",
        "definition": {
          "name": "多因素作物生长指标预测"
        },
        "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
      }
    }
  ]
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| items[].design_id | 方案唯一ID；作为列表唯一键和打开方案参数。 |
| items[].configuration.definition.name / question | 保存后的名称、问题；显示标题、摘要；没有单独title字段。 |
| items[].revision / updated_at | 修订、更新时间；显示版本和最近保存时间，日期按时区格式化。 |
| items[].configuration | 完整配置；可用于预览，正式编辑前用接口14重查。 |
| items[].configuration_sha256 | 持久化摘要；核对一致性，卡片不必显示长摘要。 |

当前最多返回最近100项，按更新时间倒序；无total、分页或搜索参数。items=[]显示尚未保存方案，不是接口失败。

## 14. 查询已保存方案并还原流程图

**GET /api/v1/research/design-drafts/{design_id}**

用途：从本系统数据库重新读取保存结果，用查询结果展示流程图并继续编辑。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| design_id（路径） | 必填UUID，正式保存回执的design_id，不是模板id或模型id。 |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
DESIGN_ID=$(jq -r '.design_id' receipt.json)
curl -fsS "$API/api/v1/research/design-drafts/$DESIGN_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -o saved.json
```

响应：HTTP200（字段节选）。

```json
{
  "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
  "revision": 1,
  "configuration_sha256": "83a41a9d263bb3330a478c3f30932e3dfad3d3c02527e816e345c8e6e8977e18",
  "updated_at": "2026-11-16T21:38:09.945171+08:00",
  "configuration": {
    "format": "research_plan_draft",
    "definition": {
      "name": "多因素作物生长指标预测"
    },
    "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
  }
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| configuration.definition | 已持久化正文；完整恢复编辑状态，不只展示保存前的浏览器缓存。 |
| configuration.definition.composition | 节点、连线、成果；按本文流程图规则渲染。 |
| configuration.definition.variables / collection_requirements | 指标及来源；恢复名称、单位、提供方式及准确绑定。 |
| design_id / revision | 本次查询的ID与修订；供后续修改提交使用。 |
| configuration_sha256 / updated_at | 持久化摘要、更新时间；核对保存结果并显示更新时间。 |

404表示当前企业不可见或方案不存在，不能切换匿名空间读取。配置接口不返回当次真实观测或运行结果。

## 15. 按保存请求ID查询成功回执

**GET /api/v1/research/design-saves/{request_id}**

用途：保存响应超时、业务落库失败或重启后确认原保存结果，避免重复创建。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| request_id（路径） | 必填UUID，原Idempotency-Key，不是design_id。 |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
curl -fsS "$API/api/v1/research/design-saves/$REQUEST_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -o receipt.json
```

响应：HTTP200。

```json
{
  "design_id": "01a1e494-59a9-7dab-a3b0-f29e8f1ec366",
  "revision": 1,
  "configuration_sha256": "83a41a9d263bb3330a478c3f30932e3dfad3d3c02527e816e345c8e6e8977e18"
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| design_id / revision / configuration_sha256 | 原保存的准确结果；用于恢复业务关联；方案后来又修改时，旧回执不代表最新修订。 |

200继续登记业务关联；404按原ID、原正文重发；超时保留pending。相同ID、不同正文返回409，不能自动换ID重复创建。

## 16. 查询本企业已训练并保存的模型

**GET /api/v1/research/models**

用途：显示训练成果模型列表。基础算法选择使用接口05；保存研究方案本身不会产生训练模型。

请求：

| 字段 | 要求及含义 |
| --- | --- |
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
curl -fsS "$API/api/v1/research/models?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY" -o models.json
```

响应：HTTP200。

```json
{
  "items": []
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| items[].model_id | 训练模型ID；模型列表唯一键、接口17的查询参数。 |
| items[].name | 保存的模型名称；显示模型标题。 |
| items[].run_id | 模型来源训练运行；关联训练来源，不能当作研究方案ID。 |
| items[].model_sha256 | 准确模型内容摘要；保留模型身份，不当作设计修订。 |
| items[].created_at | 模型保存时间；显示保存时间，不能当作数据更新截止日期。 |

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
| provider_name / company_id（查询） | 必填，来源代码/正整数；业务登录企业范围。 |

请求体：无。

curl：

```sh
MODEL_ID=$(jq -r '.items[0].model_id' models.json)
# 仅当列表有记录时调用；不要把null作为模型ID。
curl -fsS "$API/api/v1/research/models/$MODEL_ID?$SCOPE" \
  -H "X-Modarchitect-Api-Key: $KEY"
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

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| model_id / name / created_at | 模型身份、名称、保存时间；显示详情基本信息。 |
| run_id / model_sha256 | 训练来源、内容摘要；保留准确训练模型身份。 |
| model_json | 版本化训练状态；算法间结构不同，完整保留；不能用作统一设计参数表或普通研究定义。 |

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
  "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
}
```

curl：

```sh
curl -fsS -X POST "$API/api/v1/research/configurations/import" \
  -H "X-Modarchitect-Api-Key: $KEY" -H 'Content-Type: application/json' \
  --data-binary @configuration.json
```

响应：HTTP200（字段节选）。

```json
{
  "format": "research_plan_draft",
  "definition": {
    "name": "多因素作物生长指标预测"
  },
  "sha256": "70cd9bcfb3829d022533851686f1695bcab2e4993a09706f38f8618e5c3a5ead"
}
```

响应字段：

| 字段 | 含义及处理 |
| --- | --- |
| format / definition / sha256 | 校验后的完整配置；导入后恢复definition，正式保存仍调用接口10及11/12。 |

research_plan_draft核验文件身份；历史research_plan还会走对应完整合同适配，不保证未来待实现模型能按旧格式导入。导出直接下载完整configuration，不需要另一个导出API。

## 业务数据库保存字段与顺序

1. 生成本次保存UUID，先持久化原请求正文、请求ID及pending状态。
2. 接口10返回HTTP200且valid=true后调用接口11/12；正式保存会重复执行相同设计规则。
3. 收到成功回执，在业务库自己的事务中保存下面三个引用值及原业务关联，标记saved，清空待发送正文。
4. 业务事务提交后向前端返回成功；前端接口14重查并展示流程图。

| 业务库字段 | 类型 | 来源或规则 |
| --- | --- | --- |
| provider_name / company_id | 来源代码/正整数 | 复用业务企业字段，所有读写范围保持一致 |
| design_id | UUID，可空 | 本系统回执design_id |
| design_revision | integer，可空 | 回执revision |
| design_configuration_sha256 | char(64)，可空 | 回执configuration_sha256，不是configuration.sha256 |
| design_save_request_id | UUID | 发送前持久化，准确重试不变 |
| design_save_state | pending/saved/failed | 同一业务记录最多一个pending |
| design_save_payload | JSON，可空 | 原请求用于恢复，业务事务确认后清空 |

复用已有业务记录、企业、用户、项目/地块关联，不向API添加未声明业务字段。回写同时匹配业务记录ID和当前请求ID，旧回执不能覆盖新保存。本系统保存完整可编辑配置，业务库保存归属和引用；两库不是同一个事务。

## 失败与恢复

| 结果 | 业务后端处理 |
| --- | --- |
| 检查200但valid=false | 返回issues，停止正式保存 |
| 401 | Key缺失/错误，检查服务配置，不改用个人或匿名空间 |
| 403 | 无资源权限，按业务授权处理 |
| 404 | 资源不存在或本企业不可见；查回执404时按原ID、原正文重发 |
| 409 | 修订或幂等正文冲突，重读方案由用户处理，不自动覆盖 |
| 413 | 超出大小预算，提示减少配置规模 |
| 422 | 显示detail和issues，修正后作为新的保存请求；不要把它当成功 |
| 503/超时 | 可能缺服务配置或依赖异常；保存结果不明时保留pending，先查接口15再决定准确重放 |
| 本系统成功、业务库失败 | 显示方案已保存、业务登记待完成；按原回执恢复业务事务，不重复创建方案 |

错误JSON通常含detail，合同错误附issues；请求解析错误的issues可能用rule而非type，path可能以body/query/path开头。转接不能丢失这些字段。

本轮到保存→查询→流程图为止，不实际验证业务库。数据库0011，无迁移；研究写入请求上限8,000,000字节，草稿正文另有1,000,000字节预算。
