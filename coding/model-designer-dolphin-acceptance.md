# 真实 DolphinScheduler 调度验收

2026-11-11。适用于模型设计器迁移第 3 阶段。本阶段已核对旧代码、历史部署记录和 Apache DolphinScheduler 3.4.1 源码。目标研究环境的实际版本、接口响应、权限及故障行为待隔离联验。

## 旧系统证据

- `submit_shell_task()` 通过 SDK 提交定义，`wf.submit()` 返回定义编号。随后 REST 启动检查 HTTP 状态、业务 `code=0` 和非空 `data`，返回 `data[0]`。上层丢弃这个启动返回值，只回传定义编号。研究消费者用 `research-{run_id}` 命名工作流，把定义编号写成 `workflow_code` 和事件回执 `dolphin:<workflow_code>`。快速 Worker 若先完成，消费者仍能确认事件，运行终态行可能没有 `workflow_code`。 [提交和启动](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/services/dolphin.py:64>) · [消费者](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/services/research_studies/coordinator.py:52>)
- 消费者用短事务认领事件，完成外部调用后另开事务写回执。传输异常会重排同一事件，旧路径没有启动前按海豚实例对账。历史 `workflow_code` 和 `dolphin:` 回执按原义导入。缺少实例记录的历史行保留未知实例身份，只有找到可核实的历史映射后才能关联海豚实例。 [事件投递及重排](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/services/research_studies/coordinator.py:120>)
- Worker 通过内部 API 领取封存输入，校验 `input_sha256`，按 `attempt_id` 续租和回传。取消在库内撤销租约，回传旧租约返回 409。旧取消方法没有调用海豚 STOP。过期租约可触发有界恢复，继续使用原 `run_id` 和封存摘要。完成后，同一已完成尝试的同一结果可重放回执，结果和报告待投递事件一起提交。工作区版调整了报告事件组装。 [Worker 入口](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/src/pymlgrowth/research_models/remote.py:28>) · [内部回调](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/routers/research_execution.py:27>) · [运行生命周期](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/services/research_studies/runs.py:217>) · [恢复](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/api/services/research_studies/recovery.py:27>)
- 249 的 2026-11-05 研究验收使用独立 PostGIS、实际 Worker 与算法。身份、业务四接口和调度提交使用工程替身。另一个地块周采样项目的发布记录观察到 3.4.1 上停止后出现 `READY_STOP`、子任务失败与延迟重试，随后才确认父子终态及进程排空。该记录用于构造研究任务的停止测试，研究隔离环境版本和行为仍待确认。 [研究隔离记录](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/deployments/20261105-research-workflow-249.md:5>) · [周采样停止记录](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/docs/deployments/20261030-field-survey-weekly-sampling-release.md:75>)

## Apache DolphinScheduler 3.4.1 源码事实

- 普通启动为 `POST /projects/{projectCode}/executors/start-workflow-instance`，提交 `workflowDefinitionCode`，`START_PROCESS` 成功响应的 `data` 是含一个整数实例 ID 的列表。Master 在事务中插入实例和普通或串行队列命令，再返回实例 ID。普通启动路径每次构造新实例，没有按 `run_id` 或相同 `startParams` 复用实例的逻辑。推论是客户端丢失响应时，调度器可能已经接受任务，同样的请求重新发送可能创建第二个实例。 [启动控制器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/ExecutorController.java#L119-L162) · [实例及命令持久化](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/AbstractWorkflowTrigger.java#L55-L71) · [普通启动构造及响应](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/WorkflowManualTrigger.java#L45-L100)
- `GET /projects/{projectCode}/workflow-instances` 可按 `workflowDefinitionCode`、`searchVal`、日期及分页查候选。`searchVal` 对实例名做模糊匹配，普通实例名由定义名加时间戳组成。查询实现没有将 `otherParamsJson` 用作启动参数筛选。`GET /projects/{projectCode}/workflow-instances/{id}` 查实例详情，追加 `/tasks` 查任务。源码的 `/workflow-instances/trigger` 已废弃，普通启动响应没有该查询所需的 `triggerCode`。 [查询控制器](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/WorkflowInstanceController.java#L97-L139) · [详情接口](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/WorkflowInstanceController.java#L191-L202) · [分页实现](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/WorkflowInstanceServiceImpl.java#L293-L329) · [名称筛选](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-dao/src/main/resources/org/apache/dolphinscheduler/dao/mapper/WorkflowInstanceMapper.xml#L105-L135) · [已废弃查询](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/WorkflowInstanceController.java#L403-L419)
- 停止为 `POST /projects/{projectCode}/executors/execute`，参数为 `workflowInstanceId` 和 `executeType=STOP`。3.4.1 的 `SUBMITTED_SUCCESS` 暂不可停止，`SERIAL_WAIT` 支持直接停止，运行中的停止由 Master 处理。`READY_STOP` 仍可受理停止且属于非终态。停止回执只记录请求结果，实际停止需查父子状态、待重试及 Worker 进程。 [停止入口](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/controller/ExecutorController.java#L287-L303) · [状态能力](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/enums/WorkflowExecutionStatus.java#L24-L52) · [停止实现](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/executor/workflow/StopWorkflowInstanceExecutorDelegate.java#L47-L99) · [READY_STOP 状态机](https://github.com/apache/dolphinscheduler/blob/3.4.1/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/statemachine/WorkflowReadyStopStateAction.java#L75-L109)

## 迁移候选与目标环境核验

每次逻辑调度在发送前持久化唯一的提交标识，并关联 `run_id`、执行事件、冻结输入摘要、海豚项目及定义编号和版本。响应返回后记录实际海豚实例 ID。Worker 领取后关联执行尝试 `attempt_id`、海豚实例和任务实例，保留已结束尝试。提交和 Worker 尝试是两个时点。调度回执和实例映射独立于不可变的运行结果写入，允许 Worker 先领取或完成。

丢回执时先查询同一提交标识的全部候选。可在目标环境验证把唯一的提交标识加入隔离工作流定义名，或通过 `startParams` 传递后从实例详情、任务上下文读回。定义名包含旧 `run_id` 只能缩小候选范围。按项目、定义编号与版本和准确提交标识复核，时间窗及名称匹配用于查找。只有一个准确匹配时认领原实例。多个匹配时暂停自动投递并保存所有候选的证据。查询为空、不可用或只读权限不足时保留结果未知，待能证实请求未到达或未提交后才允许发送。已证实实例需要恢复时使用新的调度记录，继续使用原封存输入。

先登记目标海豚实际版本和镜像摘要、API 基址及网关路径、项目、租户、调度账号权限、Worker 组和运行包摘要。使用独立研究库、专用测试项目和队列、固定逻辑斯蒂输入。每个场景从对外研究 API 发起，故障注入限定在该环境。留存脱敏的研究请求与状态变化、海豚启动和查询响应、事件回执、Worker 任务状态与日志、研究库快照和输出摘要。使用准确时间戳串联 `study_id → run_id → 事件/提交标识 → 定义编号及版本 → 海豚实例 → 任务实例 → attempt_id → result_sha256`。

## 实际验收用例

| 场景 | 执行步骤 | 通过证据 |
|---|---|---|
| 正常启动及重放 | 用固定数据发起运行，等真实 Worker 领取和回传。重放原业务请求，同时让两个消费者尝试投递同一事件。另跑一次让 Worker 先于消费者写调度回执。 | 同一请求返回相同 `run_id` 和输入摘要，只有一个海豚实例取得本次提交，记录的实例 ID 能用详情和任务接口核实。只有一个有效领取与一份结果，结果摘要及报告事件各唯一。消费者补写调度关联后，原终态结果摘要保持。 |
| 接受后丢回执 | 让故障代理转发真实启动请求，收到海豚成功响应后对研究消费者丢弃响应。等认领到期或重启消费者，再重放原请求。另测消费者收到了响应但在持久化前退出。 | 故障代理和海豚侧记录原实例 ID。消费端记为结果未知，查询后采用同一实例。查询延迟或不可达期间没有第二次启动请求。恢复后只有一个实例和一份结果，重放沿用原事件和封存摘要。 |
| 明确未送达 | 代理在转发启动请求前拒绝请求并记录证据。恢复连接后重投同一提交意图。 | 未送达的证据与海豚候选查询一致，恢复后恰有一个实例。调度定义的创建和实例启动分别记录。 |
| 排队或计算中取消 | 分别在请求尚未发送、已接受但未取得实例 ID、`SUBMITTED_SUCCESS` 和 Worker 已领取时发起取消。让停止与任务失败后的延迟重试相遇。恢复连接后再重放取消。 | 研究侧即时撤销提交成果的权限。未发送时无启动。已接受但身份未知时先对账再向准确实例 STOP，暂不可停止时保留未确认并继续对账。STOP 回执和停止确认分别可查。观察到父子终态、无待重试、Worker 实际无进程后确认已停止。相同取消请求可重放。 |
| 迟到结果与回调乱序 | 捕获合法 Worker 结果，在取消后或租约已被接管后，用旧 `attempt_id` 重新发起续租、结果及失败回调。另测当前合法尝试完成后重放同一结果，再重放被改动的结果。 | 旧尝试回调返回 409，运行终态、结果摘要、报告待投递事件和科研发布记录保持。合法完成尝试的同一结果返回既有回执，改动的结果被拒绝。取消与结果同时到达时，按先提交的一方留下唯一状态，已完成运行取消返回冲突。 |
| Worker 失联与恢复 | 在领取后切断续租并让进程失联，等待租约到期及恢复策略触发。恢复原 Worker 的网络并回传旧尝试结果。另测超过恢复预算。 | 原尝试关闭，按配置创建有界恢复调度并记录实例，新 Worker 领取同一 `run_id` 及 `input_sha256`、不同 `attempt_id`。旧回传被拒绝，合法结果只保存一次。预算耗尽进入可查询的失败状态，留存原因。 |

旧运行入口在省略 `cutoff` 时使用当前时间。联验另用同一客户端请求身份、不传 `cutoff`，模拟 HTTP 成功后丢响应，跨时刻重发并并发重放。验收要求复用首次封存时点、`run_id` 和调度提交。显式发起新实验时按运行契约登记新的请求意图。客户端请求去重和海豚启动回执对账均需通过。

旧系统工程对照覆盖真实算法的 HTTP 入口、并发领取、取消拒绝迟到结果和过期租约恢复。目标环境还需记录停止允许状态、状态查询延迟、丢回执关联字段以及 Worker 退出和延迟重试的实际表现。 [HTTP 回归](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/tests/model_center/test_research_http_workflow.py:72>) · [运行数据库回归](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/tests/model_center/test_research_run_database.py:169>) · [恢复回归](<E:/CodexData/home/worktrees/enterprise-model-services/mlgrowth/tests/model_center/test_research_recovery.py:23>)
