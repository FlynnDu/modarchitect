# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 15:49
# @Author  : Codex
# @File    : remote_release.py
"""用本机已有凭据传输独立项目制品，不在文件或日志保存登录秘密。"""

import argparse
import os
import socket
from urllib.parse import urlsplit
from urllib.request import getproxies
import ctypes
from ctypes import wintypes
from pathlib import Path
from time import sleep

import paramiko


class Credential(ctypes.Structure):
    """Windows 凭据管理器的只读结构。"""

    _fields_ = [
        ("flags", wintypes.DWORD), ("kind", wintypes.DWORD),
        ("target", wintypes.LPWSTR), ("comment", wintypes.LPWSTR),
        ("written", wintypes.FILETIME), ("size", wintypes.DWORD),
        ("blob", ctypes.POINTER(ctypes.c_ubyte)), ("persist", wintypes.DWORD),
        ("attributes_count", wintypes.DWORD), ("attributes", ctypes.c_void_p),
        ("alias", wintypes.LPWSTR), ("username", wintypes.LPWSTR),
    ]


def configured_proxy() -> socket.socket | None:
    """运维可显式采用系统HTTP代理；SSH仍核验目标主机密钥且凭据保持加密。"""
    value = os.getenv("MODARCHITECT_SSH_PROXY_URL")
    if not value:
        return None
    if value == "system":
        value = getproxies().get("https") or getproxies().get("http")
    parsed = urlsplit(value or "")
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise OSError("Configured SSH proxy is unavailable or unsupported")
    connection = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=15)
    try:
        connection.sendall(b"CONNECT 192.168.3.249:22 HTTP/1.1\r\nHost: 192.168.3.249:22\r\n\r\n")
        header = bytearray()
        while not header.endswith(b"\r\n\r\n") and len(header) < 8192:
            part = connection.recv(1)
            if not part:
                raise OSError("Configured SSH proxy closed CONNECT")
            header.extend(part)
        if not header.endswith(b"\r\n\r\n") or bytes(header).split(b"\r\n")[0].split()[1:2] != [b"200"]:
            raise OSError("Configured SSH proxy rejected CONNECT")
        return connection
    except OSError:
        connection.close()
        raise


def connect(*, attempts: int = 3) -> paramiko.SSHClient:
    """仅使用当前主机已有的指定 SSH 凭据和已知主机密钥。"""
    api = ctypes.WinDLL("Advapi32.dll")
    item = ctypes.POINTER(Credential)()
    if not api.CredReadW(
        "ssh@192.168.3.249:22/sumfenaipc", 1, 0, ctypes.byref(item)
    ):
        raise OSError("The configured SSH credential is unavailable")
    try:
        raw = ctypes.string_at(item.contents.blob, item.contents.size)
        password = raw.decode("utf-16-le" if b"\x00" in raw else "utf-8").rstrip("\x00")
        for attempt in range(attempts):
            client = paramiko.SSHClient()
            client.load_host_keys(str(Path.home() / ".ssh" / "known_hosts"))
            try:
                client.connect(
                    "192.168.3.249", username="sumfenaipc", password=password,
                    look_for_keys=False, allow_agent=False, timeout=15, sock=configured_proxy(),
                )
                return client
            except OSError:
                # 尚未开始传输或执行，仅重试连接；认证和主机密钥失败不重试。
                client.close()
                if attempt == attempts-1:
                    raise
                sleep(1)
            except paramiko.SSHException as error:
                client.close()
                if type(error) is not paramiko.SSHException or not str(error).startswith("Error reading SSH protocol banner") or attempt == attempts-1:
                    raise
                sleep(1)
    finally:
        api.CredFree(item)


def main() -> None:
    """按显式路径传输文件或执行可审查脚本，并传递失败状态。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path)
    parser.add_argument("--send", nargs=2, action="append", default=[])
    parser.add_argument("--get", nargs=2, action="append", default=[])
    parser.add_argument("--connection-attempts", type=int, choices=range(1,13), default=3)
    args = parser.parse_args()
    with connect(attempts=args.connection_attempts) as client:
        with client.open_sftp() as sftp:
            for local, remote in args.send:
                sftp.put(local, remote)
            for remote, local in args.get:
                Path(local).parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote, local)
        if args.script:
            stdin, stdout, stderr = client.exec_command("bash -s", timeout=180)
            stdin.write(args.script.read_text(encoding="utf-8"))
            stdin.channel.shutdown_write()
            print(stdout.read().decode("utf-8"), end="")
            print(stderr.read().decode("utf-8"), end="")
            raise SystemExit(stdout.channel.recv_exit_status())


if __name__ == "__main__":
    main()
