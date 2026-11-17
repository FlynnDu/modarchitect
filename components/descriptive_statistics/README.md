# 标准观测描述统计 @1

非训练分析组件，统一清单版本 1.1。输入为准确对象日期的标准观测表，参数 `variables` 从实际输入列选择。输出计数、范围、算术均值和样本标准差，保留单位、值性质及来源摘要；不产生训练状态或预测模型。

独立预期在 `examples/expected-summary.json`：三条合成值 1、2、3 的均值为 2，样本标准差为 1；单条记录的样本标准差为 `null`。多天观测不等于多个独立试验单位，统计不能直接证明农业因果关系。

从项目根目录复跑：

```powershell
./.venv/Scripts/python.exe -m components.descriptive_statistics.verify
docker build --platform linux/amd64 --network none -t modarchitect-descriptive-statistics:1 -f components/descriptive_statistics/Dockerfile components
./.venv/Scripts/python.exe -m components.descriptive_statistics.verify --image modarchitect-descriptive-statistics:1
```

验收包含两个正例及未知列、重复选择、布尔值、非有限值、未知值性质、文件摘要被篡改六个拒绝例。容器沿模板使用只读文件系统、无网络、非 root 用户和资源限制。准确制品摘要登记在 `component.json`，未获准登记的用户清单不能执行。
