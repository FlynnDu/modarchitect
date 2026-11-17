# SoilGrids 原生像元正例

2026-11-12 从 ISRIC SoilGrids WCS 2.0.1 公开服务取得 `bdod_0-5cm_mean`。来源：ISRIC SoilGrids，CC BY 4.0；[服务](https://maps.isric.org/mapserv/bdod)、[产品说明](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)。

请求 `GetCoverage`、`image/tiff`、原生 CRS `http://www.opengis.net/def/crs/EPSG/0/152160`，`SUBSET=X(10132250,10132500)`、`SUBSET=Y(5584750,5585000)`。1×1、250m、WGS84 Homolosine，映射整数 107，规范容重 1.07 kg/dm³。用于读取真实提供方 CRS/transform 的兼容回归，不代表其他土层或区域已经验收。
