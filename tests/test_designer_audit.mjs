import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";
import { mountWizard } from "../modarchitect/web/designer/wizard.js";
import { mountMethodPicker } from "../modarchitect/web/designer/method-picker.js";
import { prepareMethodDraft } from "../modarchitect/web/designer/methods.js";
import { parameters } from "../modarchitect/web/designer/schema-fields.js";
import { blankPlan } from "../modarchitect/web/designer/editor.js";
import { inputUsageRows, modelingSteps, predictionColumns, productRows } from "../modarchitect/web/designer/modeling.js";
import { flowOverview } from "../modarchitect/web/designer/flow-overview.js";
import { researchFlow } from "../modarchitect/web/designer/research-flow.js";
import { inspect } from "../modarchitect/web/designer/panels.js";

const root = new URL("../modarchitect/", import.meta.url);
const json = async (path) => JSON.parse(await readFile(new URL(path, root), "utf8"));
const html = await readFile(new URL("web/designer/index.html", root), "utf8");
const templates = await json("contracts/study-templates-v1.json");
const names = ["logistic-growth-contracts", "multivariate-regression", "chain-components", "runtime-components", "analysis-components", "native-study-components", "agronomic-research-components", "field-research-components", "tabular-learning-components"];
const definitions = (await Promise.all(names.map((name) => json("contracts/" + name + "-v1.json")))).flat();
const compatibility = { ...await json("contracts/execution-compatibility-v1.json"), ...await json("contracts/native-study-execution-v1.json") };
const records = new Map(definitions.map((definition) => {
  const key = definition.code + "@" + definition.revision, research = definition.configuration.research_model;
  const capability = research?.execution || compatibility[key]?.capability;
  return [key, { definition, available_for_new_design: !definitions.some((next) => next.code === definition.code && next.revision > definition.revision),
    research_contract: { request_schema: research?.request_schema || definition.configuration.request_schema, capabilities: capability,
      input_uses: capability?.input_uses || {}, execution: { status: "design_only" } } }];
}));
function environment() {
  const dom = new JSDOM(html, { url: "http://localhost/designer/#configure/inputs" });
  for (const key of ["window", "document", "location", "history", "Option"]) globalThis[key] = dom.window[key];
  return dom;
}

test("技术区只读展示指标定义和来源说明，不提供新增私有指标或采样设置", () => {
  const dom = environment(), plan = templates.find((row) => row.id === "soil-weather-lai").definition;
  try {
    const host = document.getElementById("inspector-content"), flow = { inputs: [], models: [], outputs: [] };
    const variable = plan.variables[0];
    inspect(host, { definition: plan, flow, selected: "variable:" + variable.code }, {});
    assert.ok(host.textContent.includes(variable.name) && host.textContent.includes(variable.definition_version));
    assert.equal(host.querySelector("input, textarea, select"), null);
    assert.doesNotMatch(host.textContent, /采样间隔|最低记录数/);
    inspect(host, { definition: plan, flow, selected: "plan" }, { addObservation() {} });
    assert.deepEqual([...host.querySelectorAll("button")].map((button) => button.textContent), ["从系统目录选择输入"]);
  } finally { dom.window.close(); }
});

test("第5步直达确认页，确认页保留评价和版本设置并定位错误", async () => {
  const dom = environment(), plan = structuredClone(templates.find((row) => row.id === "soil-weather-lai").definition);
  try {
    history.replaceState(null, "", "#configure/outputs");
    let issue = { path: ["collection_requirements", 0], type: "unregistered_indicator" }, saves = 0;
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit(next) { Object.assign(plan, next); },
      onSave: async () => { saves++; return { revision: 1 }; },
      validate: async () => issue ? { valid: false, issues: [issue] } : { valid: true, issues: [] } });
    assert.equal(location.hash, "#review");
    assert.equal(document.querySelectorAll("[data-section]").length, 5);
    document.querySelector('[data-section="calculation"]').click();
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#review");
    document.getElementById("wizard-edit-again").click();
    assert.equal(location.hash, "#configure/calculation");
    document.getElementById("wizard-next").click();
    assert.ok(document.querySelector("#wizard-review #wizard-study-version"));
    const save = document.getElementById("wizard-save-design");
    save.click(); await new Promise(setImmediate);
    assert.equal(saves, 0);
    document.querySelector(".review-issue button").click();
    assert.equal(location.hash, "#configure/sources");
    wizard.openReview();
    issue = { path: ["evaluation", "success_criteria"], message: "Invalid criteria" };
    assert.equal(await wizard.check(), false);
    document.querySelector(".review-issue button").click();
    const criteria = document.getElementById("wizard-success");
    assert.equal(document.activeElement, criteria);
    criteria.value = "使用同日期的独立观测判断预测误差";
    criteria.dispatchEvent(new window.Event("change"));
    assert.equal(plan.evaluation.success_criteria, criteria.value);
    issue = null;
    save.click(); await new Promise(setImmediate);
    assert.equal(saves, 1);
    assert.match(document.getElementById("wizard-check-result").textContent, /研究方案已保存 · 修订 1/);
    assert.deepEqual([...document.querySelectorAll("[data-stage]")].map((step) => step.dataset.stage), ["select", "configure", "review"]);
  } finally { dom.window.close(); }
});

test("分析方案只有实际资料、分析和成果，不追加训练、数据划分或评价", () => {
  const row = templates.find((item) => item.id === "crop-high-temperature");
  const overview = flowOverview(row.definition, records, { template: row });
  assert.equal(overview.stages.length, 3);
  assert.equal(overview.stages.filter((stage) => stage.nodeCode).length, 1);
  assert.equal(overview.stages.some((stage) => ["dataset", "evaluation"].includes(stage.code)), false);
  assert.deepEqual(overview.edges.map((edge) => [edge.from, edge.to]), [["inputs", "node:analysis"], ["node:analysis", "products"]]);
});

test("日期拟合的摘要保留准确方法、实际资料和当前成果能力", () => {
  const source = templates.find((row) => row.id === "soil-weather-lai").definition;
  const { definition: plan } = prepareMethodDraft(source, records, "logistic_growth_curve@4", source.composition.nodes[0].code);
  const dom = environment();
  try {
    mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit() {}, validate() {} }).openReview();
    const summary = document.getElementById("wizard-review-summary").textContent;
    assert.match(summary, /逻辑斯蒂生长曲线模型/);
    assert.match(summary, /平台观测日期驱动/);
    assert.doesNotMatch(summary, /→|· 配置/);
    assert.doesNotMatch(document.getElementById("wizard-method-note").textContent, /开始训练/);
    assert.equal(modelingSteps(plan, records).steps[1].inputs.length, 1);
  } finally { dom.window.close(); }
});

test("日期拟合按实际四个步骤展示，自动日期处理仍可追溯", async () => {
  const sample = await json("web/designer/calendar-study.json");
  const overview = flowOverview(sample.definition, records);
  assert.equal(overview.stages.length, 4);
  for (const node of sample.definition.composition.nodes) assert.equal(overview.stages.filter((stage) => stage.nodeCode === node.code).length, 1);
  assert.equal(overview.stages.some((stage) => stage.code === "evaluation"), false);
  for (const edge of overview.edges) assert.ok(overview.stages.some((stage) => stage.code === edge.from) && overview.stages.some((stage) => stage.code === edge.to));
});

test("历史目录缺少研究表单元数据仍保留实际节点和依赖，不推测算法参数", () => {
  const row = templates.find((item) => item.id === "crop-high-temperature");
  const legacy = new Map([...records].map(([key, record]) => [key, { definition: record.definition }]));
  const overview = flowOverview(row.definition, legacy);
  assert.equal(overview.stages.length, 3);
  assert.equal(overview.stages.find((stage) => stage.kind === "calculation").nodeCode, "analysis");
  assert.equal(overview.edges.length, 2);
});

test("温室方案保留两个独立计算、下游汇合和各自产出的成果", () => {
  const row = templates.find((item) => item.id === "greenhouse-water-use");
  const overview = flowOverview(row.definition, records, { template: row });
  assert.equal(overview.stages.length, 9);
  assert.equal(overview.stages.filter((stage) => stage.nodeCode).length, 3);
  assert.equal(overview.stages.filter((stage) => stage.kind === "product").length, 3);
  assert.ok(overview.edges.some((edge) => edge.from === "node:node_1" && edge.to === "node:node_3"));
  assert.ok(overview.edges.some((edge) => edge.from === "node:node_2" && edge.to === "node:node_3"));
  assert.equal(overview.edges.some((edge) => edge.from === "node:node_1" && edge.to === "node:node_2"), false);
  assert.ok(overview.layers.some((layer) => layer.includes("node:node_1") && layer.includes("node:node_2")));
});

test("指定资料在准确端口显示指标、用途和来源，保留可见的预期成果", () => {
  const dom = environment(), row = templates.find((item) => item.id === "greenhouse-water-use");
  const plan = structuredClone(row.definition);
  plan.layout.study_template = { id: row.id, sha256: row.sha256 };
  const template = { id: row.id, sha256: row.sha256, data_kind: "synthetic", input_policy: { mode: "approved_dataset" }, input_requirements: [
    { port: "node_1_request", code: "net_radiation_mj_m2_d", name: "日净辐射", unit: "MJ/(m²·d)", kind: "input", use: "耗水估算", source: "温室合成示例" },
    { port: "node_2_request", code: "ground_area_m2", name: "栽培地面面积", unit: "m²", kind: "input", use: "单位面积耗水换算", source: "示例栽培单元" },
    { port: "node_3_request", code: "kc", name: "阶段作物系数", unit: "1", kind: "parameter", use: "方法参数", source: "指定示例作物系数" },
  ] };
  try {
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit() {}, validate() {} });
    wizard.setTemplate(template); wizard.openInputs();
    assert.equal(location.hash, "#configure/inputs");
    assert.ok(document.getElementById("open-indicator-library").hidden);
    const view = flowOverview(plan, records, { template });
    for (const item of template.input_requirements) {
      const field = document.querySelector('#wizard-role-table [data-input-port="' + item.port + '"][data-variable-code="' + item.code + '"]');
      if (item.kind === "parameter") assert.equal(field, null);
      else {
        assert.ok(field.textContent.includes(item.name) && field.textContent.includes(item.source));
        assert.equal(field.closest("details, dialog"), null);
      }
      assert.equal(view.stages.find((stage) => stage.inputCode === item.port).items[0][0], item.name);
      assert.ok(view.stages.find((stage) => stage.inputCode === item.port).items[0][1].includes(item.use));
    }
    assert.doesNotMatch(document.getElementById("wizard-role-table").textContent, /方法资料与参数|阶段作物系数/);
    assert.equal(document.querySelectorAll("#wizard-output-table [data-product]").length, 0);
    assert.match(document.getElementById("wizard-review-summary").textContent, /作物日蒸散偏差/);
    const other = flowOverview(plan, records, { template: { ...template, sha256: "superseded" } });
    assert.equal(other.stages.some((stage) => stage.items.some(([name]) => name === "栽培地面面积")), false);
  } finally { dom.window.close(); }
});

test("已调整的模拟分析指标在对应资料卡中只显示当前选择", () => {
  const row = templates.find((item) => item.id === "growth-water-response");
  const plan = structuredClone(row.definition);
  plan.layout.study_template = { id: row.id, sha256: row.sha256 };
  plan.input_recipes.settings.value.variables = ["wofost_lai"];
  const input_requirements = row.indicator_options.map((option) => ({ ...option, port: "series", source: "指定模拟成果", use: "分析指标" }));
  const view = flowOverview(plan, records, { template: { id: row.id, sha256: row.sha256,
    data_kind: "frozen_archive", input_policy: { mode: "approved_dataset" }, input_requirements } });
  const source = view.stages.find((stage) => stage.inputCode === "series");
  assert.equal(source.status, "指定资料");
  assert.deepEqual(source.items.map(([name]) => name), [row.indicator_options.find((option) => option.code === "wofost_lai").name]);
});

test("冠层温度方案显示只读模型输入与实测目标，成果统一进入确认页", () => {
  const dom = environment(), row = templates.find((item) => item.id === "canopy-temperature-rf");
  const plan = structuredClone(row.definition);
  plan.layout.study_template = { id: row.id, sha256: row.sha256 };
  const fingerprint = JSON.stringify(plan);
  const template = { ...plan.layout.study_template, input_policy: { mode: "approved_dataset" }, input_requirements: [
    { port: "request", code: "cutoff", name: "训练冻结时间", unit: "", kind: "parameter", use: "随指定资料提供", source: "指定方法示例" },
    { port: "dataset", code: "air_temperature", name: "空气温度", unit: "celsius", kind: "input", use: "训练因素", source: "合成方法示例" },
    { port: "dataset", code: "canopy_temperature", name: "冠层温度", unit: "celsius", kind: "target", use: "训练与留出评价目标", source: "合成方法示例" },
  ] };
  try {
    const unexpected = () => assert.fail("查看示例不能修改、保存、校验或切换方案");
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records,
      onEdit: unexpected, onExample: unexpected, onSave: unexpected, validate: unexpected });
    wizard.setTemplate(template); wizard.openInputs();
    const input = document.querySelector('#wizard-role-table [aria-label="模型输入"]');
    assert.deepEqual([...input.querySelectorAll("tbody tr")].map((line) => line.dataset.variableCode), ["air_temperature"]);
    assert.match(input.textContent, /空气温度.*合成方法示例.*°C.*训练因素/);
    assert.equal(input.querySelector("button, input, select"), null);
    assert.equal(input.closest("[data-wizard-section]").hidden, false);
    assert.doesNotMatch(document.getElementById("wizard-role-table").textContent, /训练冻结时间/);
    assert.equal(document.getElementById("open-system-example").hidden, true);
    document.querySelector('[data-section="targets"]').click();
    const targets = document.querySelector('#wizard-output-table [aria-label="目标指标（实测参照）"]');
    assert.deepEqual([...targets.querySelectorAll("tbody tr")].map((line) => line.dataset.variableCode), ["canopy_temperature"]);
    assert.match(targets.closest('[data-io-group="output"]').textContent, /目标指标.*冠层温度/);
    assert.doesNotMatch(targets.closest('[data-io-group="output"]').textContent, /独立留出预测/);
    assert.match(document.getElementById("wizard-review-summary").textContent, /独立留出预测/);
    assert.equal(targets.closest("[data-wizard-section]").hidden, false);
    assert.equal(targets.closest("details, dialog"), null);
    assert.equal(JSON.stringify(plan), fingerprint);
    assert.ok(document.querySelector('#wizard-select #wizard-standard-example'));
  } finally { dom.window.close(); }
});

test("只有当前已加载合成数据时才提供记录预览", async () => {
  const dom = environment(), standard = await json("web/designer/system-study.json");
  try {
    const wizard = mountWizard({ getDefinition: () => standard.definition, getRecords: () => records, onEdit() {}, validate() {} });
    const opener = document.getElementById("open-system-example");
    const close = document.getElementById("close-study-input-example");
    const content = document.getElementById("study-input-example-content");
    assert.equal(opener.hidden, true);
    wizard.setData(standard.observations, "synthetic");
    assert.equal(opener.hidden, false);
    opener.click();
    assert.match(content.textContent, /合成示例值/);
    assert.equal(content.querySelector('[data-variable-code="canopy_cover"] td:last-child').textContent, String(standard.observations.rows[0].values.canopy_cover));
    close.click(); assert.equal(document.activeElement, opener);
    wizard.setData(standard.observations, "user_supplied"); opener.click();
    assert.equal(opener.hidden, true);
    assert.equal(document.getElementById("study-input-example").open, false);
  } finally { dom.window.close(); }
});

test("土壤气象卫星方案按三路资料汇合后计算，不套用不存在的划分和评价", () => {
  const row = templates.find((item) => item.id === "soil-weather-satellite-lai");
  const overview = flowOverview(row.definition, records, { template: row });
  assert.equal(overview.stages.length, 6);
  assert.equal(overview.stages.filter((stage) => stage.kind === "input").length, 3);
  assert.deepEqual(new Set(overview.edges.filter((edge) => edge.to === "node:satellite_features").map((edge) => edge.from)), new Set(["input:observations", "input:soil", "input:satellite"]));
  assert.ok(overview.edges.some((edge) => edge.from === "node:satellite_features" && edge.to === "node:regression"));
  assert.equal(overview.stages.find((stage) => stage.nodeCode === "satellite_features").headline, "待处理");
  assert.equal(overview.stages.some((stage) => ["partition", "evaluation"].includes(stage.kind)), false);
  const soil = overview.stages.find((stage) => stage.inputCode === "soil");
  assert.deepEqual(new Set(soil.groups.flatMap((group) => group.children.flatMap((child) => child.variables.map((variable) => variable.code)))), new Set(["soil_clay", "soil_soc"]));
  assert.ok(overview.edges.every((edge) => edge.ports.length > 0));
});

test("串联步骤按各自回执展示完成，不把整次运行中当成所有步骤正在执行", () => {
  const row = templates.find((item) => item.id === "growth-trend-and-environment");
  const before = JSON.stringify(row.definition);
  const overview = flowOverview(row.definition, records, { template: row, run: { kind: "train", status: "running", result_json: { receipts: [{ node: "baseline" }] } } });
  const nodes = overview.stages.filter((stage) => stage.kind === "calculation");
  assert.deepEqual(new Set(nodes.map((stage) => stage.nodeCode)), new Set(row.definition.composition.nodes.map((node) => node.code)));
  for (const stage of nodes) assert.equal(stage.status, stage.nodeCode === "baseline" ? "已完成" : "等待步骤回执");
  assert.equal(JSON.stringify(row.definition), before);
});

test("成果卡只关联同次运行且包含该步骤状态的已保存模型", () => {
  const row = templates.find((item) => item.id === "growth-trend-and-environment");
  const run = { run_id: "run-a", kind: "train", status: "succeeded", result_json: { outputs: { trained_model: {}, predictions: {} } } };
  const model = { run_id: "run-a", name: "株高预测模型", model_json: { states: { regression: {} } } };
  const product = (context) => flowOverview(row.definition, records, { template: row, run, ...context }).stages.find((stage) => stage.kind === "product");
  assert.equal(product({ model }).description, model.name);
  assert.match(product({ model }).highlight, /模型已保存/);
  assert.doesNotMatch(product({ model: { ...model, run_id: "run-b" } }).highlight, /模型已保存/);
  assert.doesNotMatch(product({ model: { ...model, model_json: { states: { unrelated: {} } } } }).highlight, /模型已保存/);
});

test("日期拟合总览保留全部候选资料，不把自动日期当主方法或未运行当训练完成", () => {
  const original = templates.find((row) => row.id === "soil-weather-lai").definition;
  const draft = prepareMethodDraft(original, records, "logistic_growth_curve@4", original.composition.nodes[0].code).definition;
  const overview = flowOverview(draft, records);
  assert.equal(overview.stages.length, 4);
  assert.equal(overview.stages.some((stage) => ["dataset", "evaluation"].includes(stage.code)), false);
  assert.equal(overview.rows.length, inputUsageRows(original, records).length);
  assert.match(overview.stages[0].highlight, /1 项参与计算/);
  assert.match(overview.stages[2].title, /逻辑斯蒂/);
  assert.doesNotMatch(overview.stages[2].description, /平台观测日期驱动/);
  assert.equal(overview.stages[2].headline, "待拟合");
  assert.equal(overview.stages[1].headline, "自动日期处理");
  assert.equal(overview.branch, false);
  assert.equal(overview.stages.at(-1).status, "等待产出");
  assert.doesNotMatch(JSON.stringify(overview.stages), /V1\.3|V2|456|96 组|验证通过|独立验证通过/);
});

test("研究总览的缩放全屏和键盘退出可用，细节默认不重复展开", async () => {
  const dom = environment(), sample = await json("web/designer/calendar-study.json"), host = document.getElementById("public-research-flow");
  try {
    researchFlow(host, sample.definition, records);
    assert.equal(host.querySelectorAll(".research-stage-card").length, 4);
    assert.equal(host.querySelectorAll("details[open]").length, 0);
    assert.equal(host.querySelectorAll(".research-stage-number").length, 4);
    assert.equal(host.querySelectorAll("header > svg[aria-hidden=true]").length, 4);
    host.querySelector('[aria-label="放大研究流程"]').click();
    assert.equal(Number(host.dataset.flowZoom), 1.1);
    const expand = host.querySelector('[aria-label="切换研究流程全屏视图"]');
    expand.click(); assert.equal(expand.getAttribute("aria-pressed"), "true");
    assert.ok(host.classList.contains("research-flow-expanded"));
    document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" }));
    assert.equal(expand.getAttribute("aria-pressed"), "false");
    assert.equal(document.activeElement, expand);
  } finally { dom.window.close(); }
});

for (const template of templates) test("方案资料与成果完整展示：" + template.id, () => {
  const dom = environment(), plan = structuredClone(template.definition);
  plan.layout = { ...plan.layout, study_template: { id: template.id, sha256: template.sha256 } };
  try {
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, getInputCatalog: () => ({ items: [], categories: [] }), onEdit() {}, onTechnical() {}, onExample() {}, validate() {} });
    wizard.setTemplate(template); wizard.loaded();
    const inputs = document.getElementById("wizard-role-table"), outputs = document.getElementById("wizard-output-table");
    assert.ok(inputs.textContent.trim(), template.id + "的研究输入不能空白");
    assert.ok(outputs.textContent.trim(), template.id + "的目标或说明不能空白");
    assert.equal(inputs.querySelector("[data-resource-input]"), null);
    assert.equal(outputs.querySelector("[data-product]"), null);
    const summary = document.getElementById("wizard-review-summary").textContent;
    for (const port of plan.composition.inputs.filter((port) => plan.input_recipes[port.code].kind === "artifact")) {
      assert.ok(summary.includes(port.name), template.id + "必须核对真实资料端口" + port.code);
    }
    for (const product of productRows(plan, records)) assert.ok(summary.includes(product.name));
    assert.doesNotMatch(document.getElementById("wizard-review-summary").textContent, /按组件合同|已选择该研究所需的数据/);
  } finally { dom.window.close(); }
});

test("历史逻辑斯蒂合同在组件参数区换轴时清除不兼容的驱动", () => {
  const dom = environment(), source = templates.find((row) => row.id === "soil-weather-lai").definition;
  try {
    const { definition, node, record, request } = prepareMethodDraft(source, records, "logistic_growth_curve@4", source.composition.nodes[0].code);
    document.getElementById("method-detail").append(parameters(definition, node, record.research_contract.request_schema, request, (port, key, value) => {
      definition.input_recipes[port].value[key] = value;
    }));
    const driver = () => document.querySelector('#method-detail [data-field="x_code"]');
    assert.ok(driver(), document.getElementById("method-message").textContent);
    assert.equal(driver().readOnly, true);
    assert.match(driver().value, /平台观测日期/);
    const axis = document.querySelector('#method-detail [data-field="axis_kind"]');
    axis.value = "growing_degree_days"; axis.dispatchEvent(new window.Event("change"));
    assert.equal(driver().value, "");
    assert.equal([...driver().options].filter((option) => option.value).length, 0);
    assert.match(document.getElementById("method-detail").textContent, /积温.*deg_c_day/);
  } finally { dom.window.close(); }
});

test("没有天数指标也能自动建立平台日期驱动且不伪造外部来源", () => {
  const plan = templates.find((row) => row.id === "soil-weather-lai").definition;
  const result = prepareMethodDraft(plan, records, "logistic_growth_curve@4", plan.composition.nodes[0].code);
  assert.equal(result.definition.input_recipes[result.request].value.x_code, "platform_calendar_day");
  assert.ok(result.definition.composition.nodes.some((node) => node.component.code === "research_calendar_axis"));
  assert.ok(!result.definition.collection_requirements.some((item) => item.variable_code === "platform_calendar_day"));
  const repeated = prepareMethodDraft(result.definition, records, "logistic_growth_curve@4", result.node.code);
  assert.equal(repeated.definition.composition.nodes.filter((node) => node.component.code === "research_calendar_axis").length, 1);
  assert.equal(repeated.definition.input_recipes[repeated.request].value.x_code, "platform_calendar_day");
});

test("平台生长曲线样例仅要求目录生物量，日期以平台派生来源展示", async () => {
  const dom = environment(), plan = (await json("web/designer/calendar-study.json")).definition;
  try {
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit() {}, onTechnical() {}, onExample() {}, validate() {} });
    wizard.loaded();
    const inputs = document.getElementById("wizard-role-table");
    assert.ok(inputs.querySelector('[data-platform-date-axis="platform_calendar_day"]'));
    assert.doesNotMatch(inputs.textContent, /未绑定来源/);
    assert.ok(plan.collection_requirements.every((requirement) => requirement.catalog_binding));
    const sample = await json("web/designer/calendar-study.json");
    assert.deepEqual(predictionColumns({ plan, input_columns: sample.observations.columns }, records), []);
    const picker = mountMethodPicker({ getDefinition: () => plan, getRecords: () => records, loadMethods: async () => ({ items: [] }), onEdit() {}, notify() {}, validate() {} });
    picker.open();
    const steps = document.getElementById("method-target");
    assert.equal(steps.options.length, 1);
    assert.equal(plan.composition.nodes.find((node) => node.code === steps.value).component.code, "historical_logistic_training");
  } finally { dom.window.close(); }
});

for (const [key, record] of records) if (record.available_for_new_design && record.definition.composable) test("自定义方法的成果统一在确认页核对：" + key, () => {
  const dom = environment();
  try {
    const result = prepareMethodDraft(blankPlan(), records, key);
    const plan = result.definition;
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit() {}, onTechnical() {}, onExample() {}, validate() {} });
    wizard.loaded();
    assert.equal(document.querySelector("#wizard-role-table [data-resource-input], #wizard-output-table [data-product]"), null);
    const summary = document.getElementById("wizard-review-summary").textContent;
    const products = productRows(plan, records);
    assert.equal(products.length, record.definition.outputs.length);
    for (const product of products) assert.ok(summary.includes(product.name));
    if (record.research_contract.capabilities?.operations.join() === "analyze") assert.equal(plan.purpose, "explore");
  } finally { dom.window.close(); }
});

test("未参与资料有明确用途入口及移除，历史趋势的驱动仍列为有效输入", () => {
  const dom = environment(); let plan = structuredClone(templates.find((row) => row.id === "crop-growth-prediction").definition), wizard;
  const extra = { ...structuredClone(plan.variables[0]), code: "spare_factor", name: "备用资料", role: "covariate" };
  plan.variables.push(extra);
  plan.collection_requirements.push({ ...structuredClone(plan.collection_requirements[0]), code: "spare_requirement", variable_code: extra.code });
  Object.values(plan.input_recipes).find((recipe) => recipe.kind === "observations").variable_codes.push(extra.code);
  try {
    wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit(next) { plan = next; wizard.render(); }, onTechnical() {}, onExample() {}, validate() {} });
    const group = document.querySelector('[data-io-group="other"]'); assert.match(group.textContent, /尚未用于计算.*添加研究资料/);
    const row = group.querySelector('[data-variable-code="spare_factor"]');
    row.querySelector("button").click(); assert.equal(location.hash, "#configure/calculation");
    document.querySelector('[data-section="inputs"]').click();
    document.querySelector('[data-variable-code="spare_factor"]').querySelectorAll("button")[1].click();
    assert.ok(!plan.variables.some((variable) => variable.code === extra.code));
    assert.ok(!plan.collection_requirements.some((requirement) => requirement.variable_code === extra.code));
    const chain = templates.find((row) => row.id === "growth-trend-and-environment").definition;
    const driver = inputUsageRows(chain, records).find((row) => row.variable.unit === "day");
    assert.ok(driver.used); assert.equal(driver.role, "covariate");
  } finally { dom.window.close(); }
});

test("旧的待配置草稿仍可打开并定位未完成的参数", async () => {
  const dom = environment(), source = templates.find((row) => row.id === "crop-growth-prediction").definition;
  const { definition: plan } = prepareMethodDraft(source, records, "historical_logistic_training@1", source.composition.nodes[0].code, "", { deferParameters: true });
  const validate = async () => ({ valid: false, issues: [{ type: "incomplete_configuration", path: ["input_recipes", "pending"], port: "request", node: plan.composition.nodes[0].code }] });
  try {
    const wizard = mountWizard({ getDefinition: () => plan, getRecords: () => records, onEdit() {}, onTechnical() {}, onExample() {}, validate });
    assert.equal(await wizard.check(), false); assert.equal(document.querySelector("#wizard-check-result .check-success"), null);
    assert.match(document.getElementById("wizard-check-result").textContent, /参数尚未配置/);
  } finally { dom.window.close(); }
});
