# 计算组件开发

开发者从 `template/` 复制一份组件目录。每次交付包含清单、独立入口、构建方式、正反例、成果容差和准确制品。平台目录采用后，方案绑定组件代码、整数修订和合同摘要。组件参数和端口由同一份清单描述，计算放在组件执行进程。

| 文件 | 用途 |
| --- | --- |
| `component.json` | 声明代码、修订、端口、请求 Schema、执行协议、运行配置和 OCI manifest digest。 |
| `component.py` | 科学或数据处理逻辑。 |
| `entrypoint.py` | 读取请求与摘要绑定的输入，调用处理函数并写成果文件和结果清单。 |
| `file_protocol.py` | 模板共用的调用、输入摘要和成果文件逻辑。 |
| `Dockerfile` | 构建独立离线 CPU 制品，基础镜像固定摘要，以非特权用户运行。 |
| `verify.py` | 正例、应拒绝输入和成果摘要检查。对数值组件另声明预期参数及容差。 |

模板可直接在本地复跑，覆盖成功、记录不足及输入篡改。

```powershell
.\.venv\Scripts\python.exe components/template/verify.py
```

构建时将下面的路径换成实际构建输出位置。将构建元数据的 `containerimage.digest` 填入提交用的 `component.json` 副本。

```powershell
docker buildx build --provenance=false --sbom=false --tag component-template:local --metadata-file template-build.json --output type=oci,dest=template.oci.tar components/template
docker load -i template.oci.tar
.\.venv\Scripts\python.exe components/template/verify.py --image component-template:local
```

从 `GET /api/v1/model-center/component-packages/schema` 和 `GET /api/v1/model-center/component-packages/port-types` 获取当前合同。用业务 Key 向 `POST /api/v1/model-center/component-packages/validate` 提交清单。预检返回清单摘要。供方身份、签名、实际制品、资源隔离、批准采用和用户上传在后续批次联验。

文件协议使用 `/work/input/request.json` 和 `/work/output/result.json`。只读输入目录中的文件以端口、相对文件名和 SHA-256 引用。每次调用使用独立输出目录，成功后核对调用 ID、输出端口及摘要。失败退出码为 2，参考入口在输出成果后才写成功清单。

## 通用执行声明

新增组件可使用 [1.1 声明模板](template/component-v1.1.json)，在合同中说明支持的操作、输入字段用途，以及可选的准确训练状态/推理组件。原 1.0 模板及摘要保持兼容；预检不授予执行资格。完整非训练参考见 [标准观测描述统计](descriptive_statistics/README.md)，它提供独立预期和离线容器正反例。

## 逻辑斯蒂参考组件

`logistic_growth/` 是迁入的独立数值包及既有文件协议适配。使用 Python 3.12 建独立环境，通过 wheel 安装。该环境只需数值依赖及组件包。

```powershell
py -3.12 -m venv .venv-logistic
.\.venv-logistic\Scripts\python.exe -m pip wheel --no-deps components/logistic_growth -w dist
.\.venv-logistic\Scripts\python.exe -m pip install dist/mlgrowth_logistic_growth-1.0.0-py3-none-any.whl
$wheelSha = (Get-FileHash dist/mlgrowth_logistic_growth-1.0.0-py3-none-any.whl -Algorithm SHA256).Hash.ToLowerInvariant()
.\.venv-logistic\Scripts\python.exe -I components/logistic_growth/verify.py --expected-wheel-sha256 $wheelSha
```

验证器核对组件环境的独立性、安装制品摘要、合成曲线的三个参数及常量序列拒绝。历史方案回放使用原冻结 wheel 和依赖身份，见[首批验收](../coding/model-designer-first-batch-acceptance.md)。

## 多变量线性回归参考组件

`multivariate_regression/` 使用同一文件协议。请求中的 `features` 和 `targets` 是用户选择的数值列，`training_end` 按业务日期切分训练与预测。输入表须按地块、作物、种植季和日期对齐。结果为模型 JSON 和预测结果表。预测日需要已知的输入因子，正式预测前须以独立观测检查各目标误差。

从项目根目录复跑 Linux AMD64 制品。命令将准确的 NumPy wheel 下载到工作目录之外，Docker 构建离线安装并校验锁定摘要。

```powershell
$wheels = Join-Path $env:TEMP 'modarchitect-regression-wheels'
New-Item -ItemType Directory -Force $wheels | Out-Null
./.venv/Scripts/python.exe -m pip download --no-deps --only-binary=:all: --platform manylinux_2_27_x86_64 --implementation cp --python-version 3.12 --abi cp312 -r components/multivariate_regression/requirements.txt -d $wheels
docker buildx build --platform linux/amd64 --network none --provenance=false --sbom=false --tag modarchitect-multivariate-regression:1 --metadata-file regression-build.json --output type=oci,dest=regression.oci.tar --build-context "wheels=$wheels" --file components/multivariate_regression/Dockerfile components
docker load -i regression.oci.tar
./.venv/Scripts/python.exe -m components.multivariate_regression.verify --image modarchitect-multivariate-regression:1
```

单目标与双目标使用同一组合成观测，校验预测值和成果摘要。反例包括秩不足、重复对象日期及文件被篡改。准确清单见 [component.json](multivariate_regression/component.json)。

## 成果串联参考组件

`historical_logistic/` 从训练截止日之后的对象日期输出预测特征表。`forecast_join/` 接收它和实测表，以完整对象日期合并并保留标签来源。两个组件复用 `chain_tables.py` 的日期、列与对象键校验，各自的清单与镜像在对应目录声明。

已加载三个准确镜像后，在项目根目录复跑实际文件协议。验收会把前一步的成果字节和校验摘要交给后一步。

```powershell
./.venv/Scripts/python.exe -m components.verify_chain --containers
```

两份新 OCI 归档、摘要及历史逻辑斯蒂 wheel 在 `dist/components/chain-v1/`。若需构建历史预测镜像，将冻结 wheel 与 `requirements.txt` 对应的 Linux AMD64 NumPy、SciPy wheel 放入单一目录，使用 `--build-context "wheels=$wheels" --file components/historical_logistic/Dockerfile components`。合并镜像用 `--file components/forecast_join/Dockerfile components` 即可构建。两份清单分别位于 [历史预测](historical_logistic/component.json) 和 [预测合并](forecast_join/component.json)。

## 可复用训练模型

`research_runtime/` 复用已有回归算法和逻辑斯蒂数值内核，提供训练状态及独立推理。每个镜像在构建时固定一个组件代码，清单位于 `research_runtime/manifests/`。推理输入可以省略目标标签，模型列定义、单位及参数继续冻结。

| 组件 | 科学入口 | 成果 |
| --- | --- | --- |
| `multivariate_linear_training@1` | `linear.train` | 系数、特征与目标定义、训练范围和留出预测 |
| `multivariate_linear_predict@1` | `linear.predict` | 按冻结系数生成的新预测 |
| `historical_logistic_training@1` | `growth.forecast` | 按对象冻结的曲线模型及后续预测因子 |
| `historical_logistic_predict@1` | `growth.predict` | 由已有曲线模型生成的后续预测因子 |

安装项目测试依赖后，从项目根目录复跑实际文件协议、正例和错误单位反例。

```powershell
./.venv/Scripts/python.exe -m components.research_runtime.verify
```

构建沿用上述锁定 Linux wheels 目录，以 `components/research_runtime/Dockerfile` 为入口，分别传 `--build-arg COMPONENT_CODE=组件代码`。每个代码单独构建并登记 OCI manifest digest。Worker 的运行注册表额外固定本机镜像配置摘要、准确输出端口、训练状态输出端口和推理组件引用。API 和 Worker 同时核对该注册表，实际文件摘要记录在运行成果中。
