# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 00:59
# @Author  : Codex
# @File    : import_input_catalog.py
"""从指定旧源码只读导出输入合同，独立项目运行时不依赖旧仓库。"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def main() -> None:
    """读取准确源码定义，记录证据摘要并写入指定新项目制品。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.source.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("The export must not modify the source repository")
    sys.path.insert(0, str(root / "src"))
    from mlgrowth_contracts.research.source_catalog import (
        builtin_research_variables,
        builtin_source_policies,
        greenhouse_variable_profiles,
    )
    from mlgrowth_contracts.timeseries import CATALOG_DEFINITION_RECORDS
    from mlgrowth_contracts.identifiers import identity_sha256

    variables, sources = builtin_research_variables()
    paths = sorted((root / "src/mlgrowth_contracts/research/catalog").glob("*.json"))
    paths += [root / ("src/mlgrowth_contracts/" + name) for name in (
        "timeseries/platform.py", "timeseries/indicators.py",
        "research/source_dictionary.py",
    )]
    payload = {
        "format": "modarchitect_system_inputs_v1",
        "version": "1.0.0",
        "origin": "mlgrowth enterprise-model-services 53d86cb plus audited working tree",
        "evidence": [{"path": p.relative_to(root).as_posix(),
                      "sha256": sha256(p.read_bytes()).hexdigest()} for p in paths],
        "variables": [v.model_dump(mode="json") for v in variables],
        "sources": [s.model_dump(mode="json") for s in sources],
        "policies": [p.model_dump(mode="json") for p in builtin_source_policies()],
        "profiles": [p.model_dump(mode="json") for p in greenhouse_variable_profiles().values()],
        "sampling": [r for r in CATALOG_DEFINITION_RECORDS if r["kind"] == "sampling_indicator"],
    }
    envelope = {"payload": payload, "sha256": identity_sha256(payload)}
    if output.exists() and json.loads(output.read_text(encoding="utf-8")) != envelope:
        raise ValueError("Frozen input catalog differs; create a new versioned artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Exported input catalog %s (%s)" % (payload["version"], envelope["sha256"]))


if __name__ == "__main__":
    main()
