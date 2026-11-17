# 问题跟踪

当前使用本地 Markdown。功能设计放在 `coding/`，以对应设计为需求与验收的权威来源。

- 每个工作项保存为 `.scratch/<feature>/issues/<NN>-<slug>.md`，包含设计链接、范围、验收和前置工作项。
- 多任务计划可用 `.scratch/<feature>/spec.md` 记录范围及设计链接。每项工作按前置关系推进。
- 任务近顶部使用 `Status:` 记录[分流标签](triage-labels.md)。验证证据与后续讨论留在相应工作项。
