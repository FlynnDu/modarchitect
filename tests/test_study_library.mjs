import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";
import { mountStudyLibrary, showTemplateSummary, showStudyFlow } from "../modarchitect/web/designer/study-library.js";
import { mountResearch } from "../modarchitect/web/designer/research.js";
import { renderSummary, renderModelRelationships } from "../modarchitect/web/designer/result-views.js";
import { inputUsageRows, flowDataset, studySettings } from "../modarchitect/web/designer/modeling.js";
import { applicationPath } from "../modarchitect/web/designer/http-path.js";

const html = await readFile(new URL("../modarchitect/web/designer/index.html", import.meta.url), "utf8");
const historicalRows = JSON.parse(await readFile(new URL("../modarchitect/contracts/study-templates-v1.json", import.meta.url), "utf8"));
const retained = new Set([
  "crop-growth-prediction", "soil-weather-lai", "soil-weather-biomass", "soil-weather-canopy", "soil-weather-satellite-lai",
  "biomass-growth-curve", "canopy-weather-tuber-dry-matter", "satellite-biomass-prediction",
]);
const newRows = JSON.parse(await readFile(new URL("../modarchitect/contracts/study-templates-growth-v1.json", import.meta.url), "utf8"));
const rows = [...historicalRows.filter((row) => retained.has(row.id)), ...newRows];
const view = (row) => ({ ...row, icon_name: row.id, execution_mode: row.bundle_sha256 ? "frozen_case" : "observations", definition: { ...structuredClone(row.definition), layout: { study_template: { id: row.id, sha256: row.sha256 } } } });

test("关系展示读取已保存模型的真实系数和单位，区分合成数据与因果结论", () => {
  const dom = new JSDOM('<div id="host"></div>'); globalThis.document = dom.window.document;
  try {
    const host = document.getElementById("host");
    renderModelRelationships(host, { training_data_kind: "synthetic", states: { model: { format: "linear_state_v1", state: { intercepts: { lai: 1.5 }, coefficients: { temperature: [0.2], rainfall: [-0.03] } }, feature_columns: [{ code: "temperature", name: "温度", unit: "celsius" }, { code: "rainfall", name: "降雨", unit: "mm" }], target_columns: [{ code: "lai", name: "叶面积指数", unit: "m2_m2" }] } } });
    assert.match(host.textContent, /叶面积指数.*1.5/);
    assert.match(host.textContent, /温度°C0.2/); assert.match(host.textContent, /降雨mm-0.03/);
    assert.match(host.textContent, /不代表因果/); assert.match(host.textContent, /合成演示数据/);
    assert.equal(host.hidden, false);
    renderModelRelationships(host, { states: {} }); assert.equal(host.hidden, true);
  } finally { dom.window.close(); }
});

function environment() {
  const dom = new JSDOM(html, { url: "http://localhost/designer/" });
  for (const key of ["window", "document", "location", "history", "Option"]) globalThis[key] = dom.window[key];
  return dom;
}

test("旧页面导入的参数入口继续兼容，避免混合缓存阻断模块加载", async () => {
  const old = await import("../modarchitect/web/designer/schema-fields.js");
  const current = await import("../modarchitect/web/designer/request-schema.js?v=continuous1");
  assert.equal(typeof old.requestProperties, "function");
  assert.equal(old.requestProperties, current.requestProperties);
  assert.equal(old.variableCandidates, current.variableCandidates);
});

test("入口模块加载失败会显示重新加载操作，结束永久等待", async () => {
  const dom = environment();
  try {
    const source = await readFile(new URL("../modarchitect/web/designer/startup.js", import.meta.url), "utf8");
    // data入口无法解析相对模块，实际触发动态导入失败的同一错误边界。
    await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
    assert.equal(document.getElementById("designer-startup-error").hidden, false);
    assert.doesNotMatch(document.getElementById("study-library-status").textContent, /正在读取/);
    assert.match(document.getElementById("stage-loading").textContent, /重新加载/);
  } finally { dom.window.close(); }
});

test("方案目录失败不保留加载文案，可在当前页面重试恢复", async () => {
  const dom = environment(), previous = globalThis.fetch; let failed = true;
  globalThis.fetch = async () => ({ ok: !failed, json: async () => ({ items: rows.map(view) }) });
  try {
    await mountStudyLibrary({ openTemplate() {} });
    const retry = document.getElementById("retry-study-library");
    assert.ok(retry && !retry.hidden && !retry.disabled);
    assert.doesNotMatch(document.getElementById("study-library-status").textContent, /正在读取/);
    failed = false; retry.click(); await new Promise(setImmediate);
    const cards = [...document.querySelectorAll("[data-study-template]")];
    assert.equal(cards.length, 20);
    for (const card of cards) {
      const icon = card.querySelector(".study-template-icon");
      assert.equal(icon.alt, "");
      assert.ok(icon.src.endsWith("/study-icons/" + card.dataset.studyTemplate + ".svg"));
    }
    [...document.querySelectorAll(".study-topic-filters button")].find((button) => button.textContent === "土壤与生长").click();
    const visible = cards.filter((card) => !card.hidden);
    assert.ok(visible.some((card) => card.dataset.studyTemplate === "soil-texture-canopy"));
    assert.ok(visible.every((card) => card.dataset.category === "土壤与生长"));
    assert.equal(retry.hidden, true);
  } finally { globalThis.fetch = previous; dom.window.close(); }
});

test("代理路径下导航和研究目录请求保留应用前缀及查询参数", async () => {
  const dom = new JSDOM(html, { url: "http://localhost:17000/modarchitect/designer/?template=example" });
  const previous = globalThis.fetch, calls = [];
  for (const key of ["window", "document", "location", "history", "Option"]) globalThis[key] = dom.window[key];
  const items = [
    { ...view(rows[1]), icon_name: rows[1].id + ".svg" },
    { ...view(rows[2]), icon_name: undefined },
  ];
  globalThis.fetch = async (url) => { calls.push(url); return { ok: true, json: async () => ({ items }) }; };
  try {
    await mountStudyLibrary({ openTemplate() {} });
    assert.equal(calls[0], "/modarchitect/api/v1/workspace/study-templates");
    assert.equal(document.querySelector(".sono-brand").pathname, "/modarchitect/designer/");
    assert.equal(document.querySelector(".top-link").pathname, "/modarchitect/docs");
    assert.equal(applicationPath("/api/v1/workspace/plans?page=2"), "/modarchitect/api/v1/workspace/plans?page=2");
    assert.equal(applicationPath("./validate"), "./validate");
    const icons = [...document.querySelectorAll(".study-template-icon")];
    assert.deepEqual(icons.map((icon) => icon.src.split("/").at(-1)), [rows[1].id + ".svg", "crop-growth-prediction.svg"]);
  } finally { globalThis.fetch = previous; dom.window.close(); }
});

test("研究目录按问题拆分，预览与采用分开，流程不暴露验收案例和程序术语", async () => {
  const dom = environment(), previous = globalThis.fetch, calls = [];
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ items: rows.map(view) }) });
  try {
    await mountStudyLibrary({ openTemplate: async (...args) => calls.push(args) });
    assert.equal(document.querySelectorAll("[data-study-template]").length, rows.length);
    const card = document.querySelector('[data-study-template="crop-growth-prediction"]');
    card.querySelectorAll("button")[0].click(); await new Promise((resolve) => setTimeout(resolve, 0));
    card.querySelectorAll("button")[1].click(); await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls, [["crop-growth-prediction", false], ["crop-growth-prediction", true]]);
    showTemplateSummary(view(historicalRows.find((row) => row.id === "crop-growth-prediction")));
    const selected = view(historicalRows.find((row) => row.id === "crop-growth-prediction"));
    showStudyFlow({ definition: selected.definition, template: selected });
    const text = document.getElementById("study-template-list").textContent + document.getElementById("study-template-summary").textContent;
    assert.doesNotMatch(text, /658b|冻结|封存|工程验收|SHA-256/);
    assert.ok(document.querySelector('[data-flow-stage="node:regression"]'));
    assert.ok(document.querySelector('[data-flow-stage="products"]'));
    assert.equal(document.querySelector(".research-component-flow").open, false);
    assert.match(document.querySelector('[data-flow-stage="products"]').textContent, /等待产出/);
    const category = rows.find((row) => row.id === "soil-weather-lai").researcher.category;
    const filter = [...document.querySelectorAll(".study-topic-filters button")].find((button) => button.textContent === category); filter.click();
    assert.equal(document.querySelectorAll(".study-template-card:not([hidden])").length, rows.filter((row) => row.researcher.category === category).length);
    assert.equal(document.querySelector('[data-study-template="field-indicator-summary"]'), null);
    for (const id of ["start-chain", "study-chain", "study-analysis", "chain-plan"]) assert.equal(document.getElementById(id).hidden, true);
  } finally { globalThis.fetch = previous; dom.window.close(); }
});

test("独立研究方案可保存重开，数据说明面向研究者，执行时保留数据来源", async () => {
  const dom = environment(), previous = globalThis.fetch, row = view(historicalRows.find((value) => value.id === "greenhouse-water-use")), requests = [];
  let plan = row.definition, saved = null, version = null;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("/api/v1/workspace", ""), body = options.body && JSON.parse(options.body);
    requests.push({ path, body });
    let value;
    if (path === "/session") value = {};
    else if (path === "/api/v1/model-center/research-rules") value = { version: "1.0", rules: [] };
    else if (path === "/check-execution") value = { can_execute: true, issues: [] };
    else if (path === "/runs/run/plan") value = plan;
    else if (path.startsWith("/study-templates/")) value = row;
    else if ((path === "/plans" && options.method === "POST") || (path === "/plans/study" && options.method === "PUT")) value = saved = {
      design_id: "study", revision: saved ? 2 : 1, version_name: body.version_name || saved?.version_name, configuration: { definition: body.definition },
    };
    else if (path === "/plans/study/publish") value = version = { design_version_id: "version", version_name: saved.version_name || "1.0.0" };
    else if (path === "/plans/study") value = { ...saved, latest_version: version, observations: null, data_kind: "user_supplied" };
    else if (path === "/template-runs") value = { run_id: "run", kind: "simulate", status: "succeeded", input_sha256: "input", result_sha256: "output", result_json: { outputs: {}, metrics: [], pipeline: null, receipts: [] } };
    else value = { items: [] };
    return { ok: true, json: async () => value };
  };
  try {
    const runtime = mountResearch({ getDefinition: () => plan, openDefinition: async (value) => { plan = value; }, notify() {}, onTemplateChange: showTemplateSummary, onFlowChange: showStudyFlow });
    await new Promise((resolve) => setTimeout(resolve, 20));
    await runtime.openTemplate(row.id, true);
    const versionInput = document.getElementById("wizard-study-version"), currentVersion = document.getElementById("wizard-study-version-current");
    assert.match(currentVersion.textContent, /保存为可应用版本/);
    assert.equal("version_name" in requests.find((item) => item.path === "/plans" && item.body).body, false);
    versionInput.value = "春季采样基线";
    await runtime.publishConfiguration();
    assert.equal(document.getElementById("study-run").disabled, false);
    assert.match(document.getElementById("data-summary").textContent, /示例/);
    assert.doesNotMatch(document.getElementById("data-summary").textContent, /冻结|封存|SHA/);
    assert.equal(document.getElementById("upload-observations").disabled, true);
    document.getElementById("study-run").click();
    await new Promise((resolve) => setTimeout(resolve, 20));
    const request = requests.find((item) => item.path === "/template-runs");
    assert.equal(request.body.template_sha256, row.sha256);
    assert.equal(request.body.expected_revision, 2);
    assert.equal(requests.find((item) => item.path === "/plans/study" && item.body).body.version_name, "春季采样基线");
    assert.match(currentVersion.textContent, /最近保存的可应用版本 · 春季采样基线/);
    assert.equal(versionInput.value, "");
    assert.ok(requests.findIndex((item) => item.path === "/check-execution") < requests.findIndex((item) => item.path === "/template-runs"));
    assert.match(document.querySelector('[data-node-code="node_1"]').textContent, /已完成/);
    assert.equal("observations" in request.body, false);
    const select = document.getElementById("cloud-plans"); select.add(new Option("saved", "study")); select.value = "study";
    select.dispatchEvent(new window.Event("change")); await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(document.getElementById("study-run").disabled, false);
    assert.equal(document.getElementById("study-template-summary").hidden, false);
    assert.match(currentVersion.textContent, /最近保存的可应用版本 · 春季采样基线/);
  } finally { globalThis.fetch = previous; dom.window.close(); }
});

test("资格复核的缺分保持为空，方法评价显示实际留出值而不冒充保存模型", () => {
  const dom = environment();
  try {
    const host = document.createElement("div");
    renderSummary(host, { overall: { comment: "证据不足" }, module_scores: [{ name: "土壤", score: null, grade: "暂不评分", unscored_reason: "缺少适用标尺" }] });
    assert.match(host.textContent, /暂不评分/); assert.match(host.textContent, /缺少适用标尺/);
    renderSummary(host, { product: { code: "cpu_result" }, payload: { algorithm: "random_forest", training_count: 9, mae: 1, rmse: 2, target: { unit: "celsius" }, rows: [{ unit_ref: "plant-1", target_at: "2025-01-03", estimated: [3], observed: [4] }] } });
    assert.match(host.textContent, /训练 9 条 · 留出 1 条/);
    assert.match(host.textContent, /3\.0000/);
    renderSummary(host, { product: { code: "greenhouse_crop_et_comparison" }, payload: { estimated_crop_et_mm_d: 4.156, weighing_crop_et_mm_d: 3.83, difference_mm_d: .326 } });
    assert.match(host.textContent, /称重日耗水（mm\/d）/); assert.match(host.textContent, /3\.83/);
    renderSummary(host, { product: { code: "greenhouse_weighing_crop_et_day" }, payload: { hours: [{ scope: { started_at: "2025-01-01T00:00:00+08:00" }, evapotranspiration_g_h: 100, transpiration_g_h: null }] } });
    assert.match(host.textContent, /缺少蒸发分离证据/);
  } finally { dom.window.close(); }
});

test("研究者可调整日期和固定指标，参数修改进入实际方案而不替换数据", async () => {
  const dom = environment();
  try {
    const row = view(historicalRows.find((item) => item.id === "growth-water-response")); let definition = row.definition;
    const definitions = JSON.parse(await readFile(new URL("../modarchitect/contracts/agronomic-research-components-v1.json", import.meta.url), "utf8"));
    const records = new Map(definitions.map((item) => [item.code + "@1", { definition: item, research_contract: { request_schema: item.configuration.research_model.request_schema } }]));
    showTemplateSummary(row, { getDefinition: () => structuredClone(definition), getRecords: () => records, onEdit(value) { definition = value; } });
    const date = document.querySelector('[data-study-parameter="start_date"]'); date.value = "2026-10-10"; date.dispatchEvent(new window.Event("change"));
    assert.equal(definition.input_recipes.settings.value.start_date, "2026-10-10");
    const check = document.querySelector(".study-research-settings input[type=checkbox]"); check.checked = false; check.dispatchEvent(new window.Event("change"));
    assert.equal(definition.input_recipes.settings.value.variables.length, 3);
    assert.deepEqual(definition.input_recipes.series, row.definition.input_recipes.series);
    assert.match(document.getElementById("study-template-summary").textContent, /需要哪些数据/);
  } finally { dom.window.close(); }
});

test("全部研究使用有序卡片，准确成果与误差分别显示，无效草稿清除上次状态", () => {
  const dom = environment();
  try {
    for (const item of rows) {
      const row = view(item); showStudyFlow({ definition: row.definition, template: row });
      assert.equal(document.querySelectorAll("[data-node-code]").length, row.definition.composition.nodes.length);
      for (const node of row.definition.composition.nodes) assert.ok(document.querySelector('[data-node-code="' + node.code + '"]'));
      assert.match(document.querySelector('[data-flow-kind="product"]').textContent, /等待产出/);
      assert.doesNotMatch(document.getElementById("public-research-flow").textContent, /验证通过|持续入库|312 条|24 组/);
    }
    const row = view(rows[0]);
    const run = { kind: "train", status: "succeeded", result_json: { outputs: { trained_model: {}, predictions: {}, unrelated: {} }, metrics: [{ output: "predictions", status: "evaluated", target: "lai", rows: 5, rmse: 0.01, unit: "1" }] } };
    showStudyFlow({ definition: row.definition, template: row, run });
    assert.match(document.querySelector('[data-node-code="regression"]').textContent, /已完成/);
    assert.match(document.querySelector('[data-flow-stage="products"]').textContent, /2 项成果/);
    assert.match(document.querySelector('[data-flow-stage="evaluation"]').textContent, /5 条配对/);
    document.querySelector(".research-component-flow").open = true;
    showStudyFlow({ definition: row.definition, template: row, run });
    assert.equal(document.querySelector(".research-component-flow").open, true);
    row.definition.composition.outputs[0].source.node = "removed-node";
    showStudyFlow({ definition: row.definition, template: row });
    assert.match(document.querySelector('#public-research-flow [role="alert"]').textContent, /补齐输入和连接/);
    assert.equal(document.querySelectorAll(".research-stage-card").length, 0);
  } finally { dom.window.close(); }
});

test("服务端输入规则不通过时，页面保留当前方案且不保存或提交计算", async () => {
  const dom = environment(), previous = globalThis.fetch, row = view(historicalRows.find((item) => item.id === "greenhouse-water-use")), requests = [];
  let plan = row.definition;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url); requests.push({ path, method: options.method });
    let value = { items: [] };
    if (path.endsWith("/research-rules")) value = { rules: [{ code: "input_source", guidance: "请补齐当前研究的数据来源。" }] };
    else if (path.endsWith("/session")) value = {};
    else if (path.includes("/study-templates/")) value = row;
    else if (path.endsWith("/check-execution")) value = { can_execute: false, issues: [{ rule: "input_source", path: ["observations"], message: "Unavailable source" }] };
    return { ok: true, json: async () => value };
  };
  try {
    const runtime = mountResearch({ getDefinition: () => plan, openDefinition: async (value) => { plan = value; }, notify() {} });
    await new Promise((resolve) => setTimeout(resolve, 20)); await runtime.openTemplate(row.id, false);
    document.getElementById("study-run").click(); await new Promise((resolve) => setTimeout(resolve, 20));
    assert.match(document.getElementById("workspace-status").textContent, /补齐当前研究的数据来源/);
    assert.equal(requests.filter((request) => request.method === "POST" && /\/(plans|runs|template-runs)$/.test(request.path)).length, 0);
    assert.equal(plan, row.definition);
  } finally { globalThis.fetch = previous; dom.window.close(); }
});

test("串联卡片按五个外部指标逐项展示，与用途表一致，真实留出记录形成评价分支", () => {
  const dom = environment();
  try {
    const row = view(historicalRows.find((item) => item.id === "growth-trend-and-environment"));
    const context = { definition: row.definition, template: row, data: row.observations, dataKind: "synthetic" };
    showStudyFlow(context);
    const input = document.querySelector('[data-flow-stage="inputs"]');
    assert.equal(input.querySelector(".research-stage-headline").textContent, "5 项输入指标");
    assert.equal(input.querySelector(".research-stage-description").textContent, "1 张观测表 · 90 条记录");
    const labels = [...input.querySelectorAll(".research-source-variable")].map((node) => node.textContent);
    assert.deepEqual(labels, inputUsageRows(row.definition).map((entry) => entry.variable.name));
    assert.deepEqual(labels, ["定植后天数", "株高", "NDVI", "土壤体积含水率", "气温"]);
    assert.equal(labels.includes("历史曲线估计株高"), false);
    const facts = document.querySelector('[data-flow-stage="dataset"] .research-stage-body > dl').textContent;
    assert.match(facts, /历史拟合45 条/); assert.match(facts, /模型训练25 条/); assert.match(facts, /时间留出20 条/);
    const branch = document.querySelector(".research-data-branch");
    assert.equal(branch.dataset.branchSource, "dataset"); assert.equal(branch.dataset.branchTarget, "evaluation");
    assert.match(branch.getAttribute("aria-label"), /不参与训练/);
    assert.ok(document.querySelectorAll(".research-overview-edge").length > 4);
    assert.equal(document.querySelectorAll(".research-stage-eyebrow, .research-stage-recommendation").length, 0);
    assert.doesNotMatch(document.querySelector('[data-flow-stage="evaluation"] h3').textContent, /独立/);
    const draft = structuredClone(row.definition), data = structuredClone(row.observations);
    draft.variables = draft.variables.filter((item) => item.code !== "ndvi");
    draft.collection_requirements = draft.collection_requirements.filter((item) => item.variable_code !== "ndvi");
    draft.input_recipes.observations.variable_codes = draft.input_recipes.observations.variable_codes.filter((code) => code !== "ndvi");
    draft.input_recipes.regression_config.value.features = draft.input_recipes.regression_config.value.features.filter((code) => code !== "ndvi");
    data.columns = data.columns.filter((column) => column.code !== "ndvi");
    for (const record of data.rows) delete record.values.ndvi;
    showStudyFlow({ ...context, definition: draft, data });
    assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-headline').textContent, "4 项输入指标");
    assert.equal(inputUsageRows(draft).length, 4);
  } finally { dom.window.close(); }
});

test("预测输入、无留出记录和原生资料不沿用训练口径或虚构分支", () => {
  const dom = environment();
  try {
    const row = view(historicalRows.find((item) => item.id === "growth-trend-and-environment"));
    showStudyFlow({ definition: row.definition, template: row, run: { kind: "predict", status: "queued" } });
    assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-headline').textContent, "4 项输入指标");
    const labels = [...document.querySelectorAll('[data-flow-stage="inputs"] .research-source-variable')].map((node) => node.textContent);
    assert.equal(labels.includes("株高"), false);
    assert.equal(document.querySelector(".research-data-branch"), null);
    const earlier = structuredClone(row.observations); earlier.rows = earlier.rows.filter((record) => record.business_date <= "2026-06-09");
    showStudyFlow({ definition: row.definition, data: earlier });
    assert.match(document.querySelector(".research-data-branch").getAttribute("aria-label"), /待补留出实测/);
    const native = view(historicalRows.find((item) => item.id === "crop-low-temperature"));
    showStudyFlow({ definition: native.definition, template: native });
    assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-headline').textContent, "1 项输入指标");
    assert.equal(document.querySelector(".research-data-branch"), null);
  } finally { dom.window.close(); }
});

test("历史运行缺少分段原始记录时只用已存统计，不从日期跨度补造样本", () => {
  const dom = environment();
  try {
    const row = view(historicalRows.find((item) => item.id === "growth-trend-and-environment")), config = studySettings(row.definition);
    const output = row.definition.composition.outputs.find((port) => port.source.node === config.model.code && port.source.port === "predictions").code;
    const run = { kind: "train", status: "succeeded", result_json: { outputs: {}, input_sources: { row_count: 90 }, metrics: [{ output, target: "height", status: "evaluated", expected_rows: 20, rows: 18, rmse: 1, unit: "cm" }] } };
    const facts = flowDataset(row.definition, null, run);
    assert.equal(facts.periods, null); assert.equal(facts.rows, 90); assert.equal(facts.holdout, 20);
    showStudyFlow({ definition: row.definition, run });
    const body = document.querySelector('[data-flow-stage="dataset"] .research-stage-body > dl').textContent;
    assert.match(body, /建模期记录70 条/); assert.match(body, /留出期记录20 条/);
    assert.doesNotMatch(body, /历史拟合|45 条|25 条/);
    assert.match(document.querySelector('[data-flow-stage="evaluation"]').textContent, /18 条配对/);
  } finally { dom.window.close(); }
});
