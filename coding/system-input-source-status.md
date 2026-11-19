# 系统输入来源复核

本文件保留改造前的审计基线。最新第三方采集已完成，当前通道为4项人工录入和18项准确来源快照；其余来源缺口仍保留。以249 最新验收为当前状态，下面的“未接通”是当时的复核事实。

2026-11-12。复核当前项目合同、来源校验、运行输入、公开研究方案及 249 在线接口。未修改组件定义、来源策略、业务代码或数据库，未访问旧库，也未宣称完成外部提供方联验。

## 结论

**来源尚未全部定义完整。** 当前目录有 63 项输入，33 项具备准确目录绑定，30 项仍缺正式绑定。已实现的运行通道只有 4 项标准人工录入；实际研究中的数据是否已齐备，目录统一保留为未知，需要运行上下文核验。

| 类别 | 指标数 | 有准确绑定 | 来源定义现状 | 当前通道 |
| --- | ---: | ---: | --- | --- |
| 人工采集 | 15 | 15 | 指标、单位、观察尺度和人工录入协议已登记；测量描述已保留，采样记录及证据校验仍需完善 | 4 项支持标准录入，11 项缺点位/单株/样方适配 |
| 第三方平台 | 18 | 18 | 7 项天气指定 Open-Meteo；11 项土壤指定规范化 SoilGrids。准确字段、版本、方法、性质及允许属性已约定 | 本项目均未接通受权自动取数 |
| 平台分析记录 | 21 | 0 | 只明确来源方向为平台长势分析，缺实际报告/影像绑定、字段映射、方法及授权范围；20 项报告统计的科学支撑尚未落为可采用合同 | 不可采用 |
| 物联网平台 | 9 | 0 | 有仪器指标本体，缺具体平台、供应商、设备、点位、字段映射、校准方法与同步合同 | 不可采用 |

33 项“有绑定”表示能生成并校验准确目录引用，尚不能作为“33 项采集到运行闭环均完成”的验收结论。已有 13 个指定资料研究运行的是批准的示例资料，也不能据此判断实际地块的取数已接通。

## 已核实内容

1. 249 的 `GET /api/v1/model-center/research-inputs` 返回与本地安装目录完全一致，来源制品摘要为 `e4affbc231caafb4a89c60e61fa950d573c62e2b90cec93db990c55ce03d97a0`。
2. 逐项调用来源配置接口：33 项准确配置成功并通过固定绑定验证；其余 30 项返回拒绝，未产生方案或运行。第三方来源的变量引用、来源策略与来源定义版本、合同摘要均一致。
3. 63 项的 `data_available` 均为 `null`。代码说明该接口不查询项目实际数据；不能用“目录已登记”显示当次资料齐备。
4. 四个已实现录入通道为叶面积指数、地上生物量、块茎干物质和冠层覆盖度。此通道校验列、单位、范围、完整对象日期并保存主体及内容摘要，未完成业务系统自动同步。
5. 第三方输入由平台固定，土壤必须显式选择登记土层与 `mean`。来源、单位、方法或取数属性被改写会被拒绝，不能用上传数值代替第三方取数。
6. 人工方法中的 `evidence_required=True` 是声明。当前 `Observation` 只有对象、业务日期和数值，尚未提供来源记录修订、测量人员、仪器及证据资源的完整运行绑定和验收。当前记录能追溯到上传主体与内容，田间测量来源还需采集证据支撑。

本次重跑 `tests/test_system_inputs.py`，**17 项通过**。测试覆盖固定来源、33 项准确绑定往返、土壤属性、单位/名称/方法/来源篡改、估计量作目标拒绝、缺通道拒绝及内容来源摘要。没有进行外部提供方、设备或真实田间测量联验。

## 当前联合预测方案的五项输入

该方案五项均没有 `catalog_binding`，使用 `synthetic_fixture` 协议，状态明确限定为合成演示。下面是需要建立正式研究来源时的对应问题，而不是当前已经存在的取数能力。

| 输入 | 当前状态 | 正式来源需解决的问题 |
| --- | --- | --- |
| 定植后天数 | 合成演示变量，未登记正式目录输入 | 建议由可信种植管理记录的定植日期与业务日期计算，明确日期版本和换算规则 |
| 株高 | 合成演示中的地块日值 | 目录已有点位株高和单株株高；须保留相应观察尺度、点位/样株和测量方法，不能直接改成地块变量 |
| NDVI | 合成演示中的 NDVI 值 | 须明确采用报告覆盖区统计还是点位影像取值，绑定实际影像/报告、日期、质量、空间范围及权限 |
| 土壤体积含水率 | 合成演示值 | 须指定土层和测量来源；当前根区传感器仍未绑定。项目合同中的 SoilGrids 土壤水分参数标记为静态网格估计，不能充当当日实测 |
| 气温 | 合成演示值 | 可按真实研究需要采用既定 Open-Meteo 日气温估计，或将来登记的实测来源；当前前者自动通道未接通，后者还需设备/站点来源合同 |

因此，现有方案可以验证流程和数学计算；用于真实地块研究前仍需完成来源采用、科学尺度适配和真实记录接入。改指标名称、修改单位或沿用示例上传，均不能代替这些步骤。

## 补齐顺序与完成标准

优先围绕真实的株高—NDVI—土壤水分—气温研究闭环补齐来源，不用先为目录所有候选制造占位绑定：

1. 固定每项指标的真实来源、版本、字段、观察尺度、科学单位、时间口径、方法及允许属性。
2. 人工采集补测量规范和记录证据；平台分析补报告/影像与范围日期；物联网补平台、设备、点位、土层与校准；第三方补受权标准记录取数和准确转换。
3. 研究 API 只引用必要的准确来源及记录资源，复用统一采集资源，不将全部设备配置或展示字段塞入研究请求。
4. 用真实授权对象验收取数、单位/时空对齐、质量与修订、缺数拒绝、封存复跑及来源随模型保留，才能标为可运行来源。

相关实现：`modarchitect/system_inputs.py`、`modarchitect/runtime/contracts.py`、`modarchitect/runtime/preparation.py`、`modarchitect/study_templates.py`。规则依据：[固定来源设计](system-input-components.md)、[平台规则](../docs/platform-rules.md)。机器证据：本次逐项复核。下附与在线目录逐项对应的清单。

## 63 项逐项清单

“可录入”仅指当前标准人工通道；“未接通”不会被当作已取得数据。

### 人工采集（15 项）

| 指标 | 代码 | 单位 / 观察尺度 | 来源或字段 | 绑定 / 当前通道 |
| --- | --- | --- | --- | --- |
| 地上生物量 | `agb_kg_ha` | kg_ha / 地块种植季 | 标准人工记录 | 已登记；可录入 |
| 冠层覆盖度 | `canopy_cover` | fraction / 地块种植季 | 标准人工记录 | 已登记；可录入 |
| 株高 | `height_cm` | cm / 点位 | 标准人工记录 | 已登记；未接通 |
| 叶面积指数 | `lai` | m2_m2 / 地块种植季 | 标准人工记录 | 已登记；可录入 |
| 块茎干物质 | `tuber_dm_kg_ha` | kg_ha / 地块种植季 | 标准人工记录 | 已登记；可录入 |
| 单株株高 | `plant_height` | cm / 单株 | 标准人工记录 | 已登记；未接通 |
| 单株茎粗 | `stem_diameter` | mm / 单株 | 标准人工记录 | 已登记；未接通 |
| 单株节间长 | `internode_length` | cm / 单株 | 标准人工记录 | 已登记；未接通 |
| 叶片长度 | `leaf_length` | cm / 单株 | 标准人工记录 | 已登记；未接通 |
| 叶片宽度 | `leaf_width` | cm / 单株 | 标准人工记录 | 已登记；未接通 |
| 单株总叶面积 | `plant_leaf_area` | cm2_plant / 单株 | 标准人工记录 | 已登记；未接通 |
| 叶鲜重 | `leaf_fresh_mass` | g_plant / 单株 | 标准人工记录 | 已登记；未接通 |
| 茎鲜重 | `stem_fresh_mass` | g_plant / 单株 | 标准人工记录 | 已登记；未接通 |
| 茎叶总鲜重实测 | `stem_leaf_fresh_mass` | g_plant / 单株 | 标准人工记录 | 已登记；未接通 |
| 商品果产量 | `marketable_fruit_yield` | kg_m2 / 样方 | 标准人工记录 | 已登记；未接通 |

### 第三方平台（18 项）

| 指标 | 代码 | 单位 / 观察尺度 | 来源或字段 | 绑定 / 当前通道 |
| --- | --- | --- | --- | --- |
| 日最低气温 | `temperature_minimum_daily` | celsius / 地块种植季 | Open-Meteo 天气 / TMIN | 已登记；未接通 |
| 日最高气温 | `temperature_maximum_daily` | celsius / 地块种植季 | Open-Meteo 天气 / TMAX | 已登记；未接通 |
| 日平均气温 | `temperature_mean_daily` | celsius / 地块种植季 | Open-Meteo 天气 / TEMP | 已登记；未接通 |
| 日降水量 | `precipitation_daily` | mm / 地块种植季 | Open-Meteo 天气 / RAIN | 已登记；未接通 |
| 日太阳辐射 | `solar_radiation_daily` | kj_m2 / 地块种植季 | Open-Meteo 天气 / IRRAD | 已登记；未接通 |
| 2米日风速 | `wind_speed_2m_daily` | m_s / 地块种植季 | Open-Meteo 天气 / WIND | 已登记；未接通 |
| 日露点换算水汽压 | `vapour_pressure_daily` | kpa / 地块种植季 | Open-Meteo 天气 / VAP | 已登记；未接通 |
| 土壤容重 | `soil_bdod` | kg_dm3 / 地块种植季 | SoilGrids 单位与网格参考适配 / bdod | 已登记；未接通 |
| 土壤阳离子交换量 | `soil_cec` | cmol_kg / 地块种植季 | SoilGrids 单位与网格参考适配 / cec | 已登记；未接通 |
| 土壤粗碎片体积分数 | `soil_cfvo` | percent / 地块种植季 | SoilGrids 单位与网格参考适配 / cfvo | 已登记；未接通 |
| 土壤黏粒含量 | `soil_clay` | percent / 地块种植季 | SoilGrids 单位与网格参考适配 / clay | 已登记；未接通 |
| 土壤pH（水提） | `soil_phh2o` | dimensionless / 地块种植季 | SoilGrids 单位与网格参考适配 / phh2o | 已登记；未接通 |
| 土壤砂粒含量 | `soil_sand` | percent / 地块种植季 | SoilGrids 单位与网格参考适配 / sand | 已登记；未接通 |
| 土壤粉粒含量 | `soil_silt` | percent / 地块种植季 | SoilGrids 单位与网格参考适配 / silt | 已登记；未接通 |
| 土壤有机碳 | `soil_soc` | g_kg / 地块种植季 | SoilGrids 单位与网格参考适配 / soc | 已登记；未接通 |
| 土壤10kPa持水量 | `soil_wv0010` | fraction / 地块种植季 | SoilGrids 单位与网格参考适配 / wv0010 | 已登记；未接通 |
| 土壤33kPa持水量 | `soil_wv0033` | fraction / 地块种植季 | SoilGrids 单位与网格参考适配 / wv0033 | 已登记；未接通 |
| 土壤1500kPa持水量 | `soil_wv1500` | fraction / 地块种植季 | SoilGrids 单位与网格参考适配 / wv1500 | 已登记；未接通 |

### 平台分析记录（21 项）

| 指标 | 代码 | 单位 / 观察尺度 | 来源或字段 | 绑定 / 当前通道 |
| --- | --- | --- | --- | --- |
| 报告覆盖区 NDVI 均值 | `growth_report_ndvi_mean` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDVI 标准差 | `growth_report_ndvi_stddev` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDVI 最小值 | `growth_report_ndvi_min` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDVI 最大值 | `growth_report_ndvi_max` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 GNDVI 均值 | `growth_report_gndvi_mean` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 GNDVI 标准差 | `growth_report_gndvi_stddev` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 GNDVI 最小值 | `growth_report_gndvi_min` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 GNDVI 最大值 | `growth_report_gndvi_max` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDRE 均值 | `growth_report_ndre_mean` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDRE 标准差 | `growth_report_ndre_stddev` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDRE 最小值 | `growth_report_ndre_min` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 NDRE 最大值 | `growth_report_ndre_max` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 LCI 均值 | `growth_report_lci_mean` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 LCI 标准差 | `growth_report_lci_stddev` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 LCI 最小值 | `growth_report_lci_min` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 LCI 最大值 | `growth_report_lci_max` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 OSAVI 均值 | `growth_report_osavi_mean` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 OSAVI 标准差 | `growth_report_osavi_stddev` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 OSAVI 最小值 | `growth_report_osavi_min` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 报告覆盖区 OSAVI 最大值 | `growth_report_osavi_max` | dimensionless / 覆盖区支撑待明确 | 平台长势分析记录 | 缺正式绑定；未接通 |
| 采样点局部 NDVI | `growth_point_ndvi` | dimensionless / 点位 | 平台长势分析记录 | 缺正式绑定；未接通 |

### 物联网平台（9 项）

| 指标 | 代码 | 单位 / 观察尺度 | 来源或字段 | 绑定 / 当前通道 |
| --- | --- | --- | --- | --- |
| 棚内空气温度 | `greenhouse_air_temperature` | celsius / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 棚内相对湿度 | `greenhouse_relative_humidity` | fraction / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 棚内光合有效辐射 | `greenhouse_par` | umol_m2_s / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 棚内日净辐射 | `greenhouse_net_radiation_daily` | mj_m2_d / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 棚内日地表热通量 | `greenhouse_ground_heat_flux_daily` | mj_m2_d / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 温室根区含水率 | `greenhouse_root_zone_water_content` | fraction / 土层 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 小时进液质量 | `greenhouse_inflow_mass` | g_h / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 小时排液质量 | `greenhouse_drainage_mass` | g_h / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
| 小时称重平台质量变化 | `greenhouse_platform_mass_change` | g_h / 点位 | 待登记物联网来源 | 缺正式绑定；未接通 |
