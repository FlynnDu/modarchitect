# 标准观测表回归

随机森林、XGBoost和高斯过程分别交付训练与独立预测组件。输入沿用系统指标定义的research_observation_table；每个目标独立拟合，训练截止日后仅预测，预测不读取目标标签。

component.py负责表结构、科学列定义和切分；estimators.py负责算法与显式JSON状态；entrypoint.py由镜像固定算法身份。目录合同由scripts/build_tabular_contracts.py生成，准确发布清单在manifests/；不得改变已有版本的源文件或合同。

依赖按requirements.txt准确版本和SHA锁定，Linux AMD64 Python3.12；离线构建上下文的wheels目录放置锁定制品。推理不使用pickle。随机森林保存树数组；高斯过程保存仅由训练集拟合的标准化参数和RBF状态；XGBoost保存官方JSON模型。参数和模型列定义随状态保存。

```sh
python -m pytest tests/test_tabular_learning.py -q
docker build --platform linux/amd64 --network none --build-arg COMPONENT_CODE=random_forest_training -f components/tabular_learning/Dockerfile components
```

三算法都要求至少8条训练行，GP最多1000条、树方法最多10000条；单次输入按50万因素单元和3.8MB状态预算执行，不以业务变量数量固定截断。科学适用性和独立验证另行核实，不能把工程样例误差当作科研结论。
