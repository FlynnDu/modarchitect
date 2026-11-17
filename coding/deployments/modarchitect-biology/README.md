# 生物所SR850部署

2026-11-17 11:51（北京时间）更新。包版本0.1.1；数据库0011。

| 项目 | 地址 / 状态 |
| --- | --- |
| API | http://172.16.1.122:18925 |
| Nginx API入口 | http://172.16.1.122:17000/modarchitect/ |
| API文档 | http://172.16.1.122:18925/docs |
| Nginx设计器 | http://172.16.1.122:17000/modarchitect/ |
| Nginx API文档 | http://172.16.1.122:17000/modarchitect/docs |
| 存活检查 | http://172.16.1.122:18925/health |
| Nomad Job | modarchitect-api，SR850，健康 |
| API模板 | nomad/job-templates/modarchitect-api |
| 独立执行服务 | http://172.16.1.122:18926/health；modarchitect-execution，SR850 |
| 执行模板 | nomad/job-templates/modarchitect-execution |
| Key变量 | nomad/jobs/modarchitect-api → api_key |
| 数据库 | modarchitect；独立应用及迁移角色 |
| 海豚原Worker | 5个实例，Job36；通过HTTP请求本项目独立执行服务 |

服务安全方案：`ModarchitectApiKey`；请求头`X-Modarchitect-Api-Key`；进程变量`MODARCHITECT_API_KEY`。Key独立随机生成并注入，未写模板明文。业务后端传`provider_name/company_id`，同企业共享方案；用户登录与用户权限由业务系统负责，不调用登录身份端。

[业务curl与数据库字段](../../../docs/business-api-integration.md) · [前端curl](../../../docs/frontend-integration.md)

2026-11-17 11:30（北京时间）已在SR850的`/etc/nginx/conf.d/mlgrowth-api.conf`新增`/modarchitect/`→`http://172.16.1.122:18925/`。业务API可将原直连基础地址替换为`http://172.16.1.122:17000/modarchitect`，原路径、查询参数和`X-Modarchitect-Api-Key`保持原合同。[映射健康检查](http://172.16.1.122:17000/modarchitect/health)返回200；28项组件目录和带Key的20份业务模板与直连一致；缺少/错误Key均401。配置检查和平滑重载通过，旧服务OpenAPI响应保持不变。API镜像、Job、数据库均未修改。

11:30首轮仅交付API映射；11:51已补齐设计器和API文档的前缀支持。现在首页跳到`/modarchitect/designer/`，文档读取`/modarchitect/openapi.json`，Servers明确显示`/modarchitect`。直连文档保持根地址`/`，两种入口共用schema时互不覆盖。20份方案目录、设计保存、导出导入和新页面重开通过，全部请求保留前缀、HTTP错误0；带Key的业务查询正常，无效Key仍401。实际HTTP/DOM验收不含原生浏览器像素检查。

原Nginx配置备份为`/etc/nginx/conf.d/mlgrowth-api.conf.bak-modarchitect-20261117T112956`；恢复时复制备份到原文件，先`nginx -t`，通过后重载并等待应用入口就绪。本批页面修复未再修改Nginx文件。[首轮映射](nginx-proxy-acceptance-20261117.json) · [当前部署](nginx-prefix-deployment.json) · [跳转与文档](nginx-prefix-http-acceptance.json) · [页面保存](nginx-prefix-ui-acceptance.json) · [新页面重开](nginx-prefix-ui-reopened.json)

## 版本

- API wheel SHA-256：`d841cffce61345055c891707980ebf2751d2ca7f5df76450d119bb2653ad16e2`。
- API：`172.16.1.122/sumfen/modarchitect-api:0.1.1-20261117-d841cffce613@sha256:ac0d62e3d649830b9b1a683be9c177daea8fe90720b0a7a95b6028090fc281e7`。
- 独立Worker及分发进程仍为`172.16.1.122/sumfen/modarchitect-api:0.1.1-20261116-570beac9e18b@sha256:bf8d47b82c7577993f9f6028700f18c0d93f9fe2b66749a9e5ac86cb851e299c`，wheel SHA-256仍为`570beac9e18b38dbb43ead5b007399897f5cb5d1cf98ed3d1f752bd8f24822a1`。
- Worker：`172.16.1.122/dolphinscheduler/worker:modarchitect-0.1.1-20261116-3805897175a1@sha256:9c8bff144db5a67b4a064b4a188fb349bdee34d4c8c051b99019d9608c81ec6a`。
- API Job版本13，141个包文件逐项核对无差异；独立执行Job版本5；原海豚Worker Job版本36未变。两个本项目模板与运行镜像一致，API当前版本deployment successful，Consul passing。
- 当前API制品目录：`/data/modarchitect/releases/nginx-prefix-20261117-d841cffce613/`；上一批设计闭环制品在`/data/modarchitect/releases/api-design-loop-20261116/`；表格回归制品在`/data/modarchitect/releases/tabular-learning-20261116/`；原海豚Worker制品仍在`/data/modarchitect/releases/20261116-3805897175a1/`。

## 已验证

- 首批线上真实curl：22个采用组件、65项指标、20个模板；配置生成/往返、保存、修改、重开、重放、旧修订409、跨企业及跨来源404、缺Key/旧头401。本批追加6项合同，当前28个可采用组件、9项准确运行制品。
- 合法JSON媒体类型的大小写和`+json`均通过；兼容方案写入入口共用8,000,000字节预算。
- 保存回执保持原修订；API重启及镜像切换后仍可重开同一方案，配置摘要一致。
- 真实数据库0011；新增合同为数据迁移，无结构改动，原25项合同摘要保持。应用角色不是超级用户、表所有者或BYPASSRLS，使用既有强制行级隔离；迁移版本由独立迁移角色核验。
- 首次0.1.1发布时API与5个海豚Worker各133个包文件核对通过；旧Worker可导入、GDAL/HDF4与rasterio指纹保留。当前API、独立Worker和分发进程各140个包文件逐项核对无差异，算法依赖锁定在独立计算镜像。
- 最新隔离库完整回归136通过；前端42项通过；14个自有Python文件的文件头及Ruff通过。上一批3算法隔离容器正反例及真实海豚训练/预测8项SUCCESS证据保留；本批仅验收设计保存查询，没有新增计算。
- 本批真实curl验证20份模板详情、65项指标配置、28项模型目录；28项模型实际DOM选择及线上检查均通过。三份方案正式保存后重查内容、摘要一致，并由重查配置还原流程图；非法提交422且不落库。

[部署证据](deployment-acceptance-20261116.json) · [线上curl证据](live-api-acceptance.json)

## 范围

已交付浏览、设计、配置保存、重查流程图及个人研究空间。65项指标和28项可组合模型全部开放设计，未接通资料和参数可明确保留待配置；实际执行继续检查取数、适配、制品及授权。此前已验证纯第三方气象单次分析，以及线性、随机森林、XGBoost、高斯过程的标准表格训练、模型保存和独立预测。其他模型和每日凌晨2点连续调度仍需按各自合同联验。业务系统转接、业务引用表及用户权限由业务项目对接，本批不验证业务库。

2026-11-16 18:18实际执行预检：标准多变量方案返回`can_execute=false`，规则`execution_artifact`，原因`Research execution profiles are not configured`。线性训练、线性预测及历史曲线训练的线上目录状态均为`design_only`。未创建运行或启动海豚任务；当前不能按成功训练闭环验收。[预检证据](execution-readiness-20261116.json)

上述为登记运行制品前的历史检查记录。后续已为气象及4组回归训练/预测登记准确制品并通过真实运行；历史曲线训练仍待本环境启用。

现有监测任务1749/工作流668按用户明确许可发送STOP，再进行单实例滚动升级。未修改旧mlgrowth-api服务或其源码。Nomad两节点控制面未重启，PostgreSQL原数据与扩展视图保留。

初次API启动发现缺少系统库libexpat；已补齐依赖并加入镜像导入自检，最终镜像与所有当前allocation均正常。失败的首批allocation保留为历史记录。

## 备份与后续升级

迁移前备份：`/data/modarchitect/releases/20261116-861ff71f8afb/before-modarchitect.dump`，36809字节，SHA-256 `d1b4a2c58e880304a9738dbf19597a0e2d202eb5ff88f2e9347b51cfc0212c12`。

原Worker Job/模板保存在最终制品目录的`worker-before-job.private.json`与`worker-before-template.private.json`，权限0600。回退前确认活动任务，恢复原模板/Job并单实例滚动；保留0010与新增研究数据，不执行数据库降级或清库。原Worker镜像摘要`sha256:b270d8971558c41e96353b204b5914423ee8ab6b02c850e88e7070b8709f436e`。

后续迁移连接从Nomad变量`nomad/jobs/modarchitect-migration`的`database_url`取得，仅供迁移进程；API仅接收应用连接。更新镜像后先更新模板，再提交Job；不能把保存模板当作运行版本已经变更。


## 设计器直接访问修复

[打开设计器](http://172.16.1.122:18925/designer/#select)。原报错源于漏配工作区签名密钥，已在Nomad变量的workspace_key独立生成并持久化，模板注入MODARCHITECT_WORKSPACE_KEY。已有业务Key、企业方案、镜像和Worker保持原状态；该签名密钥后续更新时应保留，不轮换。

真实线上DOM验收：20方案加载、预览流程、编辑名称、保存、在新页面重开同一方案及JSON导出再导入，HTTP错误数0。另验证其他工作区404、伪造Cookie401、业务API缺Key仍401。原生浏览器工具此次连接失败，以上为真实DOM与线上HTTP验证，不含像素布局检查。

[配置修复证据](designer-workspace-fix-20261116.json) · [首次保存](designer-created.json) · [新页面重开与导出](designer-reopened.json)

## 输入来源展示修复

此前来源展示修复：用途表逐项展示来源二级分类、提供方及数据提供方式；土壤保留已选土层/统计属性，合成示例单独提示。当时65项登记中24项可添加；本批已改为65项全部可用于设计，执行就绪状态单独说明。

上述历史线上DOM及HTTP验证了来源、保存、重开及配置往返。当时未接通平台指标configure返回422；本批已通过准确planned_source绑定允许设计，实际执行仍拒绝未接通来源。原生浏览器未做像素布局验收。

[来源字段对接](../../../docs/frontend-integration.md) · [功能设计](../../designer-input-provision.md) · [部署与API证据](input-provision-deployment-20261116.json) · [添加保存](input-provision-created.json) · [新页面重开](input-provision-reopened.json)

## 纯第三方气象闭环

[打开气象研究方案](http://172.16.1.122:18925/designer/?template=crop-high-temperature) · [操作及curl](../../../docs/third-party-research-quickstart.md)。新浏览器在自己的空间采用和保存方案，不能直接读取验收空间的私有ID。

海豚独立项目modarchitect，代码189844146633280；计算工作流189844146864704，采集工作流189844147094080。两者引用已存在的sumfen-mlgrowth环境，代码183740803734080；环境正文未修改。连接配置保存在nomad/jobs/modarchitect-execution，凭据未写入镜像、方案或公开证据。

实际接口验收：采集730/任务1755、分析731/任务1756全部SUCCESS；页面验收：采集736、分析737及其任务全部SUCCESS。标准来源快照→保存重开→预检→分析回传→报告和7点曲线→新页面重查完成；缺快照和篡改值拒绝，幂等重放保持原任务。页面无HTTP错误，纯平台资料标记为来源估计，分析不开放保存预测模型。

参考位置50.46/119.85，2026-07-01至07-07；7天完整日最高温，最大25.2℃，未达到35℃参考条件。该结果是网格估计的条件分析，不是田间灾害诊断。来源环境/提供方、原文证据和计算摘要均保留。

计算组件：catalog_weather_conditions@1，镜像sha256:0d64d6dd35cda97b29e3f690d5755ad2ad43931cee3e992285e201b2fde5ff1c；准确清单见weather-component-manifest.json，API与执行Worker使用同一runtime-profiles.json。组件隔离验证完整高温、缺日及错误单位；离线计算无外网，API不接Docker。

原生浏览器工具未能初始化，本次页面验收为真实DOM事件及线上HTTP，不含像素检查。原海豚Worker和旧mlgrowth服务未重启；数据库及原密钥保留。

[部署与包核对](third-party-deployment-acceptance.json) · [接口真实结果](third-party-research-acceptance.json) · [页面闭环](third-party-ui-acceptance.json) · [新页面重开](third-party-ui-reopened.json) · [海豚实例映射](third-party-scheduler-acceptance.json)

## 计算方法选择

计算与评价新增“选择／配置计算方法”，候选直接来自版本化组件目录；兼容方法配置后先检查再应用，失败保留原图。准确方法、参数、连线和成果随方案保存，不另存页面选中值。多步骤研究可选择要配置的步骤，运行启用状态单独显示。

真实页面事件与线上HTTP已验证：打开目录、随机森林评估限制、线性模型切换历史曲线、保存、新进程重开；前后配置摘要相同，HTTP错误0。验收使用合成工程样例，仅验证设计保存，没有新增训练运行；原气象报告与7点曲线重查通过。未做原生浏览器像素检查。

上述为第一批方法入口验收。后续已为随机森林、XGBoost和高斯过程追加标准表训练/预测身份，保留原评估合同；最新范围见下节。

[设计与命令](../../designer-method-selection.md) · [部署](method-selection-deployment.json) · [首次保存](method-selection-created.json) · [新页面重开](method-selection-reopened.json) · [原气象结果回归](method-selection-weather-regression.json)

## 标准表格基础回归

“计算与评价”→“选择／配置计算方法”，适合当前研究操作的方法优先显示。线性、随机森林、XGBoost及高斯过程均支持多因素、多目标，实际模型及参数随同一方案保存；预测使用已保存状态，不再训练。

三种新增方法和线性模型均完成真实页面事件、保存重开、海豚训练、保存模型及无标签预测，共8个SUCCESS实例；132项隔离库测试及41项前端检查通过。模型新客户端重开摘要一致，跨工作区404。验收使用明确标注的合成工程资料，没有科研精度或原生浏览器像素验收。

当前9项运行登记为上述4组训练/预测及气象条件分析。LSTM/ConvLSTM保留指定序列/网格资料评估，尚未接入通用训练状态；统计、温室和机理方法需采用对应研究用途及输入，不能把所有方法直接当作任意表格回归。

本批迁移前数据库备份：`/data/modarchitect/releases/tabular-learning-20261116/before-modarchitect.dump`，SHA-256 `b9f887ff34d89c8e0dad6f3e51bf3c0eae2e797222bc4d24d5f5c6dec1c827cd`。回退时保留0011、新合同和用户数据；旧镜像不认识新增组件，兼容回退须保留当前目录。

[设计及命令](../../tabular-learning-methods.md) · [部署](tabular-deployment-acceptance.json) · [组件正反例](tabular-component-acceptance.json) · [随机森林](tabular-random-forest-ui.json) · [XGBoost](tabular-xgboost-ui.json) · [高斯过程](tabular-gaussian-ui.json) · [线性](tabular-linear-ui.json) · [模型重开](tabular-reopened-models.json) · [海豚实例映射](tabular-scheduler-acceptance.json) · [原气象重查](tabular-weather-regression.json)

## 研究方案设计保存闭环

业务前端采用方案或自定义设计→配置目录指标和模型→检查→正式保存→重新查询→显示流程图。业务系统先调用检查API，valid=true后调用design-saves；成功回执只有design_id/revision/configuration_sha256，随后业务系统在自己的数据库保存关联。保存端重复执行同一规则，错误返回422及字段/节点/端口定位；不能仅凭先前检查结果绕过校验。

未接通的30项指标保留计划来源及原采样尺度；模型可选择立即配置或明确保留待配置步骤。可设计不代表可运行，参数或资料待配置状态随方案保存。

三条真实curl路径均已保存并重新查询：已有模板、自定义65项指标、准确序列类型的未来模型。流程图使用查询结果的composition和组件目录，未另存重复流程字段。实际DOM/HTTP验证，不含原生浏览器像素检查；未启动取数、计算和海豚任务，业务库按文档接入，不做实际落库验证。

本批无数据库迁移；发布前Job与模板私有快照在当前制品目录，权限0600。回退前确认活动任务和目录兼容，不降级数据库或清理用户方案。

[设计及实际命令](../../api-design-loop.md) · [真实curl](api-design-loop-acceptance.json) · [28项模型选择](api-design-model-selection.json) · [流程图核对](api-design-flow-acceptance.json) · [部署核对](api-design-loop-deployment.json) · [保存后流程示例](api-design-flow-custom.html)

## 按接口对接文档

前端和业务两份文档已按接口拆分，各18个示例覆盖17种HTTP操作，分别列用途、参数/请求体、curl和响应；前端逐项说明字段的显示与使用。保留独立API-Key约定及获取位置，完整示例集中在docs/examples/model-designer.json。21次真实curl、文档路由/方法、JSON及shell语法检查已核对；仅更新文档及公开验收记录，未改运行服务。

[前端逐接口说明](../../../docs/frontend-integration.md) · [业务逐接口说明](../../../docs/business-api-integration.md) · [完整JSON](../../../docs/examples/model-designer.json) · [文档核对证据](api-interface-docs-acceptance.json)
