# 输入目录二级分类盘点

2026-11-13。最初为只读调查，后续落实情况见实施补记。盘点阶段未修改来源资格，未访问数据库、实际账户或凭据。先核原 63 目录/133 本体基线（摘要 `e4affbc231caafb4a89c60e61fa950d573c62e2b90cec93db990c55ce03d97a0`），并补读新增 2 项 Sentinel 后的本地目录。补读制品 `modarchitect/contracts/system-inputs-v1.json` 摘要 `5d7a15c44c6f1a252293a69687cc373903c36bf814f3ab5a6d7a1794162959a3`，现为 65 项目录/135 本体；基线与增量分别记数。分类验收与提供方、海豚实际联验分别留证。

## 结论

实施补记（2026-11-13）：盘点结果已落实到 `contracts/input-taxonomy-v1.json`，API 仍复用原条目，只追加 `subcategory` 与一级类别的 `children`（code/name/count）。前端采用相同分类提供二级筛选与名称搜索。科学定义、来源绑定、执行资格和请求未增加分类字段。当前65项完整归属：人工15、第三方20、平台分析21、物联网9；10个有指标的二级组，另保留三维表型空分类并明确暂无已登记指标。下文原始调查与建议作为推导依据，不代表额外完成了取数联验。

验收：`tests/test_system_inputs.py` 经公开目录核对65项、准确归属和计数；重命名分类后已保存配置和历史解析保持完全一致；遗漏或错误归属会拒绝发布目录。`tests/test_modeling.mjs` 验证真实二级筛选、搜索、空分类提示，以及多表研究新增指标必须指定数据组。分类变更不会把未接通来源变为可执行。

四类来源可继续保留，但需要按研究人员理解增加二级分类。原 63 项可以完整落到 9 个有指标的二级组；新增卫星 2 项后是 65 项、10 组。三维表型及其他已有变量候选需要单列状态，不能把分类树展开等同于新增可用输入。

分类只是查找入口。变量是什么、从哪里来、怎样测量或计算、是否允许作标签、是否已接通，仍由准确科学定义、来源/方法及实际取数证据决定。原始 `greenhouse_phenotype` 表示表型研究主题，不能被直接翻译成“三维表型服务”。

## 数量与迁入边界

| 集合 | 数量 | 实际含义 |
| --- | ---: | --- |
| 原始研究变量本体基线 | 133 | 变量制品已在新项目包内，不等于全部已采用为外部输入 |
| 其中温室 profiles | 83 | 是上述 133 的子集，不再相加；含单位支撑和原始来源属性 |
| 原系统输入目录基线 | 63 | 5 采样标准 + 10 人工 profiles + 9 仪器 profiles + 18 指定第三方 + 21 长势候选 |
| 原始本体基线中已进入目录 | 58 | 当前 63 减去另行登记的 5 项采样标准 |
| 原始本体中未进入输入目录 | 75 | 64 未采用 profiles + 10 NDVI 五档业务面积/占比 + 1 历史 NASA 小时气温变量 |

并行改造新增 `sentinel2_red_reflectance`、`sentinel2_nir_reflectance` 两项后，本体为 135、目录为 65、指定第三方为 20，原 profiles 83 与未采用本体 75 均未变化。新增两项的来源字段分别 B04/B08、单位 dimensionless、空间支撑为 10m 请求网格参考，不能叫地块均值。

83 profiles 按原始 `source` 分别为人工 `manual` 10、仪器 `instrument` 9、影像 `image` 10、派生 `derived` 51、业务上下文 `context` 3。当前只把前两类的 19 项投影进外部输入目录。其余 64 项不是“源码丢失”，而是**已有本体、缺采用为准确外部来源的合同**；派生量本来应由计算节点生成，不能为凑全输入目录而改成外部实测。

原始 133 的主题组：长势报告 30、长势点位 1、天气 8、土壤 11、温室表型 15、温室环境 10、温室影像 45、温室水分 11、种植上下文 2。这些 `group` 是研究主题，不是四类来源的替代品。

依据：[当前目录投影](E:/python/modarchitect/modarchitect/system_inputs.py:117)、[原始制品](E:/python/modarchitect/modarchitect/contracts/system-inputs-v1.json)、[旧 profiles 合同](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/mlgrowth_contracts/research/source_catalog.py:55)。

## 原 63 项与新增卫星的建议二级分类

下表是可依据现有指标立即整理的分组，**未改变每项原有来源绑定和执行状态**。英文短码仅为建议分类标识，不宣称已经增加 API 字段或成为科学合同。

| 一级来源 | 二级分类 | 建议短码 | 现有数量 | 实际覆盖 |
| --- | --- | --- | ---: | --- |
| 人工采集 | 植株形态 | plant_morphology | 6 | 点位株高、单株株高、茎粗、节间长、叶长、叶宽 |
| 人工采集 | 叶面积与覆盖 | leaf_area_cover | 3 | 单株总叶面积、地块 LAI、冠层覆盖度 |
| 人工采集 | 生物量与产量 | biomass_yield | 6 | 地上生物量、块茎干物质、叶/茎/茎叶鲜重、商品果产量 |
| 第三方平台 | 气象 | weather | 7 | 最低/最高/平均气温、降水、太阳辐射、2m 风速、露点换算水汽压 |
| 第三方平台 | 土壤 | soil | 11 | 容重、CEC、粗碎片、砂粉黏、有机碳、pH、三个吸力点持水量 |
| 第三方平台 | 卫星 | satellite | 2（本次新增） | B04 红光、B08 近红外反射率；未借长势候选充数；真实接通状态另验 |
| 平台分析记录 | 长势分析 | growth_monitoring | 21 | NDVI/GNDVI/NDRE/LCI/OSAVI 的报告覆盖区均值、标准差、最小、最大共 20 项，以及点位局部 NDVI |
| 物联网平台 | 棚内环境 | greenhouse_environment | 5 | 气温、相对湿度、PAR、日净辐射、日地表热通量 |
| 物联网平台 | 根区水分 | root_zone_water | 1 | 指定土层的根区体积含水率 |
| 物联网平台 | 水肥与称重 | water_fertigation_weighing | 3 | 小时进液、排液、平台质量变化 |

原 63 项有指标的组为 9 个，补读的本次新增卫星纳入后共 10 个。平台分析的报告覆盖区与点位值可以在同一长势入口下查找，但单项必须继续显示自身空间支撑，不能把二级分组当成科学单位。

人工 15 项中，当前只有 4 项适配地块种植季数值表；其余点位、单株、样方仍需适配。第三方、长势与物联网是否已接通，以本次实际来源实现和联验为准；本分类不重新签发可用资格。

## 未采用定义的完整候选整理

以下建议将已有定义按研究任务整理，方便后续逐类推进。分类可先进入内部盘点；只有取得准确来源、方法与有效性证据的条目才进入普通研究的可选入口。

| 研究人员看到的二级方向 | 现有定义证据 | 数量与原始性质 | 接入决定 |
| --- | --- | --- | --- |
| 平台分析 → 植株影像表型 | `stem_leaf_fresh_mass_image`、`plant_height_image`、`canopy_cover_image`、`plant_projected_area` | 4 项 image | 冻结相机/比例尺/ROI/掩膜及估算模型，再绑定准确服务结果；不是三维来源 |
| 平台分析 → 光谱与纹理分析 | 5 波段冠层反射率；NDVI/NDRE/GNDVI、8 项 GLCM、其他可见光/红边指数及纹理 | 5 项 image + 36 项 derived | 原始影像与算法输出分开；51 项派生中的这 36 项优先作为计算节点成果，复用外部发布结果时才另作来源采用 |
| 平台分析 → 冠层热成像 | `greenhouse_canopy_temperature`、`canopy_thermal_*`、冠气温差 | 1 项 image + 5 项 derived | 辐射校准、发射率、掩膜、环境参考时窗与差温单位均需保留 |
| 计算成果 → 植株形态派生 | `stem_leaf_fresh_mass_allometric`、`plant_lai` | 2 项 derived | 前者冻结异速方程/拟合样本，后者固定样方面积分母；不改成人工测量或三维服务输出 |
| 计算成果 → 水分与灌溉分析 | 基质蒸发、作物小时蒸腾、ET₀、ETc、蒸散偏差、灌溉水生产率 | 6 项 derived | 输入质量、称重守恒、参考与作物蒸散方法、面积/时间口径分别验收 |
| 计算成果 → 环境派生分析 | VPD、根区水分衰减速率 | 2 项 derived | 同窗温湿度、土层与变化时段明确，不能当成新增传感器实测 |
| 种植管理上下文 | `irrigation_applied_depth`、`days_after_transplanting`、`greenhouse_cultivation_area` | 3 项 context | 先确认可信管理记录或主数据；来源确认后再归入相应四类来源，不因用户可填写就擅定为人工实测 |
| 第三方平台 → 气象（历史候选） | `temperature_hourly_sample_mean_daily` | 1 项变量；历史 NASA 小时日界适配 | 当前平台策略未采用，保持历史解释；不可在 Open-Meteo 缺测时自动切换 |
| 平台分析 → 三维表型 | 旧需求与设计中存在独立服务方向 | 没有找到准确变量来源或运行入口 | 可以保留明确待接入方向；不能标可选或复用影像株高伪造合同 |
| 平台分析 → 病虫害识别 | 旧 Figma 差距清单要求真实外部影像服务 | 133 本体中无相应识别结果变量 | 是明确需求缺口；气象病害风险和作物识别不替代病虫害影像诊断 |

“计算成果”行是能力归属说明，不新增第五种外部来源。若把一个已经发布的计算成果作为下一次研究的外部资料，其来源可以采用“平台分析记录”，但必须绑定准确运行/模型/成果修订与摘要，不能只凭名称自动采用。研究内部串联的派生输出仍走有类型的计算端口。

另外 10 项 NDVI 五档面积/占比是长势业务报告统计，应保留业务视图语义。没有研究面积口径、阈值、掩膜、范围及算法版本时，不通过“分类整理”把它们重新加入数学建模输入。

### 尚未采用的影像字段、单位与入口

| 已有字段代码 | 单位 / 科学支撑 | 已有定义与实际接入缺口 |
| --- | --- | --- |
| `stem_leaf_fresh_mass_image` | g_plant / plant | 已有本体要求冻结模型、样株 ROI 与各影像；未找到对应外部服务准确字段映射 |
| `plant_height_image` | cm / plant | 要求相机标定、几何尺度及有效样株掩膜；不等于三维点云株高服务 |
| `canopy_cover_image` | fraction / quadrat | 要求有效视域与植株掩膜；不能改成整地块比例 |
| `plant_projected_area` | cm2_plant / plant | 要求比例尺、影像视角和有效 ROI；二维投影面积不等于三维表面积 |
| `greenhouse_canopy_temperature` | celsius / quadrat | 要求热红外辐射校准、发射率和掩膜 |
| `canopy_{red,green,blue,red_edge,nir}_reflectance` | fraction / quadrat | 5 个准确字段；要求定标、波段及有效像元；已有目录上限 1，不得直接与允许大于 1 的 Sentinel REFLECTANCE 合同混用 |

上述 10 项的准确定义入口是旧 [greenhouse-v1.json](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/mlgrowth_contracts/research/catalog/greenhouse-v1.json)，新项目已收录相同 profiles。这里“字段代码”是变量本体代码，**不是已经验证存在的提供方 JSON 路径**。两者须在正式采用时建立准确映射。

旧遥感已有实际输入/处理链，可参考 [Sentinel provider](E:/python/mlgrowth/src/pymlgrowth/remote_sensing/adapters/sentinelhub/provider.py)、[指数计算](E:/python/mlgrowth/src/pymlgrowth/remote_sensing/algorithms/indices.py)、[遥感发布器](E:/python/mlgrowth/src/pymlgrowth/timeseries/remote_sensing/publisher.py) 与 [长势盘点](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/coding/research-variable-remote-sensing-inventory-20261110.md)。但已有日产品或图片不证明上述单株/样方来源均已接通。

### 三维表型：目前能确定与不能确定的内容

已核到旧项目需求将三维表型作为独立服务；旧订阅设计明确未由该仓库交付。旧 Figma 差距清单要求核验真实服务，特别写明不能用株高指标冒充三维表型。[原需求审查](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/specs/enterprise-model-services/original-requirements-review.md:32)、[真实服务映射要求](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/coding/enterprise-figma-task-gap-analysis-20261102.md:121)

本次在两份旧项目的 API models/schemas/services/routers、来源词典、研究目录与组件材料中，未找到可确认的三维服务 API、准确输出字段路径、单位合同、服务修订或授权读取实现。`plant_height_image`、`plant_projected_area` 及“株高/LAI/冠层体积”等产品说明，不能补足这些证据。三维叶面积、三维体积等字段名和单位**本次不自行定义**。

因此三维方向可以登记“待核实服务”，但没有指标数、可选来源、运行资格或“已迁移”结论。需要提供方合同、样例真实结果、研究对象/尺度、单位、重建与校准方法、结果修订、授权及读取入口后，才能确定其具体指标清单。该要求不会阻止现有 63 项按二级分类完成整理。

## 分类实施约束与验收建议

1. 当前每个可见条目恰好归入一个一级/二级主分类；过滤前后总数一致。名称、代码、别名可参与检索，来源提供方保持独立，不按 Open-Meteo、ISRIC、相机品牌不断增加科学分类层级。
2. 同名物理量可位于不同来源分类，但保留不同身份，例如人工株高、影像株高、三维服务株高。点位/单株/样方/地块是科学支撑，不混作二级来源分类。
3. 分类调整不改变变量本体、单位、方法、准确来源、版本及制品摘要。分类元数据不成为 Worker 决定取数方式的字符串分支，也不改变历史方案的科学身份解析。
4. 来源已定义、已采用、通道可用、当次数据齐备分别判断；新增分类不能把 `binding=None`、缺提供方或派生变量自动改成可选真实输入。
5. 当前公共 API 只增加前端筛选确实需要的分类信息，复用目录条目，不复制一份“二级指标表”或将分类文案塞进采集/训练请求。具体结构由后续设计确认，本调查不擅定新增协议字段。
6. 分类完整性回归核对原 63 项及本次新增 2 项无遗漏、无重复归属；附录未采用 75 项按原始性质保持状态。新增 Sentinel 条目按新采用目录另验，不改写原 63 基线数字。

## 旧四类来源的权威依据

旧 [source_dictionary.py](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/mlgrowth_contracts/research/source_dictionary.py:26) 明确一级类别只有 `manual/third_party/platform_analysis/iot_platform`；来源代码目前包括人工、Open-Meteo、规范化 SoilGrids、长势分析及历史 NASA/原始 SoilGrids。没有三维、热成像、病虫害的已采用来源代码。旧 [source-view.js](E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/web/model_center/source-view.js) 也是同样四类展示，没有二级分类。

以上分类与覆盖均由现有本体、profiles、指定来源和已记录业务需求推导。候选二级名称是本次建议，执行能力并未因此增加。下列附录逐条列出原 63 项、本次新增 2 项以及未采用的 75 项，便于后续按证据落实。

## 附录 A：当前 65 项逐条分类

原 63 项完整保留，新增 2 项 Sentinel 反射率单列于第三方/卫星。来源定义进入目录不证明真实取数联验已完成。

| 一级 / 二级 | 变量代码 | 名称 | 物理单位 | 科学支撑 | 来源或准确字段 |
| --- | --- | --- | --- | --- | --- |
| 人工采集 / 叶面积与覆盖 | `canopy_cover` | 冠层覆盖度 | `fraction` | field_season | 标准人工记录 |
| 人工采集 / 叶面积与覆盖 | `lai` | 叶面积指数 | `m2_m2` | field_season | 标准人工记录 |
| 人工采集 / 叶面积与覆盖 | `plant_leaf_area` | 单株总叶面积 | `cm2_plant` | plant | 标准人工记录 |
| 人工采集 / 植株形态 | `height_cm` | 株高 | `cm` | point | 标准人工记录 |
| 人工采集 / 植株形态 | `internode_length` | 单株节间长 | `cm` | plant | 标准人工记录 |
| 人工采集 / 植株形态 | `leaf_length` | 叶片长度 | `cm` | plant | 标准人工记录 |
| 人工采集 / 植株形态 | `leaf_width` | 叶片宽度 | `cm` | plant | 标准人工记录 |
| 人工采集 / 植株形态 | `plant_height` | 单株株高 | `cm` | plant | 标准人工记录 |
| 人工采集 / 植株形态 | `stem_diameter` | 单株茎粗 | `mm` | plant | 标准人工记录 |
| 人工采集 / 生物量与产量 | `agb_kg_ha` | 地上生物量 | `kg_ha` | field_season | 标准人工记录 |
| 人工采集 / 生物量与产量 | `leaf_fresh_mass` | 叶鲜重 | `g_plant` | plant | 标准人工记录 |
| 人工采集 / 生物量与产量 | `marketable_fruit_yield` | 商品果产量 | `kg_m2` | quadrat | 标准人工记录 |
| 人工采集 / 生物量与产量 | `stem_fresh_mass` | 茎鲜重 | `g_plant` | plant | 标准人工记录 |
| 人工采集 / 生物量与产量 | `stem_leaf_fresh_mass` | 茎叶总鲜重实测 | `g_plant` | plant | 标准人工记录 |
| 人工采集 / 生物量与产量 | `tuber_dm_kg_ha` | 块茎干物质 | `kg_ha` | field_season | 标准人工记录 |
| 平台分析记录 / 长势分析 | `growth_point_ndvi` | 采样点局部 NDVI | `dimensionless` | point | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_gndvi_max` | 报告覆盖区 GNDVI 最大值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_gndvi_mean` | 报告覆盖区 GNDVI 均值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_gndvi_min` | 报告覆盖区 GNDVI 最小值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_gndvi_stddev` | 报告覆盖区 GNDVI 标准差 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_lci_max` | 报告覆盖区 LCI 最大值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_lci_mean` | 报告覆盖区 LCI 均值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_lci_min` | 报告覆盖区 LCI 最小值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_lci_stddev` | 报告覆盖区 LCI 标准差 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndre_max` | 报告覆盖区 NDRE 最大值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndre_mean` | 报告覆盖区 NDRE 均值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndre_min` | 报告覆盖区 NDRE 最小值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndre_stddev` | 报告覆盖区 NDRE 标准差 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndvi_max` | 报告覆盖区 NDVI 最大值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndvi_mean` | 报告覆盖区 NDVI 均值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndvi_min` | 报告覆盖区 NDVI 最小值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_ndvi_stddev` | 报告覆盖区 NDVI 标准差 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_osavi_max` | 报告覆盖区 OSAVI 最大值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_osavi_mean` | 报告覆盖区 OSAVI 均值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_osavi_min` | 报告覆盖区 OSAVI 最小值 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 平台分析记录 / 长势分析 | `growth_report_osavi_stddev` | 报告覆盖区 OSAVI 标准差 | `dimensionless` | 报告覆盖区待准确绑定 | growth_trend_analysis；尚无正式字段绑定 |
| 物联网平台 / 根区水分 | `greenhouse_root_zone_water_content` | 温室根区含水率 | `fraction` | soil_layer | 未登记具体设备/字段 |
| 物联网平台 / 棚内环境 | `greenhouse_air_temperature` | 棚内空气温度 | `celsius` | point | 未登记具体设备/字段 |
| 物联网平台 / 棚内环境 | `greenhouse_ground_heat_flux_daily` | 棚内日地表热通量 | `mj_m2_d` | point | 未登记具体设备/字段 |
| 物联网平台 / 棚内环境 | `greenhouse_net_radiation_daily` | 棚内日净辐射 | `mj_m2_d` | point | 未登记具体设备/字段 |
| 物联网平台 / 棚内环境 | `greenhouse_par` | 棚内光合有效辐射 | `umol_m2_s` | point | 未登记具体设备/字段 |
| 物联网平台 / 棚内环境 | `greenhouse_relative_humidity` | 棚内相对湿度 | `fraction` | point | 未登记具体设备/字段 |
| 物联网平台 / 水肥与称重 | `greenhouse_drainage_mass` | 小时排液质量 | `g_h` | point | 未登记具体设备/字段 |
| 物联网平台 / 水肥与称重 | `greenhouse_inflow_mass` | 小时进液质量 | `g_h` | point | 未登记具体设备/字段 |
| 物联网平台 / 水肥与称重 | `greenhouse_platform_mass_change` | 小时称重平台质量变化 | `g_h` | point | 未登记具体设备/字段 |
| 第三方平台 / 卫星 | `sentinel2_nir_reflectance` | 哨兵2近红外反射率（B08） | `dimensionless` | field_season | sentinelhub_s2_l2a_reference / B08 |
| 第三方平台 / 卫星 | `sentinel2_red_reflectance` | 哨兵2红光反射率（B04） | `dimensionless` | field_season | sentinelhub_s2_l2a_reference / B04 |
| 第三方平台 / 土壤 | `soil_bdod` | 土壤容重 | `kg_dm3` | field_season | soilgrids_reference_normalization / bdod |
| 第三方平台 / 土壤 | `soil_cec` | 土壤阳离子交换量 | `cmol_kg` | field_season | soilgrids_reference_normalization / cec |
| 第三方平台 / 土壤 | `soil_cfvo` | 土壤粗碎片体积分数 | `percent` | field_season | soilgrids_reference_normalization / cfvo |
| 第三方平台 / 土壤 | `soil_clay` | 土壤黏粒含量 | `percent` | field_season | soilgrids_reference_normalization / clay |
| 第三方平台 / 土壤 | `soil_phh2o` | 土壤pH（水提） | `dimensionless` | field_season | soilgrids_reference_normalization / phh2o |
| 第三方平台 / 土壤 | `soil_sand` | 土壤砂粒含量 | `percent` | field_season | soilgrids_reference_normalization / sand |
| 第三方平台 / 土壤 | `soil_silt` | 土壤粉粒含量 | `percent` | field_season | soilgrids_reference_normalization / silt |
| 第三方平台 / 土壤 | `soil_soc` | 土壤有机碳 | `g_kg` | field_season | soilgrids_reference_normalization / soc |
| 第三方平台 / 土壤 | `soil_wv0010` | 土壤10kPa持水量 | `fraction` | field_season | soilgrids_reference_normalization / wv0010 |
| 第三方平台 / 土壤 | `soil_wv0033` | 土壤33kPa持水量 | `fraction` | field_season | soilgrids_reference_normalization / wv0033 |
| 第三方平台 / 土壤 | `soil_wv1500` | 土壤1500kPa持水量 | `fraction` | field_season | soilgrids_reference_normalization / wv1500 |
| 第三方平台 / 气象 | `precipitation_daily` | 日降水量 | `mm` | field_season | openmeteo_weather / RAIN |
| 第三方平台 / 气象 | `solar_radiation_daily` | 日太阳辐射 | `kj_m2` | field_season | openmeteo_weather / IRRAD |
| 第三方平台 / 气象 | `temperature_maximum_daily` | 日最高气温 | `celsius` | field_season | openmeteo_weather / TMAX |
| 第三方平台 / 气象 | `temperature_mean_daily` | 日平均气温 | `celsius` | field_season | openmeteo_weather / TEMP |
| 第三方平台 / 气象 | `temperature_minimum_daily` | 日最低气温 | `celsius` | field_season | openmeteo_weather / TMIN |
| 第三方平台 / 气象 | `vapour_pressure_daily` | 日露点换算水汽压 | `kpa` | field_season | openmeteo_weather / VAP |
| 第三方平台 / 气象 | `wind_speed_2m_daily` | 2米日风速 | `m_s` | field_season | openmeteo_weather / WIND |

## 附录 B：135 本体中未进入输入目录的 75 项

这是已迁入包的原始定义清单，不给它们增加外部输入资格。`image/derived/context` 为原始 profile 来源属性；具体服务输出字段尚未绑定。

| 候选方向 | 变量代码 | 名称 | 单位 / 支撑 | 原始性质与缺口 |
| --- | --- | --- | --- | --- |
| 冠层热成像 | `greenhouse_canopy_air_temperature_difference` | 冠气温差 | `delta_celsius` / quadrat | derived；需热定标、掩膜及匹配时窗 |
| 冠层热成像 | `greenhouse_canopy_temperature` | 冠层温度 | `celsius` / quadrat | image；需热定标、掩膜及匹配时窗 |
| 环境派生 | `greenhouse_root_zone_water_decline` | 根区含水率衰减速率 | `fraction_h` / soil_layer | derived；需同窗输入与明确计算方法 |
| 环境派生 | `greenhouse_vapor_pressure_deficit` | 棚内水汽压亏缺 | `kpa` / point | derived；需同窗输入与明确计算方法 |
| 种植管理（具体一级来源待核实） | `days_after_transplanting` | 定植后天数 | `day` / plant | context；需可信管理记录/日期/面积来源 |
| 种植管理（具体一级来源待核实） | `greenhouse_cultivation_area` | 栽培支撑面积 | `m2` / quadrat | context；需可信管理记录/日期/面积来源 |
| 光谱与纹理 | `canopy_blue_reflectance` | 冠层蓝光反射率 | `fraction` / quadrat | image；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_con` | 灰度共生矩阵对比度 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_cor` | 灰度共生矩阵相关性 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_dis` | 灰度共生矩阵相异性 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_ene` | 灰度共生矩阵能量 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_ent` | 灰度共生矩阵熵 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_hom` | 灰度共生矩阵同质性 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_mean` | 灰度共生矩阵均值 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_glcm_var` | 灰度共生矩阵方差 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_green_reflectance` | 冠层绿光反射率 | `fraction` / quadrat | image；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_brvi` | 蓝红植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_cire_1` | 红边叶绿素指数一 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_cire_2` | 红边叶绿素指数二 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_cive` | 可见光植被提取指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_evi` | 稿件增强植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_exgi` | 超绿指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_exgr` | 超绿减超红指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gci` | 绿色叶绿素指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gdrvi` | 稿件通用动态范围指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gdvi` | 绿光差值植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gli` | 绿叶指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gndre` | 绿色归一化红边差异指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gndvi` | 影像冠层 GNDVI | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gni` | 绿色归一化指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_gsavi` | 绿光土壤调整植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_mddi` | 改进双差指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_mni` | 改进氮指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_ndi` | 绿红归一化差异指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_ndre` | 影像冠层 NDRE | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_ndvi` | 影像冠层 NDVI | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_ngi` | 稿件归一化绿度指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_regrvi` | 红边绿光植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_rervi` | 红边比值指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_revari` | 红边抗大气植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_savi` | 稿件可见光土壤调整植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_sri` | 可见光简单比值指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_image_vari` | 可见光抗大气植被指数 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_nir_reflectance` | 冠层近红外反射率 | `fraction` / quadrat | image；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_red_edge_reflectance` | 冠层红边反射率 | `fraction` / quadrat | image；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_red_reflectance` | 冠层红光反射率 | `fraction` / quadrat | image；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 光谱与纹理 | `canopy_rgb_texture` | 冠层 RGB 纹理特征 | `dimensionless` / quadrat | derived；需固定波段、算法/窗口/掩膜；派生不改实测 |
| 冠层热成像 | `canopy_thermal_max` | 冠层最高温度 | `celsius` / quadrat | derived；需热定标、掩膜及匹配时窗 |
| 冠层热成像 | `canopy_thermal_mean` | 冠层平均温度 | `celsius` / quadrat | derived；需热定标、掩膜及匹配时窗 |
| 冠层热成像 | `canopy_thermal_min` | 冠层最低温度 | `celsius` / quadrat | derived；需热定标、掩膜及匹配时窗 |
| 冠层热成像 | `canopy_thermal_ncrt` | 归一化冠层相对温度 | `dimensionless` / quadrat | derived；需热定标、掩膜及匹配时窗 |
| 植株影像表型 | `canopy_cover_image` | 影像冠层覆盖度 | `fraction` / quadrat | image；需准确模型/方法、样株及ROI证据 |
| 植株影像表型 | `plant_height_image` | 影像株高估计 | `cm` / plant | image；需准确模型/方法、样株及ROI证据 |
| 植株形态派生 | `plant_lai` | 温室样方面积口径 LAI | `m2_m2` / quadrat | derived；需准确模型/方法、样株及ROI证据 |
| 植株影像表型 | `plant_projected_area` | 单株投影面积 | `cm2_plant` / plant | image；需准确模型/方法、样株及ROI证据 |
| 植株形态派生 | `stem_leaf_fresh_mass_allometric` | 茎叶鲜重异速估计 | `g_plant` / plant | derived；需准确模型/方法、样株及ROI证据 |
| 植株影像表型 | `stem_leaf_fresh_mass_image` | 影像茎叶鲜重估计 | `g_plant` / plant | image；需准确模型/方法、样株及ROI证据 |
| 水分与灌溉派生 | `greenhouse_crop_et_daily_bias` | 作物日蒸散偏差 | `mm_d` / point | derived；需守恒、单位及时间/面积方法 |
| 水分与灌溉派生 | `greenhouse_crop_et_daily_value` | 作物日蒸散 ETc | `mm_d` / point | derived；需守恒、单位及时间/面积方法 |
| 水分与灌溉派生 | `greenhouse_crop_transpiration_hourly` | 小时作物蒸腾估算 | `g_h` / point | derived；需守恒、单位及时间/面积方法 |
| 水分与灌溉派生 | `greenhouse_reference_et_daily_value` | 日参考蒸散 ET₀ | `mm_d` / point | derived；需守恒、单位及时间/面积方法 |
| 水分与灌溉派生 | `greenhouse_substrate_evaporation` | 基质小时蒸发 | `g_h` / point | derived；需守恒、单位及时间/面积方法 |
| 种植管理（具体一级来源待核实） | `irrigation_applied_depth` | 实际灌溉深度 | `mm` / quadrat | context；需可信管理记录/日期/面积来源 |
| 水分与灌溉派生 | `irrigation_water_productivity` | 灌溉水生产率 | `kg_m3` / quadrat | derived；需守恒、单位及时间/面积方法 |
| 长势业务五档统计 | `growth_report_ndvi_average_area` | NDVI 一般档面积 | `mu` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_average_percent` | NDVI 一般档占比 | `percent` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_strong_area` | NDVI 较好档面积 | `mu` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_strong_percent` | NDVI 较好档占比 | `percent` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_very_strong_area` | NDVI 很好档面积 | `mu` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_very_strong_percent` | NDVI 很好档占比 | `percent` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_very_weak_area` | NDVI 很弱档面积 | `mu` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_very_weak_percent` | NDVI 很弱档占比 | `percent` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_weak_area` | NDVI 较弱档面积 | `mu` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 长势业务五档统计 | `growth_report_ndvi_weak_percent` | NDVI 较弱档占比 | `percent` / 见原始来源合同 | 业务面积/占比；当前刻意排除，缺研究范围/阈值方法 |
| 气象历史候选 | `temperature_hourly_sample_mean_daily` | 日内小时气温均值 | `celsius` / 见原始来源合同 | 历史NASA小时日界来源；当前指定策略未采用 |
