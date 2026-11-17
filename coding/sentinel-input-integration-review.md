# 哨兵卫星输入接入核对

2026-11-13。范围：只读核对 mlgrowth 既有调用链与官方资料，指导土壤、天气、卫星联合研究的接入设计。本次没有读取 `.env` 或用户提供的含密配置正文，没有请求令牌、下载影像、运行旧服务、访问旧库或修改旧项目。代码已存在、方法合理和真实接通分别验收。

## 结论与建议边界

- mlgrowth 已有 Sentinel Hub Catalog → Process → 光学/QA 栅格 → 质量处理 → 指数计算的实现，能作为本项目参考。不能直接引入其整个数据库、资产上传及融合系统。
- 当前用户要求由 DolphinScheduler Worker 取数、账户只走环境变量。Worker 按服务端固定来源合同发起采集，API 不下载影像，不接收密钥、任意远程地址或用户伪造第三方数值。NDVI 是明确计算节点，读取节点只交付红/近红外反射率、QA 及场景证据。
- 先做固定参考像元的研究输入；10m 参考像元不等于地块均值，20m SCL 分类也不能因输出为 10m 就称为 10m 原生质量信息。若以后改为地块统计，需要登记范围、覆盖门槛和聚合方法的新合同。
- 无当日清晰观测可以明确缺数据并拒绝需要该日齐备的研究；不能前向填补、插值或把多日合成数值伪装为每日观测，更不能把派生 NDVI 当成株高等田间实测标签。

## 旧项目源码链路

本次主要参考根目录 `E:/python/mlgrowth`；邻近迁移 worktree 亦有同名 Sentinel Hub 模块。以下路径均相对该旧项目根目录，仅静态阅读，未运行旧测试。

| 职责 | 实际入口 | 已核到的规则 |
| --- | --- | --- |
| 账户与端点 | `src/pymlgrowth/configuration.py` 的 `SentinelHubConfiguration`、`load_sentinel_hub_configuration` | 配置字段与读取集中；密钥 `repr=False`；ID/secret 必须同时存在 |
| 公开请求配置 | `remote_sensing/adapters/sentinelhub/provider_context.py` | profile、窗口/并发/预算等公开参数与私有账户分开；公开清单没有密钥或令牌 |
| 发现场景 | `sentinelhub/catalog.py` 的 `build_catalog_query`、`discover_catalog_acquisitions` | 完整空间几何查询；保存采集时刻、集合、候选 ID、处理版本等元数据；按 UTC 采集时刻分组 |
| 获取实现 | `sentinelhub/client.py` 的 `DefaultSentinelHubClient` | 延迟装配 sentinelhub 3.x SDK；Catalog 有 4096 条预算；数据集合显式绑定 `service_url`，避免 SDK 内置集合覆盖 CDSE 地址 |
| 长批次认证 | `sentinelhub/authentication.py` | 每次 HTTP 尝试前检查有效期；共享刷新锁；401 关闭响应后最多刷新重放一次；不锁住实际下载 |
| Process 请求 | `sentinelhub/process/requests.py` | 以已发现采集时刻约束窗口；光学与分类 QA 分离；请求指纹包含波段、网格、转换与重采样方法 |
| 物化与复用 | `sentinelhub/provider.py`、`process/materialization.py` | 下载文件原子发布、摘要校验；候选集与生成的 AOI acquisition 明确区别，不冒称逐个原始瓦片文件 |
| 质量处理 | `remote_sensing/algorithms/qa/sentinel2.py` | 默认 SCL 仅 4/5，dataMask=1；可选 CLM/CLP 进一步筛选；QA 最近邻重采样 |
| 指数与有效性 | `remote_sensing/algorithms/indices.py`、`field_surveys/imagery_quality.py` | 公式与输入波段映射受控；NDVI 分母绝对值需大于 1e-6、反射率非负、保留有效零值 |
| 真实观测追溯 | `field_surveys/imagery_evidence.py`、`api/services/field_surveys/satellite_evidence.py` | 真实观测与融合产品分开，保存影像/掩膜摘要、采集时刻及覆盖质量；同日多瓦片不增加独立观测日 |

相关已有回归：`tests/remote_sensing/test_sentinelhub_adapter.py`、`test_sentinelhub_stream_authentication.py`、`test_sentinelhub_stream_download.py`、`test_preprocess_sentinel2.py`。本次只核对测试入口和断言方向，未声称测试已重跑。

### 环境变量名称与替换规则

以下仅来自配置源代码的名称，不含任何账户值：

| 名称 | 责任 |
| --- | --- |
| `SH_CLIENT_ID`、`SH_CLIENT_SECRET` | Worker 运行时 OAuth 客户端身份；成对提供 |
| `SH_BASE_URL` | Sentinel Hub 服务基址；默认 CDSE，部署端受控修改 |
| `SH_TOKEN_URL` | 身份令牌服务；与获准提供方身份域配套 |
| `SH_PROFILE` | 旧实现的非敏感 profile 名称 |

旧实现有凭据时使用 `SHConfig(use_defaults=True, ...)`，避免读取用户目录 `config.toml`；没有凭据时允许读取本机 profile。**本项目不应保留后一个自动回退**，因为用户已要求账户统一从环境变量读取。缺少成对凭据时应在采集开始前明确拒绝。`SH_PROFILE` 即使为兼容保留，也不应成为偷偷从本机目录获取账户的路径。

不要把旧 PG、OSS、EarthData 配置带入新项目；不将整份环境配置复制到研究定义、运行 JSON 或海豚任务参数。部署可向执行 Worker 注入获准的 SH 变量；Worker 内再向实际采集进程显式传递，不依赖 API 容器碰巧拥有相同环境。秘密和 access token 不进入日志、异常详情、请求指纹、制品、模型或报告。账户轮换不改写历史数据证据；来源端点或产品改变仍需核对准确来源采用资格。

## 土壤、天气与海豚环境的旧代码证据

本节补充用户要求的“先找到之前怎么做”的准确依据。均来自只读源码，**不代表已读取实际海豚环境配置或在新 Worker 完成注入**。

### 三条取数链的实际入口

| 功能 | 旧项目准确文件与行号 | 核实到的行为 |
| --- | --- | --- |
| Open-Meteo 任务 | [weather.py:95](E:/python/mlgrowth/api/routers/weather.py:95) → [commands.py:82](E:/python/mlgrowth/src/pymlgrowth/cli/commands.py:82) → [script.py:310](E:/python/mlgrowth/src/pymlgrowth/openmeteo_weather/script.py:310) | API 构造 `dp-config ... dp-meteo ...`，Shell 执行 CLI，再调用 `sync_weather` |
| Open-Meteo 完整日期范围 | [script.py:187](E:/python/mlgrowth/src/pymlgrowth/openmeteo_weather/script.py:187) → [script.py:106](E:/python/mlgrowth/src/pymlgrowth/openmeteo_weather/script.py:106) → [conversion.py:105](E:/python/mlgrowth/src/pymlgrowth/openmeteo_weather/conversion.py:105) | `fetch_weather_range` 划分历史/预报段，`requests.get` 请求，按实际端点标记；转换器核验单位、上海日界和小时完整性 |
| 通用土壤任务 | [soilgrids.py:11](E:/python/mlgrowth/api/routers/soilgrids.py:11) → [commands.py:42](E:/python/mlgrowth/src/pymlgrowth/cli/commands.py:42) → [script.py:441](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/script.py:441) | `dp-soilgrids` 调 `sync_soil_data`；这是通用旧 CSV 路径，不是当前研究的精确原生参考点方法 |
| 勘察原生土壤剖面 | [analysis.py:318](E:/python/mlgrowth/src/pymlgrowth/field_surveys/analysis.py:318) → [soil.py:100](E:/python/mlgrowth/src/pymlgrowth/field_surveys/soil.py:100) → [profile.py:37](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/profile.py:37) | 勘察实际已使用 WCS 单像元六层 mean，来源版本 `soilgrids_wcs_250m_nearest_v4` |
| 原生像元定位 | [profile.py:23](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/profile.py:23) → [script.py:228](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/script.py:228) | WGS84 以 `always_xy=True` 变换 IGH，再以 `floor(x/250)`、`floor(y/250)` 取 250m 边界 |
| 实际 WCS 访问 | [script.py:303](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/script.py:303) → [script.py:243](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/script.py:243) | OWSLib `WebCoverageService` → `getCoverage` → GeoTIFF；请求中明确版本、图层、subsetting/output CRS 与分辨率 |
| 研究标准土壤换算 | [source_normalization.py:19](E:/python/mlgrowth/src/pymlgrowth/research_models/source_normalization.py:19) | 独立 `SOIL_UNITS` 字典规定研究单位，cfvo÷10、soc÷10、水量÷1000；不能误用旧通用 CSV 的 cfvo/soc 因子 |
| Sentinel 账户/请求 | [configuration.py:1077](E:/python/mlgrowth/src/pymlgrowth/configuration.py:1077) → [client.py:128](E:/python/mlgrowth/src/pymlgrowth/remote_sensing/adapters/sentinelhub/client.py:128) → [provider.py:67](E:/python/mlgrowth/src/pymlgrowth/remote_sensing/adapters/sentinelhub/provider.py:67) | 环境配置装配 SDK，Catalog 发现实际采集，再按网格生成 Process 请求 |

重要差异：`field_surveys/soil.py:123` 先读取 bdod 作完整性探测，`:133` 再读其余属性。该旧勘察方法允许在代表点缺有效剖面时，于 1km 范围寻找最近有效点并保存实际坐标/距离。这是**显式的旧勘察策略**，不能无声进入新项目固定参考点合同。固定点失效时应拒绝；如要采用邻点采样，需要单独登记相应方法和研究适用条件。

### 哪些已有环境配置，哪些在旧代码确实固定

| 项目 | 源码事实 | 本次设计应如何处理 |
| --- | --- | --- |
| Sentinel 身份与服务域 | [configuration.py:132](E:/python/mlgrowth/src/pymlgrowth/configuration.py:132) 定义五个 `SH_*` 名称；`:1077` 从同一环境映射读取；[client.py:133](E:/python/mlgrowth/src/pymlgrowth/remote_sensing/adapters/sentinelhub/client.py:133) 装配使用 | 沿用这些已有名称及集中装配；不把账户或域写进组件函数、请求、模板与制品 |
| Open-Meteo 端点 | [script.py:39](E:/python/mlgrowth/src/pymlgrowth/openmeteo_weather/script.py:39) 的 `ARCHIVE_URL`、`FORECAST_URL` 是源码常量；请求函数没有 API Key 参数 | 不能宣称旧代码已有天气 URL/Key 环境变量。新项目若要求运行配置可替换，应在统一 settings 明确新增，而非编造旧配置名或散落 `getenv` |
| SoilGrids 端点 | [script.py:335](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/script.py:335) 的 WCS 地址在函数内固定；[profile.py:19](E:/python/mlgrowth/src/pymlgrowth/isric_soilgrids/profile.py:19) 固定 WCS 方法版本与 CRS | 参考真实 WCS 获取方式，但将可部署服务地址收束为集中设置；CRS、单位、土层与准确算法属于版本化合同，不能任意改值冒充同一来源 |
| 通用应用设置 | [configuration.py:216](E:/python/mlgrowth/src/pymlgrowth/configuration.py:216) 的 `_values` 默认读 `os.environ`；`:823` 的 `load_application_configuration` 组合数据库、OSS、数据根和 API 地址 | 仅借鉴统一配置入口，不能复制整套旧基础设施；天气/土壤脚本导入时加载旧应用配置这一耦合也不照搬 |
| 海豚环境名 | [api/configuration.py:54](E:/python/mlgrowth/api/configuration.py:54) 定义 `MLGROWTH_DS_ENVIRONMENT_NAME`；[api/config.py:241](E:/python/mlgrowth/api/config.py:241) 映射为 settings，源码默认 `sumfen-mlgrowth` | 环境名来自部署配置，不能为每个研究或来源节点写死；现有名称不等于已经注入新执行进程 |
| 海豚连接 | [api/configuration.py:55](E:/python/mlgrowth/api/configuration.py:55) 定义 `MLGROWTH_DS_ENDPOINT`、`MLGROWTH_DS_TOKEN` 等 | 调度服务自己的连接配置与第三方数据账户分开，禁止当成来源证据封存 |

本次没有发现旧 Open-Meteo 公共接口或 SoilGrids WCS 读取账户密钥；这两个实现使用公开请求。若当前天气商业接入需要新账户，必须显式定义对应设置和验收，不以 Sentinel 账户代替，也不声称旧代码已有商业账号支持。

### 旧海豚怎样使变量进入取数进程

已核实的旧链路是 **Shell Task，不是 Python Task，也不是调用远端 HTTP Worker 来执行这些 CLI**：

```text
API settings.MLGROWTH_DS_ENVIRONMENT_NAME
  → api/services/dolphin.py:116 Shell(environment_name=...)
  → SDK core/task.py:453 environment_code 按环境名查询编号
  → 海豚执行已绑定环境的 Shell
  → dp-meteo / dp-soilgrids / dp-survey 启动本机 Python CLI
  → 取数代码的中央配置读取此进程 os.environ
```

准确证据：

- [dolphin.py:96](E:/python/mlgrowth/api/services/dolphin.py:96) 导入 `pydolphinscheduler.tasks.shell.Shell`；`:116` 创建 Shell 并传 `environment_name=settings.DS_ENVIRONMENT_NAME`；`:156` 启动时传任务的 `environment_code`。
- [task.py:453](E:/python/mlgrowth/src/dolphinscheduler-sdk-python/src/pydolphinscheduler/core/task.py:453) 把 `_environment_name` 交给 `gateway.query_environment_info`；这是按名称解析已有环境，不是把当前 API 的全部 `os.environ` 发给 Worker。
- [shell.py:57](E:/python/mlgrowth/src/dolphinscheduler-sdk-python/src/pydolphinscheduler/tasks/shell.py:57) 把命令保存为 Shell raw script。
- [tasks.py:153](E:/python/mlgrowth/api/services/field_surveys/tasks.py:153) 构造 `dp-survey run --survey-id ...` 并提交同一 Shell 入口；勘察内部再调用土壤、天气、遥感模块。

上述是源码数据流。真实海豚服务怎样保存环境脚本、当前环境是否授权指定 Worker 组，以及具体 shell 是否成功导出变量，本次未读取实际配置也未联验，不能由源码直接宣布通过。

### 新项目独立 HTTP Worker 不会自动继承海豚环境

本次核到新项目 [runtime/worker.py:44](E:/python/modarchitect/modarchitect/runtime/worker.py:44) 通过 HTTP `/acquire` 进入来源执行；[input_sources/worker.py:15](E:/python/modarchitect/modarchitect/input_sources/worker.py:15) 从内部 API 领取封存任务后调用采集；[runtime/scheduler.py:61](E:/python/modarchitect/modarchitect/runtime/scheduler.py:61) 的启动参数仍为 `environmentCode=-1`。

即使把海豚任务改为绑定 `sumfen-mlgrowth`，环境也只影响执行那段任务的进程。**如果任务只是 HTTP 调用另一个常驻 Worker 容器，后者不会获得这些变量。** 请求携带任务 ID 不会转移进程环境，不能把密钥塞入 HTTP 业务参数“补齐”。

实施前应明确选择并验证一种方式：

1. 采用旧模式：有边界的采集 CLI 在海豚 Worker 的任务进程执行，直接读取已绑定环境；仍只使用新项目内部 API/身份领取和回传，拒绝使用旧数据库配置。
2. 保留独立服务：由部署配置向独立 Worker 注入明确列出的第三方变量，海豚只负责触发；从 Worker 实际进程检查**所需变量存在与解析成功**，不打印值。不能把 API 环境或 DS 环境“已保存”当成 Worker 已就绪。

以上两种方式都需要真实任务回执和取数证据；不能混合两条方式造成“日志显示海豚环境正确、真正取数进程却读另一份账户”的漂移。采用哪条路径由本次架构设计决定，当前调查不擅自改调度或注入秘密。

## 官方端点与认证事实

| 用途 | 当前官方端点 |
| --- | --- |
| Sentinel Hub OAuth | `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token` |
| Sentinel Hub Catalog Search | `https://sh.dataspace.copernicus.eu/catalog/v1/search` |
| Sentinel Hub Process | `https://sh.dataspace.copernicus.eu/process/v1` |
| CDSE 公共 STAC 根目录 | `https://stac.dataspace.copernicus.eu/v1/` |
| CDSE 公共 STAC Search | `https://stac.dataspace.copernicus.eu/v1/search` |

OAuth 使用 `grant_type=client_credentials`；令牌有效期以实际响应/声明为准，不能硬编码为“永远一小时”，也不应每个影像请求重新取令牌。[官方身份认证](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html)

2026 年官方新增 `/<service>/<version>` 路径，旧 `/api/v1/process` 等路径为兼容形式。新实现优先采用当前路径，SDK 接入则确认其组装结果，避免重复添加 `/api`。[官方路径更新](https://dataspace.copernicus.eu/news/2026-3-9-api-path-structure-updates-sentinel-hub-services)

公共 CDSE STAC 与 Sentinel Hub Catalog 是不同查询服务。旧 `catalogue.dataspace.copernicus.eu/stac` 已列为弃用；不要将两个目录的候选 ID 假定为同一产品身份。最小实现建议使用与 Process 同域的 Sentinel Hub Catalog，减少额外目录映射。将来切换发现服务时，在提供方接入内验证 ID、日期、瓦片与处理版本的对应关系。[CDSE STAC 说明](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)、[Sentinel Hub Catalog](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Catalog.html)

纯 HTTP 可以实现该链路，不必为了小范围参考像元引入旧 SDK 的所有 GIS/业务依赖。是否使用 SDK 是传输实现选择；外部合同、质量规则和追溯要求不随之简化。HTTP 实现仍需有界超时/响应体、授权续期、限流处理与资源释放。429 不能解释成没有影像。[官方限流说明](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/RateLimiting.html)

## Process 会不会合成不同采集时间

**会。** `timeRange` 表示候选范围，并非“一天一条真实观测”。一次 Process 请求默认只生成一幅输出，图像如何取样取决于 mosaicking 类型和顺序。官方时序指南建议先用 Catalog 列出实际场景，再逐次处理。[官方时序指南](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/UserGuides/TimeSeries.html)

- `SIMPLE` 输出已经镶嵌的 sample，其 `scenes` 对象为空，无法仅靠它获得所用准确场景清单。
- `ORBIT` 的场景按日组织，同日瓦片仍会合成，不能直接证明严格单次过境。
- `TILE` 保留 `samples[i]` 与 `scenes.tiles[i]` 对应关系，可检查具体采集日期及数据路径。最小参考像元应选择并记录一个明确 sample，不对多景求均值。[官方 evalscript 函数语义](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Evalscript/Functions.html)

建议正常流程：

```text
上海业务日与可信参考位置
  → 转 UTC 时间窗，Catalog 查询实际候选
  → 冻结候选身份与 acquisition timestamp
  → 窄时间窗 Process（TILE，必要时 preProcessScenes 限定候选）
  → TIFF + userdata.json，验证实际所用样本/场景和返回网格
  → 云/缺测/反射率质量门禁
  → 独立 NDVI 节点
  → 与同日天气及静态土壤参考按明确方法对齐
```

官方支持 `updateOutputMetadata` 写出 `scenes.tiles` 与 `inputMetadata` 到 `userdata.json`，Process 多输出可用 tar 承载。应只按白名单读取指定成员，不解压任意路径。保存实际被选中的场景与 sample 索引、原始响应摘要、处理服务版本和 evalscript 摘要。Catalog 只是候选，不能冒称其所有候选都参与了某个像元。[官方元数据输出示例](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/UserGuides/Metadata.html)

如果采用 `preProcessScenes` 按某一产品筛选，必须确认实际元数据确有对应字段；字段缺失或身份无法对上应失败，不能拼造产品 ID。即使使用窄窗，也要检查返回场景是否唯一、是否处于指定上海业务日；相邻瓦片、重处理版本与同日多次采集应有明确选择规则。

## 固定参考像元、单位与质量

1. 读取 `sentinel-2-l2a` 的 B04（红光）、B08（宽近红外），同时读取 SCL 与 dataMask。光学原生 10m、SCL 原生 20m，输出网格由合同固定。使用投影米制网格和明确像元边界，验证 CRS、transform、尺寸与参考点包含关系；不要将任意经纬度 1×1 请求叫做原生 10m 像元。[官方波段表](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html#available-bands-and-data)
2. 读取明确的 `REFLECTANCE`，QA 用 DN。反射率可用 FLOAT32 保存，不能用默认 AUTO 输出的拉伸显示值计算指数。旧实现将反射率编码 UINT16×10000，属于需保留在方法中的另一种确定编码。[evalscript 输入输出单位](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Evalscript/Functions.html#input-units-and-output-values)
3. 保留 `harmonizeValues` 的明确设置及处理版本，避免不同 Sentinel-2 基线的原始 DN 被直接混用。[官方 harmonize 说明](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html#harmonize-values)
4. dataMask 只说明有无数据，不说明无云；场景云量也不是点上晴空。旧项目默认 SCL4/5、dataMask=1 的保守农田规则可作为首版版本化方法；分类 QA 必须最近邻，不能插值出新类别。[官方 dataMask 语义](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/UserGuides/Datamask.html)
5. 独立节点计算 `NDVI = (B08 - B04) / (B08 + B04)`，输出无量纲且保留实际影像日期、质量和派生来源。有效零值不删；分母接近零、非有限或不符合采用方法的反射率应拒绝。不要将反射率更名后直接填入当前旧演示的 `ndvi`。

上海业务日要从 `acquired_at` 的时区明确换算得到。若查询是业务日 D，UTC 搜索下界是 D 前一天 16:00Z，上界是 D 当天 16:00Z；对包含端点的外部 API，可抓取后再以 `[start,end)` 严格筛选，防止次日零点重复。不得将 UTC 日期字符串截取当作上海业务日。历史回测也不能只凭采集时间证明当时已可取得，需保留抓取/可用时间。

## 最小验收与当前限制

- 配置缺失、只配 ID、外域端点、持续 401/403、429、超时与截断响应应明确失败；无秘密泄露、无用户目录 profile 回退。
- 通过 Worker 正常入口验证单个有预算的实际参考位置/业务日，而不是只在 API 进程中取数。认证成功、影像取回、清晰观测合格、研究结果分别记录。
- 覆盖多场景合成、元数据缺失、错日、空候选、dataMask=0、SCL云/影、分类重采样、分母近零和合法 NDVI=0；不以填零制造通过。
- 一个研究中的土壤是静态网格参考、气象是逐日网格估计、卫星是离散时间遥感观测。对齐必须是显式方法节点，并保留各自空间支撑；不足样本时不强行产出预测模型。
- 当前系统的 `growth_report_ndvi_*` / `growth_point_ndvi` 是未绑定的平台分析候选；新 Sentinel 原始光学来源与 NDVI 计算节点需有自己的准确合同。不能仅把原候选 `available` 改成真，也不能将报告覆盖区指标改成参考像元值。

本次未读取任何实际账户值，未验证提供的环境在新 Worker 中可用，未消耗影像处理配额，未证明清晰观测日数量或真实预测效果。上述事项交由后续有预算的隔离 Worker 联验，不把本调查当作“卫星已接通”的证据。
