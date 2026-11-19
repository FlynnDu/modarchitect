# 平台规则与研究流程验收

2026-11-12。当前入口：`http://127.0.0.1:8000/designer/#select`。

## 已交付

- 输入调整包含记录新增/删除/替换、输入增删、因素和目标增删以及分析指标筛选。准许调整仍需按准确来源、单位、模型合同和本次数据重新校验。
- 指定资料方案只开放登记参数，服务端核验实际指标范围，未知指标不会因字符串格式合法而进入队列。合成演示不取得真实地块输入资格。
- 只读预检与真实启动共用 `runtime/preparation.py`，沿用结构、连线、来源、标签与执行合同。没有增加第二套科学计算或校验规则。启动继续检查修订和授权，并持久化准确输入。
- 新检查请求只含当前方案、操作及需要的观测/数据性质；响应仅为 `can_execute` 和 `issues`，每项问题仅含规则、位置和正文。新输入政策只有 `mode` 和 `editable`，参数白名单复用既有字段。
- 卡片沿用方案和运行资源，标题、颜色与固定阶段不进入 API。只新增该次运行的准确方案读取，不返回原始输入、镜像配置和 Worker 凭据。
- 五阶段卡片显示实际运行与成果，默认收起模型连接图，保留原高级编辑器。编辑后清除旧成果状态，无效草稿显示提示；计算完成不冒充验证通过。

## 已执行验证

1. 独立验收数据库和低权限角色：**61 项 Python 测试通过**。覆盖输入增删、删空目标、删除必需输入、缺列、错误单位、估计标签、指定资料越权编辑、超范围指标、预检与启动拒绝规则一致、失败不入队、历史版本与跨工作区隔离。已有训练、串联、模型保存及预测回归保留。
2. **23 项前端测试通过**。包括 16 个主题的五阶段展示、实际成果和误差分开、无效草稿清除旧绿灯、保留展开状态、预检失败不保存或提交。
3. **7 个在线规则场景通过**，核对最小 OpenAPI 合同；检查前后没有新增方案和运行。
4. 最终镜像在线实际运行：16 个公开主题、两个可选方法、两个参数实验、一个历史版本、两个模型后续预测、研究人员界面及原预测界面，共 **26 个真实工作流**。DolphinScheduler 工作流与任务状态全部为 SUCCESS，实例范围 120–145。串联输入输出摘要一致，继续预测没有重新训练。
5. 研究人员界面采用真实 DOM 事件和在线 HTTP：预览不保存，采用后保存，修改日期、重开、运行及卡片更新通过；无 HTTP 或页面脚本错误。未进行原生浏览器像素验收。
6. **11 个本次自有 Python 文件头检查和 Ruff 通过**。249 安装的 **94 个包文件**与最终 wheel 和本机源码一致。31 个科学合同文件与上一方案库发布逐字节一致，运行制品注册表未改变。

真实命令：

```powershell
$env:PYTHONPATH='.'
.\.venv-ops\Scripts\python.exe .ops/verify_remote_database.py
npm test
.\.venv\Scripts\python.exe scripts/verify_study_templates.py --output .ops/flow-release/research-themes-acceptance.json
node scripts/verify_study_library_ui.mjs --output .ops/flow-release/researcher-ui-acceptance.json
node scripts/verify_designer_ui.mjs --output .ops/flow-release/prediction-ui-acceptance.json
```

文件头检查使用 `E:/CodexData/home/skills/python-project-standards/scripts/check_python_headers.py`，输入为本次 8 个应用文件、平台规则测试、模板验收脚本及调度验收脚本；Ruff 检查同一组文件。

## 部署与兼容

- API、Worker 与调度消费者：`modarchitect:0.1.0-rules-d2b111fbb2bc`。
- wheel SHA-256：`d2b111fbb2bcc61bc3c78f524281aa930c133e0f05c837fb9d0b0a8ba244fbe8`。
- 镜像身份：`sha256:756644c156c0dfc56258eb42855aabcba6d8353de4f0412f09ca3f82a504044b`。
- 数据库仍为 0007，无本批表结构迁移。最终切换前的 26 个模型和 89 个方案版本摘要均保持不变，运行注册表保持原字节。
- 发布目录：`/mnt/sda1/modarchitect/releases/platform-rules-20261112-final/`。保留切换前数据库备份、Compose、准确版本对照与回退配置。继续使用 `compose.yaml` 加 `compose.studies.yaml` 启动，不操作旧项目。

机器证据：部署验收记录。规则说明：[研究平台规则](../docs/platform-rules.md)。设计：[规则实施](research-platform-rules.md)及[截图 API 差距](research-flow-cards.md)。

## 尚未交付的截图业务

逐地块实际齐备矩阵、参数版本分配、部分启动与补数复检、WOFOST 实际模拟持续入库、通用模拟实测配对及报告复核仍待实现。当前卡片没有虚构对应状态和统计，也没有把分析已有模拟输出说成已接通 WOFOST。来源自动取数和科学独立验证继续按各自资格验收。
