# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:15
# @Author  : Codex
# @File    : build_tabular_contracts.py
"""从已验收的标准表训练协议生成三种算法的准确版本化合同。"""

from copy import deepcopy
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"random_forest": ("随机森林", "64棵深度不超过8的单线程随机森林"),
           "xgboost": ("XGBoost", "64轮CPU直方图树提升，深度4，学习率0.08"),
           "gaussian_process": ("高斯过程", "训练集标准化与固定RBF核精确高斯过程，alpha=0.01")}


def main() -> None:
    """只生成新增身份；原线性及原生评估合同保持字节不变。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path)
    parser.add_argument("--profiles", type=Path)
    args = parser.parse_args()
    contracts = ROOT / "modarchitect/contracts"
    prior = json.loads((contracts / "runtime-components-v1.json").read_text(encoding="utf-8"))
    templates = {row["code"]: row for row in prior}
    digest = sha256((ROOT / "components/tabular_learning/component.py").read_bytes()).hexdigest()
    rows = []
    for algorithm, (name, method) in METHODS.items():
        for action in ("training", "predict"):
            row = deepcopy(templates["multivariate_linear_" + action])
            row.update(code=algorithm + "_" + action, name=name + ("回归训练" if action == "training" else "模型预测"),
                       summary="使用固定系统指标训练并保存可复用回归模型。" if action == "training" else "使用已保存的模型与已知因素预测，不重新训练。",
                       algorithm=method, mechanism="每个数值目标独立训练，保留准确特征定义和模型状态。")
            row["implementation"] = {"module": "components.tabular_learning.component", "symbol": "train" if action == "training" else "predict", "source_sha256": digest}
            config = row["configuration"]
            config["call_kwargs"] = {"algorithm": algorithm}
            row["native_parameters"].append({"code": "algorithm", "required": True})
            config.setdefault("research_model", {})["kind"] = "regression"
            row["requirements"] = ["训练标签须为实测，因素与目标不得重叠；输入按完整对象及业务日期对齐。", "模型使用前须用独立资料验证适用性；因素在预测时必须已知。"]
            row["limitations"] = ["本版本只处理完整有限数值，不自动补值或合成实测标签。", "同一地块的多个日期不代表多个独立试验单位。", "高斯过程每次最多1000个训练样本；树方法最多10000个，按资源预算执行。"]
            if action == "training":
                state = next(port for port in row["outputs"] if port["code"] == "trained_model")
                state["data_type"].update(semantic=algorithm + "_regression_model", version=1)
                state["description"] = "准确算法JSON状态、列定义、训练范围及来源；不使用pickle。"
                model = config["research_model"]
                model["request_schema"]["properties"]["seed"] = {"title": "复现种子", "type": "integer", "minimum": 0, "maximum": 2147483647, "default": 17}
                model["execution"] = {"operations": ["train"], "state_output": "trained_model", "inference": {"code": algorithm + "_predict", "revision": 1}, "input_uses": {"features": {"role": "feature", "phases": ["training", "application"]}, "targets": {"role": "label", "phases": ["training", "evaluation"]}}}
                model["table_outputs"] = {"predictions": {"predicted": ["targets"], "fit_through": "training_end"}}
            else:
                next(port for port in row["inputs"] if port["code"] == "model")["data_type"].update(semantic=algorithm + "_regression_model", version=1)
                config["research_model"]["execution"] = {"operations": ["predict"], "input_uses": {}}
            rows.append(row)
    (contracts / "tabular-learning-components-v1.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generated six exact tabular component contracts")
    if args.images:
        if not args.profiles:
            raise ValueError("An explicit runtime profile destination is required")
        sys.path.insert(0, str(ROOT))
        from modarchitect.catalog import catalog
        from modarchitect.execution_contracts import execution_capability
        from modarchitect.contracts.identifiers import identity_sha256
        from modarchitect.contracts.model_center.component_packages import ComponentPackageManifest

        profiles = json.loads(args.profiles.read_text(encoding="utf-8")) if args.profiles.exists() else {}
        destination = ROOT / "components/tabular_learning/manifests"
        destination.mkdir(exist_ok=True)
        for image in json.loads(args.images.read_text(encoding="utf-8")):
            definition = catalog()[image["code"], 1].definition
            capability = execution_capability({"code": image["code"], "revision": 1})
            raw = {"manifest_version": "1.1", "component": {"code": definition.code, "revision": 1, "name": definition.name, "category": definition.category},
                   "contract": {"summary": definition.summary, "method": definition.algorithm, "requirements": list(definition.requirements), "limitations": list(definition.limitations),
                                "inputs": [port.model_dump(mode="json") for port in definition.inputs if port.code != "request"], "outputs": [port.model_dump(mode="json") for port in definition.outputs],
                                "request_schema": definition.configuration.get("research_model", {}).get("request_schema") or {"type": "object", "additionalProperties": False, "properties": {}}, "execution": capability.model_dump(mode="json")},
                   "artifact": {"kind": "oci_image", "manifest_digest": image["repo_digest"].split("@", 1)[1]}, "runtime": {"protocol_version": "1.0", "profile_code": "offline_cpu"}}
            manifest = ComponentPackageManifest.model_validate(raw).model_dump(mode="json")
            (destination / (definition.code + ".json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            profile = {"image": image["image"], "outputs": [port.code for port in definition.outputs], "manifest_digest": "sha256:" + identity_sha256(manifest), "memory_bytes": 536870912}
            if capability.state_output:
                profile.update(state_output=capability.state_output, inference=capability.inference.code + "@" + str(capability.inference.revision))
            profiles[definition.code + "@1"] = profile
        args.profiles.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
        print("Bound exact component manifests and runtime profiles")


if __name__ == "__main__":
    main()
