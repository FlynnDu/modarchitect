# 项目初始化设计

2026-11-11。建立可安装的独立 Python 项目，交接模型设计器迁移需求并提供最小运行入口。

## 目标与验收

- 从项目根目录构建 wheel，在独立 Python 环境中仅用该 wheel 和声明依赖安装。
- 安装后从其他目录导入 `modarchitect`，运行 FastAPI 的 `GET /health`，得到 HTTP 200 和 `{"status":"ok"}`。
- 把运行依赖与测试依赖写入 `pyproject.toml`。项目目录和安装包可以独立于 `mlgrowth` 源码使用。
- 迁移需求、阶段验收和旧系统证据见[模型设计器迁移计划](model-designer-migration.md)。项目初始化验收覆盖打包、安装和进程存活，独立数据库、外部鉴权、研究 API 与 DolphinScheduler 另有阶段验收。

## 目录与依赖

```text
modarchitect/
├── AGENTS.md
├── README.md
├── GLOSSARY.md
├── pyproject.toml
├── modarchitect/
│   ├── __init__.py
│   └── api.py
├── tests/
│   └── test_health.py
├── coding/
└── docs/
```

`modarchitect/` 是标准的仓库根目录包布局。setuptools 只发现该包及其子包。FastAPI 与 Uvicorn 是运行依赖，HTTPX 与 pytest 是测试依赖。后续由对应功能记录决定何时引入数据库、迁移或共享契约依赖。

当前调用链为 Uvicorn → FastAPI → 存活响应。包入口保留中文说明，导入时装配路由。数据库、调度及科学计算按实际迁移需要接入。

## 检查

运行自有 Python 文件的文件头检查、HTTP 回归和独立 wheel 安装验证。首次业务功能按[开发工作流](../docs/development-workflow.md)更新设计记录。
