# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:35
# @Author  : Codex
# @File    : scheduler.py
"""从持久投递队列向独立 DolphinScheduler 项目提交真实任务。"""

import json
import logging
import os
import time

import httpx
from .environments import read_environment

logger = logging.getLogger("modarchitect.scheduler")


class DolphinScheduler:
    """固定工作流接收准确运行身份，启动返回的实例身份独立持久化。"""

    def __init__(self):
        """端点、凭据及项目均来自本项目部署环境。"""
        self.project = os.environ["MODARCHITECT_DS_PROJECT"]
        self.workflow = os.environ["MODARCHITECT_DS_WORKFLOW"]
        self.source_workflow = os.getenv("MODARCHITECT_DS_SOURCE_WORKFLOW")
        self.source_environment_name = os.getenv("MODARCHITECT_DS_SOURCE_ENVIRONMENT_NAME")
        self.source_environment_code = None
        self.tenant = os.environ["MODARCHITECT_DS_TENANT"]
        self.client = httpx.Client(
            base_url=os.environ["MODARCHITECT_DS_URL"].rstrip("/") + "/",
            headers={"token": os.environ["MODARCHITECT_DS_TOKEN"]},
            timeout=20,
        )

    def close(self) -> None:
        """释放调度客户端连接。"""
        self.client.close()

    def submit(self, job: dict) -> str:
        """不重试结果未知的启动请求，返回真实工作流实例编号。"""
        return self._start(self.workflow, {"run_id": job["run_id"], "dispatch_token": job["dispatch_token"]})

    def submit_acquisition(self, job: dict) -> str:
        """采集使用独立工作流，不把采集任务伪装成科研训练。"""
        if not self.source_workflow:
            raise ValueError("Source acquisition workflow is not configured")
        if self.source_environment_code is None:
            self.prepare_source_environment()
        return self._start(self.source_workflow, {"acquisition_id": job["acquisition_id"], "dispatch_token": job["dispatch_token"]}, environment=self.source_environment_code)

    def prepare_source_environment(self) -> None:
        """认领来源队列前验证环境，配置错误不伪装成已提交后结果未知。"""
        environment = read_environment(self.client, self.source_environment_name or "")
        response = self.client.get("projects/"+self.project+"/workflow-definition/"+self.source_workflow)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0:
            raise ValueError("Source workflow environment cannot be verified")
        tasks = body["data"]["taskDefinitionList"]
        if not tasks or any(str(task.get("environmentCode")) != environment.code for task in tasks):
            raise ValueError("Source task environment differs from the configured environment")
        self.source_environment_code = environment.code

    def _start(self, workflow: str, parameters: dict, *, environment: str = "-1") -> str:
        """共享真实海豚传输与回执校验，保留两种任务的独立身份。"""
        response = self.client.post(
            "projects/" + self.project + "/executors/start-workflow-instance",
            data={
                "workflowDefinitionCode": workflow,
                "scheduleTime": "",
                "failureStrategy": "END",
                "warningType": "NONE",
                "warningGroupId": "0",
                "taskDependType": "TASK_POST",
                "execType": "START_PROCESS",
                "workflowInstancePriority": "MEDIUM",
                "workerGroup": "default",
                "tenantCode": self.tenant,
                "environmentCode": environment,
                "dryRun": "0",
                "startParams": json.dumps(parameters),
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0 or not body.get("data"):
            raise ValueError("DolphinScheduler did not confirm the submitted instance")
        instance = body["data"][0]
        if type(instance) is not int or instance <= 0:
            raise ValueError("DolphinScheduler instance identity differs")
        return str(instance)


def main() -> None:
    """持续领取未投递记录，投递超时保留结果未知并等待准确对账。"""
    logging.basicConfig(level=logging.INFO)
    scheduler = DolphinScheduler()
    try:
        with httpx.Client(
            base_url=os.environ["MODARCHITECT_INTERNAL_API"].rstrip("/"),
            headers={"X-Research-Worker-Key": os.environ["MODARCHITECT_WORKER_KEY"]},
            timeout=20,
        ) as client:
            while True:
                try:
                    queues = [("/internal/v1/research", "run_id", scheduler.submit, "/runs/")]
                    if scheduler.source_workflow:
                        try:
                            scheduler.prepare_source_environment()
                        except (httpx.HTTPError, ValueError, KeyError):
                            logger.warning("Source dispatch is waiting for its configured environment")
                        else:
                            queues.append(("/internal/v1/input-acquisitions", "acquisition_id", scheduler.submit_acquisition, "/"))
                    dispatched = False
                    for base, identity, submit, segment in queues:
                        response = client.post(base + "/dispatch/next")
                        response.raise_for_status()
                        job = response.json()["job"]
                        if job is None:
                            continue
                        dispatched = True
                        report = {}
                        try:
                            report["scheduler_id"] = submit(job)
                        except (httpx.HTTPError, ValueError):
                            report["error"] = "Scheduler submission requires reconciliation"
                        acknowledgement = client.post(base + segment + job[identity] + "/dispatch", json=report)
                        acknowledgement.raise_for_status()
                    if os.getenv("MODARCHITECT_DS_DAILY_WORKFLOW"):
                        advanced = client.post("/internal/v1/report-tasks/advance")
                        advanced.raise_for_status()
                        dispatched = dispatched or advanced.json()["advanced"]
                    if not dispatched:
                        time.sleep(2)
                except (httpx.HTTPError, ValueError, KeyError):
                    logger.warning("Research dispatch is waiting for a dependency")
                    time.sleep(5)
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
