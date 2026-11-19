# 每日研究任务的 DolphinScheduler 接入核对

2026-11-13。仅作一手契约研究；未修改运行代码、数据库或线上调度。与[研究输入及发布改造报告](research-template-inputs-and-model-publication-review.md)配套。

版本说明：前九节的一手源码以 Apache `3.4.1` 标签核对。追加实查发现 249 安装的 API/service JAR 内 `pom.properties` 为 **3.4.0**，不能把源码标签当作实际部署版本；实际字节码、序列化及部署依据见第十节。需由发布验收最终登记准确镜像/制品，不能只按旧文档的“3.4.1”判断。

## 1. 现状与接入选择

当前[投递器](../modarchitect/runtime/scheduler.py)每两秒查看持久队列，向海豚调用 `executors/start-workflow-instance`。这是单次实例提交，不是每日 cron。已有准确 `run_id` 与一次性领取凭据不适合直接写进每日计划重复使用。

已采用首期方案：新增一个真正由海豚每日 02:00（`Asia/Shanghai`）触发的**日研究分配工作流**，传入准确逻辑触发时刻与海豚实例身份，平台按已登记研究的观察范围、状态、权限，持久化每个研究/日期的唯一批次，再驱动原有独立采集与计算工作流。所有研究仍由海豚定时触发，平台只作业务筛选、冻结和幂等，不另起系统 cron 或无限循环冒充定时调度。

用户已确认：每日按前一完整业务日计算。观察日期为闭区间 `[S,E]` 时，触发日期为 `[S+1,E+1]` 每日 02:00；首次覆盖 S，最后在 E+1 生成 E 的报告。平台批次按 **研究实例 + observation_day** 唯一，准确计划修订作为该批次冻结内容，不因同日变更计划而意外重复生成另一份默认日报。

这样保留平台方案准确版本、多租户授权和来源门禁，避免每启用一个研究就创建一份相同 Shell 定义及凭据。权衡是海豚日分配实例与每个研究采集/计算实例是不同身份，数据库/UI 必须分别记录。若改为每研究独立海豚工作流，则每研究都有专属 schedule，但需承担创建、变更、停用、失败对账与规模成本；这不是完成业务规则的捷径。

## 2. 已核实的 HTTP 契约

API 基址后的共同前缀为 `/projects/{projectCode}`；使用当前项目受控 `token` 请求头。以下均为表单参数，不是把 JSON 直接作为整个请求 body。

| 动作 | 路径及主要字段 |
| --- | --- |
| 创建 | `POST /schedules`：`workflowDefinitionCode`、`schedule`（JSON 字符串）；可显式固定 `warningType=NONE`、`warningGroupId=0`、`failureStrategy=END`、`workerGroup=default`、`tenantCode`、`environmentCode=-1`、`workflowInstancePriority=MEDIUM` |
| 查询/创建对账 | `GET /schedules?workflowDefinitionCode={code}&pageNo=1&pageSize=100`；成功 `data` 是分页对象，检查 `total` 和 `totalList` |
| 启用 | `POST /schedules/{id}/online`，成功数据为 `true` |
| 暂停 | `POST /schedules/{id}/offline`，成功数据为 `true` |
| 修改 | `PUT /schedules/{id}`，传 `schedule` 及执行设置；先暂停再修改，然后启用 |
| 预览 | `POST /schedules/preview`，表单 `schedule`；只用于辅助检查，不能代替真实调度实例证据 |

端点、字段与状态来自固定标签的[控制器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/SchedulerController.java#L97-L227)。参数实体为[ScheduleParam](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/dto/ScheduleParam.java#L23-L37)。

```json
{
  "startTime": "2026-11-14 00:00:00",
  "endTime": "2026-12-01 23:59:59",
  "timezoneId": "Asia/Shanghai",
  "crontab": "0 0 2 * * ?"
}
```

这是观察 2026-11-13 至 2026-11-30 时相应触发范围的内层字符串示例，不是每个研究都必须创建该截止日期的公共扫描计划。公共日分配计划可有部署级期限；各研究自己的观察区间必须由平台准确校验。

创建时验证工作流、租户、cron 与日期，初始状态为 `OFFLINE`；一个工作流只允许一份 schedule。重复创建会得到 `SCHEDULE_ALREADY_EXISTS`，成功 `data` 含日程对象及 `id`。已在线日程不能直接修改；启用要求工作流也在线。创建/启用超时先按准确工作流查询并核对内容、状态，再决定是否继续，不能盲目新增。[服务实现](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/SchedulerServiceImpl.java#L142-L205)、[启停及修改约束](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/SchedulerServiceImpl.java#L624-L727)。

## 3. 时区、起止与漏跑

实现将 API 保存的起止墙钟时间从服务器默认时区转换到 schedule 时区，再设置 Quartz 的 `startAt/endAt` 和 `inTimeZone`；不要在调用侧随意再减 8 小时。真实环境需以预览、持久日程字段及实例 `scheduleTime` 三者核对。若起点已早于当前时间，构建器将起点改为当前时刻；重启/重新上线后不能假定所有历史日期会被补齐。构建器也声明忽略 misfire，平台仍应使用持久日期批次检查遗漏。[Quartz 构建器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-scheduler-plugin/dolphinscheduler-scheduler-quartz/src/main/java/org/apache/dolphinscheduler/scheduler/quartz/QuartzCornTriggerBuilder.java#L59-L85)。

起止参数是调度时间界限，不是农业观测日期合同。平台应独立核对业务日期闭区间，并测试起始日、末日、单日区间、启用时已过 02:00 和跨日延迟。若末日仍要 02:00 触发，不能把 `endTime` 设成末日 00:00。示例采用末日 23:59:59，避免末日 02:00 被排除；不要以不明边界时刻代替应用层日期约束。

已确认的观察区间 `[S,E]` 与触发日 `[S+1,E+1]` 严格区分：正常触发日 D 的 `observation_day=D-1`，只为 `S<=observation_day<=E` 建立批次，E+1 必须处理 E。来源发布延迟可能进一步影响可用截止；计划逻辑日不因迟到而改变，缺少 E 数据则记录待资料，按明确补齐政策继续，不能把结果日期换成当前日期或填补未知值。

## 4. 获取逻辑调度时间，而非 Worker 当前时间

| 内置参数 | 3.4.1 的含义 |
| --- | --- |
| `${system.datetime}` | 逻辑调度时刻，格式 `yyyyMMddHHmmss`；3.4.1 实际参数装配会用无显式时区格式覆盖，不能无条件当作 Shanghai 字符串，见第 8 节 |
| `${system.biz.curdate}` | 调度日，格式 `yyyyMMdd` |
| `${system.biz.date}` | 调度日前一天，格式 `yyyyMMdd`，不得再重复减一天 |
| `${system.workflow.instance.id}` | 本次海豚工作流实例身份 |

上述定义来自[固定版本参数文档](https://github.com/apache/dolphinscheduler/blob/3.4.1/docs/docs/en/guide/parameter/built-in.md#basic-built-in-parameter)。[BusinessTimeUtils](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/utils/placeholder/BusinessTimeUtils.java#L44-L73)在 `runTime` 非空时用它计算日期并按传入时区格式化；若它为空会退回系统现在，因此不能接受缺失逻辑时间后自行补当前日期。

Quartz 任务使用 `context.getScheduledFireTime()`，不是进程开始的 `getFireTime()`，将其和时区传给 Master；后者写入实例 `scheduleTime`，另以当前时刻记 `startTime`。迟到执行因此仍应归原逻辑日，不应归实际启动日。[Quartz 触发](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-scheduler-plugin/dolphinscheduler-scheduler-quartz/src/main/java/org/apache/dolphinscheduler/scheduler/quartz/ProcessScheduleTask.java#L54-L111)、[实例构造](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/WorkflowScheduleTrigger.java#L43-L91)。

首期建议 Shell 把已替换的 `${system.biz.curdate}`（纯调度日）与 `${system.workflow.instance.id}` 传入受信日分配入口；服务端按已经固定的 02:00 / Asia/Shanghai 合同构造逻辑触发时刻，并核对准确海豚工作流及 command 时区。不要把 `${system.datetime}` 无条件解析为上海时刻。正常定时不接受前端自报日期；补跑走显式授权入口，不能靠任意请求修改“今天”。验收中还需确认精确替换、时区、失败重跑与逻辑时间保持。

## 5. 工作流版本与串行并不等于业务去重

日程仅关联工作流 code；每次 Quartz 触发都读取当前在线定义的 version，再把 code/version 传给 Master。平台研究应另行冻结准确方案、计算组件与来源版本，不能把“定时器仍是原 code”当成“研究仍执行初始版本”。应受控发布日分配工作流的修改，留下运行时准确版本。[触发时版本选择](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-scheduler-plugin/dolphinscheduler-scheduler-quartz/src/main/java/org/apache/dolphinscheduler/scheduler/quartz/ProcessScheduleTask.java#L72-L111)。

Master 在事务内创建工作流实例，`PARALLEL` 写普通命令，串行模式写 `SERIAL_WAIT` 和串行命令。无论哪种模式都会产生新实例；串行不按本平台研究/日期去重。公共分配器可以短任务运行，最终必须依靠数据库唯一批次及原子认领防止重发和重试造成重复业务计算。[触发事务](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/AbstractWorkflowTrigger.java#L55-L71)、[执行模式枚举](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/enums/WorkflowExecutionTypeEnum.java#L25-L30)。

## 6. 单次启动与补跑的区别

`POST /executors/start-workflow-instance` 的 `START_PROCESS` 分支使用 `startParams`，成功返回一个实例整数 ID 列表；该分支**没有把入参 `scheduleTime` 送入触发请求**。不能因为在表单填了某历史时刻，就声称按该逻辑日期执行。`COMPLEMENT_DATA` 分支才解析 `scheduleTime` 的补跑范围/列表。[单次与补跑分支](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/ExecutorController.java#L119-L188)。

因此功能测试可通过平台的显式受权补齐机制验证日期边界，真正定时验收必须观察 `SCHEDULER` 实例及正确的 `scheduleTime`。若临时改为短周期验证自动触发，应明确记录测试频率并恢复 02:00，不能把短周期或手动触发当成已经观察到每日凌晨 02:00。

## 7. 本平台需要落实的不变量与最小验收

- 按研究实例/观察业务日唯一建立批次，并冻结其准确计划修订；扫描重试和海豚重复触发返回原批次。每天新建采集/运行，不复用已成功 `run_id`；同日改计划不能静默产生第二份默认日报。
- 研究停用、观察区间结束和授权撤销后，不因仍在运行的公共扫描工作流继续创建任务。查询无到期研究时允许成功空批次；这个实例不伪装成农业结果。
- 采集成功、输入齐备、计算成功、结果可发布分别记录；来源未到和失败均有证据。HTTP 超时不直接推定海豚未接受，未知提交继续按本项目已有对账规则处理。
- 服务重启或漏掉某夜，扫描应在有界策略下识别之前遗漏日期，而不是只看 Worker 的当前日；是否自动补跑及资料可用范围是平台业务规则。
- 数据库保留日分配实例、研究批次、独立采集/计算实例、准确输入与输出的关联；UI 用有效观测日期及实际模型版本绘图，滚动窗口重复日期不直接拼接。
- 验收应包含真实启用的 02:00 日程、正确时区、真实自动触发证据、观察首尾日、延迟启动、重复触发、来源延迟、暂停/过期、服务恢复与授权隔离。没有观察到真实 02:00 时刻则单列待观察，不伪造通过。

除前述 3.4.1 一手源码及已有仓库实现，本记录不依赖第三方教程，也不把通用调度能力视为平台每日研究业务已经完成。

## 8. 追加核查：`system.datetime` 的时区覆盖问题

**确有风险。** 即使 Quartz 日程的 `timezoneId=Asia/Shanghai`，也不能只凭此条件认定最终 `${system.datetime}` 为上海墙钟；当 Master JVM 默认 UTC、无该线程的时区上下文时，上海 2026-11-14 02:00 的逻辑实例会把该变量输出为 `20261113180000`。若应用再当作上海时间，会错到前一日。

已沿 3.4.1 的实际链路核对：

1. [TaskExecutionContextFactory](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/runner/TaskExecutionContextFactory.java#L153-L165)在 Master 调用参数装配。
2. [CuringParamsServiceImpl](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-service/src/main/java/org/apache/dolphinscheduler/service/expand/CuringParamsServiceImpl.java#L171-L230)先从实例 `commandParam.getTimeZone()` 取得日程时区，以它生成 built-in 日期。
3. 同一方法后续调用 `preBuildBusinessParams()` 并覆盖同名项；该方法对准确 `scheduleTime` 使用 `DateUtils.format(..., null)` 重新生成 **`system.datetime`**。它不同时覆盖 `system.biz.curdate/date`。[覆盖实现](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-service/src/main/java/org/apache/dolphinscheduler/service/expand/CuringParamsServiceImpl.java#L318-L330)。
4. [DateUtils](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/utils/DateUtils.java#L59-L66)对空显式时区采用线程时区，否则采用 JVM 默认；[格式分支](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/utils/DateUtils.java#L116-L123)没有自动再次读取 Schedule。
5. Shell 插件只消费已准备好的字符串 map，不以 Worker 操作系统 `TZ` 修正它。因此只改 Shell/Worker `TZ` 不能修复 Master 已生成的日期。[ShellTask](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-task-plugin/dolphinscheduler-task-shell/src/main/java/org/apache/dolphinscheduler/plugin/task/shell/ShellTask.java#L54-L61)。

一般的 `${...}` 替换直接采用字符串；`$[...]` 的日期表达式又会通过无显式时区的 parse 分支解释 `system.datetime`，也不是可靠的“换个写法就自动纠正”。[ParameterUtils](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-task-plugin/dolphinscheduler-task-api/src/main/java/org/apache/dolphinscheduler/plugin/task/api/utils/ParameterUtils.java#L59-L79)。

### 首期稳妥处理

- 当前需求只需固定时区的每日批次，传 `${system.biz.curdate}` + 实例 ID 即可；其正常日程 built-in 使用 `commandParam.timeZone=Asia/Shanghai`，没有上述第二次覆盖。禁止项目/全局/局部参数或 varPool 自定义同名 `system.*` 项，否则参数优先级可以覆盖 built-in。
- 平台按调度日 D 构造 `D 02:00:00+08:00`，以 D−1 作为观察日；对缺失、未知时区、非预期工作流或未知触发方式明确拒绝，不用当前时间补造。
- 核验实例详情时，除预期 workflow code 外，还要核对准确 command、非空 `scheduleTime` 和 `commandParam.timeZone`。详情 API 的日期字段若是无偏移字符串，不得自动当 UTC 或上海；须先确认该 API 的日期序列化合同/受控账号时区，再转换，或采用下面的毫秒时间。
- 若继续传 `system.datetime`，必须显式固定并验证 **Master JVM** 的 `-Duser.timezone=Asia/Shanghai`，同时验证实际参数输出，而非只查看容器 `date` 或 Worker `TZ`。本次只读研究没有检查或改变 249 JVM 配置，不宣称该前提已满足。

### 需要精确瞬时时间时

更一般的接入可让受控任务插件直接传 `TaskExecutionContext.getScheduleTime()` 的 **epoch 毫秒**。Master 的 [TaskExecutionContextBuilder](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/runnable/TaskExecutionContextBuilder.java#L91-L99)从实例 Date 构造该字段；[DateUtils.dateToTimeStamp](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/utils/DateUtils.java#L628-L635)直接返回 `Date.getTime()`。接收端先按 UTC epoch 建 aware 时间，再转换 Asia/Shanghai，不受无时区字符串影响。**不能臆造现成 `${system.schedule.epoch}` Shell 参数；它不是本次已核实的 built-in。**

针对本问题的真实验收至少比较：Quartz 日程时区、实例逻辑日期、Shell 中 `system.biz.curdate/date/datetime` 三个实际值、平台保存的 aware 触发时间及观察日。UTC Master 场景应证明日期仍准确，或通过显式部署约束拒绝不满足的环境；测试不得只在所有机器碰巧同一时区时通过。

## 9. 实例详情、命令与回调的可实现核验

### 准确读取地址与实际字段

当前部署内部地址为：

```text
GET http://127.0.0.1:18927/dolphinscheduler/projects/{projectCode}/workflow-instances/{instanceId}
token: <受控调度账号凭据>
```

例如 2026-11-13 只读实查本项目 `projectCode=189418703706848`、实例 `160` 成功。响应为 `code=0`、`data` **对象**，不是实例列表。控制器调用项目/准确实例校验，服务读取其准确 code/version 并附入 DAG。[控制器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/WorkflowInstanceController.java#L191-L202)、[详情服务](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/WorkflowInstanceServiceImpl.java#L227-L251)。

| `data` 字段 | 线上确认的类型与含义 |
| --- | --- |
| `id` | 整数实例 ID，必须与路径及回调相同 |
| `projectCode`、`workflowDefinitionCode`、`workflowDefinitionVersion` | 数值；核对受控项目、获准日分配工作流及准确版本 |
| `commandType`、`historyCmd`、`state` | 字符串；实查旧单次实例分别是 `START_PROCESS`、`START_PROCESS`、`SUCCESS` |
| `scheduleTime` | 日程时刻；实查手动实例为 `null`，不能以 `startTime` 顶替 |
| `startTime`、`endTime` | API 时间表示；实查 `startTime` 是无偏移字符串 `2026-11-12 23:06:48`，不自带 UTC/Shanghai 证明 |
| `commandParam` | **JSON 字符串**，需再解析一次；实查键为 `commandType/subWorkflowInstance/startNodes/commandParams/timeZone`；准确键为驼峰 `timeZone` |
| `globalParams` | **JSON 字符串**，内容为 Property 数组；实查旧计算实例包含 `run_id/dispatch_token`，普通日志不得输出其值 |
| `dagData` | 对象，实查含 `workflowDefinition`、`workflowTaskRelationList`、`taskDefinitionList` |
| `dagData.taskDefinitionList[].taskParams` | 该准确任务的参数，按返回的字符串/对象表示解析；`localParams` 是自定义局部 Property 数组 |
| `varPool` | 实例变量池，另有每任务变量池；不可自动当作已批准系统参数 |

这些名称也与[WorkflowInstance 实体](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-dao/src/main/java/org/apache/dolphinscheduler/dao/entity/WorkflowInstance.java#L48-L145)相符。以上实查只输出字段名、类型和非秘密运行元数据，未输出原始全局参数或令牌。旧实例不是新日分配工作流的自动触发证据。

**勿用 `GET /workflow-definition/{code}/versions/{version}` 来“只读历史版本”。3.4.1 此端点实际执行版本切换。** 核验应采用实例详情中关联的准确 `dagData`，而不是误触线上切换。[有副作用的版本端点](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/WorkflowDefinitionController.java#L285-L300)。

### 命令名、代码与重跑

| 命令 | 内部枚举代码 | 用途 |
| --- | --- | --- |
| `START_PROCESS` | 0 | 手动新建，不是正常定时回调依据 |
| `COMPLEMENT_DATA` | 5 | 显式补数 |
| `SCHEDULER` | 6 | Quartz 正常定时触发 |
| `REPEAT_RUNNING` | 7 | 重跑已有实例 |
| `START_FAILURE_TASK_PROCESS` | 4 | 从失败任务恢复 |
| `RECOVER_SUSPENDED_PROCESS` | 3 | 暂停恢复 |
| `RECOVER_TOLERANCE_FAULT_PROCESS` | 2 | 故障容错恢复 |

API 实查命令为字符串，枚举中的数字是内部 `code`，不能未经核对就拿数字 6 与 JSON 字符串比较。[CommandType](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/enums/CommandType.java#L44-L78)。`commandParam.commandType` 亦为类型名，其多态合同明确登记 `SCHEDULER/START_PROCESS/COMPLEMENT_DATA/...`；共同参数定义有 `commandParams` 和 `timeZone`。[ICommandParam](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-extract/dolphinscheduler-extract-master/src/main/java/org/apache/dolphinscheduler/extract/master/command/ICommandParam.java#L25-L49)、[共同参数](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-extract/dolphinscheduler-extract-master/src/main/java/org/apache/dolphinscheduler/extract/master/command/AbstractCommandParam.java#L29-L36)。

正常日回调只接受已登记 `SCHEDULER` 来源。若要允许整工作流补数/重跑，须显式验证对应授权、准确原实例/补数日和命令历史，不能把任意 `START_PROCESS` 或恢复命令一概当作正常自动触发。任务自身的有界重试与人工重跑整个工作流分别验收。

### 首期 `trigger_date` 回调门禁

已确认使用 **`trigger_date=YYYYMMDD`（来自 `${system.biz.curdate}`）+ `instance_id`**；该日期是触发日 D，观察日再取 D−1。若接口将字段命名为 `business_date` 却传此值，容易混同已经 D−1 的 `${system.biz.date}`，故采用 `trigger_date`。

可实现的核验顺序：

1. 以内部执行凭据进入，严格校验日期和正整数 ID；从受控 DS 基址/项目读取实例，不允许请求自报主机/项目或回传一个伪造详情对象。
2. 解析上述双层 JSON，核对 ID、项目、获准 workflow code/version；日分配版型必须是已登记的固定 Shell 图及准确参数合同。`commandType`、`commandParam.commandType` 均须满足该入口允许的真实触发方式；正常新定时要求 `SCHEDULER`、非子工作流、非空 `scheduleTime`。
3. 要求 `commandParam.timeZone == "Asia/Shanghai"`，不接受缺省/未知值。需要同时查询日程时，用 `GET /schedules?workflowDefinitionCode=...&pageNo=1&pageSize=100` 核对 `timezoneId` 和 cron；**实例自己的 commandParam 才是该次触发的冻结时区，当前日程状态不能倒推历史。** 已受理合法实例随后日程离线，也不能仅凭当前 OFFLINE 就把它改成非定时。
4. 检查命名空间覆盖，以下参数的**名称**不允许 `system.*`：实例 `globalParams[].prop`、准确 DAG 的全局/局部 `prop`、`commandParam.commandParams[].prop`、项目参数 `paramName`、运行时变量池 `prop`。值中正常引用 `${system.biz.curdate}` 是允许的，不是覆盖定义。
5. 项目参数可分页读取 `GET /projects/{projectCode}/project-parameter?pageNo=1&pageSize=100`，必须遍历完整分页；线上实查本项目 `data.total=0`。此接口的字段是 `paramName` 等，不是 `prop`。[项目参数控制器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/ProjectParameterController.java#L115-L134)。
6. 采用无上游的固定单 Shell 触发任务、拒绝额外 OUT/启动参数和 `varPool`，能使首期核验小而明确；若未来允许多节点/上游变量，则按准确任务实例核对变量池后再授权回调。只看 workflow code 而允许任意新版本改 Shell 不够；单查当前项目参数也不能证明历史上从未覆盖，需要受控编辑权限及已登记版本/合同的证据。
7. 合同固定为 Shanghai 02:00，服务端据 `trigger_date` 构造带 `+08:00` 的逻辑时间；其日值与已确认实例逻辑日相符后，再创建 D−1 的唯一观察批次。精确核对 `scheduleTime` 时须使用已验证的 API 时间合同或 epoch，禁止读取 `startTime` 或本系统当前时间替代。

上述检查是实施建议，尚未在本文件内实现；回调层最终应把获准的日期、准确实例/版本与检查依据交给同一权威调度领域流程。凭据/详情查询失联返回可恢复错误，不应因无法核验而按前端日期继续执行。

## 10. 实际 Date 序列化，以及如何把日回调绑定到准确实例时刻

### 一手源码与实际部署的交叉核对

`scheduleTime` 非空只能证明存在一个日程时刻，**不能**证明它对应调用方提供的 `trigger_date`；必须解析为 aware 时间并严格比较平台预期时刻。

真正决定此 API 日期字符串的，是 service 包内的 Spring `@JsonComponent`：[DateJsonSerializer](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-service/src/main/java/org/apache/dolphinscheduler/service/json/DateJsonSerializer.java#L29-L34)。它直接调用 `DateUtils.dateToString(Date)`；[3.4.0 同名实现](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-service/src/main/java/org/apache/dolphinscheduler/service/json/DateJsonSerializer.java#L29-L34)亦相同。此自定义序列化路径不以 `spring.jackson.time-zone` 决定 Date 输出时区。

Token 认证的 [LoginHandlerInterceptor](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/interceptor/LoginHandlerInterceptor.java#L57-L87)将该用户的 `timeZone` 写入线程上下文；[DateUtils](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/utils/DateUtils.java#L59-L66)优先采用此值。请求结束移除上下文。**因此详情 Date JSON 取 Token 用户的时区，不是 schedule 时区，也不能根据容器 TZ 或 Spring YAML 单独推断。**

2026-11-13 的只读实查（未修改用户、容器或任何配置）：

| 项目 | 实际结果 |
| --- | --- |
| 专属容器 | `modarchitect-dolphin-249-dolphin-1`；Java 进程 `/proc/12` |
| 安全环境 | `TZ=Asia/Shanghai`、`SPRING_PROFILES_ACTIVE=postgresql`；未发现显式 `-Duser.timezone` 或 `spring.jackson` 启动覆盖 |
| YAML | `standalone-server/conf/application.yaml` 的 Jackson 为 UTC，格式 `yyyy-MM-dd HH:mm:ss` |
| 当前 Token 用户 | `GET /users/get-user-info` 返回 `timeZone=Asia/Shanghai` |
| 详情实例160 | `startTime="2026-11-12 23:06:48"`，无偏移；手动实例的 `scheduleTime=null` |
| 请求时区头实验 | 不带头、`timezone/X-Timezone=UTC`、`timezone/X-Timezone=Asia/Shanghai`，上述 `startTime` 均相同。未发现可用于固定输出时区的这类请求头合同 |
| 实际安装版本 | `/opt/dolphinscheduler/libs/dolphinscheduler-api-3.4.0.jar`，其 `pom.properties.version=3.4.0`；service 包亦为3.4.0 |
| 实际序列化字节码 | 用只读 `javap` 核对 `DateJsonSerializer.serialize()`，确实调用 `DateUtils.dateToString` 再写字符串，与前述一手源码一致 |

实际 API JAR SHA-256：`39a995bfa1860efac7372231eae5711178c737846f4d1ba7d7e6044931574176`；service JAR SHA-256：`a05203931177a509692caa5a3a559b8ec8cfd2b6dc5747a9018203508e77f0fd`。它们是本次容器实读的制品身份，不表示已经逐字节核验完整发行包。一次后续 SSH 查询出现连接超时；前述已成功读取的配置、API 和字节码证据仍分别成立，未将超时解释成平台业务失败。

### 首期已决定的接入门禁：不修改 DS 用户时区

使用同一个受控调度客户端和 Token，按顺序执行：

1. `GET /users/get-user-info`，要求成功、主体身份有效，`data.timeZone` **严格等于 `Asia/Shanghai`**；不满足则明确拒绝当前接入，不调用用户修改接口。
2. `GET /projects/{projectCode}/workflow-instances/{instanceId}`，同时核对第九节的项目、工作流准确版、命令、参数及非空 `scheduleTime`。
3. 再以相同客户端/Token 读取 `/users/get-user-info`，要求身份与时区前后一致且仍为 Shanghai。缺失、漂移、查询失败都不得继续使用前端日期运行。
4. 详情 `scheduleTime` 必须严格符合已核实的 `yyyy-MM-dd HH:mm:ss` 合同；按该已验证的 **Token 输出时区**附加现代 Shanghai 的 `+08:00`，转为 UTC，与平台由 `trigger_date + 02:00 +08:00` 得出的 `tick.scheduled_at/expected_at` **严格相等**，不能只比较日期或只检查非空。
5. 一致后才允许建立观察日 D−1 的唯一批次；不一致拒绝并记录实例身份/错误类型，勿记录包含凭据的原始参数。

例如 `trigger_date=20261114` 的预期为 `2026-11-14T02:00:00+08:00`（UTC `2026-11-13T18:00:00Z`）。详情在已验证 Shanghai 用户下必须为 `2026-11-14 02:00:00`；如果它属于另一日、另一时刻，即使工作流相同也必须拒绝。固定 `+08:00` 是本期现代研究日期合同，不能泛化为历史所有年代的 Shanghai 夏令时规则。

这项门禁是受控接入账号时区稳定的运维约定，前后读取可发现通常配置漂移，不是把可变外部账号状态声称为跨请求原子事务。该账号不得由其他应用并发修改时区；如果无法提供此稳定约定，需改用准确 epoch 或带偏移的扩展接口，不能为了兼容修改共享 DS 用户时区。当前249已符合 Shanghai 条件，无需修改任何用户。

### 正常定时与受权补数的 JSON 合同

实际部署的 `ScheduleWorkflowCommandParam.getCommandType()` 字节码返回 `SCHEDULER`；官方 [BackfillWorkflowCommandParam](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-extract/dolphinscheduler-extract-master/src/main/java/org/apache/dolphinscheduler/extract/master/command/BackfillWorkflowCommandParam.java)返回 `COMPLEMENT_DATA`。本次只读查询未制造新的定时或补数实例，真正动态应答仍由主任务联验记录。

在正常定时中，详情外层 `commandType` 和二次解析后的 `commandParam.commandType` 应为 `SCHEDULER`；补数则两者为 `COMPLEMENT_DATA`，保留真实命令，不能改写成正常定时。`commandParam` 结构仍是 JSON **字符串**；除共同 `timeZone/subWorkflowInstance/startNodes/commandParams` 外，补数有 `backfillTimeList`。[定时构造](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/WorkflowScheduleTrigger.java#L79-L92)、[补数构造](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/WorkflowBackfillTrigger.java#L84-L100)。

公开给海豚执行接口的 `startParams` 是表单中一个 JSON 字符串，可为简单名称/值对象，或 Property 数组；[PropertyUtils](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-task-plugin/dolphinscheduler-task-api/src/main/java/org/apache/dolphinscheduler/plugin/task/api/utils/PropertyUtils.java#L40-L50)先尝试对象转换为 `prop/direct=IN/type=VARCHAR/value` 数组，再尝试原数组。实例 `commandParam` 保存的是转换后的 **`commandParams` 数组**（或没有自定义值时的 null/空数组），不是必须存在一个同名 `startParams` 键。保留名检查须检查这层数组，不应漏查或只检查原请求字段。

本期补数只由 DS 已授权的 `COMPLEMENT_DATA` 发起，不增加公开任意日期触发接口；来源、准确工作流/合同、账户时区及上述时刻相等检查仍适用。补数日期列表按相同的 02:00 上海合同指定，每个观察日仍复用同一唯一批次和冻结范围。错误日期、未来日期、越观察范围、带 `system.*` 覆盖、任意 `START_PROCESS` 伪装，以及时刻不等于该日02:00，均不能因“补数”绕过门禁。

## 11. 取数账户统一来自指定海豚环境，以及 HTTP Worker 的边界

### 已确认要求和实际版本

用户指定取数账户统一取自海豚环境名 **`research-environment`**，不在代码中写账户。以下外部合同直接核对官方 **3.4.0** 源码，与第十节已经读取的实际部署 JAR 版本对应；不是把3.4.1的推论直接当成部署事实。本节调查未读取或展示该环境的配置正文，也未修改 DS 环境、任务、用户或新旧数据库。

2026-11-13 使用既有 `scripts/remote_release.py` 的 `connect()`（本机 `.venv-ops/Scripts/python.exe`）尝试在249只输出环境 `name/code/id`，SSH 连接超时。因此 **尚未确认该名称在本项目专属 DS 地址18927中存在，更未取得实际 code**；不能默认旧 mlgrowth 连接的 DS 与本项目专属实例拥有同一条环境记录。接入时必须使用部署指定的凭据来源 DS，先完成元数据与权限核验，不得为了查不到而复制旧数据库配置或改写旧环境。

### 准确查询接口与精确名称解析

以下路径均相对于受控 `.../dolphinscheduler/`，以已授权 Token 请求。

| 用途 | HTTP合同 | 返回及约束 |
| --- | --- | --- |
| 按名称搜索并分页 | `GET /environment/list-paging?searchVal=research-environment&pageNo=1&pageSize=100` | `data.totalList` 为环境 DTO 数组，`data.total` 为总数。搜索为 SQL `LIKE`，必须完整分页后以 `name == "research-environment"` 精确匹配唯一记录，不能直接取首条。 |
| 取得可见环境列表 | `GET /environment/query-environment-list` | `data` 为环境 DTO 数组，受当前用户可见资源限制；仍须精确名称匹配。 |
| 复核选中的 code | `GET /environment/query-by-code?environmentCode=<code>` | `data` 为单个环境 DTO；ID是数据库行身份，`code` 才是执行参数，不能混用。 |

3.4.0 控制器没有公开 `query-by-name` GET；Service 虽有 `queryEnvironmentByName()`，不能据此臆造 HTTP 路径。[EnvironmentController](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/EnvironmentController.java#L135-L210)、[EnvironmentServiceImpl](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/EnvironmentServiceImpl.java#L148-L270)、[EnvironmentMapper](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-dao/src/main/resources/org/apache/dolphinscheduler/dao/mapper/EnvironmentMapper.xml#L36-L60)。

查询 DTO 会携带 `config`，官方接口没有字段投影参数。运维调查只投影 `name/code/id`，不查看或记录配置正文；真正执行取数时由受控凭据提供器在内存中读取最少必要值，错误日志也不得带原始响应。0条、同名歧义、权限不足、查询失败或名称与code漂移均须明确失败，不能退回本机旧账户。旧项目 `api/services/dolphin_environments.py` 已使用分页搜索后精确名称匹配；它可作为访问方式参考，不能直接复制旧项目部署配置。

### `environmentCode` 的选择与优先级

`POST /projects/{projectCode}/executors/start-workflow-instance` 的表单有 `environmentCode`，默认 `-1`；它进入工作流实例，不等于强制覆盖每个任务。[ExecutorController](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/ExecutorController.java#L139-L187)。

3.4.0 第一次执行时先从任务定义注入，再从工作流实例补空。`EnvironmentUtils` 将 `null` 或 `<=0` 判为空，仅在空时采用后一个值。因此实际优先级为 **任务已选正code → 启动/日程工作流环境 → 未选择**，执行器传正code不能覆盖任务定义中已有的另一正code。[首次任务构造顺序](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/runnable/FirstRunTaskInstanceFactory.java#L48-L53)、[两层注入](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/runnable/AbstractTaskInstanceFactory.java#L77-L109)、[判空规则](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-dao/src/main/java/org/apache/dolphinscheduler/dao/utils/EnvironmentUtils.java#L20-L51)。

若要采用此环境运行海豚 Shell，应核验准确任务版本的 `environmentCode` 和实际任务实例选值；可令任务明确选择已解析code，或让任务留空并采用工作流环境。不能沿用旧任务的未知正code，再声称启动器选择了新环境。`config` 是可变环境配置，不是研究方案或模型的版本化科学合同；轮换账户应在下一次取数时刷新，已封存的科学输入仍保持可追溯。

### 海豚 Shell 的环境不会通过 HTTP 自动进入 Worker

DS Master 按最终任务code读取环境配置，再交给执行上下文；任务执行器将其追加为本次 Shell 的自定义环境脚本。[按code取配置](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/runner/TaskExecutionContextFactory.java#L183-L192)、[Shell环境装配](https://github.com/apache/dolphinscheduler/blob/3.4.0/dolphinscheduler-task-plugin/dolphinscheduler-task-api/src/main/java/org/apache/dolphinscheduler/plugin/task/api/AbstractCommandExecutor.java#L77-L84)。

本项目的实际调用链为：

```text
DS任务Shell（仅本进程有DS环境）
  └─HTTP POST /acquire（acquisition_id、dispatch_token）
      └─独立常驻Worker（Compose runtime-worker.env）
          └─execute_acquisition → 来源适配器
```

证据为 `.ops/source-release/setup_scheduler.py` 的 `rawScript`、`modarchitect/runtime/worker.py` 的 `/acquire`、`modarchitect/input_sources/service.py` 的来源装配和 `coding/deployments/examples/compose.yaml` 的独立Worker。现状Shell未把DS环境加入HTTP请求；HTTP本身也不携带发起进程的环境。仅修改 `environmentCode`，**不能**让适配器中的 `os.getenv()` 获得DS账户。当前 `runtime/scheduler.py` 传 `environmentCode=-1`，源工作流安装脚本又复制旧任务的该字段，这两点都须在实际改造中核验。

### 建议的最小接入：Worker内注入按来源限定的凭据提供器

保留当前采集与研究计算分离及封存身份合同。由 Worker 装配一个可替换的 `SourceCredentialProvider`，通过受控 DS 客户端按部署配置的环境名精确解析；各来源适配器只接收其自身所需的账户对象，不依赖海豚 HTTP、环境脚本文本或进程全局变量。该层与科学变量、来源合同、取数属性分别维护。

- 取数请求仍只传采集身份和授权令牌；用户、研究方案、模型制品不得存放账户值。DS Token、DS地址和环境名属于部署引导配置，提供方账户来自指定DS环境。
- 每次采集采用一次一致的凭据读取，或明确的短时缓存；刷新失败停止采集，不静默使用已失效缓存。旧项目回传配置的30秒缓存可作故障行为参考，时长本身不构成新项目要求。
- 仅解析该适配器**明确允许的键**及已约定的静态赋值语法；禁止 `eval`、`exec`、`source`、`os.environ.update` 或执行整个环境脚本。无法解析的必需账户明确报配置错误；不把配置正文带入异常。
- **使用允许名单，不能只排除 `PG_*`。** 旧数据库、回调密钥及其他平台配置均不得进入新项目数据库连接、适配器、计算容器或对外API。新项目数据库继续只由独立部署配置连接。
- `SH_*` 属于其对应提供方；不能把它们当作 Open-Meteo 或 SoilGrids 账户。当前源码只有 `OpenMeteoSource` 和 `SoilGridsSource`：天气的可选商业key与访问用途是不同属性，SoilGrids WCS 本身没有账户参数。若新增SH来源，必须有准确的独立适配合同、允许键、权限及真实取数验收，不能仅因环境存在SH账户便声称该来源已接通。
- 更换天气供应商时替换来源适配器及其凭据投影；组件输入输出与科学单位验证不跟着读取海豚。更换凭据存储时只替换提供器，来源转换规则不变。

最小验收包括：同名模糊结果不误选；缺名/失权/刷新失败拒绝；任务code优先级确实符合配置；账户轮换用于下一次取数；DS环境中存在的旧PG等键未改变新项目连接；敏感配置未进入日志、API、快照或模型；独立HTTP Worker实际使用指定环境的目标账户完成取数。以上是本节调查建议，未在本次只读任务中实现或宣称通过实跑。
