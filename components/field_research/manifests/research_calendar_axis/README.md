# 平台观测日期驱动

`research_calendar_axis@1`按`business_date − 1970-01-01`生成精确日坐标；基准固定并随准确组件版本、方案与模型保留。只转换已有记录，保留对象、来源摘要和稀疏日期。预测换批次不重新归零。它不代表播种后天数、定植后天数或积温，也不是外部采集指标或实测标签。

`component.json`交付统一组件清单与真实本地OCI身份，`contract.json`交付平台采用合同，`positive.json/negative.json`交付独立正反例。固定身份入口复用标准文件协议，组件不读取数据库、账户或调度设置。

在项目根目录复跑：

```powershell
.venv/Scripts/python.exe -m components.field_research.verify_calendar
docker build --network none --build-arg APPROVED_BASE=python:3.12-slim --build-arg COMPONENT_CODE=research_calendar_axis -f components/field_research/Dockerfile -t modarchitect-calendar-axis:20261117 components
.venv/Scripts/python.exe -m components.field_research.verify_calendar --image modarchitect-calendar-axis:20261117
```

通过标准文件入口核对真实输出摘要、间隔日期的0/3日换算、错误时间基准拒绝及输入摘要篡改拒绝。清单记录的是此次本机构建的准确身份；再次构建后需核对新的实际摘要并单独验收，不能靠相同标签声明制品相同。自动日期变量只可在图内派生，客户端上传该列、将其用作实测目标均由平台拒绝。
