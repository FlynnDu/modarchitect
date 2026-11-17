# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 17:06
# @Author  : Codex
# @File    : verify_ndvi.py
"""独立从文件协议复跑NDVI正反例，兼容本地入口和固定离线镜像。"""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from components.template.verify import command


def fixture() -> dict:
    """已知红光0.2、近红外0.6的NDVI为0.5，标签和土壤应原样保留。"""
    obj = {"field_ref": "field-a", "crop_code": "potato", "season_ref": "2025"}
    tables = {}
    for port, columns in {"observations": [("lai", "m2_m2", "observed", 2)],
                          "soil": [("clay", "percent", "estimated", 20)],
                          "satellite": [("red", "dimensionless", "estimated", .2), ("nir", "dimensionless", "estimated", .6)]}.items():
        tables[port] = {"columns": [{"code": code, "name": code, "unit": unit, "value_kind": nature} for code, unit, nature, value in columns],
                        "rows": [{"object": dict(obj), "business_date": "2025-04-02", "values": {code: value for code, unit, nature, value in columns}}],
                        "source_sha256": ["a"*64]}
    return tables


def verify(image: str | None = None) -> None:
    """计算、零值、配对、单位、性质、分母、摘要和端口均通过同一公开入口验证。"""
    original = fixture()
    for case in ("valid", "zero", "day", "object", "unit", "nature", "denominator", "negative", "tamper", "port"):
        inputs = deepcopy(original)
        table = inputs["satellite"]
        if case == "zero":
            table["rows"][0]["values"]["nir"] = .2
        if case == "day":
            table["rows"][0]["business_date"] = "2025-04-03"
        if case == "object":
            table["rows"][0]["object"]["field_ref"] = "other"
        if case == "unit":
            table["columns"][0]["unit"] = "percent"
        if case == "nature":
            table["columns"][0]["value_kind"] = "observed"
        if case == "denominator":
            table["rows"][0]["values"] = {"red": 0, "nir": 0}
        if case == "negative":
            table["rows"][0]["values"]["red"] = -.2
        with TemporaryDirectory() as directory:
            source, target = Path(directory)/"input", Path(directory)/"output"
            source.mkdir()
            target.mkdir()
            references = {}
            for port, table in inputs.items():
                data = json.dumps(table).encode("utf-8")
                (source/(port+".json")).write_bytes(data)
                references[port] = {"path": port+".json", "sha256": sha256(data).hexdigest()}
            if case == "tamper":
                references["satellite"]["sha256"] = "0"*64
            if case == "port":
                references.pop("soil")
            request = {"protocol_version": "1.0", "invocation_id": "0196d000-0000-7000-8000-000000000001",
                       "component": {"code": "sentinel_ndvi_features", "revision": 1},
                       "parameters": {"red_code": "red", "nir_code": "nir", "output_code": "ndvi"}, "inputs": references}
            (source/"request.json").write_text(json.dumps(request), encoding="utf-8")
            args = command(source, target, image) if image else [sys.executable, "-m", "components.field_research.entrypoint", "--input-dir", str(source), "--output-dir", str(target)]
            result = subprocess.run(args, env={**os.environ, "COMPONENT_CODE": "sentinel_ndvi_features"}, capture_output=True, timeout=45)
            if case not in {"valid", "zero"}:
                assert result.returncode == 2 and not list(target.iterdir()), (case, result.stderr)
                continue
            assert result.returncode == 0, (case, result.stderr)
            manifest = json.loads((target/"result.json").read_bytes())
            assert set(manifest["outputs"]) == {"table"}
            raw = (target/manifest["outputs"]["table"]["path"]).read_bytes()
            assert sha256(raw).hexdigest() == manifest["outputs"]["table"]["sha256"]
            values = json.loads(raw)["rows"][0]["values"]
            assert abs(values["ndvi"]-(.5 if case == "valid" else 0)) < 1e-12
            assert values["lai"] == 2 and values["clay"] == 20
    print("NDVI file protocol: two positive and eight rejection cases passed")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--image")
    verify(parser.parse_args().image)
