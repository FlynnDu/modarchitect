# 249 独立部署记录

## 当前持续研究与三来源验收（2026-11-13）

当前API、Worker、调度和迁移镜像统一固定为`sha256:d591403811242e3b3659932b4d6a566dede46ff062353ffcaa2883b40a2d9919`，数据库0009。20份研究方案全部实际运行通过，6份训练方案保存模型并完成预测；65项输入目录规则通过，20项第三方指标真实取数，4项人工通道经页面采用。三日补数、持久批次、真实曲线、重复补数去重与线上DOM交互通过。首次真正凌晨2点自动触发、原生浏览器像素与真实业务授权/农业精度仍单独待验。

使用`docker compose -f compose.yaml -f compose.studies.yaml up -d`，独立海豚使用`scheduler-compose.yaml`。组件OCI/旧执行映射保留，旧mlgrowth只读。上线前32个模型、116个方案版本、46份来源快照摘要一致。提供方账户来自同名`sumfen-mlgrowth`环境，不写入研究JSON或业务界面。

完整结果与限制见[本轮验收报告](continuous-research-acceptance.md)。最后运维复跑预检遇到SSH中断，独立连接进程仍在重连；上面的运行/模型/日报/UI证据已下载保存，尾检待确认。历史发布内容保留在下方，不代表当前运行版本。

## 上一批指标清单与评价分支（2026-11-12）

当前 API 页面镜像为 `modarchitect:0.1.0-input-view-eb9971db6d9f`；Worker、调度消费者及迁移服务保留 `modarchitect:0.1.0-rules-d2b111fbb2bc`。51 个 Python 包文件与 31 个科学合同文件均与上一批相同，数据库仍为 `0007`。输入卡片逐项列指标和单位，表数及记录数分开显示；时间留出训练方案显示数据集到评价的实测分支。用户入口为 `http://192.168.3.249:18925/designer/#select`。

当前启动必须使用两个配置：

```sh
cd /mnt/sda1/modarchitect
docker compose -f compose.yaml -f compose.studies.yaml up -d
```

当前发布与证据在 `/mnt/sda1/modarchitect/releases/input-flow-20261112/`，只更新 API 页面。见[当前验收](../../input-flow-acceptance.md)、[平台规则](../../../docs/platform-rules.md)和[研究人员使用说明](../../../docs/research-study-guide.md)。前一平台规则批次保留在 `/mnt/sda1/modarchitect/releases/platform-rules-20261112-final/`；更早的方案库批次保留在 `/mnt/sda1/modarchitect/releases/researcher-library-20261112/`。日常启动沿用上方两个配置。


## 历史发布记录

2026-11-12 设计器页面版本为 `modarchitect:0.1.0-figma-ui-b62341979b81`。本次用 [compose.ui.yaml](compose.ui.yaml) 只覆盖 API 页面镜像，Worker/调度仍为 `modarchitect:0.1.0-general-e02005883aaf`，54 份 Python 与科学合同文件逐字节相同，数据库仍为 0005。日常启动使用 `docker compose -f compose.yaml -f compose.ui.yaml up -d`，避免遗漏页面覆盖配置。完整功能验收见 [Figma 设计器实现](../../figma-designer-implementation.md)。

此前运行通用化已增量迁移至 0005，其历史模型兼容结果见[首批通用化验收](../../runtime-generalization.md#2026-11-12-实施与验收结果)及[不含凭据的验收证据](general-runtime-acceptance.json)。下文保留各历史批次记录。

2026-11-11 16:48（北京时间）验收通过。API 与独立 PostgreSQL 由同一个 Compose 项目管理，研究库从空库迁移初始化。

| 项目 | 运行值 |
| --- | --- |
| 局域网入口 | [API 文档](http://192.168.3.249:18925/docs) · [健康检查](http://192.168.3.249:18925/health) |
| 部署位置 | 249 的 `/mnt/sda1/modarchitect`，权限 `0700` |
| Compose 项目 | `modarchitect-249` |
| 应用容器 | `modarchitect-249-api-1`，镜像 `modarchitect:0.1.0-e04006a58b65` |
| PostgreSQL | `modarchitect-249-database-1`，PostgreSQL 18.4，库名 `modarchitect`，通过 Compose 网络连接 |
| 持久化 | 数据卷 `modarchitect-249_research_data`，容器内数据目录 `/var/lib/postgresql/18/docker` |
| 数据库角色 | `modarchitect_migrator` 持有表，`modarchitect_app` 原生登录并仅有应用所需权限。两个角色均为非超管且无 `BYPASSRLS`。 |

## 制品和配置

安装 wheel 的 SHA-256 为 `e04006a58b654cd5776145b4dad20cf2d18c3f835578e3c186933ac79df9123f`。应用镜像配置摘要为 `sha256:119f86c7f852116408044689afb87c71efdb5702383f1c24cc39e8db7e63970a`。PostgreSQL 来源镜像摘要为 `sha256:f7ce845ee6873dd84be93c9828fe0d1fab0f9707dc9ac569694657398b290bce`，运行平台镜像配置摘要为 `sha256:77adef0f455dbfddbe70e501ded6b5ea439472e0bbb9447fe37ed18cff875e32`。两个离线镜像归档和校验文件保存在部署目录。

主机生成独立凭据。`database.env` 保存数据库初始化配置，`migration.env` 保存迁移连接，`api.env` 保存应用连接和业务 Key，配置文件权限为 `0600`。应用和数据库容器均为 `unless-stopped`。数据库端口仅供 Compose 网络内的服务访问。

## 首次启动和复核

在部署目录执行。首次初始化由 [init-roles.sql](init-roles.sql) 建立角色，迁移后通过 [app-grants.sql](app-grants.sql) 授予应用权限。

```sh
cd /mnt/sda1/modarchitect
docker compose config --quiet
docker compose up -d --wait --wait-timeout 100 database
docker compose run --rm -T migration </dev/null
docker compose exec -T database psql -U postgres -d modarchitect -v ON_ERROR_STOP=1 -f - < app-grants.sql
docker compose up -d --wait --wait-timeout 120 api
docker compose ps
curl -fsS http://192.168.3.249:18925/health
```

- 空库迁移版本为 `0001`。核对到 4 条冻结组件版本、0 个资源范围、0 份方案、0 份草稿和 0 个方案版本。5 张受保护的表启用强制行级安全，应用账号通过 PostgreSQL 网络认证。
- 两个容器均为 `healthy`。从本机访问局域网地址，健康检查、API 文档、OpenAPI 和逻辑斯蒂 V4 目录均成功。无凭据访问私有草稿返回 401。
- 在 249 应用容器内用本批业务 Key 复查，V3 和 V4 的准确目录与文件导入通过，V4 草稿合同检查通过。缺少真实身份端配置时，带委托的私有请求返回 503。

企业身份、选地服务和真实调度按后续接入步骤验收。日常核对使用 `docker compose ps`，需停用 API 时在部署目录执行 `docker compose stop api`。

## 设计器演示更新

2026-11-11 17:13（北京时间），[模型设计器](http://192.168.3.249:18925/designer/) 已发布。应用首页跳转到演示。新 wheel SHA-256 为 `303bec09e2cf3f9d644405577168699620c32eb1e8031eceac6e3881e672311d`，运行镜像为 `modarchitect:0.1.0-designer-303bec09e2cf`，镜像配置摘要为 `sha256:39e546647e1faa7dbf7d55f8ed9e8ff59150918154163a320c2d9f2847fdb925`。

候选镜像先在项目网络内通过数据库登录、公开方案检查和私有接口鉴权，然后执行 `docker compose up -d --no-deps --wait --wait-timeout 100 api`。发布后两个容器均为 `healthy`，数据库容器 ID 与发布前一致，迁移版本为 `0001`，草稿数为 0。原版配置和新版镜像归档保存在 `/mnt/sda1/modarchitect/releases/designer-303bec09e2cf/`。回退时恢复其中的 `previous.env`，再只重启 API。 [演示验收](../../model-designer-demo.md)

## 空白画布更新

2026-11-11 17:39（北京时间）发布。运行镜像为 `modarchitect:0.1.0-editor-f77ee03c64ba`，wheel SHA-256 为 `f77ee03c64baf892d32de99952e9736496695bceb9e9732926df40ddc06861fb`，镜像配置摘要为 `sha256:5800355187d1db4d0c306f9492142530a5fab528e6a08e5e54df83adb3598a4e`。

候选镜像通过数据库连接、样例校验和私有接口 401 检查。执行 `docker compose up -d --no-deps --wait --wait-timeout 100 api` 后，两个容器均为 `healthy`。数据库容器 ID 与发布前一致，迁移版本为 `0001`，数据库草稿数为 0。用 Chrome 复测从空白搭建、校验、浏览器保存与刷新恢复、JSON 往返和手机触屏连线。归档与 `previous.env` 位于 `/mnt/sda1/modarchitect/releases/editor-f77ee03c64ba/`。回退时恢复其中的 `previous.env`，再只重启 API。 [设计器](http://192.168.3.249:18925/designer/) · [空白画布验收](../../model-designer-demo.md#空白画布验收)

## 多变量与多目标更新

2026-11-11 18:46（北京时间）发布。运行镜像为 `modarchitect:0.1.0-research-377c0652126a`，wheel SHA-256 为 `377c0652126ab243d53944b3434e8b444dcca395f296cbced7ede34550ec2674`，镜像配置摘要为 `sha256:457c1234174da824f17b0baa8ef21bceb286499630ab051a0b68b87e536fdac6`。

候选应用在项目网络内通过数据库登录、目录、历史样例及私有接口鉴权检查。使用项目迁移角色运行 `modarchitect-db`，独立库升级到 `0002`，保留原四个逻辑斯蒂版本并登记 `multivariate_linear_regression@1`。发布后两个容器均健康，数据库容器 ID 与发布前一致，库内草稿为 0。

独立回归容器以只读输入、无网络和资源限额跑出两个合成预测值 41 和 48.7，并复核成果 SHA-256。浏览器从空白完成四输入、双目标配置、校验、保存恢复和 JSON 导入导出。应用及组件归档、校验记录和 `previous.env` 位于 `/mnt/sda1/modarchitect/releases/research-377c0652126a/`。回退应用时恢复 `previous.env` 并重启 API，库内保留已登记的冻结组件定义。 [设计器](http://192.168.3.249:18925/designer/) · [验收](../../model-designer-demo.md#验收记录)

## 模型成果连接更新

2026-11-11 19:38（北京时间）发布。应用为 `modarchitect:0.1.0-chain-60c6c8fca238`，wheel SHA-256 为 `60c6c8fca23881d9887234d5b96010db009ebd3c6538b30f38190bf8a33fa06c`，应用配置摘要为 `sha256:7c7d29ebafba09cd9fc1ff3d87973b59b5941004c48cc2bae26eac0d21055a23`。

新增历史预测和预测合并组件。249 上用三个隔离容器顺序执行串联样例及失败用例，预测 91.48452580 cm，并核对成果摘要。候选 API 核对新旧样例、独立数据库登录和私有接口 401。项目库迁移至 `0003`，共 7 条冻结组件记录。应用和数据库容器均为 `healthy`，数据库容器 ID 与发布前一致。

归档、SHA-256、独立复跑脚本、样例及 `previous.env` 位于 `/mnt/sda1/modarchitect/releases/chain-v1/`。应用回退时恢复 `previous.env` 并重启 API。 [设计器](http://192.168.3.249:18925/designer/) · [串联验收](../../model-composition.md#复跑记录)

## 串联样例可见性更新

2026-11-11 20:00（北京时间）发布应用 `modarchitect:0.1.0-visible-ports-28b3f2d345e0`。wheel SHA-256 为 `28b3f2d345e07b16ee80d71d64b59727c9691de74be778afaf2531f7c75d4c2c`，应用镜像配置摘要为 `sha256:54f3d1db800496e7c59a7ded6e438b3957386ead7c73b64afe0751ad9212d70a`。

无登录浏览器复跑直达链接、组件端口、数据流列表、键盘及触屏连线和本地草稿恢复。公开预览返回 200，私有草稿接口仍要求授权并返回 401。应用与数据库容器均健康，独立库迁移版本为 `0003`。应用归档和回退配置保存在 `/mnt/sda1/modarchitect/releases/visible-ports/`。 [串联样例](http://192.168.3.249:18925/designer/?example=chain)

## 研究运行与模型预测更新

2026-11-11 23:18（北京时间）完成真实服务验收。[多变量研究](http://192.168.3.249:18925/designer/?research=multivariable) · [串联研究](http://192.168.3.249:18925/designer/?research=chain) · [完整验收证据](runtime-acceptance.json) · [功能设计和边界](../../research-execution.md)

应用为 `modarchitect:0.1.0-runtime-831b6018872e-pinned`，wheel SHA-256 `831b6018872ebfac5987d11376c288bf2e958d52245bf4207f1ce37e3b18005c`。249 的镜像配置摘要为 `sha256:b0ff9f574cc41645a7b1f5c1457773b09f8dc8ce22e4327eb4d641b9d3f66024`，OCI manifest 为 `sha256:a22a9dc90a630556d2f40bd391855a52b4d52f8065d623063048066d1ac9e6c0`。本次没有新增应用运行依赖，使用 [Dockerfile.runtime](Dockerfile.runtime) 保留已验过的 Python 依赖层，只替换核对过全部包内源文件的 wheel。首次联网安装的构建因下载缓慢中止，不用于本批部署。

镜像归档、前版配置、迁移前数据库备份、执行登记表及验收证据放在 `/mnt/sda1/modarchitect/releases/runtime-831b6018872e/`。迁移前备份为 `before-runtime.dump`，28609 字节。研究库升级到 `0004`，11 条冻结组件定义，8 张表启用强制行级安全。数据库容器仍为 `8bc6629e6230`，原数据卷和既有目录保留。原生应用登录和迁移登录均不是超管且无 `BYPASSRLS`。

API、Worker 和独立调度消费者使用 [compose.yaml](compose.yaml)。`runtime-api.env` 存工作区签名与内部执行凭据，`runtime-worker.env` 存内部 API 和执行凭据，`runtime-scheduler.env` 存专属海豚账号 token、项目和工作流编号。密钥文件均为 `0600`。`runtime-profiles.json` 只包含已批准制品及端口，绑定为只读，文件权限应为 `0644`，以供容器内非 root 的 API 读取。部署目录保持 `0700`。

Docker Desktop 导出的 OCI manifest 与 Linux Docker 所用镜像配置摘要分别保留。Worker 的 `image` 字段使用 249 实际可解析的准确配置摘要，组件清单的 `manifest_digest` 保留 OCI manifest 摘要。导入归档后逐个 `docker image inspect` 核对，不将两种摘要混用。

### 独立 DolphinScheduler

原有海豚 Master 因系统盘约 97% 占用拒绝消费，初次测试研究保留 `uncertain`。本批为新项目建立独立 DolphinScheduler 3.4.0 Standalone，使用 [scheduler-compose.yaml](scheduler-compose.yaml)，不加入旧集群或修改旧服务配置。

- 镜像配置摘要 `sha256:5d3feccbac2317e738ab8caa68fd4e552d6808080e3cab749fe3f249b8145605`，复用主机已有 DS 3.4.0 发行制品中的 Standalone 入口。
- 调度数据库 `modarchitect_scheduler` 位于本项目专属 PostgreSQL，由独立低权限角色 `modarchitect_ds` 持有，JDBC registry 与 Quartz 均持久化于该库。JDBC URL 使用 `?stringtype=unspecified`，启用 `postgresql` profile，关闭 H2 初始化。启动前运行发行包的 `tools/bin/upgrade-schema.sh`。
- Shell 插件单独复制到本项目的只读插件目录，SHA-256 `792c1633c18d5d63456aa3d370321fa98cbfb501840d1e5f5e0805ed099ae8dc`。原服务仅作为已安装发行制品的读取来源。
- 控制 API 仅在主机 `127.0.0.1:18927`，带随机认证的 Python Gateway 仅在 `127.0.0.1:18948`。初始化管理员默认口令已替换，凭据仅保存在主机 `dolphin-identity.json`，文件 `0600`。应用调度消费者使用专属普通账号 token，不使用管理员凭据。
- 数据、工作与日志分别挂到 `dolphin/data`、`dolphin/work`、`dolphin/logs`。通过 `MANAGEMENT_METRICS_SYSTEM_DISKSPACE_PATHS=/scheduler-data` 指定实际任务使用的大盘监控路径，保留 Master/Worker 的负载保护及默认 80% 磁盘阈值。实测占用 `0.7826165`，空闲约 427.78 GB。该配置来自 [DS 指标实现](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-meter/src/main/java/org/apache/dolphinscheduler/meter/metrics/DefaultMetricsProvider.java) 与 [Spring Boot 路径配置](https://github.com/spring-projects/spring-boot/blob/v2.7.11/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsProperties.java)。
- 专属项目 `189418703706848`，固定工作流 `189418908454624`。Shell 仅用单运行凭据调用项目网络内 `http://worker:8001/execute`，等待计算及结果落库后返回。Worker 没有主机发布端口。

复核运行服务使用以下命令。不会重新初始化凭据或数据库。

```sh
cd /mnt/sda1/modarchitect
docker compose -f scheduler-compose.yaml up -d --wait --wait-timeout 120
docker compose up -d --no-deps --wait --wait-timeout 120 api worker scheduler
docker compose ps
docker compose -f scheduler-compose.yaml ps
```

### 实际结果和重启验证

| 方案 | 训练 / 首次推理实例 | 保存的模型 | 首条新预测 |
|---|---|---|---|
| 多变量、双目标 | 1 / 2 | `01a1cb29-5cd1-71ac-9a8f-0d00ff96f957` | 株高 `91.18013994 cm`，叶面积 `271.61608183 cm2` |
| 历史曲线→因子合并→回归 | 3 / 4 | `01a1cb29-7546-7128-9da1-608f22d77d36` | 株高 `101.83049418 cm` |

四个工作流及对应 Shell 任务均为 `SUCCESS`。串联相邻节点的输出摘要与输入摘要逐边一致。两个模型均以不可变状态登记。推理输入没有目标标签，训练状态没有重新计算。

重启研究 API 和独立海豚后，方案、运行结果及模型摘要均可重新读取。将新输入首行 NDVI 增加 0.02，再使用已有模型完成海豚实例 5/6，株高变为 `91.78013994 cm`、`102.07049418 cm`；两个实例及任务也均为 `SUCCESS`。

这些数值来自合成数据的已知关系，属于工程验收。真实作物精度另用独立采样检验。页面交互未通过浏览器点击验收：工具因无法可靠识别当前 Windows 浏览器网址而中止；前端模块语法、静态资源及页面所用真实 API 已分别验证。

个人工作区由同一浏览器的签名 Cookie 持续识别，当前未接跨设备账号恢复。验收模型属于验收会话；新用户打开上述研究样例会得到自己可编辑、可保存和可运行的副本。成功后可保存自己的模型继续预测。

应用回退时先停本项目 `scheduler` 和 `worker`，恢复本发布目录中的 `previous.env`、`previous-compose.yaml` 并只重建 API。数据库保留已写证据和兼容迁移；不执行删除表的降级。独立海豚可单独停止，保留其元数据库和 `dolphin/` 持久目录。

## 研究者视图与节点布局更新

2026-11-12 00:45（北京时间）完成本批更新。[设计器](http://192.168.3.249:18925/designer/) · [易用性与数学关系报告](../../model-designer-usability-report.md) · [成熟产品研究](../../modeling-usability-product-research.md) · [验收证据](modeling-acceptance.json)

默认入口改为研究目标、因素、模型关系和检验方式；可直接修改名称、问题、目标、因素及截止日期。中间趋势是下游因素，数据配对有对象、日期、缺失和实测性质说明。组件图按真实依赖从左到右分层，参数在模型设置中，跨层数据边用正交通道和箭头；用户可展开精确实现并主动自动整理。

最终应用 `modarchitect:0.1.0-modeling-635a4a9972f8`，wheel SHA-256 `635a4a9972f86b109f538841c9ffc9ff3e7b89377ec147421172f600d166a0a9`。249 镜像配置摘要 `sha256:0d15ee5efdb701274c45a0cd406dc0d4b8a157a7456453a651de70a47d79a231`，OCI manifest `sha256:295c7d424c15b597379735cd38e6b1c1332c293d3118562bd923b13d4eebb1c6`，镜像归档 SHA-256 `31f54cd01a4d6cf314c544dac4ea10abd40929add71ba8e72600b21b20fb0989`。

应用包内 65 个文件与源码逐字节核对，部署后的 HTML、JavaScript 和 CSS 也与本地逐字节一致。43 个生产 Python 文件与前版完全一致，科学镜像及执行登记表保持原制品。本批不新增迁移，数据库仍为 `0004`，容器仍为 `8bc6629e6230`。候选服务先核对数据库登录、工作区、准确执行登记和新资产；更新前停止投递，等运行中的研究完成，再更新本项目 API、Worker 和调度消费者。数据库及独立海豚均保持运行。

验证结果：11 项 Node 逻辑/DOM 测试和 19 项 Python 行为测试通过。实际引导编辑产生的定义通过真实服务合同检查，并完成以下真实执行。

| 研究修改 | 训练实例 | 推理实例 | 结果 |
|---|---|---|---|
| 多变量双目标，删除气温因素 | 8 | 9 | 株高与叶面积各 20 条留出评价、新输入 3 条预测，模型状态保持一致 |
| 历史趋势串联，删除土壤水分因素 | 10 | 11 | 株高 20 条留出评价、新输入 3 条预测，相邻节点成果摘要一致 |
| 改为估测 NDVI | 12 | 13 | 20 条留出评价，按天数、株高、气温生成 3 条 NDVI 预测 |

上述六个海豚实例及对应任务均为 `SUCCESS`。最终应用更新后再次使用保存的串联模型完成推理实例 14，训练状态不变。方案、观测、模型和结果可在同一验收工作区重开。模型归属验收 Cookie，用户打开样例后保存到自己的工作区。

报告先于实现落地。DOM 集成测试覆盖引导入口、变量勾选、名称编辑、展开组件图、按依赖整理、云端保存及数据保留。DOM 不提供真实布局引擎；原生浏览器工具本次仍因当前网址识别不可靠而中止，因此真实浏览器像素、手机触屏和最终视觉效果没有记录为已验收。

最终制品、三份方案的执行证据和本批前配置归档于 `/mnt/sda1/modarchitect/releases/modeling-635a4a9972f8/`。首次候选 `01cf10f1ed45` 与最终包的差别只在配对帮助文字，最终文字按用户实际选择的因素解释。回退使用最终发布目录中的 `previous.env` 和 `previous-compose.yaml`，恢复到本批前的 `runtime-831b6018872e`，保留新增方案、模型和运行记录。

## 四类固定来源输入目录

2026-11-12 更新。[设计器](http://192.168.3.249:18925/designer/) · [系统指标示例](http://192.168.3.249:18925/designer/?research=system) · [旧项目规则审计](../../system-input-component-source-audit.md) · [功能设计](../../system-input-components.md) · [验收记录](input-components-acceptance.json)

目录有 63 项：人工采集 15、第三方平台 18、平台分析记录 21、物联网 9。准确绑定的 33 项可以用于设计；当前工作区只有 `lai`、`agb_kg_ha`、`tuber_dm_kg_ha`、`canopy_cover` 四项标准人工记录具有运行通道。其余分别显示取数接入、点位/单株/样方适配或来源绑定缺失，不能上传数值冒充。新增普通输入采用系统定义，固定代码、名称、单位、方法和来源版本；土壤深度等按来源 Schema 选择。合成演示、历史私有输入和上游派生指标分别保留。

训练冻结输入来源清单，模型保留训练来源，预测形成当次来源而不覆盖训练证据。观测列名也须与准确目录一致。新增因素后的模板按当前配方补列，已有数值保留、新值留空，并提示补齐。

最终应用为 `modarchitect:0.1.0-inputs-3ce6e3db84ca`，wheel SHA-256 `3ce6e3db84cac8027ad204d26259229d8db34102db9dfaa2613d5881e25a00e2`。镜像配置摘要 `sha256:e17957b26db0b7f1822e307f567587eaadf5d99d2d64316922baa178cc7d40f0`，OCI manifest `sha256:0961e3a80db913fa4d367205ade36926d4d14e925e184a8a99ba223bd9965ee1`。70 个包内文件与源码核对；目录制品摘要 `e4affbc231caafb4a89c60e61fa950d573c62e2b90cec93db990c55ce03d97a0`，保留原始合同和源文件证据。未新增运行依赖、数据库迁移或科学镜像，数据库仍为 `0004`，原独立数据库容器和数据卷继续使用。

发布前先在项目内部网络运行候选 API，验证目录、运行制品登记、工作区和低权限数据库读取；停止调度投递并等待已提交计算完成后更新本项目 API、Worker 和调度消费者。部署目录 `/mnt/sda1/modarchitect/releases/inputs-3ce6e3db84ca/` 保存镜像、wheel、前版配置、发布前数据库备份和冻结模型/版本摘要。`runtime-profiles.json` 的摘要在发布前后相同。

本机通过 39 项 Python 行为测试、14 项 Node 逻辑/DOM 测试及 11 个 Python 文件头检查。真实服务验收复跑系统双目标研究和原串联研究的保存、重开、训练、模型登记及预测，并检查准确海豚实例和 Shell 任务、来源摘要、模型状态及跨工作区隔离；编号和完整结果以验收 JSON 为准。发布前的冻结模型和方案版本逐项核对摘要保持不变。

这些数值是构造数据的工程验证。人工通道是本工作区按标准填写/导入，不表示已连接业务系统表单。第三方、平台分析与物联网真实业务取数尚未接通；点位株高、单株叶面积没有被改成地块观测。原生浏览器工具仍因网址识别不可靠而停止，真实像素和手机布局未验收。

回退时停本项目调度消费者、等活动运行结束，再使用该目录的 `previous.env` 和 `previous-compose.yaml` 重建本项目 API、Worker、调度消费者。保留数据库和新增证据，不降级或删除表。首次验证批次 `inputs-df10500d370c` 保留为归档，最终版进一步清除了未绑定来源的人工方法占位，不改变科学制品。

## 2026-11-16企业保存接入（本机隔离验收）

新增企业模板、模型读取和不可变保存回执；迁移0010。Python125通过、前端34通过。此记录在本机独立PostgreSQL验收，未更新249服务。

[设计及命令](../../business-design-saving.md) · [curl证据](business-curl-acceptance-20261116.json) · [迁移约束](business-save-migration-acceptance-20261116.json) · [业务接入文档](../../../docs/business-api-integration.md)
