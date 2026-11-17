# 生物所SR850与Nomad部署

2026-11-16。用户授权实际部署独立modarchitect服务、使用modarchitect数据库、通过Nomad模板创建，并升级现有DolphinScheduler Worker安装本次包。旧mlgrowth源码和API服务不修改。

## 目标与边界

- 新建`nomad/job-templates/modarchitect-api`，参照实时mlgrowth-api模板的网络、DNS、镜像仓库和健康检查方式；服务约束到SR850。运行密钥单独进入Nomad变量，不把明文密钥写进模板、报告或源码。
- PostgreSQL通过Consul的`pg-master`发现。先检查是否存在modarchitect库及数据，再按当前迁移初始化/升级0010。使用独立迁移与应用角色，应用不能是表所有者、超级用户或BYPASSRLS。已有库先备份，禁止重建已有数据。
- API镜像与海豚Worker均安装本次准确wheel。Worker从实时镜像摘要增量构建，保留已有算法、Conda/GDAL/HDF4栈与旧包，不对整个科学环境盲目升级依赖。
- 保存旧Worker Job、模板和镜像以便回退，先检查活动任务，再沿现有单实例滚动策略更新5个Worker；不停止/清空控制面或数据库Job。
- 用户进一步确认：本项目只验证服务API-Key，业务后端已完成用户鉴权并传企业信息；不调用用户登录身份端。新项目使用`ModarchitectApiKey`、`X-Modarchitect-Api-Key`与`MODARCHITECT_API_KEY`，不沿用旧项目的名称。

## 本次接入合同调整

默认`api_key`模式：所有研究入口先验证新Key；企业私有资源按业务后端声明的`provider_name + company_id`隔离，固定主体`business_api`使密钥轮换不改变数据归属。同企业由业务后端管理用户权限，本系统不声称按个人隔离。设计保存可在请求根级传这两个字段；读取和其他资源写操作用同名查询参数。正文和查询同时给出时必须一致，缺少或公司0号拒绝；无Key不得采用正文范围。

原外部委托链仅保留为显式`delegation`兼容模式用于历史合同，生物所部署不启用。API-Key不写入配置JSON。site/entity等是实际研究对象的信息，不作为无关目录或设计保存的强制字段。采样点或地块资料要求继续保留科学完整性，不以Key替代缺失资料。

新增行为回归覆盖：无Key/旧名称Key拒绝、新Key保存/重开/重放、默认不调用身份端、公司及来源隔离、正文查询冲突、Key轮换后归属稳定，以及OpenAPI的新安全方案。先写失败测试再修改入口，不修改数据库隔离策略或科学计算。

复核补齐媒体类型大小写及`application/*+json`的范围解析，避免合法JSON正文被忽略；兼容的model-center/designs写入纳入同一正文预算。先用行为测试复现，再增量更新本次包和镜像，保持Worker既有依赖版本。

## 已确认现网

15:39（北京时间）SR850及12个Client ready；Nomad现有2个Server peers，无第三个成员；本次不重启控制节点。5个Worker健康，mlgrowth-api在SN550-13，PostgreSQL主库通过Consul指向SN550-6。modarchitect-api Job尚不存在。

## 验收

记录准确镜像摘要、模板与运行Job一致性、SR850 allocation、Consul passing、API目录与配置文件生成、数据库0010与低权限RLS、重启后读取。Worker构建及部署后分别验证modarchitect准确文件摘要、旧包入口、GDAL/HDF4、基础依赖和各实例健康。调度执行若涉及新入口，必须核实实际领取/回传路径及环境变量，不能把“包可导入”当作研究调度闭环完成。

真实执行结果与未完成条件写入`coding/deployments/modarchitect-biology/`；凭据和原始含密钥Job仅保存在忽略的私有运维目录及目标主机受限目录。

## 生物所实际交付

2026-11-16已部署。最终包0.1.1，SHA-256 `3805897175a1c0d7cf2b077dc4b9ec357dc8201c18bb0f90d321a259d7dad3f7`。SR850的modarchitect-api与5个海豚Worker均健康；真实curl及数据库验证完成。服务Key随机独立生成，Nomad变量注入。

[地址、准确镜像、验证、范围与回退](deployments/modarchitect-biology/README.md)。本轮不重复宣称研究执行、每日触发和真实取数已经在生物所完成联验。

## 2026-11-17 Nginx API入口

用户要求在SR850的`/etc/nginx/conf.d/mlgrowth-api.conf`新增本项目映射。沿用现有Nginx的17000端口，新增`/modarchitect/`转发到固定`172.16.1.122:18925/`，去除外部路径前缀并传递Host、客户端地址及转发协议信息。保留既有location原始字节、API-Key和企业范围合同；本次不更新API镜像、Nomad Job或数据库。

验收为：变更前备份目标文件；`nginx -t`通过后平滑重载；新入口health、公开目录及带Key的业务只读查询正常；缺少/错误Key仍拒绝；原有Nginx存活入口及旧服务响应与变更前一致。配置检查、重载或基础应用检查失败时恢复备份并重新检查/重载。记录准确备份路径、配置摘要、命令和线上结果。

当前设计器的`/api/v1/...`绝对请求路径和API文档的OpenAPI地址尚未适配外部前缀；本次交付API映射，不把页面返回200视为设计器或文档完整可用。

11:30（北京时间）已完成。目标文件新增`/modarchitect/`转发及无尾斜杠的308跳转，原有配置字节保持；备份为`/etc/nginx/conf.d/mlgrowth-api.conf.bak-modarchitect-20261117T112956`。`nginx -t`、`systemctl reload nginx`及`systemctl is-active nginx`通过。新入口health、28项组件目录及20份业务模板通过；带Key业务查询与直连结果一致，缺少/错误Key均401；原有`/healthz`和`/mlgrowth/openapi.json`保持200及原响应。API Job仍为版本11，原allocation健康，Consul passing。

平滑重载会先返回，再由新Worker接管请求：首次尝试的即时health检查未通过，已恢复原文件；最终发布记录了health从404到200的两次探测，间隔0.5秒。后续应在重载命令成功后按应用入口做有界就绪探测，不能仅凭命令退出或即时单次请求判断生效。[实际命令、摘要与线上证据](deployments/modarchitect-biology/nginx-proxy-acceptance-20261117.json)。本次没有修改自有Python文件，无需Python行为回归及文件头检查。
