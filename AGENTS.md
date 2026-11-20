# modarchitect 开发规则

使用简体中文协作。先查入口、契约、调用方和测试，再区分事实、假设、建议及其验证方式。发现方案有漏洞时说明具体影响并给出可行替代方案。

- 迁移任务先读[模型设计器迁移计划](coding/model-designer-migration.md)。涉及目录、方案、采集、运行和发布的术语时查阅 [GLOSSARY.md](GLOSSARY.md)。
- 新增或扩展 Python 功能前，使用 `python-project-standards` 和 `karpathy-guidelines`。先在 `coding/` 建立或更新功能设计，再实现最小可验收的改动。声明依赖和测试扩展写入 `pyproject.toml`。完成后运行相关行为测试及本次自有 Python 文件的文件头检查。
- 调查、设计、实现、故障排查、评审和交接按[团队协作与开发工作流](docs/development-workflow.md)选择适用的技能和验证方式。
- 新增领域能力、调整模块或依赖、扩展组件接入及重构时，按[架构与编码质量规范](docs/engineering-standards.md)核对职责、抽象、调用方和改造场景，用相应行为与历史兼容结果验收。
- 研究业务规则在权威模块实现一次。对外 API 负责协议和授权。数据库负责持久化约束。DolphinScheduler 负责实际调度，Worker 领取封存输入后计算并回传。
- 开发或接入计算组件、设计用户上传流程时，先读[组件架构约束](coding/model-designer-migration.md#组件架构约束)。每个组件按统一模板交付可独立复跑的正反例及准确制品。内置组件与用户组件共用版本化合同，用户制品经隔离验收并获准采用后进入设计和执行。
- 新增或修改计算组件时遵循[计算组件开发规则](docs/calculation-component-rules.md)，按准确合同声明实际操作、输入用途、参数、成果和验收。第 5 步按同一套合同展示训练和评价能力。
- 普通研究的外部输入从[系统输入目录](coding/system-input-components.md)采用，固定变量定义、科学单位、准确来源和方法；取数属性按来源合同选择。目录设计资格与实际执行资格分开：已登记指标和模型允许设计组合，未接通来源保留计划绑定及原采样尺度；缺取数、制品或适配时拒绝实际运行。四类来源与计算组件分类分别维护。历史私有变量、合成演示和上游派生变量分别保留，不授予真实输入资格，禁止上传数值冒充已接通来源。
- 使用当前项目的虚拟环境或独立验收环境，记录真实命令、结果和待验证项。数据库、企业授权及真实 DolphinScheduler 联验使用已确认的隔离环境。

## 仓库推送与发布

- 用户要求推送当前仓库时，默认同步公开发布代码到两个远程：`origin` 为 `https://github.com/FlynnDu/modarchitect.git`，目标分支 `main`；`gongfeng` 为 `https://git.code.tencent.com/sonoagi/modarchitect.git`，目标分支 `master`。两端使用同一个已验收的公开提交及版本 tag。
- 复用已有仓库和远程，不重新 `git init`，不覆盖 `origin`，不把内部部署记录、凭据或无关未完成文件推入公开历史。显式列出提交文件，禁止为了推送使用 `git add .` 混入其他工作。
- 工蜂账户为 `feidu`。认证优先使用本机 Git 凭据管理器中的已保存凭据，不再重复询问已配置的账户信息；密钥不写入本文件、源码、文档、日志或命令行参数。远程实际拒绝认证时先核查本机凭据配置，不通过关闭校验或扩大权限绕过。
- 用户已明确授权推送或部署后，完成对应检查、推送、上线和回读验证，不重复询问同一授权。推送前检查两端远程进度；分支保持快进。用户明确要求更新同名 tag 时，记录旧 tag 对象和提交，以准确远端旧值执行 `--force-with-lease`，保留旧制品和回退依据。
- 推送后核对两个远程的目标分支与 tag 指向同一公开提交；发布文档、附件摘要和部署记录使用该准确提交。认证或远程并发阻止同步时，明确记录尚未完成的目标，不把单端成功当作双端完成。
- 每次发布同步更新 `pyproject.toml` 版本。FastAPI 从正式安装包元数据读取版本，发布后核对 Git tag、安装包版本及线上 `/openapi.json` 的 `info.version` 一致，并确认 `/docs` 加载同一份规范。

## Agent skills

### Issue tracker

初期使用本地 Markdown。见 [问题跟踪规则](docs/agents/issue-tracker.md)。

### Triage labels

本地任务使用 Matt 技能的默认标签。见 [分流标签](docs/agents/triage-labels.md)。

### Domain docs

项目当前采用单一领域术语入口。见 [领域文档](docs/agents/domain.md)。
