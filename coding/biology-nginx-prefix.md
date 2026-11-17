# 生物所Nginx路径前缀修复

2026-11-17。用户要求修复`17000/modarchitect/`跳转丢前缀及`17000/modarchitect/docs`目录加载错误，并在线验收。

## 已复现与验收

真实HTTP反馈：`/modarchitect/`返回307及`Location: /designer/`；文档HTML引用`/openapi.json`；设计器导航与三个请求入口均使用根路径。配置已能转发API，但不能据此验收页面。根因直接由响应与源码字面路径对应，无需对网络、数据库或调度另作故障假设。

验收覆盖首页跳转、静态资源、设计器目录与工作区会话、保存重开、Swagger读取准确OpenAPI并实际调用健康接口，以及18925直连兼容。业务缺少/错误Key仍401；既有mlgrowth入口响应保持。只更新本项目API镜像及其模板，不修改执行Worker、数据和密钥。

## 实现与边界

- Nginx沿用去除`/modarchitect/`前缀的转发，并固定发送`X-Forwarded-Prefix: /modarchitect`。
- API装配支持显式`MODARCHITECT_PROXY_PREFIX`；只有请求头与部署配置精确一致时恢复ASGI的`root_path/path/raw_path`。未配置、无请求头或不同前缀仍按原直连解释，不从任意请求头生成外部地址。研究正文预算先按原路由执行，再恢复代理上下文，不改变认证与上传限制。
- 首页跳转从请求的root_path生成；OpenAPI禁用按请求向共享缓存插入servers，返回时按当前入口显式给出`/modarchitect`（代理）或`/`（直连）。用户明确要求Servers像mlgrowth一样显示具体root，不采用`.`。只复制schema最外层并替换servers，不修改共享缓存。依据[FastAPI代理文档](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)及[OpenAPI URL规则](https://spec.openapis.org/oas/v3.1.0.html#server-object)。
- 页面导航使用相对链接；三个fetch入口共用按页面地址解析应用根路径的方法，保留查询参数和请求选项。不做Nginx正文替换，不另建页面或业务规则。

预计修改`modarchitect/api.py`、`designer.py`及设计器的公共路径方法、三个fetch入口与HTML；测试沿用`test_designer_demo.py`和`test_study_library.mjs`。发布从当前准确API镜像增量安装wheel并核验包文件，备份运行Job/模板、按并发索引发布，保留原镜像供回退；不涉及数据库迁移。

## 完成与复跑

11:51（北京时间）最终API Job13部署successful，allocation健康，Consul passing；准确镜像与wheel见[部署证据](deployments/modarchitect-biology/nginx-prefix-deployment.json)。已核对141个包文件无差异；原执行Job5、海豚Worker Job36、密钥和Nginx文件保持。初始API Job11与模板快照保存在忽略目录`.ops/biology-nginx-prefix/private/`，并归档到当前服务制品目录的受限private子目录；回退恢复初始Job/模板及其原镜像，不降级或清理数据库。

执行命令与结果：

- `.venv/Scripts/python.exe -m pytest tests/test_designer_demo.py tests/test_design_api.py -q`：11通过，8项专属隔离库测试因本次未配置该库而跳过；不把线上业务库作为pytest目标。
- `npm test`：43通过，覆盖前缀、查询参数、页面相对校验地址及原直连调用。
- 当前Python执行`E:/CodexData/home/skills/python-project-standards/scripts/check_python_headers.py modarchitect/api.py modarchitect/designer.py tests/test_designer_demo.py`及`-m ruff check`相同三个文件：通过。
- `node scripts/verify_designer_ui.mjs --base-url http://172.16.1.122:17000/modarchitect --design-only --session-file .ops/biology-nginx-prefix/private/session.json --output coding/deployments/modarchitect-biology/nginx-prefix-ui-acceptance.json`：真实DOM事件与线上HTTP通过；20份目录、预览、保存、导出导入，HTTP错误0。
- 相同命令增加`--reopen-study 01a1e7a1-ae96-7105-bf55-143b0484ce42`并输出`nginx-prefix-ui-reopened.json`：新进程重开同一方案、修订和配置摘要一致，HTTP错误0。未启动采集、计算或海豚任务。

[HTTP验收](deployments/modarchitect-biology/nginx-prefix-http-acceptance.json)已确认首页307目标保留前缀、全部页面资源200、83个API路径、代理Servers为`/modarchitect`、直连Servers为`/`，各自按schema根地址发起health均成功。认证正反例保留。原生浏览器连接不可用，Chrome窗口在恢复尝试后仍最小化，未进行原生像素检查；以上不表述为完整浏览器视觉验收。

页面保存验收曾检出公共方法错误拼接`./validate`；已补最小失败用例，修复为保留相对地址，再发布最终制品并重新完成保存与新进程重开。两轮发布按具体JobVersion匹配deployment及allocation，不能取deployments列表首项当作当前发布成功。
