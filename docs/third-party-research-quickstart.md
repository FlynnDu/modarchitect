# 纯第三方气象研究

入口：[作物高温暴露条件分析](http://172.16.1.122:18925/designer/?template=crop-high-temperature#configure/sources)。每个浏览器在自己的研究空间保存。

1. 采用方案，在“数据来源”填写地块编号、作物代码、种植季、参考坐标及日期。
2. 点击“采集所选平台指标”，等待“已采用”记录；来源数值只读。
3. 保存方案，可从云端方案列表重新打开。
4. 进入检查与确认，点击“检查并开始分析”。完成后查看分析报告、日最高气温曲线及海豚运行编号。

可复测的参考范围：纬度50.46，经度119.85，2026-07-01至2026-07-07，作物代码potato，种植季2026。参考位置不代表用户真实地块授权。气象为平台网格估计，使用上海业务日。

本例产出条件分析结果及逐日曲线。35℃为组件登记的参考条件，不是分作物生育阶段的灾害诊断；分析成果不能保存为预测模型。

## 接口顺序

以下为个人研究工作区接口，Cookie保留在自己的客户端；企业保存接口及服务Key规则见[业务接入](business-api-integration.md)。

```sh
API=http://172.16.1.122:18925
curl -fsS -c session.cookie "$API/api/v1/workspace/session"
curl -fsS -b session.cookie "$API/api/v1/workspace/study-templates/crop-high-temperature" -o template.json
curl -fsS -b session.cookie -H 'X-Workspace-Request: 1' -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $SAVE_REQUEST_ID" -d @plan.json "$API/api/v1/workspace/plans"
curl -fsS -b session.cookie -H 'X-Workspace-Request: 1' -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $ACQUIRE_REQUEST_ID" -d @acquire.json "$API/api/v1/workspace/plans/$DESIGN_ID/input-acquisitions"
curl -fsS -b session.cookie "$API/api/v1/workspace/input-acquisitions/$ACQUISITION_ID"
curl -fsS -b session.cookie "$API/api/v1/workspace/input-snapshots/$SNAPSHOT_ID"
curl -fsS -b session.cookie -H 'X-Workspace-Request: 1' -H 'Content-Type: application/json' \
  -d @check.json "$API/api/v1/workspace/check-execution"
curl -fsS -b session.cookie -X PUT -H 'X-Workspace-Request: 1' -H 'Content-Type: application/json' \
  -d @update.json "$API/api/v1/workspace/plans/$DESIGN_ID"
curl -fsS -b session.cookie -H 'X-Workspace-Request: 1' -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $RUN_REQUEST_ID" -d @run.json "$API/api/v1/workspace/runs"
curl -fsS -b session.cookie "$API/api/v1/workspace/runs/$RUN_ID"
```

请求ID各用一个新UUID，重放时复用原ID和正文。采集状态succeeded后读取快照，再提交检查和运行。保存响应仅返回方案信息；来源引用从重新读取的方案取得。

| 文件 | 必需内容 |
| --- | --- |
| plan.json | definition，取template.json.definition并编辑 |
| acquire.json | expected_revision、object、reference_point、start_date、end_date |
| check.json | definition、design_id、operation=analyze、observations、source_snapshot_ids |
| update.json | definition、expected_revision、observations、source_snapshot_ids |
| run.json | design_id、expected_revision、operation=analyze、observations、source_snapshot_ids |

observations原样取快照响应；禁止改值或省略来源引用。update后使用新的revision发起运行。
