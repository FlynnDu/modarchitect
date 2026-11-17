# 第三方数据接入的一手资料核对

2026-11-12。仅调查与设计依据；本文件不代表已经接通研究运行。本次未访问旧库、旧服务、环境凭据或企业数据，未修改应用代码。mlgrowth 仅只读参考。按最新范围收束探测，先确认可替换的接入边界与科学规则，再实施。

## 决策结论

1. 天气保留已经采用的 Open-Meteo 来源；土壤使用 ISRIC SoilGrids **WCS**，不实现或回退到暂停的 REST 服务。
2. 更换提供方、产品、科学尺度或转换算法，不是修改 URL。接入实现应只产出带原始证据、准确版本、单位与时空支撑的标准记录；现有目录绑定、研究准备、运行封存及模型来源规则继续由权威模块维护。
3. SoilGrids WCS 在本次小请求中确实返回了栅格，但发现请求框改变像元尺寸、错误单位元数据、海域零值且缺 NoData 标签等问题。未经门禁和正反例验收，不应将目录直接标成已可用。

## 官方资料与科学约束

### Open-Meteo

- 官方历史服务地址为 `https://archive-api.open-meteo.com/v1/archive`。固定请求 `timezone=Asia/Shanghai`、`temperature_unit=celsius`、`wind_speed_unit=ms`、`precipitation_unit=mm`，逐日与逐小时日期都需要校验。日界、所选模式、返回网格坐标和高程须随资料保存。[历史接口参数](https://open-meteo.com/en/docs/historical-weather-api)
- 历史再分析与预报是不同产品。官方当前列示 IFS、ERA5 与 ERA5-Land 的更新延迟不同，不能沿用旧代码统一“延迟两天”的经验来证明某日完整。近实时缺测不得静默改取预报，历史回测还须保留抓取时点与可用时间，避免把事后资料当成当时已知输入。[产品和更新表](https://open-meteo.com/en/docs/historical-weather-api#data_sources)
- 免费 API 限非商业使用，并有调用限额；商业服务应使用对应订阅接入。来源署名和数据许可须保留，不能把旧项目的“免费无需 Key”说明直接当成本项目任意部署的资格。[官方使用条款](https://open-meteo.com/en/terms)、[官方定价与商业接口](https://open-meteo.com/en/pricing)

本项目 7 项天气变量的转换应与已采用的准确方法一致；下面来自旧项目现行 `openmeteo_weather/conversion.py`，并非宣称本次重新验证了全部 API 数值：

| 项目输出 | 原始资料与转换 | 必须保留的含义 |
| --- | --- | --- |
| `TMIN` / `TMAX` | 对应当地日最低、最高 2m 气温 | 摄氏度 |
| `TEMP` | 完整 24 小时气温均值；旧实现缺小时值时用同日极值均值并标记质量方法 | 小时均值和极值均值不是同一算法；是否允许该回退须由准确方法决定 |
| `RAIN` | `precipitation_sum` | mm，不沿用进入 PCSE 内核后的 cm |
| `IRRAD` | `shortwave_radiation_sum` × 1000 | 原始 MJ/m² → 项目 kJ/m² |
| `WIND` | 10m 小时风速日均 × `4.87 / ln(67.8 * 10 - 5.42)` | 估算的 2m 风速 m/s，不是传感器直接测量 |
| `VAP` | 对 24 小时露点先求均值 `Td`，再算 `0.6108 * exp(17.27 * Td / (Td + 237.3))` | kPa；不能改称“逐小时水汽压的均值” |

风速高度换算和露点到水汽压关系可核对 [FAO-56 气象资料章节](https://www.fao.org/4/X0490E/x0490e07.htm)。温度、湿度和风速必须具有 24 个唯一整点和有限值，缺测处理由已采用方法明确声明；不自动插补、不换站或换提供方。天气是网格估计，不能成为独立实测标签。批次需要保留原始响应摘要、请求日期范围、产品和转换版本，以便复跑。

### SoilGrids：WCS 与单位

官方 access 页当前说明 REST 暂停且没有恢复时间，并推荐 WCS 或文件服务等访问方式。本任务采用 WCS，文件服务仅作为官方原始元数据调查依据，不新增另一条取数回退链。[官方访问说明](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html)

WCS 入口为 `https://maps.isric.org/mapserv/<property>`；`mapserv?map=/map/<property>.map` 也是官方示例形式。采用 `SERVICE=WCS`、`VERSION=2.0.1`，先解释 `DescribeCoverage`，再用准确 `COVERAGEID=<property>_<depth>_mean` 发起 `GetCoverage`，格式 `image/tiff`。固定属性白名单，用户不能提交任意服务地址、Mapfile 或图层。[官方服务目录](https://maps.isric.org/)、[官方 WCS 示例](https://docs.isric.org/globaldata/soilgrids/wcs_from_R.html)

六个允许土层为 `0-5cm`、`5-15cm`、`15-30cm`、`30-60cm`、`60-100cm`、`100-200cm`，统计量目前只采用 `mean`。取数实现不能将不同土层或中位数替代这些合同值。[官方层定义](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)

| 属性 | 原始映射整数 | 到项目单位的除数 | 项目单位 |
| --- | --- | ---: | --- |
| `bdod` | cg/cm³ | 100 | kg/dm³ |
| `cec` | mmol(c)/kg | 10 | cmol(c)/kg |
| `cfvo` | cm³/dm³ | 10 | 体积百分数 |
| `clay` / `sand` / `silt` | g/kg | 10 | 质量百分数 |
| `phh2o` | pH × 10 | 10 | 无量纲 |
| `soc` | dg/kg | 10 | g/kg |
| `wv0010` / `wv0033` / `wv1500` | 10⁻³ cm³/cm³ | 1000 | 体积分数 |

单位来自官方层表和本项目固定来源合同。官方水量表中“除以 10”对应的是**百分数**，本项目采用 fraction，故应除以 1000；旧 CSV 中的 `d_factor` 也不能不加辨别复用。官方服务目录确实列出 `wv0033`，FAQ 层表中的 `wv003` 不能据此改写准确指标身份。[属性与单位](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)、[wv0033 当前服务](https://maps.isric.org/generated/soilgrids/wv0033.html)

土壤为静态网格预测参考；三种水量表示不同吸力条件下的含水参数，不能作为每日真实土壤水分。单个参考点所在像元不能改称地块平均值；重复展开到业务日也不会增加独立土壤样本。[官方产品说明](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)

## 本次实际小请求及发现

以下由项目 `.venv` 的标准库 HTTPS 请求实测，所有请求均为无凭据公开资料的小范围读取。没有实际研究启动或 DolphinScheduler 运行，也没有探测旧服务。

### 原生网格

请求 `https://maps.isric.org/mapserv/bdod?SERVICE=WCS&VERSION=2.0.1&REQUEST=DescribeCoverage&COVERAGEID=bdod_0-5cm_mean` 返回 HTTP 200、XML：

- 原生 CRS：`http://www.opengis.net/def/crs/EPSG/0/152160`，Homolosine；轴 `x y`，单位 m。
- 覆盖外边界：下角 `(-19949000, -6147500)`，上角 `(19861750, 8361000)`。
- WCS 2.0.1 网格 origin 是像元**中心** `(-19948875, 8360875)`，步长 `(250, 0)`、`(0, -250)`。
- 同服务 WCS 1.0.0 描述中的 origin 是外边界 `(-19949000, 8361000)`。不同版本中心/边界差异要通过解析合同解释，不应拼接使用。
- 描述原文 SHA-256：`cf98d3ca1bbdfbdc0fb6a73ce5ff6b0570b402566e174e68eb3773b254e8a8ec`。

坐标转换应使用明确的 `+proj=igh +datum=WGS84` 和 `always_xy=True`，不能依赖“152160”在常见 EPSG 数据库中可直接解析的假设。ISRIC 的历史服务使用该自定义编号，官方说明另给出了 Homolosine 的投影定义。[官方 CRS 说明](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html#how-can-i-use-the-homolosine-projection)

### 请求框会改变像元尺寸

同一 `bdod_0-5cm_mean`、`FORMAT=image/tiff`：

| 两个 SUBSET 参数 | HTTP / 图像 | GeoTIFF 实际空间信息 | 实测原始值 |
| --- | --- | --- | ---: |
| `X(-999999,-999751)`、`Y(1999751,1999999)` | 200 / 1×1 / 1064 字节 | 像元 248m，左上 `(-999999,1999999)` | 149 |
| `X(-1000000,-999750)`、`Y(1999750,2000000)` | 200 / 1×1 / 1064 字节 | 像元 250m，左上 `(-1000000,2000000)` | 149 |

因此“返回 1×1”不足以证明取得原生像元。建议先求参考点对应原生像元的准确边界，再取该 250m 方框；返回后核对 CRS、shape、transform、参考点包含关系、波段和整数值。不做地理坐标输出后的任意重采样，不对附近像元求均值冒充固定参考点方法。

### 单位与缺失值不能仅信响应元数据

- 上述 bdod 的 WCS 2.0.1 `rangeType` 返回通用 `uom='W.m-2.Sr-1'`、空 `nilValues`、通用整数区间；这明显不能用于土壤科学单位转换。单位必须使用登记的准确属性合同，并验证图层身份。
- 同层 WCS 1.0.0 描述给出 `nullValues=-32768`，但不能推导 WCS 2.0.1 一定保留这个标记。
- 海域测试 `SUBSET=X(0,250)`、`SUBSET=Y(-250,0)` 返回 HTTP 200、1×1、250m 栅格、原始值 **0**，没有 GDAL_NODATA 标签。`FORMAT=GEOTIFF_INT16` 也表现相同。只检查成功状态或栅格 mask，会错误地认为“取得了有效土壤值”。

必须在设计中明确覆盖与零值门禁。对于 bdod，零值本身不满足正容重约束，应拒绝。对于可能合法为零的其他属性，不能未经证据将所有零值都删掉，也不能默认为有效。可研究同像元正值 bdod 作为必要覆盖门禁，同时保留目标图层自身的缺失与质量检查；**这仅是待验收建议，尚未证明充分性**。若无法得到可信覆盖证据，应明确拒绝该来源，而不是填值或换到 REST。官方说明土壤预测有空间掩膜，并非覆盖所有位置。[官方覆盖掩膜说明](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html#which-soil-mask-was-used)

## 与 mlgrowth 对照及待实施验收

只读依据：`E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/pymlgrowth/openmeteo_weather/{script.py,conversion.py}`、`isric_soilgrids/script.py`、`research_models/source_normalization.py`。可参考其固定来源、日界验证、换算和来源摘要；不直接复制旧配置加载、资产上传或数据库依赖。

旧土壤脚本会按区域请求并对有效像元求均值，且存在同时传经纬度 CRS 与分辨率数值的路径；该行为不能直接替代当前原生参考点合同。当前接入应在一个独立外部访问实现中封装网络和栅格解释，由公共转换产生标准记录，研究服务只依赖标准记录和来源证据。更换 HTTP 客户端不改变研究规则；更换产品、聚合范围、转换算法或提供方，需要新准确来源/方法版本并重新采用。

建议验收集中于以下可观察行为：

1. 7 项天气与 11 项土壤按目录准确绑定取数；单位、产品、日界、土层及参考点证据随封存输入保留。
2. 覆盖天气完整日、缺一小时、重复小时、错误时区/单位、未来日期、提供方限流和失败；不静默切预报、填零或换提供方。
3. 覆盖土壤合法原生像元、错层、错 CRS、错 transform、无覆盖、零值语义不明、NoData、服务 XML 错误伪装 HTTP 200；所有拒绝发生在采用/运行前。
4. 网络访问有固定端点、超时、响应体上限和有界重试；429 与临时失败按提供方响应处理，失败重试不更换来源。真实外部请求与纯转换回归分别记录，不用合成响应代替接通结论。
5. 普通研究不能上传数值伪装第三方记录；授权对象与可信坐标由业务接入取得，API 只接必要资源引用。Worker 计算使用封存标准记录，不在重跑时重新下载并覆盖历史来源。

未验证项：本次没有进行 Open-Meteo 真实数值调用，没有逐项抓取全部 11×6 土壤图层，没有证明覆盖门禁的充分性，也未执行企业授权或真实研究运行。后续实现与验收应如实补齐，不将本调查标记成“第三方平台已接通”。
