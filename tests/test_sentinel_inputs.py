# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:50
# @Author  : Codex
# @File    : test_sentinel_inputs.py
"""以独立栅格和HTTP响应验证真实协议、稀疏场景、账户隔离及NDVI派生。"""

from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import tarfile

import httpx
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from components.field_research.ndvi import derive_ndvi
from modarchitect.input_sources.contracts import AcquisitionRequest
from modarchitect.input_sources.sentinel_scene import SceneNotUsable, decode_scene, reference_grid
from modarchitect.input_sources.service import execute_acquisition, prepare_acquisition
from modarchitect.input_sources.settings import SourceSettings, environment_keys
from modarchitect.input_sources.transport import SourceUnavailable
from modarchitect.study_templates import template


def scene_tar(grid: dict, acquired: str, *, scl: int = 4, scenes: int = 1, red: float = .2, nir: float = .6) -> bytes:
    """独立制作单像元浮点GeoTIFF与实际场景元数据，不调用待测转换器。"""
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=1, height=1, count=4, dtype="float32", crs="EPSG:%s" % grid["epsg"], transform=from_origin(grid["bbox"][0], grid["bbox"][3], 10, 10)) as raster:
            raster.write(np.asarray([red,nir,scl,1], dtype=np.float32).reshape(4,1,1))
        image = memory.read()
    metadata = {"scenes": [{"date": acquired, "shId": 123456789, "dataPath": "s3://sentinel-scene/reference"} for _ in range(scenes)], "serviceVersion": "test-service-1"}
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in [("bands.tif", image), ("userdata.json", json.dumps(metadata).encode())]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, BytesIO(data))
    return stream.getvalue()


def account_settings() -> SourceSettings:
    """只使用工程账户字符串，任何测试不读取真实秘密。"""
    return SourceSettings.from_mapping({"SH_CLIENT_ID": "test-client", "SH_CLIENT_SECRET": "do-not-persist-this-secret", "SH_BASE_URL": "https://sh.dataspace.copernicus.eu", "SH_TOKEN_URL": "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"})


def test_scene_decoder_requires_exact_grid_single_scene_date_and_pixel_quality():
    """不把多景、云像元或错日响应当作有效的每日观测。"""
    grid = reference_grid(116,39)
    acquired = datetime(2025,4,1,16,30,tzinfo=timezone.utc)
    pixel = decode_scene(scene_tar(grid, acquired.isoformat()), grid, acquired)
    assert pixel["bands"]["B04"] == pytest.approx(.2)
    with pytest.raises(SceneNotUsable):
        decode_scene(scene_tar(grid, acquired.isoformat(), scl=9), grid, acquired)
    with pytest.raises(SceneNotUsable):
        decode_scene(scene_tar(grid, acquired.isoformat(), scenes=2), grid, acquired)
    with pytest.raises(ValueError, match="acquisition differs"):
        decode_scene(scene_tar(grid, acquired.isoformat()), grid, datetime(2025,4,2,16,30,tzinfo=timezone.utc))
    wrong = deepcopy(grid)
    wrong["bbox"][0] += 10
    with pytest.raises(ValueError, match="grid"):
        decode_scene(scene_tar(grid, acquired.isoformat()), wrong, acquired)


def test_sentinel_acquisition_uses_environment_oauth_and_preserves_sparse_shanghai_dates():
    """两个波段复用同一实际清晰场景；OAuth秘密和令牌不进入封存结果。"""
    plan = template("soil-weather-satellite-lai")["definition"]
    codes = ("sentinel2_red_reflectance", "sentinel2_nir_reflectance")
    request = AcquisitionRequest(expected_revision=1, object={"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}, reference_point={"latitude": 39.0, "longitude": 116.0}, start_date="2025-04-01", end_date="2025-04-03", requirements=codes)
    payload = prepare_acquisition(plan, request)
    calls = []

    def respond(message: httpx.Request) -> httpx.Response:
        """以已知云/清晰两景校验网络请求，再返回准确独立像元。"""
        calls.append(message.url.path)
        if message.url.path.endswith("/token"):
            assert b"client_secret=do-not-persist-this-secret" in message.content
            return httpx.Response(200, json={"access_token": "ephemeral-test-token", "expires_in": 180})
        assert message.headers["Authorization"] == "Bearer ephemeral-test-token"
        body = json.loads(message.content)
        if message.url.path.endswith("/catalog/v1/search"):
            assert message.headers["Accept"] == "application/geo+json"
            assert body["collections"] == ["sentinel-2-l2a"]
            return httpx.Response(200, json={"features": [{"id": "cloud-candidate", "properties": {"datetime": "2025-04-01T01:00:00Z"}}, {"id": "clear-candidate", "properties": {"datetime": "2025-04-01T16:30:00Z"}}]})
        assert message.url.path.endswith("/process/v1")
        assert message.headers["Accept"] == "application/x-tar"
        assert body["output"]["width"] == 1 and 'mosaicking:"TILE"' in body["evalscript"]
        cloud = body["input"]["data"][0]["dataFilter"]["timeRange"]["from"].startswith("2025-04-01T00:")
        acquired = "2025-04-01T01:00:00Z" if cloud else "2025-04-01T16:30:00Z"
        return httpx.Response(200, content=scene_tar(reference_grid(116,39), acquired, scl=9 if cloud else 4))

    result = execute_acquisition(payload, lambda: None, transport=httpx.MockTransport(respond), settings=account_settings())
    assert len(result) == 2
    assert all([row["business_date"] for row in snapshot["observations"]["rows"]] == ["2025-04-02"] for snapshot in result)
    assert all(snapshot["quality"]["missing_dates"] == ["2025-04-01", "2025-04-03"] for snapshot in result)
    assert sum(path.endswith("/process/v1") for path in calls) == 2
    assert sum(path.endswith("/token") for path in calls) == 1
    serialized = json.dumps(result)
    assert "do-not-persist-this-secret" not in serialized and "ephemeral-test-token" not in serialized
    assert all(snapshot["support"]["scene_records"][0]["scene"]["shId"] == 123456789 for snapshot in result)
    from modarchitect.contracts.identifiers import identity_sha256
    from modarchitect.datasets import assemble_tables
    from modarchitect.system_inputs import seal_input_sources
    merged = assemble_tables([snapshot["observations"] for snapshot in result])

    def references(snapshots):
        """模拟已受权存储的准确内容引用，不省略封存时的摘要核验。"""
        return [{"snapshot_id": "source-%s" % index, "snapshot": snapshot, "sha256": identity_sha256(snapshot)} for index,snapshot in enumerate(snapshots)]

    seal_input_sources(plan, merged, "user_supplied", "owner", source_snapshots=references(result))
    mismatch = deepcopy(result)
    mismatch[1]["support"]["requested_point"]["latitude"] = 40.0
    with pytest.raises(ValueError, match="same actual scene and reference grid"):
        seal_input_sources(plan, merged, "user_supplied", "owner", source_snapshots=references(mismatch))
    mismatch = deepcopy(result)
    mismatch[1]["support"]["scene_records"][0]["scene"]["shId"] = 987654321
    with pytest.raises(ValueError, match="same actual scene and reference grid"):
        seal_input_sources(plan, merged, "user_supplied", "owner", source_snapshots=references(mismatch))


def test_long_single_source_download_renews_lease_during_provider_io(monkeypatch):
    """31景累计341秒仍在600秒预算内，下载期间须续租而非结尾才失权。"""
    from modarchitect.input_sources import transport

    clock, renewed = [1000.0], [1000.0]
    monkeypatch.setattr(transport, "monotonic", lambda: clock[0])
    plan = template("soil-weather-satellite-lai")["definition"]
    request = AcquisitionRequest(expected_revision=1, object={"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}, reference_point={"latitude": 39.0, "longitude": 116.0}, start_date="2025-04-01", end_date="2025-05-01", requirements=("sentinel2_red_reflectance",))

    def respond(message):
        """每景模拟11秒网络耗时，实际不sleep也不访问提供方。"""
        if message.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "ephemeral-test-token", "expires_in": 1800})
        body = json.loads(message.content)
        if message.url.path.endswith("/catalog/v1/search"):
            from datetime import date, timedelta
            return httpx.Response(200, json={"features": [{"id": str(index), "properties": {"datetime": (date(2025,4,1)+timedelta(days=index)).isoformat()+"T01:00:00Z"}} for index in range(31)]})
        clock[0] += 11
        from datetime import timedelta
        acquired = (datetime.fromisoformat(body["input"]["data"][0]["dataFilter"]["timeRange"]["from"].replace("Z", "+00:00"))+timedelta(seconds=1)).isoformat()
        return httpx.Response(200, content=scene_tar(reference_grid(116,39), acquired))

    def heartbeat():
        """模拟真实五分钟租约，过期后不能补续以掩盖失权。"""
        assert clock[0]-renewed[-1] <= 300
        renewed.append(clock[0])

    result = execute_acquisition(prepare_acquisition(plan, request), heartbeat, transport=httpx.MockTransport(respond), settings=account_settings())
    assert len(result[0]["observations"]["rows"]) == 31
    assert len(renewed) > 3 and max(right-left for left,right in zip(renewed,renewed[1:])) < 45


def test_source_settings_ignore_unrelated_accounts_and_reject_dynamic_secret_scripts():
    """旧PG/PATH不被执行或带入；不需要卫星的任务也不解析其错误表达式。"""
    text = "export MLGROWTH_PGSQL_PASSWORD=$(never-execute)\nexport SH_CLIENT_ID='client-a'\nexport SH_CLIENT_SECRET='secret-$-literal'\nexport SH_BASE_URL=\"$(must-not-run)\"\nexport MODARCHITECT_WEATHER_ACCESS=research\n"
    weather = SourceSettings.from_exports(text, environment_keys(frozenset({"openmeteo_archive"})))
    assert dict(weather.values) == {"MODARCHITECT_WEATHER_ACCESS": "research"}
    assert "secret" not in repr(weather)
    with pytest.raises(SourceUnavailable, match="literal"):
        SourceSettings.from_exports(text)
    settings = SourceSettings.from_exports("export SH_CLIENT_ID='client-a'\nexport SH_CLIENT_SECRET='secret-$-literal'\n")
    assert settings.get("SH_CLIENT_SECRET") == "secret-$-literal" and "secret-$-literal" not in repr(settings)
    with pytest.raises(SourceUnavailable, match="adopted"):
        SourceSettings.from_mapping({"SH_BASE_URL": "https://other.invalid"}).endpoint("SH_BASE_URL")


def test_registered_source_window_is_enforced_before_queueing_and_split_without_gaps():
    """卫星请求按31日合同分段，天气仍保留366日预算，不将限制写进算法。"""
    from datetime import date
    from modarchitect.input_sources.service import acquisition_windows

    plan = template("soil-weather-satellite-lai")["definition"]
    requirements = ("sentinel2_red_reflectance", "sentinel2_nir_reflectance")
    periods = acquisition_windows(plan, requirements, date(2025,1,1), date(2025,3,5))
    assert periods == [(date(2025,1,1), date(2025,1,31)), (date(2025,2,1), date(2025,3,3)), (date(2025,3,4), date(2025,3,5))]
    assert acquisition_windows(plan, ("temperature_mean_daily",), date(2025,1,1), date(2025,3,5)) == [(date(2025,1,1), date(2025,3,5))]
    body = AcquisitionRequest(expected_revision=1, object={"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}, reference_point={"latitude": 39.0, "longitude": 116.0}, start_date="2025-01-01", end_date="2025-02-01", requirements=requirements)
    with pytest.raises(ValueError, match="registered source limit: 31"):
        prepare_acquisition(plan, body)


def test_named_scheduler_environment_uses_exact_paged_match_and_private_source_settings(monkeypatch):
    """模糊首项不能被采用；不同任务的账户通过显式注入保持隔离。"""
    from types import SimpleNamespace
    from modarchitect.runtime.environments import read_environment
    from modarchitect.runtime import source_environment

    def response(request):
        """第一页只有相似环境，准确环境位于第二页。"""
        assert "searchVal" not in request.url.params
        page = int(request.url.params["pageNo"])
        records = [{"code": 10, "name": "chosen-copy", "config": "export SH_CLIENT_ID='wrong'"}]*100 if page == 1 else [{"code": 11, "name": "chosen", "config": "export SH_CLIENT_ID='correct'\nexport SH_CLIENT_SECRET='private-secret'"}]
        return httpx.Response(200, json={"code": 0, "data": {"total": 101, "totalList": records}})

    def scheduler():
        """真实环境查询客户端仅替换传输；每个调用独立创建。"""
        client = httpx.Client(base_url="https://scheduler.invalid/", transport=httpx.MockTransport(response))
        return SimpleNamespace(client=client, close=client.close)

    with scheduler().client as client:
        environment = read_environment(client, "chosen")
        assert environment.code == "11" and "private-secret" not in repr(environment)
        with pytest.raises(ValueError, match="missing or ambiguous"):
            read_environment(client, "missing")
    monkeypatch.setenv("MODARCHITECT_DS_SOURCE_ENVIRONMENT_NAME", "chosen")
    monkeypatch.setenv("SH_CLIENT_SECRET", "unrelated-process-account")
    monkeypatch.setattr(source_environment, "DolphinScheduler", scheduler)
    selected = source_environment.source_settings(environment_keys(frozenset({"sentinelhub_s2_l2a"})))
    assert selected.get("SH_CLIENT_ID") == "correct" and selected.get("SH_CLIENT_SECRET") == "private-secret"
    weather = source_environment.source_settings(environment_keys(frozenset({"openmeteo_archive"})))
    assert weather.get("SH_CLIENT_SECRET") is None
    import os
    assert os.environ["SH_CLIENT_SECRET"] == "unrelated-process-account"


def test_oauth_rejection_and_actual_token_expiry_refresh_without_persisting_secrets(monkeypatch):
    """401只换令牌重试一次，真实寿命到期后再认证，不在证据里留下账户或令牌。"""
    from modarchitect.input_sources import sentinel
    clock, authenticated, catalog_calls = [1000.0], [], []
    monkeypatch.setattr(sentinel, "monotonic", lambda: clock[0])
    request = AcquisitionRequest(expected_revision=1, object={"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}, reference_point={"latitude": 39.0, "longitude": 116.0}, start_date="2025-04-01", end_date="2025-04-01", requirements=("sentinel2_red_reflectance",))

    def respond(message):
        """认证后第一次目录故意401；目录成功后让第二令牌按expires_in到期。"""
        if message.url.path.endswith("/token"):
            token = "private-token-%s" % len(authenticated)
            authenticated.append(token)
            return httpx.Response(200, json={"access_token": token, "expires_in": 1})
        assert message.headers["Authorization"] == "Bearer "+authenticated[-1]
        if message.url.path.endswith("/catalog/v1/search"):
            catalog_calls.append(True)
            if len(catalog_calls) == 1:
                return httpx.Response(401, json={"reason": "expired"})
            clock[0] += 2
            return httpx.Response(200, json={"features": [{"id": "scene", "properties": {"datetime": "2025-04-01T01:00:00Z"}}]})
        return httpx.Response(200, content=scene_tar(reference_grid(116,39), "2025-04-01T01:00:00Z"))

    result = execute_acquisition(prepare_acquisition(template("soil-weather-satellite-lai")["definition"], request), lambda: None, transport=httpx.MockTransport(respond), settings=account_settings())
    assert len(authenticated) == 3 and len(catalog_calls) == 2
    assert not any(token in json.dumps(result) for token in authenticated)


def test_concurrent_provider_accounts_are_request_private():
    """两个真实采集流程并发时只使用各自账户，不覆盖进程环境或交叉Bearer。"""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import parse_qs
    plan = template("soil-weather-satellite-lai")["definition"]
    request = AcquisitionRequest(expected_revision=1, object={"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}, reference_point={"latitude": 39.0, "longitude": 116.0}, start_date="2025-04-01", end_date="2025-04-01", requirements=("sentinel2_red_reflectance",))

    def acquire(identity):
        """每个任务拥有自己的只读设置及网络会话。"""
        settings = SourceSettings.from_mapping({**account_settings().values, "SH_CLIENT_ID": identity, "SH_CLIENT_SECRET": "secret-"+identity})

        def respond(message):
            """以账户检查认证正文和后续Bearer，错配直接使测试失败。"""
            if message.url.path.endswith("/token"):
                data = parse_qs(message.content.decode())
                assert data["client_id"] == [identity] and data["client_secret"] == ["secret-"+identity]
                return httpx.Response(200, json={"access_token": "token-"+identity, "expires_in": 120})
            assert message.headers["Authorization"] == "Bearer token-"+identity
            if message.url.path.endswith("/catalog/v1/search"):
                return httpx.Response(200, json={"features": [{"id": "scene", "properties": {"datetime": "2025-04-01T01:00:00Z"}}]})
            return httpx.Response(200, content=scene_tar(reference_grid(116,39), "2025-04-01T01:00:00Z"))

        result = execute_acquisition(prepare_acquisition(plan, request), lambda: None, transport=httpx.MockTransport(respond), settings=settings)
        assert "token-"+identity not in json.dumps(result) and "secret-"+identity not in json.dumps(result)
        return len(result[0]["observations"]["rows"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(acquire, ("account-a", "account-b"))) == [1,1]


def test_explicit_ndvi_node_preserves_soil_weather_and_valid_zero_without_fake_labels():
    """比例结果为估计，合法零值保留，原实测标签不被替换。"""
    obj = {"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}

    def table(columns, values):
        """创建具有固定来源的独立标准算例。"""
        return {"columns": columns, "rows": [{"object": obj, "business_date": "2025-04-02", "values": values}], "source_sha256": ["a"*64]}

    inputs = {"observations": table([{"code": "lai", "name": "叶面积指数", "unit": "m2_m2", "value_kind": "observed"}], {"lai": 2}), "soil": table([{"code": "clay", "name": "黏粒", "unit": "percent", "value_kind": "estimated"}], {"clay": 20}), "satellite": table([{"code": code, "name": code, "unit": "dimensionless", "value_kind": "estimated"} for code in ("red", "nir")], {"red": .2, "nir": .2})}
    parameters = {"red_code": "red", "nir_code": "nir", "output_code": "ndvi"}
    result = derive_ndvi(inputs, parameters)["table"]
    assert result["rows"][0]["values"] == {"lai": 2, "clay": 20, "ndvi": 0}
    assert result["columns"][-1]["value_kind"] == "estimated"
    context = inputs["observations"]
    context["columns"], context["rows"][0]["values"] = [], {}
    minimal = derive_ndvi(inputs, parameters)["table"]
    assert minimal["rows"][0]["values"] == {"clay": 20, "ndvi": 0}
    inputs["satellite"]["rows"][0]["values"] = {"red": 0, "nir": 0}
    with pytest.raises(ValueError, match="denominator"):
        derive_ndvi(inputs, parameters)


@pytest.mark.parametrize("include_weather", [True, False])
def test_joint_source_graph_and_removing_weather_both_train_and_predict(tmp_path, include_weather):
    """完整三来源与去除天气组合均实际运行；空天气背景只保留对象日期。"""
    from datetime import date, timedelta
    from modarchitect.runtime.contracts import ObservationTable
    from modarchitect.runtime.executor import execute
    from modarchitect.runtime.preparation import prepare_observations, prepare_prediction
    from test_research_runtime import ScientificRunner, profiles_file

    plan = deepcopy(template("soil-weather-satellite-lai")["definition"])
    settings = plan["input_recipes"]["regression_config"]["value"]
    if not include_weather:
        settings["features"] = ["soil_clay", "soil_soc", "sentinel_ndvi"]
    registered = json.loads(profiles_file(tmp_path/"profiles.json").read_text())
    codes = {"soil_clay", "soil_soc", "sentinel2_red_reflectance", "sentinel2_nir_reflectance", "lai"}
    if include_weather:
        codes.update(code for code in settings["features"] if code != "sentinel_ndvi")
    requirements = {row["variable_code"]: row for row in plan["collection_requirements"]}
    columns = [{"code": var["code"], "name": var["name"], "unit": var["unit"], "value_kind": requirements[var["code"]]["catalog_binding"]["value_nature"]} for var in plan["variables"] if var["code"] in codes]
    rows = []
    for index in range(32):
        red, nir = .1+(index%5)*.02, .4+(index%7)*.02
        clay, soc = 10+(index%3)*4, 1+(index%4)*.4
        values = {"soil_clay": clay, "soil_soc": soc, "sentinel2_red_reflectance": red, "sentinel2_nir_reflectance": nir, "lai": 1+clay*.02+soc*.3+2*(nir-red)/(nir+red)}
        if include_weather:
            selected = [code for code in settings["features"] if code not in {"soil_clay", "soil_soc", "sentinel_ndvi"}]
            weather_values = [5+index%6, 15+index*7%11, 1+index*5%7]
            values.update(zip(selected, weather_values))
            values["lai"] += sum(weather_values)*.01
        rows.append({"object": {"field_ref": "reference-%s" % (index//8), "crop_code": "potato", "season_ref": "2025"}, "business_date": (date(2025,5,16)+timedelta(days=index%8)).isoformat(), "values": values})
    table = ObservationTable.model_validate({"columns": columns, "rows": rows})
    prepared = prepare_observations(plan, "train", table, "synthetic", "engineering", lambda definition: registered)
    trained = execute(prepared.payload, ScientificRunner())
    assert trained["pipeline"] is not None
    model = {"model_id": "engineering-model", "model_sha256": "a"*64, "model_json": trained["pipeline"]}
    prediction = deepcopy(table.model_dump(mode="json"))
    prediction["columns"] = [column for column in prediction["columns"] if column["code"] != "lai"]
    prediction["rows"] = [row for row in prediction["rows"] if row["business_date"] > "2025-05-20"]
    for row in prediction["rows"]:
        del row["values"]["lai"]
    request = prepare_prediction(model, ObservationTable.model_validate(prediction), "synthetic", "engineering", registered, [])
    predicted = execute(request.payload, ScientificRunner())
    actual = next(output for output in predicted["outputs"].values() if isinstance(output,dict) and "rows" in output and output["rows"] and "lai" in output["rows"][0]["values"])
    expected = {(row["object"]["field_ref"], row["business_date"]): row["values"]["lai"] for row in rows}
    assert len(actual["rows"]) == 12
    assert all(row["values"]["lai"] == pytest.approx(expected[row["object"]["field_ref"], row["business_date"]], abs=1e-8) for row in actual["rows"])
