# modarchitect 开发规则

使用简体中文协作。先查入口、契约、调用方和测试，再区分事实、假设、建议及其验证方式。发现方案有漏洞时说明具体影响并给出可行替代方案。

- 迁移任务先读[模型设计器迁移计划](coding/model-designer-migration.md)。涉及目录、方案、采集、运行和发布的术语时查阅 [GLOSSARY.md](GLOSSARY.md)。
- 新增或扩展 Python 功能前，使用 `python-project-standards` 和 `karpathy-guidelines`。先在 `coding/` 建立或更新功能设计，再实现最小可验收的改动。声明依赖和测试扩展写入 `pyproject.toml`。完成后运行相关行为测试及本次自有 Python 文件的文件头检查。
- 调查、设计、实现、故障排查、评审和交接按[团队协作与开发工作流](docs/development-workflow.md)选择适用的技能和验证方式。
- 新增领域能力、调整模块或依赖、扩展组件接入及重构时，按[架构与编码质量规范](docs/engineering-standards.md)核对职责、抽象、调用方和改造场景，用相应行为与历史兼容结果验收。
- 研究业务规则在权威模块实现一次。对外 API 负责协议和授权。数据库负责持久化约束。DolphinScheduler 负责实际调度，Worker 领取封存输入后计算并回传。
- 开发或接入计算组件、设计用户上传流程时，先读[组件架构约束](coding/model-designer-migration.md#组件架构约束)。每个组件按统一模板交付可独立复跑的正反例及准确制品。内置组件与用户组件共用版本化合同，用户制品经隔离验收并获准采用后进入设计和执行。
- 普通研究的外部输入从[系统输入目录](coding/system-input-components.md)采用，固定变量定义、科学单位、准确来源和方法；取数属性按来源合同选择。目录设计资格与实际执行资格分开：已登记指标和模型允许设计组合，未接通来源保留计划绑定及原采样尺度；缺取数、制品或适配时拒绝实际运行。四类来源与计算组件分类分别维护。历史私有变量、合成演示和上游派生变量分别保留，不授予真实输入资格，禁止上传数值冒充已接通来源。
- 使用当前项目的虚拟环境或独立验收环境，记录真实命令、结果和待验证项。数据库、企业授权及真实 DolphinScheduler 联验使用已确认的隔离环境。

## Agent skills

### Issue tracker

初期使用本地 Markdown。见 [问题跟踪规则](docs/agents/issue-tracker.md)。

### Triage labels

本地任务使用 Matt 技能的默认标签。见 [分流标签](docs/agents/triage-labels.md)。

### Domain docs

项目当前采用单一领域术语入口。见 [领域文档](docs/agents/domain.md)。
