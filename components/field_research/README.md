# 标准田间研究组件

共用统一文件协议和构建入口，每个准确组件单独交付清单及隔离制品：

- `manifests/catalog_weather_conditions/component.json`：标准日值气象暴露分析。
- `manifests/sentinel_ndvi_features/component.json`：卫星NDVI计算与土壤气象配对。
- `manifests/research_calendar_axis/`：平台观测日期驱动，独立合同、实际制品身份及正反例见[交付说明](manifests/research_calendar_axis/README.md)。

前两份清单的镜像摘要标为待构建，不代表已经批准上线。日期组件已完成本地构建与隔离验收，尚未发布生产。实际部署应登记镜像摘要并按原清单格式验收，不以可变镜像标签代替准确制品。

独立协议验收可在项目根目录执行：

```powershell
.venv/Scripts/python.exe -m components.field_research.verify
.venv/Scripts/python.exe -m components.field_research.verify_ndvi
.venv/Scripts/python.exe -m components.field_research.verify_calendar
```

三者均接受 `--image sha256:<实际镜像摘要>`，从同一文件协议复跑本地正反例。NDVI包含已知比值、合法零值、错误日期/对象、错误单位/性质、零分母、负反射率、摘要篡改与缺端口。空背景列只用于保留对象日期；必需的红光与近红外列仍完整核验。

运行镜像只复制算法、固定入口和文件协议。批准清单、文档与验收程序在镜像之外交付；清单中的实际镜像摘要不反过来参与同一镜像构建，避免身份自引用及重新构建时摘要漂移。OCI清单摘要与Docker运行配置摘要分别记录，并以实际加载和运行核验。

提供方取数和NDVI计算分别验收：云遮挡、缺景、实际场景及请求网格由来源接入保留；两波段在封存输入时核对同景同网格。算法只消费准确表，不读取账户、不直接请求卫星或混入调度逻辑。
