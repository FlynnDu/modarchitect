# 基础回归方法的真实接入

2026-11-16。用户指出方法目录中很多基础模型仍不能选择。上一批仅接通方法选择，未解决训练、保存及推理缺口。

## 事实和范围

- 生物所22项采用组件中，标准观测表可复用训练只有线性和历史曲线合同；均未登记运行制品。原随机森林、XGBoost、高斯过程、LSTM与ConvLSTM版本是指定资料评估，不能拿评估报告冒充模型。
- 本次给随机森林、XGBoost、高斯过程分别增加标准观测表训练及独立推理组件，原合同及指定资料研究保持。共同使用系统指标、完整对象和业务日期；不改变来源资格，不要求用户重新发明变量。
- LSTM与ConvLSTM需要序列/网格资料；温室、统计及其他分析方法按对应研究用途展示，不作为当前表格训练的替代项。不可执行能力不能标为可运行。

## 职责和规则

1. 科学实现放在components/tabular_learning：component.py负责标准表、切分和模型元数据；estimators.py负责三种算法的训练及安全JSON状态推理；entrypoint.py复用固定身份文件协议。按准确清单构建独立非特权离线镜像，锁定依赖，正反例独立复跑。
2. 新版本化合同单独装配目录，已有准确身份和摘要不改。迁移只追加6个合同身份，校验冲突，不修改历史方案/模型。API、Worker与调度沿用原执行能力合同和持久化流程，不新增算法API。
3. 每个目标独立拟合，不限制业务上的目标和因素个数；以资源预算约束单次样本/状态大小。目标须有实测，因素可来自已接通估计来源；目标与因素不得重叠。预测仅要求被冻结的因素及单位，不读标签、不重新训练。
4. 截止日及之前训练；之后仅预测和评价。标准化仅训练集拟合，模型保存准确列定义、参数、训练范围、完整对象集合及来源摘要。拒绝缺失、非有限值、重复对象日、错单位和状态算法不匹配。
5. 随机森林保存有界树数组、高斯过程保存标准化参数及RBF训练状态；XGBoost使用官方JSON模型格式。禁止pickle加载。准确模型状态只在对应隔离推理制品中读取。
6. 引导页按真实训练能力识别表格训练参数，避免只认识线性模型；新算法展示f(X)关系，不套用线性方程。适配当前操作的方法先展示，其他用途/指定资料方法单独说明。方法配置和用途编辑更新同一份definition。
7. 部署准确制品及目录后登记运行；默认线性训练/预测和历史曲线训练/预测一并核对。独立执行服务更新包；原海豚Worker仅在新工作流实际需要新包时更新，保留既有科学依赖。密钥、环境和来源配置不变。

## 验收

- 三算法各自双目标训练、无标签独立推理、保存再读取数值一致；后段标签篡改不影响训练状态，错单位及缺列等反例拒绝。人工与估计来源保持原规则。
- 组件清单、合同、源码摘要、镜像和独立文件协议一致，真实隔离容器正反例；参数表单及用途编辑回归。
- 生物所目录→选择→保存→重开→海豚训练→保存模型→独立预测，记录准确版本、运行和结果。合成资料仅作工程验收，不报科研准确率。

## 一手依据

XGBoost官方说明模型JSON与内存快照的区别及save/load接口：[模型格式](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html)。scikit-learn官方提示pickle持久化的执行风险及版本约束：[持久化](https://scikit-learn.org/stable/model_persistence)。本项目以显式JSON状态和准确推理制品避免通用对象反序列化；模型本身仍须独立科学验证。

## 已完成验收

- `.venv/Scripts/python.exe .ops/verify_local_database.py`：新建隔离库及非特权角色，升级0011，Alembic检查无额外结构差异，132项全部通过；使用项目独立临时目录，不把跳过数据库的运行计作全量验收。
- `npm test`：41/41通过，新增三种算法真实切换、用途编辑、非线性公式展示，原有串联、来源和历史页面回归保持。
- Linux AMD64依赖SHA锁定，三算法各自实际隔离容器双目标训练和无标签推理通过，错误单位、估计目标反例拒绝；本地另与独立scikit-learn/XGBoost算法参考逐值比较，并验证改变留出标签不改变训练状态。
- 生物所SR850迁移只新增6项合同，原25项合同摘要保持；API Job9、独立执行Job3均部署成功、Consul各1 passing。API/执行Worker/分发进程各139个包文件逐项核对，密钥、工作区签名和来源环境保持。
- 原海豚Worker Job36保持。实际任务只通过HTTP交给独立Worker计算；已更新承担本次目录与执行职责的独立服务，无需重启其他项目任务。
- 线上真实DOM事件及HTTP：线性、随机森林、XGBoost、高斯过程各自选择、保存、重开、海豚训练、保存模型及无标签预测完成，共8个SUCCESS工作流。模型新客户端重开摘要一致；预测状态保持，调用的是独立推理组件；其他工作区访问404。
- 真实运行号：随机森林738/739；高斯过程740/742；XGBoost741/743；线性744/745。全部为明确合成工程数据，数值可用不等于独立科研精度；本次没有凌晨2点每日调度验收。
- 原气象737报告和7点曲线新页面重查正常。原生浏览器环境未能初始化，本次没有像素布局验收。

页面验收命令（分别替换训练组件）：

```sh
node scripts/verify_designer_ui.mjs --base-url http://172.16.1.122:18925 --training-method random_forest_training --session-file .ops/tabular-learning/private/forest-session.json --output coding/deployments/modarchitect-biology/tabular-random-forest-ui.json
```

[部署与包核对](deployments/modarchitect-biology/tabular-deployment-acceptance.json) · [组件正反例](deployments/modarchitect-biology/tabular-component-acceptance.json) · [随机森林](deployments/modarchitect-biology/tabular-random-forest-ui.json) · [XGBoost](deployments/modarchitect-biology/tabular-xgboost-ui.json) · [高斯过程](deployments/modarchitect-biology/tabular-gaussian-ui.json) · [线性](deployments/modarchitect-biology/tabular-linear-ui.json) · [模型重开与隔离](deployments/modarchitect-biology/tabular-reopened-models.json) · [海豚准确运行](deployments/modarchitect-biology/tabular-scheduler-acceptance.json)

## 仍保留的边界

LSTM/ConvLSTM的现有版本是指定序列/网格资料评估，尚未完成通用训练状态接入；历史曲线训练在本环境仍待启用。其他统计、温室和指标分析方法按相应研究用途和真实端口使用。本批不解除这些科学要求，不把所有目录条目标记成任意指标表均可训练。
