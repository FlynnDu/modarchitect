# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:27
# @Author  : Codex
# @File    : containers.py
"""通过本机 Docker 接口隔离执行准确组件，核对实际文件成果。"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import logging
import re
import tarfile

import httpx

from ..contracts.identifiers import canonical_json, new_uuid7

MAX_BYTES = 8_000_000
logger = logging.getLogger("modarchitect.components")


def log_text(raw: bytes) -> str:
    """解析 Docker 的标准输出帧，只保留有界诊断正文。"""
    messages = []
    while len(raw) >= 8 and raw[0] in {1, 2} and raw[1:4] == b"\0\0\0":
        length = int.from_bytes(raw[4:8], "big")
        messages.append(raw[8 : 8 + length])
        raw = raw[8 + length :]
    return b"".join(messages + [raw]).decode("utf-8", errors="replace")[-2000:]


@dataclass(frozen=True)
class Artifact:
    """保留上游实际文件字节，下游调用直接复用该制品。"""

    raw: bytes

    @property
    def value(self) -> dict:
        """按 JSON 对象解释已核验的成果。"""
        value = json.loads(self.raw)
        if not isinstance(value, dict):
            raise ValueError("An artifact must contain a JSON object")
        return value

    @property
    def digest(self) -> str:
        """返回实际文件的准确摘要。"""
        return sha256(self.raw).hexdigest()

    @classmethod
    def encode(cls, value: dict) -> "Artifact":
        """为外部封存数据或准确模型状态建立本次输入文件。"""
        return cls(canonical_json(value).encode("utf-8"))


def archive(files: dict[str, bytes], mode: int, directory_name: str) -> bytes:
    """生成仅含受控文件名的目录归档，不携带宿主机路径。"""
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as bundle:
        directory = tarfile.TarInfo(directory_name)
        directory.type, directory.mode = tarfile.DIRTYPE, mode
        bundle.addfile(directory)
        for filename, raw in files.items():
            member = tarfile.TarInfo(directory_name + "/" + filename)
            member.size, member.mode = len(raw), 0o444
            bundle.addfile(member, BytesIO(raw))
    return buffer.getvalue()


def invocation_files(component: dict, parameters: dict, inputs: dict[str, Artifact], invocation: str) -> dict[str, bytes]:
    """以独立文件名引用输入，原生 request 端口不能覆盖协议清单。"""
    references = {port: {"path": "input_%s.json" % index, "sha256": artifact.digest} for index, (port, artifact) in enumerate(inputs.items())}
    files = {references[port]["path"]: artifact.raw for port, artifact in inputs.items()}
    request = {"protocol_version": "1.0", "invocation_id": invocation, "component": component, "parameters": parameters, "inputs": references}
    files["request.json"] = canonical_json(request).encode("utf-8")
    return files


class ContainerRunner:
    """Worker 专用执行器，API 进程不连接 Docker。"""

    def __init__(self, socket: str = "/var/run/docker.sock"):
        """连接受信本机引擎，镜像来自已登记运行制品。"""
        self.client = httpx.Client(
            transport=httpx.HTTPTransport(uds=socket),
            base_url="http://docker",
            timeout=httpx.Timeout(15, read=50),
        )

    def close(self) -> None:
        """释放 Worker 调用的网络资源。"""
        self.client.close()

    def call(
        self,
        component: dict,
        profile: dict,
        parameters: dict,
        inputs: dict[str, Artifact],
    ) -> dict[str, Artifact]:
        """用独立匿名卷传递摘要绑定输入，超时确认终止并清理资源。"""
        invocation = str(new_uuid7())
        files = invocation_files(component, parameters, inputs, invocation)
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("Component input exceeds its byte budget")
        response = self.client.post(
            "/containers/create",
            json={
                "Image": profile["image"],
                "User": "65532:65532",
                "Cmd": [
                    "--input-dir",
                    "/work/input/inputs",
                    "--output-dir",
                    "/work/output/artifacts",
                ],
                "Volumes": {"/work/input": {}, "/work/output": {}},
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "NetworkMode": "none",
                    "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=67108864,mode=1777"},
                    "Memory": min(max(int(profile.get("memory_bytes", 536870912)), 134217728), 2147483648),
                    "NanoCpus": 1000000000,
                    "PidsLimit": 64,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                },
            },
        )
        response.raise_for_status()
        container = response.json()["Id"]
        path = "/containers/" + container
        try:
            for directory, content in (
                ("/work/input", archive(files, 0o555, "inputs")),
                ("/work/output", archive({}, 0o777, "artifacts")),
            ):
                copied = self.client.put(
                    path + "/archive", params={"path": directory}, content=content
                )
                copied.raise_for_status()
            self.client.post(path + "/start").raise_for_status()
            try:
                waited = self.client.post(
                    path + "/wait", params={"condition": "not-running"}
                )
                waited.raise_for_status()
            except httpx.TimeoutException as exc:
                self.client.post(path + "/kill")
                self.client.post(path + "/wait", timeout=10).raise_for_status()
                raise ValueError(
                    "Component exceeded its execution time budget"
                ) from exc
            if waited.json()["StatusCode"] != 0:
                logs = self.client.get(
                    path + "/logs",
                    params={"stdout": "true", "stderr": "true", "tail": "20"},
                )
                detail = log_text(logs.content)
                logger.error("Component %s failed: %s", component["code"], detail)
                prefix = "Invalid research component invocation: "
                reason = (
                    detail.split(prefix, 1)[1].strip()[:300]
                    if prefix in detail
                    else "Component rejected the data or failed to calculate"
                )
                raise ValueError(reason)
            with self.client.stream(
                "GET", path + "/archive", params={"path": "/work/output/artifacts"}
            ) as output:
                output.raise_for_status()
                raw, total = [], 0
                for chunk in output.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("Component output exceeds its byte budget")
                    raw.append(chunk)
            return self._outputs(b"".join(raw), invocation, profile["outputs"])
        finally:
            removed = self.client.delete(path, params={"force": "true", "v": "true"})
            removed.raise_for_status()

    def _outputs(
        self, raw: bytes, invocation: str, ports: list[str]
    ) -> dict[str, Artifact]:
        """核对普通文件、调用身份、声明端口和每个真实字节摘要。"""
        files = {}
        with tarfile.open(fileobj=BytesIO(raw)) as bundle:
            for member in bundle:
                if member.isdir():
                    continue
                filename = member.name.rsplit("/", 1)[-1]
                if (
                    not member.isfile()
                    or member.size > MAX_BYTES
                    or len(files) >= 64
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}\.json", filename)
                    or filename in files
                ):
                    raise ValueError("Component returned an invalid artifact file")
                files[filename] = Artifact(bundle.extractfile(member).read())
        manifest_file = files.pop("result.json", None)
        if manifest_file is None:
            raise ValueError("Component result manifest is missing")
        manifest = manifest_file.value
        if (
            manifest.get("protocol_version") != "1.0"
            or manifest.get("invocation_id") != invocation
        ):
            raise ValueError("Component result invocation differs")
        outputs = manifest.get("outputs")
        if not isinstance(outputs, dict) or set(outputs) != set(ports):
            raise ValueError(
                "Component result ports differ from its registered contract"
            )
        paths = [reference.get("path") for reference in outputs.values() if isinstance(reference, dict)]
        if len(paths) != len(ports) or any(not isinstance(path, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}\.json", path) or path == "result.json" for path in paths) or len(set(paths)) != len(paths) or set(paths) != set(files):
            raise ValueError("Component result artifact references differ")
        result = {}
        for port, reference in outputs.items():
            artifact = files[reference["path"]]
            if reference != {"path": reference["path"], "sha256": artifact.digest}:
                raise ValueError("Component artifact checksum differs")
            canonical_json(artifact.value)
            result[port] = artifact
        return result
