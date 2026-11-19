# 部署示例

按项目首页创建隔离数据库和角色。容器构建使用本版 Python 安装包。组合示例从环境变量读取镜像、绑定地址和端口，从部署方的环境文件读取连接和密钥。请按实际部署提供环境文件和 `runtime-profiles.json`。组件运行配置引用部署方的准确组件版本及镜像摘要。

原生组件镜像使用 `APPROVED_BASE` 指定依赖镜像。Python 安装目录由 `COMPONENT_PYTHON_PREFIX` 指定，默认 `/usr/local`。
