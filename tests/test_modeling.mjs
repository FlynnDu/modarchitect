import test from "node:test";
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { JSDOM } from "jsdom";
import { dependencyLayers, orthogonalPoints } from "../modarchitect/web/designer/graph-layout.js";
import { dataPeriods, editStudy, modelingSteps, predictionColumns, studySettings } from "../modarchitect/web/designer/modeling.js";
import { mountModeling } from "../modarchitect/web/designer/modeling-view.js";
import { describe } from "../modarchitect/web/designer/panels.js";
import { blankPlan } from "../modarchitect/web/designer/editor.js";
import { addSystemInput, buildInputModel, mountSystemInputs } from "../modarchitect/web/designer/system-inputs.js";
import { observationTemplate } from "../modarchitect/web/designer/research.js";
import { renderSummary, runOperation } from "../modarchitect/web/designer/result-views.js";
import { parameters } from "../modarchitect/web/designer/schema-fields.js";
import { changeInputRole, inputUsageRows, mountWizard } from "../modarchitect/web/designer/wizard.js";
import { acquisitionRange, commonSourceDates, mergeSourceTables, mountSourceData, splitAcquisitionRange } from "../modarchitect/web/designer/source-data.js";
import { inputProvision } from "../modarchitect/web/designer/input-provision.js";
import { prepareMethodDraft, methodRestriction } from "../modarchitect/web/designer/methods.js";
import { mountMethodPicker } from "../modarchitect/web/designer/method-picker.js";

const directory = new URL("../modarchitect/web/designer/", import.meta.url);
const sample = async (name) => JSON.parse(await readFile(new URL(name + "-study.json", directory), "utf8"));
const [direct, chain, html] = await Promise.all([sample("multivariable"), sample("chain"), readFile(new URL("index.html", directory), "utf8")]);
const standard = await sample("system");
const inputItems = standard.definition.variables.map((variable) => ({
  key: "sampling_indicator:" + variable.code + "@1.0.0", variable, category: "manual", unit_kind: "field_season", selectable: true,
  source: { name: "标准人工记录", binding: standard.definition.collection_requirements.find((r) => r.variable_code === variable.code).catalog_binding, selection_schema: { properties: {} } },
  execution: { available: true },
}));
const soilInput = { key: "variable_source:soil_phh2o@1.0.0", variable: { name: "土壤 pH", code: "soil_phh2o", unit: "dimensionless", description: "网格参考估计" }, category: "third_party", unit_kind: "field_season", selectable: true,
  source: { name: "SoilGrids", binding: { value_nature: "estimated" }, selection_schema: { properties: { depth: { enum: ["0-5cm", "5-15cm"] }, statistic: { enum: ["mean"] } } } }, execution: { available: false, reason: "需受权取数接入" } };
const inputCatalog = { categories: [["manual", "人工采集", 4], ["third_party", "第三方平台", 1], ["platform_analysis", "平台分析记录", 0], ["iot_platform", "物联网平台", 0]].map(([code, name, count]) => ({ code, name, count })), items: [...inputItems, soilInput] };
const definitions = (await Promise.all(["runtime-components-v1.json", "chain-components-v1.json", "tabular-learning-components-v1.json"].map(async (name) =>
  JSON.parse(await readFile(new URL("../modarchitect/contracts/" + name, import.meta.url), "utf8"))))).flat();
const compatibility = Object.assign({}, ...(await Promise.all(["execution-compatibility-v1.json", "native-study-execution-v1.json"].map(async (name) => JSON.parse(await readFile(new URL("../modarchitect/contracts/" + name, import.meta.url), "utf8"))))));
const records = definitions.map((definition) => ({ definition, available_for_new_design: true,
  research_contract: { capabilities: definition.configuration.research_model?.execution || compatibility[definition.code+"@"+definition.revision]?.capability,
    execution: { status: "available" }, request_schema: definition.configuration.research_model?.request_schema ?? null } }));
const recordMap = new Map(records.map((value) => [`${value.definition.code}@${value.definition.revision}`, value]));

test("更换方法修改实际节点和公开成果，保留来源及原草稿，拒绝不兼容下游", () => {
  const original = structuredClone(direct.definition);
  const changed = prepareMethodDraft(original, recordMap, "historical_logistic_training@1", "regression");
  assert.equal(changed.node.component.code, "historical_logistic_training");
  assert.equal(changed.definition.schema_version, "1.5");
  assert.equal(changed.definition.input_recipes[changed.request].value.x_code, "day");
  assert.equal(changed.definition.input_recipes[changed.request].value.target_code, "height");
  assert.deepEqual(changed.definition.evaluation.target_codes, ["height"]);
  assert.deepEqual(changed.definition.collection_requirements, original.collection_requirements);
  assert.deepEqual(changed.definition.composition.outputs.map((output) => output.source.port), ["forecast", "trained_model"]);
  assert.equal(original.composition.nodes[0].component.code, "multivariate_linear_training");
  assert.throws(() => prepareMethodDraft(chain.definition, recordMap, "multivariate_linear_training@1", "baseline"), /不能直接接入/);
  const missingDriver = prepareMethodDraft(standard.definition, recordMap, "historical_logistic_training@1", "regression");
  assert.equal(missingDriver.definition.input_recipes[missingDriver.request].value.x_code, undefined);
  const planned = prepareMethodDraft(standard.definition, recordMap, "historical_logistic_training@1", "regression", "", { deferParameters: true });
  assert.equal(planned.definition.input_recipes[planned.node.bindings.find((binding) => binding.port === "request").source.port].kind, "deferred");
  const fixed = structuredClone(original); fixed.input_recipes.original = { kind: "artifact" };
  assert.deepEqual(prepareMethodDraft(fixed, recordMap, "multivariate_linear_training@1", "regression").definition.input_recipes.original, fixed.input_recipes.original);
});

test("表格回归方法真实切换后可编辑因素和目标，并按实际方法展示非线性关系", () => {
  for (const code of ["random_forest", "xgboost", "gaussian_process"]) {
    const result = prepareMethodDraft(direct.definition, recordMap, code + "_training@1", "regression");
    const context = studySettings(result.definition, recordMap);
    assert.ok(context); assert.equal(context.model.component.code, code + "_training");
    assert.deepEqual(context.parameters.targets, ["height", "leaf_area"]);
    const edited = changeInputRole(result.definition, "ndvi", "target", recordMap);
    assert.ok(studySettings(edited, recordMap).parameters.targets.includes("ndvi"));
    assert.ok(!studySettings(edited, recordMap).parameters.features.includes("ndvi"));
    const step = modelingSteps(edited, recordMap).steps[0];
    assert.ok(step.formula.every((text) => text.includes("= f(")));
    assert.ok(!step.formula.join("").includes("截距"));
    assert.equal(inputUsageRows(edited, recordMap).find((r) => r.variable.code === "temperature").editable, true);
  }
});

test("未接通方法可形成准确待接入输入，检查失败不覆盖原方案", async () => {
  const dom = domEnvironment(), all = new Map(recordMap), messages = []; let plan = structuredClone(direct.definition), valid = false, edits = 0, delayed = false, release;
  const native = JSON.parse(await readFile(new URL("../modarchitect/contracts/native-study-components-v1.json", import.meta.url), "utf8")).find((d) => d.code === "random_forest");
  const forest = { definition: native, available_for_new_design: true, research_contract: { execution: { status: "design_only" }, capabilities: compatibility["random_forest@1"].capability, request_schema: native.configuration.research_model.request_schema } };
  all.set("random_forest@1", forest);
  assert.equal(methodRestriction(forest), null);
  const future = prepareMethodDraft(plan, all, "random_forest@1", "regression");
  const dataset = future.node.bindings.find((b) => b.port === "dataset").source;
  assert.equal(future.definition.input_recipes[dataset.port].kind, "deferred");
  assert.equal(future.definition.composition.inputs.find((i) => i.code === dataset.port).data_type.semantic, "research_cpu_tabular_dataset");
  const view = mountMethodPicker({ getDefinition: () => plan, getRecords: () => all, notify: (text) => messages.push(text), onEdit(next) { edits++; plan = next; }, validate: async () => delayed ? new Promise((resolve) => { release = resolve; }) : ({ valid, issues: valid ? [] : [{ message: "独立结构检查拒绝" }] }) });
  try {
    view.open();
    document.querySelector('[data-method="random_forest@1"] button').click();
    assert.match(document.getElementById("method-detail").textContent, /待接入输入/); assert.equal(document.getElementById("apply-method").disabled, false);
    document.querySelector('[data-method="historical_logistic_training@1"] button').click();
    assert.equal(document.getElementById("apply-method").disabled, false);
    document.getElementById("apply-method").click(); await new Promise(setImmediate);
    assert.equal(edits, 0); assert.match(document.getElementById("method-message").textContent, /独立结构检查拒绝/);
    delayed = true; document.getElementById("apply-method").click();
    const date = document.querySelector('#method-detail input[type="date"]'); date.value = "2026-06-15"; date.dispatchEvent(new dom.window.Event("input"));
    release({ valid: true, issues: [] }); await new Promise(setImmediate);
    assert.equal(edits, 0); assert.match(document.getElementById("method-message").textContent, /方法设置已变化/);
    delayed = false;
    valid = true; document.getElementById("apply-method").click(); await new Promise(setImmediate);
    assert.equal(edits, 1); assert.equal(plan.composition.nodes[0].component.code, "historical_logistic_training");
    assert.match(messages.at(-1), /历史曲线训练/);
  } finally { dom.window.close(); }
});

test("用途表逐项说明人工与第三方取数，示例和历史来源不会伪装成已取数", () => {
  const dom = domEnvironment(), plan = structuredClone(standard.definition), catalog = structuredClone(inputCatalog);
  const binding = { kind: "variable_source", code: "weather_minimum", definition_version: "1.0.0", contract_sha256: "weather-sha", selectors: {}, value_nature: "estimated" };
  const weather = { code: "temperature_minimum_daily", name: "日最低气温", unit: "celsius", role: "covariate" };
  plan.variables.push(weather);
  plan.collection_requirements.push({ variable_code: weather.code, source: "third_party", catalog_binding: binding });
  Object.values(plan.input_recipes).find((r) => r.kind === "observations").variable_codes.push(weather.code);
  catalog.categories.find((c) => c.code === "third_party").children = [{ code: "weather", name: "气象", count: 1 }];
  catalog.items.push({ variable: weather, category: "third_party", subcategory: "weather", source: { name: "Open-Meteo 气象", binding: structuredClone(binding) }, execution: { available: true, channel: "source_snapshot" } });
  const view = mountWizard({ getDefinition: () => plan, getRecords: () => recordMap, getInputCatalog: () => catalog, onEdit() {}, onExample() {}, onTechnical() {}, validate() {} });
  try {
    view.loaded();
    const host = document.getElementById("wizard-role-table");
    assert.match(host.querySelector("tr").textContent, /数据提供方式/);
    const row = (name) => [...document.querySelectorAll("#wizard-role-table tr, #wizard-output-table tr")].find((line) => line.querySelector("td")?.textContent === name);
    assert.match(row("叶面积指数").textContent, /人工采集/);
    assert.match(row("叶面积指数").textContent, /填写或导入/);
    assert.match(row("日最低气温").textContent, /第三方平台 · 气象/);
    assert.match(row("日最低气温").textContent, /Open-Meteo 气象/);
    assert.match(row("日最低气温").textContent, /平台采集/);
    view.setData(standard.observations, "synthetic");
    assert.match(host.textContent, /合成示例.*不表示.*真实资料/);
    binding.contract_sha256 = "retired-sha"; view.render();
    assert.match(row("日最低气温").textContent, /历史来源待核验/);
    assert.doesNotMatch(row("日最低气温").textContent, /Open-Meteo/);
    plan.collection_requirements = plan.collection_requirements.filter((r) => r.variable_code !== weather.code); view.render();
    assert.match(row("日最低气温").textContent, /未绑定来源/);
  } finally { dom.window.close(); }
});

test("未接通指标显示待接入及分类可添加数，不提供无效用途选择", () => {
  const dom = domEnvironment(), catalog = structuredClone(inputCatalog), plan = blankPlan();
  catalog.items.push({ key: "research_variable:gndvi@1.0.0", variable: { name: "报告覆盖区 GNDVI 均值", unit: "dimensionless", code: "gndvi" }, category: "platform_analysis", selectable: false, unit_kind: null,
    source: { name: "平台长势分析记录", binding: null, selection_schema: { properties: {} } }, execution: { available: false, reason: "尚未完成报告范围、日期与授权取数绑定" } });
  catalog.categories.find((c) => c.code === "platform_analysis").count = 1;
  mountSystemInputs({ catalog, getDefinition: () => plan, getRecords: () => recordMap, onEdit() {}, configure() { throw new Error("不能配置未接通指标"); }, notify() {} });
  try {
    document.querySelector('[data-category="platform_analysis"]').click();
    const card = document.querySelector(".input-catalog-card");
    assert.equal(card.querySelector("button").textContent, "待接入");
    assert.equal(card.querySelector("button").disabled, true);
    assert.equal(card.querySelectorAll("select").length, 0);
    assert.match(card.textContent, /授权取数绑定/);
    assert.match(document.querySelector('[data-category="platform_analysis"]').textContent, /已登记 1.*可添加 0/);
  } finally { dom.window.close(); }
});

test("已登记的计划来源和点位指标可通过真实点击加入设计，不冒充运行已接通", async () => {
  const dom = domEnvironment(), catalog = structuredClone(inputCatalog); let plan = blankPlan(), calls = 0;
  const entry = { key: "research_variable:planned_sensor@1.0.0", variable: { code: "planned_sensor", name: "计划传感器气温", unit: "celsius" }, category: "iot_platform", selectable: true, unit_kind: "point",
    source: { name: "物联网监测（待接入）", binding: { kind: "planned_source", value_nature: "observed" }, selection_schema: { properties: {} } }, execution: { available: false, reason: "设备取数待接入" } };
  catalog.items.push(entry);
  mountSystemInputs({ catalog, getDefinition: () => plan, getRecords: () => recordMap, onEdit(next) { plan = next; }, async configure() { calls++; return { variable: { ...entry.variable, role: "covariate" }, requirement: { variable_code: "planned_sensor", source: "business_system", unit_kind: "point", required_for: ["train"], catalog_binding: entry.source.binding } }; }, notify() {} });
  try {
    document.querySelector('[data-category="iot_platform"]').click();
    const card = document.querySelector(".input-catalog-card");
    assert.match(card.textContent, /设备取数待接入/); assert.equal(card.querySelector("button").disabled, false);
    card.querySelector("button").click(); await new Promise(setImmediate);
    assert.equal(calls, 1); assert.equal(plan.variables.at(-1).code, "planned_sensor");
    assert.equal(plan.collection_requirements.at(-1).unit_kind, "point");
    assert.equal(plan.collection_requirements.at(-1).catalog_binding.kind, "planned_source");
  } finally { dom.window.close(); }
});

test("土壤来源保留已选属性，历史版本与摘要均须准确匹配", () => {
  const binding = { kind: "variable_source", code: "soil_ph", definition_version: "1.0.0", contract_sha256: "soil-sha", selectors: {} };
  const catalog = { categories: [{ code: "third_party", name: "第三方数据", children: [{ code: "soil", name: "土壤" }] }], items: [
    { category: "third_party", subcategory: "soil", source: { name: "SoilGrids", binding, definition: { support: { temporal_support: "static" } } }, execution: { available: true, channel: "source_snapshot" } },
  ] };
  const requirement = { source: "third_party", catalog_binding: { ...binding, selectors: { depth: "5-15cm", statistic: "mean" } } };
  const result = inputProvision(requirement, catalog);
  assert.equal(result.label, "第三方数据 · 土壤");
  assert.match(result.details.join(" "), /SoilGrids.*土层：5-15cm.*统计方式：均值.*静态网格/);
  for (const key of ["kind", "code", "definition_version", "contract_sha256"]) {
    const history = structuredClone(requirement); history.catalog_binding[key] = "different";
    assert.equal(inputProvision(history, catalog).label, "历史来源待核验");
  }
});

test("原型的模型选择、配置导航与用途表修改同一份模型，错误校验保持可见", async () => {
  const dom = domEnvironment(); let plan = blankPlan(), checks = 0;
  const view = mountWizard({ getDefinition: () => structuredClone(plan), getRecords: () => recordMap,
    onEdit(value) { plan = value; view.render(); }, onExample() {}, onTechnical() {},
    async validate() { checks++; return { valid: false, issues: [{ message: "配置不合法", path: plan.responsible_user_id === " " ? ["responsible_user_id"] : ["evaluation", "target_codes"] }] }; } });
  try {
    assert.equal(document.getElementById("wizard-select").hidden, false);
    document.getElementById("select-model-next").click();
    document.getElementById("wizard-next").click();
    assert.equal(document.querySelector('[data-wizard-section="basic"]').hidden, false);
    assert.match(document.getElementById("wizard-error").textContent, /填写/);
    const basic = document.querySelector('[data-wizard-section="basic"]');
    assert.equal(basic.querySelectorAll('.wizard-fields input, .wizard-fields textarea').length, 5);
    const studyVersion = document.getElementById("wizard-study-version");
    assert.equal(studyVersion.readOnly, false);
    assert.equal(studyVersion.value, "");
    assert.equal(document.getElementById("wizard-purpose"), null);
    assert.doesNotMatch(basic.textContent, /当前计算对象|研究作物|样本单位|研究方式|主要输出/);
    const owner = document.getElementById("wizard-responsible-user-id");
    owner.value = "9007199254740993"; owner.dispatchEvent(new dom.window.Event("change"));
    assert.equal(plan.responsible_user_id, "9007199254740993");
    const version = document.getElementById("wizard-template-version");
    assert.equal(version.readOnly, true); assert.equal(version.value, "自定义");
    plan.layout.study_template = { id: "example-template", sha256: "exact-template" };
    view.setTemplate({ id: "example-template", sha256: "exact-template", revision: 7, title: "作物生长研究" });
    assert.equal(version.value, "作物生长研究 · v7");
    view.setTemplate({ id: "example-template", sha256: "wrong", revision: 8, title: "其他版本" });
    assert.equal(version.value, "模板版本待加载");
    delete plan.layout.study_template; view.render();
    assert.equal(version.value, "自定义");
    const name = document.getElementById("wizard-name"), question = document.getElementById("wizard-question");
    name.value = "原型交互验收"; name.dispatchEvent(new dom.window.Event("change"));
    question.value = "研究叶面积与生物量的预测关系"; question.dispatchEvent(new dom.window.Event("change"));
    document.getElementById("wizard-next").click();
    assert.equal(document.querySelector('[data-wizard-section="inputs"]').hidden, false);
    assert.equal(plan.name, "原型交互验收");
    plan = structuredClone(standard.definition); view.loaded();
    assert.equal(document.querySelector('[data-io-group="input"]').closest('[data-wizard-section]').dataset.wizardSection, "inputs");
    assert.equal(document.querySelector('[data-io-group="output"]').closest('[data-wizard-section]').dataset.wizardSection, "targets");
    assert.match(document.querySelector('[data-section="inputs"]').textContent, /研究资料与候选因素/);
    assert.match(document.querySelector('[data-section="targets"]').textContent, /模型输出与研究成果/);
    assert.match(document.querySelector('[data-io-group="input"]').textContent, /模型输入/);
    assert.match(document.querySelector('[data-io-group="output"]').textContent, /预测输出/);
    assert.equal(document.querySelectorAll('#wizard-role-table select').length, 0);
    assert.doesNotMatch(document.getElementById("wizard-role-table").textContent, /已知因素 X|实测预测目标 Y|标签 Y|因素 X/);
    const control = document.querySelector('[data-variable-role="canopy_cover"]');
    control.click();
    assert.ok(studySettings(plan).parameters.targets.includes("canopy_cover"));
    assert.ok(!studySettings(plan).parameters.features.includes("canopy_cover"));
    assert.ok(document.querySelector('[data-io-group="output"] [data-variable-code="canopy_cover"]'));
    const usage = inputUsageRows(plan).find((row) => row.variable.code === "canopy_cover");
    assert.equal(usage.application, false);
    const beforeFailure = structuredClone(plan);
    document.querySelector('[data-variable-role="tuber_dm_kg_ha"]').click();
    assert.deepEqual(plan, beforeFailure);
    assert.match(document.getElementById("wizard-error").textContent, /至少选择/);
    assert.ok(document.querySelector('[data-io-group="input"] [data-variable-code="tuber_dm_kg_ha"]'));
    document.querySelector('[data-stage="review"]').click();
    assert.equal(await view.check(), false); view.setData(standard.observations, "synthetic");
    assert.match(document.getElementById("wizard-check-result").textContent, /目标变量/);
    assert.equal(checks, 1);
    plan.responsible_user_id = " ";
    assert.equal(await view.check(), false);
    assert.match(document.getElementById("wizard-check-result").textContent, /负责人用户ID/);
    assert.equal(checks, 2);
    assert.equal(document.querySelector('[data-template="simulation"]').disabled, true);
    assert.equal(document.querySelector('[data-template="vision"]').disabled, true);
    assert.throws(() => changeInputRole(plan, "tuber_dm_kg_ha", "target"), /至少选择/);
  } finally { dom.window.close(); }
});

test("未选基础模型时只采用已知因素也能继续配置来源和计算方法", () => {
  const dom = domEnvironment(), plan = blankPlan();
  plan.name = "土壤条件研究"; plan.question = "采用土壤指标后选择研究方法";
  addSystemInput(plan, {
    variable: { ...soilInput.variable, role: "covariate" },
    requirement: { code: soilInput.variable.code, variable_code: soilInput.variable.code,
      source: "third_party", unit_kind: "field_season", catalog_binding: soilInput.source.binding },
  });
  const original = structuredClone(plan);
  mountWizard({ getDefinition: () => plan, getRecords: () => recordMap, getInputCatalog: () => inputCatalog,
    onEdit() {}, onExample() {}, onTechnical() {}, validate() { throw new Error("导航不应提交完整设计检查"); } });
  try {
    document.querySelector('[data-section="inputs"]').click();
    assert.match(document.getElementById("wizard-role-table").textContent, /土壤 pH/);
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#configure/targets", document.getElementById("wizard-error").textContent);
    assert.equal(document.querySelector('[data-wizard-section="inputs"]').hidden, true);
    assert.equal(document.querySelector('[data-wizard-section="targets"]').hidden, false);
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#configure/sources");
    assert.equal(document.getElementById("wizard-error").hidden, true);
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#configure/calculation");
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#configure/calculation");
    assert.match(document.getElementById("wizard-error").textContent, /从模型目录选择/);
    assert.deepEqual(plan, original);
  } finally { dom.window.close(); }
});

test("非训练研究发送分析操作，真实成果展示统计值且保留独立样本提示", async () => {
  const analysis = await sample("analysis"), dom = domEnvironment();
  try {
    mountWizard({ getDefinition: () => analysis.definition, getRecords: () => recordMap,
      onEdit() {}, onExample() {}, onTechnical() {}, validate() {} });
    const outputGroup = document.querySelector('[data-io-group="output"]');
    assert.match(outputGroup.textContent, /计算成果/);
    assert.doesNotMatch(outputGroup.textContent, /预测输出|训练和验证时需要/);
    assert.equal(outputGroup.querySelectorAll("button, select").length, 0);
    assert.deepEqual(runOperation(analysis.definition), { operation: "analyze" });
    assert.deepEqual(runOperation(direct.definition), {});
    const summary = JSON.parse(await readFile(new URL("../components/descriptive_statistics/examples/expected-summary.json", import.meta.url), "utf8"));
    const host = document.getElementById("run-output");
    assert.equal(renderSummary(host, summary), true);
    assert.match(host.textContent, /多天观测不等于多个独立试验单位/);
    assert.deepEqual([...host.querySelectorAll("tr")[1].querySelectorAll("td")].map((v) => v.textContent), ["叶面积指数 · m²/m²", "3", "1", "3", "2", "1"]);
    assert.equal(renderSummary(host, { format: "unknown" }), false);
  } finally { dom.window.close(); }
});

test("新方案的节点目标可选同一标准列，旧方案仍按全局角色限制", () => {
  const dom = domEnvironment(), plan = structuredClone(standard.definition);
  try {
    plan.variables.forEach((v) => { v.role = "covariate"; });
    const node = plan.composition.nodes[0], schema = recordMap.get("multivariate_linear_training@1").research_contract.request_schema;
    const render = () => parameters(plan, node, schema, "regression_config", () => {});
    assert.equal(render().querySelectorAll('[data-targets="canopy_cover"]').length, 0);
    plan.schema_version = "1.5";
    assert.equal(render().querySelectorAll('[data-targets="canopy_cover"]').length, 1);
  } finally { dom.window.close(); }
});

test("实际串联按数据依赖分为五层，输入排列与重复边不影响计算先后", () => {
  const flow = describe(chain.definition, recordMap);
  const items = [...flow.outputs, ...flow.models.toReversed(), ...flow.inputs.filter((v) => v.kind !== "parameter")];
  const keys = new Set(items.map((v) => v.key));
  const edges = flow.edges.filter(([a, b]) => keys.has(a) && keys.has(b));
  const result = dependencyLayers(items, [...edges, edges[0]]);
  assert.equal(result.layers.length, 5);
  for (const [from, to] of edges) assert.ok(result.depth.get(from) < result.depth.get(to));
  assert.deepEqual(result.layers.slice(1, 4).map((layer) => layer[0].code), ["baseline", "merge", "regression"]);
});

test("分支保留并行层，循环及失效引用给出明确失败", () => {
  const items = ["out", "b", "source", "a"].map((key) => ({ key }));
  const result = dependencyLayers(items, [["source", "a"], ["source", "b"], ["a", "out"], ["b", "out"]]);
  assert.equal(result.depth.get("a"), result.depth.get("b"));
  assert.throws(() => dependencyLayers(items, [["a", "b"], ["b", "a"]]), /循环/);
  assert.throws(() => dependencyLayers(items, [["absent", "a"]]), /不存在/);
});

test("正交连接保留真实端点，跨层通道从节点下方通过", () => {
  for (const options of [{}, { bypass: 340 }]) {
    const points = orthogonalPoints({ x: 230, y: 70 }, { x: 780, y: 210 }, options);
    assert.deepEqual(points[0], { x: 230, y: 70 });
    assert.deepEqual(points.at(-1), { x: 780, y: 210 });
    for (let i = 1; i < points.length; i++) assert.ok(points[i - 1].x === points[i].x || points[i - 1].y === points[i].y);
    if (options.bypass) assert.ok(points.some((point) => point.y === 340));
  }
});

test("默认关系来自真实配置，隐藏的对齐仍保留在原图且可追溯", () => {
  const before = structuredClone(chain.definition);
  const result = modelingSteps(chain.definition, recordMap);
  assert.equal(result.steps.length, 2);
  assert.match(result.steps[0].formula[0], /历史株高趋势估计/);
  assert.match(result.steps[1].formula[0], /NDVI/);
  assert.match(result.steps[1].formula[0], /土壤/);
  assert.deepEqual(chain.definition, before);
  assert.equal(chain.definition.composition.nodes.length, 3);
});

test("修改目标与因素更新同一研究合同，目标不会留在输入因素中", async () => {
  const plan = editStudy(direct.definition, { targets: ["ndvi"], features: ["day", "height", "ndvi", "temperature"] });
  assert.deepEqual(studySettings(plan).parameters.features, ["day", "height", "temperature"]);
  assert.deepEqual(plan.evaluation.target_codes, ["ndvi"]);
  assert.equal(plan.variables.find((v) => v.code === "height").role, "covariate");
  assert.equal(plan.variables.find((v) => v.code === "ndvi").role, "target");
  assert.deepEqual(direct.definition.input_recipes.regression_config.value.targets, ["height", "leaf_area"]);
  if (process.env.MODARCHITECT_UI_EDITED_PLAN) await writeFile(process.env.MODARCHITECT_UI_EDITED_PLAN, JSON.stringify(plan));
});

test("至少一个目标和因素，历史时间顺序及实测来源不能因易用表单而丢失", () => {
  assert.throws(() => editStudy(direct.definition, { targets: [] }), /实测/);
  assert.throws(() => editStudy(direct.definition, { features: [] }), /因素/);
  assert.throws(() => editStudy(chain.definition, { fitThrough: "2026-06-10" }), /早于/);
  assert.throws(() => editStudy(chain.definition, { targets: ["prior_height"] }), /实测|估计/);
  const changed = editStudy(chain.definition, { features: ["ndvi", "temperature"] });
  assert.deepEqual(studySettings(changed).parameters.features, ["prior_height", "ndvi", "temperature"]);
});

test("未知及伪装成已知结构的图不会被引导表单覆盖", () => {
  const plan = structuredClone(chain.definition);
  plan.composition.nodes[1].bindings.find((b) => b.port === "forecast").source.port = "other";
  assert.equal(studySettings(plan), null);
  assert.equal(modelingSteps(plan, recordMap).steps.length, 3);
  assert.throws(() => editStudy(plan, { features: ["ndvi"] }), /自定义/);
  const experimental = structuredClone(direct.definition);
  experimental.variables[2].role = "group";
  assert.equal(studySettings(experimental), null);
  const runtime = structuredClone(direct.definition);
  runtime.input_recipes.regression_config.runtime_fields.training_end = "cutoff_date";
  assert.equal(studySettings(runtime), null);
});

test("日期分组区分拟合、训练、留出和完整对象身份", () => {
  assert.deepEqual(dataPeriods(direct.definition, direct.observations), {
    first: "2026-04-01", last: "2026-05-30", rows: 60, objects: 1, history: null, training: 40, holdout: 20,
  });
  const result = dataPeriods(chain.definition, chain.observations);
  assert.deepEqual([result.history, result.training, result.holdout], [45, 25, 20]);
  const table = structuredClone(chain.observations);
  table.rows[0].object.season_ref = "other-season";
  assert.equal(dataPeriods(chain.definition, table).objects, 2);
});

test("预测表单只要求原始已知因素，派生量由上游模型计算", () => {
  const make = (value, plan = value.definition) => ({ plan, input_columns: value.observations.columns });
  assert.deepEqual(predictionColumns(make(chain)).map((v) => v.code), ["day", "ndvi", "soil_water", "temperature"]);
  const plan = editStudy(direct.definition, { targets: ["ndvi"], features: ["height", "temperature"] });
  assert.deepEqual(predictionColumns(make(direct, plan)).map((v) => v.code), ["height", "temperature"]);
});

function domEnvironment() {
  const dom = new JSDOM(html, { url: "http://localhost/designer/" });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location,
    history: dom.window.history, localStorage: dom.window.localStorage, Option: dom.window.Option,
    matchMedia: () => ({ matches: false }),
    ResizeObserver: class { observe() {} } });
  document.fonts = { ready: Promise.resolve() };
  dom.window.HTMLElement.prototype.scrollIntoView = function () {};
  return dom;
}

test("研究表单的真实勾选事件更新公式，并在无目标时恢复有效状态", () => {
  const dom = domEnvironment(); let plan = structuredClone(direct.definition), message;
  const view = mountModeling({ getDefinition: () => plan, getRecords: () => recordMap,
    onEdit(value) { plan = value; view.render(); }, onExample() {}, onTechnical() {}, notify(value) { message = value; } });
  view.render(); view.setData(direct.observations);
  const feature = [...document.querySelectorAll("#modeling-settings fieldset:nth-of-type(2) input")].find((input) => input.value === "temperature");
  feature.checked = false; feature.dispatchEvent(new dom.window.Event("change"));
  assert.ok(!studySettings(plan).parameters.features.includes("temperature"));
  assert.ok(!document.querySelector(".modeling-formula").textContent.includes("气温"));
  for (const code of ["leaf_area", "height"]) {
    const input = [...document.querySelectorAll("#modeling-settings fieldset:first-of-type input")].find((value) => value.value === code);
    input.checked = false; input.dispatchEvent(new dom.window.Event("change"));
  }
  assert.match(message, /至少/);
  assert.equal(document.querySelectorAll("#modeling-settings fieldset:first-of-type input:checked").length, 1);
  dom.window.close();
});

test("公开方案目录不等待组件与个人工作区初始化", async () => {
  const dom = domEnvironment(), previous = globalThis.fetch; let release;
  const componentReply = new Promise((resolve) => { release = resolve; });
  const reply = (value) => ({ ok: true, status: 200, json: async () => value });
  globalThis.fetch = async (url) => {
    const path = new URL(url, location.href).pathname;
    if (path === "/api/v1/workspace/study-templates") return reply({ items: [{ id: "available-study", title: "可浏览的现成方案" }] });
    if (path === "/api/v1/model-center/components") return componentReply;
    if (path === "/api/v1/model-center/research-inputs") return reply(inputCatalog);
    if (path === "/api/v1/model-center/research-rules") return reply({ rules: [] });
    return reply({ items: [] });
  };
  const loading = import(new URL("studio.js?independent-directory", directory));
  try {
    for (let attempt = 0; attempt < 80 && !document.querySelector('[data-study-template="available-study"]'); attempt++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.ok(document.querySelector('[data-study-template="available-study"]'));
    assert.equal(document.getElementById("study-library-status").dataset.state, "ready");
    assert.match(document.getElementById("stage-loading").textContent, /正在读取组件目录/);
  } finally {
    release(reply({ total: records.length, page_size: 100, items: records }));
    await loading; await new Promise(setImmediate); globalThis.fetch = previous; dom.window.close();
  }
});

test("完整页面从引导入口载入、编辑并保存同一方案，组件视图保留实际五层", async () => {
  const dom = domEnvironment(); const calls = [], saved = new Map(), published = new Map();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    const parsed = new URL(url, location.href), path = parsed.pathname, body = options.body && JSON.parse(options.body);
    calls.push({ path, method: options.method || "GET", body });
    let value;
    if (path === "/api/v1/model-center/components") value = { total: records.length, page_size: 100, items: records };
    else if (path === "/api/v1/model-center/research-inputs") value = inputCatalog;
    else if (path === "/api/v1/model-center/research-rules") value = { version: "1.0", rules: [] };
    else if (path.startsWith("/api/v1/model-center/components/")) value = records.find((v) => v.definition.code === path.split("/").at(-1));
    else if (path.endsWith("/session")) value = { workspace: "test" };
    else if (path.endsWith("/examples/chain")) {
      value = structuredClone(chain); value.definition.layout.designer_positions = { "node:regression": { x: .1, y: .1 } };
    }
    else if (path.endsWith("/validate")) value = { check: { valid: true, issues: [], compiled: {} } };
    else if (path === "/api/v1/workspace/plans" && options.method === "POST") {
      value = { design_id: "saved-study", draft_id: "first-draft", draft_state: "draft", revision: 1, configuration: { definition: body.definition }, observations: body.observations, data_kind: body.data_kind }; saved.set(value.design_id, value);
    } else if (path === "/api/v1/workspace/plans/saved-study" && options.method === "PUT") {
      assert.equal(saved.get("saved-study").draft_state, "draft");
      value = { ...saved.get("saved-study"), revision: body.expected_revision + 1, configuration: { definition: body.definition } }; saved.set(value.design_id, value);
    } else if (path === "/api/v1/workspace/plans/saved-study/publish") {
      const current = saved.get("saved-study");
      value = { design_version_id: "published-version", version_name: "1.0.0" };
      published.set(value.design_version_id, structuredClone(current.configuration.definition));
      Object.assign(current, { draft_state: "published", published_version_id: value.design_version_id, latest_version: value });
    } else if (path === "/api/v1/workspace/plans/saved-study") value = saved.get("saved-study");
    else if (path === "/api/v1/workspace/design-versions/published-version/drafts") {
      assert.ok(options.headers["Idempotency-Key"]);
      const current = saved.get("saved-study");
      Object.assign(current, { draft_id: "second-draft", draft_state: "draft", base_version_id: "published-version", published_version_id: null, revision: current.revision + 1 });
      value = current;
    } else if (path.endsWith("/plans") || path.endsWith("/models") || path.endsWith("/runs")) value = { items: [] };
    else throw new Error("Unexpected test request " + path);
    return { ok: true, status: 200, json: async () => value };
  };
  const waitFor = async (condition) => {
    for (let attempt = 0; attempt < 80; attempt++) { if (condition()) return; await new Promise((resolve) => setTimeout(resolve, 10)); }
    throw new Error("Page did not reach expected state: " + document.getElementById("workspace-status").textContent);
  };
  try {
    await import(new URL("studio.js?dom-integration", directory));
    await waitFor(() => document.getElementById("workspace-status").textContent.includes("个人工作区已连接"));
    assert.equal(document.querySelectorAll("#input-categories button").length, 4);
    document.getElementById("start-chain").click();
    await waitFor(() => saved.size === 1 && !document.getElementById("cloud-save").disabled);
    assert.equal(document.querySelectorAll("#modeling-flow > li").length, 2);
    assert.equal(document.getElementById("technical-workspace").hidden, true);
    assert.equal(document.querySelectorAll("#graph .lane").length, 5);
    assert.equal(document.querySelectorAll("#graph [data-source$='_config']").length, 0);
    assert.equal(document.querySelectorAll("#graph .graph-settings").length, 3);
    document.getElementById("technical-toggle").click();
    assert.equal(document.getElementById("technical-workspace").hidden, false);
    assert.equal(document.getElementById("technical-toggle").getAttribute("aria-expanded"), "true");
    assert.ok(saved.get("saved-study").configuration.definition.layout.designer_positions);
    document.getElementById("auto-layout").click();
    const name = document.querySelector("#modeling-settings .modeling-date input");
    name.value = "易用性验证方案"; name.dispatchEvent(new dom.window.Event("change"));
    document.getElementById("technical-toggle").click();
    document.getElementById("component-library-link").click();
    assert.equal(document.getElementById("technical-workspace").hidden, false);
    const factor = [...document.querySelectorAll("#modeling-settings fieldset:nth-of-type(2) input")].find((value) => value.value === "temperature");
    factor.checked = false; factor.dispatchEvent(new dom.window.Event("change"));
    document.getElementById("cloud-save").click();
    await waitFor(() => saved.get("saved-study").revision === 2 && !document.getElementById("cloud-save").disabled);
    const last = calls.findLast((call) => call.method === "PUT");
    assert.equal(last.body.expected_revision, 1);
    assert.equal(last.body.definition.name, "易用性验证方案");
    assert.equal(last.body.definition.layout.designer_positions, undefined);
    assert.ok(!last.body.definition.input_recipes.regression_config.value.features.includes("temperature"));
    assert.equal(last.body.observations.rows.length, 90);
    assert.equal(document.querySelectorAll("#modeling-flow > li").length, 2);
    await waitFor(() => !document.getElementById("research-inspection").hasAttribute("aria-busy"));
    document.getElementById("wizard-save-design").click();
    await waitFor(() => saved.get("saved-study").draft_state === "published" && !document.getElementById("cloud-save").disabled);
    assert.ok(document.getElementById("wizard-name").matches(":disabled"));
    assert.match(document.getElementById("draft-lifecycle-status").textContent, /已发布.*只读/);
    const originalVersion = structuredClone(published.get("published-version"));
    document.getElementById("open-version-draft").click();
    await waitFor(() => saved.get("saved-study").draft_id === "second-draft" && !document.getElementById("wizard-name").matches(":disabled") && !document.getElementById("cloud-save").disabled);
    const editedName = document.getElementById("wizard-name");
    editedName.value = "新草稿"; editedName.dispatchEvent(new dom.window.Event("change"));
    document.getElementById("cloud-save").click();
    await waitFor(() => saved.get("saved-study").configuration.definition.name === "新草稿" && !document.getElementById("cloud-save").disabled);
    assert.deepEqual(published.get("published-version"), originalVersion);
    await waitFor(() => !document.getElementById("research-inspection").hasAttribute("aria-busy"));
  } finally { globalThis.fetch = originalFetch; dom.window.close(); }
});

test("系统输入建立双目标模型，新增因素与目标同步实际参数而不发明变量", () => {
  const plan = blankPlan();
  const add = (code, role) => {
    const variable = structuredClone(standard.definition.variables.find((v) => v.code === code)); variable.role = role;
    const requirement = standard.definition.collection_requirements.find((r) => r.variable_code === code);
    addSystemInput(plan, { variable, requirement });
  };
  add("lai", "target"); add("canopy_cover", "covariate");
  buildInputModel(plan, recordMap, "2026-05-10");
  add("agb_kg_ha", "target"); add("tuber_dm_kg_ha", "covariate");
  const context = studySettings(plan);
  assert.deepEqual(context.parameters.targets, ["lai", "agb_kg_ha"]);
  assert.deepEqual(context.parameters.features, ["canopy_cover", "tuber_dm_kg_ha"]);
  assert.equal(plan.schema_version, "1.5");
  assert.ok(plan.collection_requirements.every((r) => r.catalog_binding));
  assert.throws(() => add("lai", "target"), /已在方案/);
});

test("四类输入真实点击选入固定指标，第三方属性必须逐项明确选择", async () => {
  const dom = domEnvironment(); let plan = blankPlan(); const calls = [], messages = [];
  const view = mountSystemInputs({ catalog: inputCatalog, getDefinition: () => plan, getRecords: () => recordMap,
    onEdit(value) { plan = value; }, notify(value) { messages.push(value); },
    async configure(value) {
      calls.push(value);
      if (value.key === soilInput.key) throw new Error("取数未接通，测试不伪造目录结果");
      const code = value.key.split(":")[1].split("@")[0];
      return { variable: { ...standard.definition.variables.find((v) => v.code === code), role: value.role }, requirement: standard.definition.collection_requirements.find((r) => r.variable_code === code) };
    } });
  try {
    assert.equal(document.querySelectorAll("#input-categories button").length, 4);
    const lai = [...document.querySelectorAll(".input-catalog-card")].find((card) => card.querySelector("h3").textContent === "叶面积指数");
    assert.equal(lai.querySelectorAll("input").length, 0);
    assert.equal(lai.querySelectorAll("select").length, 0);
    lai.querySelector('[data-input-role="target"]').click();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(plan.variables[0].code, "lai"); assert.equal(plan.variables[0].unit, "m2_m2");
    assert.equal(plan.variables[0].role, "target");
    assert.match(document.getElementById("selected-system-inputs").textContent, /标准人工记录/);
    document.querySelector('[data-category="third_party"]').click();
    const controls = document.querySelectorAll(".input-catalog-card select");
    assert.equal(controls[0].value, ""); assert.equal(controls[1].value, "");
    controls[0].value = "5-15cm"; controls[0].dispatchEvent(new dom.window.Event("change"));
    controls[1].value = "mean"; controls[1].dispatchEvent(new dom.window.Event("change"));
    document.querySelector(".input-catalog-card button").click();
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.at(-1).selectors, { depth: "5-15cm", statistic: "mean" });
    assert.equal(document.querySelector('.input-catalog-card [data-input-role="target"]'), null);
    assert.match(messages.at(-1), /未接通/);
    view.render();
  } finally { dom.window.close(); }
});

test("资料和目标各自打开指标库，只采用当前步骤的用途并保留准确来源", async () => {
  const dom = domEnvironment(); let plan = blankPlan(), wizard; const calls = [];
  const library = mountSystemInputs({ catalog: inputCatalog, getDefinition: () => plan, getRecords: () => recordMap,
    onEdit(value) { plan = value; wizard.render(); }, notify() {},
    async configure(value) {
      calls.push(value); const code = value.key.split(":")[1].split("@")[0];
      return { variable: { ...standard.definition.variables.find((v) => v.code === code), role: value.role },
        requirement: standard.definition.collection_requirements.find((r) => r.variable_code === code) };
    } });
  wizard = mountWizard({ getDefinition: () => plan, getRecords: () => recordMap, getInputCatalog: () => inputCatalog,
    onEdit(value) { plan = value; wizard.render(); }, onChooseIndicators: (role) => library.setAdoptionRole(role),
    onExample() {}, onTechnical() {}, validate() {} });
  try {
    document.querySelector('[data-section="inputs"]').click();
    document.getElementById("open-indicator-library").click();
    assert.equal(document.querySelectorAll('.input-catalog-card [data-input-role="target"]').length, 0);
    const card = (name) => [...document.querySelectorAll(".input-catalog-card")].find((item) => item.querySelector("h3").textContent === name);
    card("冠层覆盖度").querySelector('[data-input-role="covariate"]').click(); await new Promise(setImmediate);
    document.getElementById("close-indicator-library").click();
    document.getElementById("wizard-next").click();
    assert.equal(location.hash, "#configure/targets");
    document.getElementById("open-output-library").click();
    assert.equal(document.querySelectorAll('.input-catalog-card [data-input-role="covariate"]').length, 0);
    const duplicate = card("冠层覆盖度");
    assert.equal(duplicate.querySelector("button").disabled, true);
    assert.match(duplicate.textContent, /已选为研究资料/);
    const callsBeforeDuplicate = calls.length;
    duplicate.querySelector("button").click(); await new Promise(setImmediate);
    assert.equal(calls.length, callsBeforeDuplicate);
    card("叶面积指数").querySelector('[data-input-role="target"]').click(); await new Promise(setImmediate);
    assert.deepEqual(calls.map((value) => value.role), ["covariate", "target"]);
    assert.ok(document.querySelector('#wizard-role-table [data-variable-code="canopy_cover"]'));
    assert.ok(document.querySelector('#wizard-output-table [data-variable-code="lai"]'));
    assert.equal(document.querySelector('#wizard-role-table [data-variable-code="lai"]'), null);
    assert.match(card("叶面积指数").textContent, /已选为目标指标/);
    assert.equal(card("叶面积指数").querySelector("button").disabled, true);
    document.getElementById("close-indicator-library").click();
    document.querySelector('[data-section="inputs"]').click();
    document.getElementById("open-indicator-library").click();
    assert.equal(card("叶面积指数").querySelector("button").disabled, true);
    assert.match(card("叶面积指数").textContent, /已选为目标指标/);
    document.getElementById("close-indicator-library").click();
    document.querySelector('[data-section="targets"]').click();
    document.getElementById("open-output-library").click();
    assert.equal(document.getElementById("indicator-dialog").closest('[data-wizard-section]'), null);
    document.querySelector('[data-category="third_party"]').click();
    assert.equal(card("土壤 pH").querySelector('[data-input-role]'), null);
    assert.match(card("土壤 pH").textContent, /不是实测/);
    assert.match(document.querySelector('[data-category="third_party"]').textContent, /可添加 0/);
  } finally { dom.window.close(); }
});

test("输入目录按二级分类筛选与搜索，预留三维分类不虚构可用指标", async () => {
  const taxonomy = JSON.parse(await readFile(new URL("../modarchitect/contracts/input-taxonomy-v1.json", import.meta.url), "utf8"));
  const catalog = structuredClone(inputCatalog);
  for (const item of catalog.items) item.subcategory = taxonomy.assignments[item.key];
  for (const parent of catalog.categories) parent.children = taxonomy.groups.filter((group) => group.parent === parent.code).map((group) => ({ code: group.code, name: group.name, count: catalog.items.filter((item) => item.subcategory === group.code).length }));
  const dom = domEnvironment(), plan = blankPlan();
  mountSystemInputs({ catalog, getDefinition: () => plan, getRecords: () => recordMap, onEdit() {}, configure() {}, notify() {} });
  try {
    document.querySelector('[data-subcategory="manual_leaf_cover"]').click();
    assert.deepEqual([...document.querySelectorAll(".input-catalog-card h3")].map((element) => element.textContent).sort(), ["冠层覆盖度", "叶面积指数"].sort());
    document.querySelector('[data-category="third_party"]').click();
    assert.equal(document.querySelector('[data-subcategory=""]').getAttribute("aria-pressed"), "true");
    document.querySelector('[data-subcategory="third_party_soil"]').click();
    assert.equal(document.querySelectorAll(".input-catalog-card").length, 1);
    const search = document.getElementById("input-catalog-search"); search.value = "土壤数据"; search.dispatchEvent(new window.Event("input"));
    assert.equal(document.querySelectorAll(".input-catalog-card").length, 1);
    search.value = ""; search.dispatchEvent(new window.Event("input"));
    document.querySelector('[data-category="platform_analysis"]').click();
    document.querySelector('[data-subcategory="analysis_3d_phenotype"]').click();
    assert.equal(document.querySelectorAll(".input-catalog-card").length, 0);
    assert.match(document.getElementById("input-catalog-list").textContent, /暂时没有可选指标/);
  } finally { dom.window.close(); }
});

test("多输入研究新增指标需明确目标数据组，不同时写入全部输入", () => {
  const plan = structuredClone(chain.definition);
  plan.input_recipes.second = { kind: "observations", variable_codes: [] };
  const configuration = { variable: { ...standard.definition.variables.find((row) => row.code === "lai"), role: "covariate" }, requirement: standard.definition.collection_requirements.find((row) => row.variable_code === "lai") };
  const original = structuredClone(plan);
  assert.throws(() => addSystemInput(plan, configuration), /明确/);
  assert.deepEqual(plan, original);
  addSystemInput(plan, configuration, "second");
  assert.deepEqual(plan.input_recipes.second.variable_codes, ["lai"]);
  assert.ok(!Object.values(plan.input_recipes).some((recipe) => recipe.kind === "observations" && recipe !== plan.input_recipes.second && recipe.variable_codes.includes("lai")));
});

test("新增系统因子后模板按当前配方补列，保留已有值并要求填写新值", () => {
  const plan = blankPlan();
  const add = (code, role) => addSystemInput(plan, { variable: { ...standard.definition.variables.find((v) => v.code === code), role }, requirement: standard.definition.collection_requirements.find((r) => r.variable_code === code) });
  add("lai", "target"); add("canopy_cover", "covariate"); buildInputModel(plan, recordMap, "2026-05-10");
  const old = observationTemplate(plan);
  old.rows[0].values = { lai: 1.5, canopy_cover: 0.4 }; const before = structuredClone(old);
  add("agb_kg_ha", "covariate");
  const template = observationTemplate(plan, old);
  assert.deepEqual(template.columns.map((c) => c.code), ["lai", "canopy_cover", "agb_kg_ha"]);
  assert.deepEqual(template.rows[0].values, { lai: 1.5, canopy_cover: 0.4, agb_kg_ha: null });
  assert.equal(template.columns[2].name, "地上生物量");
  assert.deepEqual(old, before);
});

test("平台资料按完整对象日期补齐因素，保留实测并拒绝错配", () => {
  const object = { field_ref: "f", crop_code: "potato", season_ref: "2025" };
  const original = { columns: [{ code: "lai", name: "叶面积指数", unit: "m2_m2", value_kind: "observed" }], rows: [{ object, business_date: "2025-04-01", values: { lai: 2 } }] };
  const source = { columns: [{ code: "temperature_mean_daily", name: "日平均气温", unit: "celsius", value_kind: "estimated" }], rows: [{ object, business_date: "2025-04-01", values: { temperature_mean_daily: 15 } }] };
  const result = mergeSourceTables(original, [source]);
  assert.equal(result.rows[0].values.lai, 2);
  assert.equal(result.rows[0].values.temperature_mean_daily, 15);
  assert.equal(result.columns.at(-1).value_kind, "estimated");
  assert.equal(original.columns.length, 1);
  const wrong = structuredClone(source); wrong.rows[0].object.field_ref = "other";
  assert.throws(() => mergeSourceTables(original, [wrong]), /对象和日期/);
  const repeated = structuredClone(original); repeated.rows.push({ ...repeated.rows[0], object: { ...object, season_ref: "2026" } });
  assert.throws(() => acquisitionRange(repeated), /多个对象/);
});

test("自动取数无需伪造实测表，多对象同指标来源按完整身份装配", () => {
  const first = { field_ref: "A", crop_code: "potato", season_ref: "2025" }, second = { ...first, field_ref: "B" };
  const column = { code: "temperature_mean_daily", name: "日平均气温", unit: "celsius", value_kind: "estimated" };
  const source = (object, value) => ({ columns: [column], rows: [{ object, business_date: "2025-04-01", values: { temperature_mean_daily: value } }] });
  const automatic = mergeSourceTables(null, [source(first, 15)]);
  assert.equal(automatic.rows[0].values.temperature_mean_daily, 15);
  const manual = { columns: [{ code: "lai", name: "叶面积指数", unit: "m2_m2", value_kind: "observed" }], rows: [first, second].map((object) => ({ object, business_date: "2025-04-01", values: { lai: 2 } })) };
  const combined = mergeSourceTables(manual, [source(first, 15), source(second, 19)]);
  assert.equal(combined.rows[0].values.temperature_mean_daily, 15);
  assert.equal(combined.rows[1].values.temperature_mean_daily, 19);
  assert.ok(combined.rows.every((row) => row.values.lai === 2));
  assert.throws(() => mergeSourceTables(manual, [source(first, 15), source(first, 15)]), /重复对象和日期/);
});

test("平台采集真实提交并采用来源引用，合成记录不能自动取得真实资格", async () => {
  const dom = domEnvironment();
  let adopted = null, saved = 0, dataKind = "synthetic";
  const object = { field_ref: "f", crop_code: "potato", season_ref: "2025" };
  const data = { columns: [{ code: "lai", name: "叶面积指数", unit: "m2_m2", value_kind: "observed" }], rows: [{ object, business_date: "2025-04-01", values: { lai: 2 } }] };
  const messages = [];
  const view = mountSourceData({ getDefinition: () => ({ collection_requirements: [{ source: "third_party", catalog_binding: { code: "weather", contract_sha256: "test" } }] }), getData: () => data, getDataKind: () => dataKind,
    async saveDefinition() { saved++; return { design_id: "plan", revision: 2 }; },
    async api(path, options) {
      if (path === "/api/v1/model-center/research-inputs") return { items: [{ source: { binding: { code: "weather", contract_sha256: "test" } } }] };
      if (options?.method === "POST") { assert.deepEqual(options.body.object, object); assert.equal(options.body.expected_revision, 2); return { acquisition_id: "job" }; }
      if (path.includes("input-acquisitions")) return { status: "succeeded", snapshot_ids: ["snapshot"] };
      return { support: { requested_point: { latitude: 39, longitude: 116 } }, observations: { columns: [{ code: "temperature_mean_daily", name: "日平均气温", unit: "celsius", value_kind: "estimated" }], rows: [{ object, business_date: "2025-04-01", values: { temperature_mean_daily: 15 } }] } };
    }, adopt(ids, table) { adopted = { ids, table }; }, report(message) { messages.push(message); } });
  try {
    view.render();
    const form = document.querySelector("#source-data-panel form");
    form.elements.namedItem("latitude").value = "39"; form.elements.namedItem("longitude").value = "116";
    form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(saved, 0); assert.equal(adopted, null); assert.match(messages.at(-1), /合成示例/);
    dataKind = "user_supplied";
    form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(saved, 1); assert.deepEqual(adopted.ids, ["snapshot"]);
    assert.equal(adopted.table.rows[0].values.temperature_mean_daily, 15);
    assert.doesNotMatch(messages.at(-1), /实测目标仍需提供/);
  } finally { dom.window.close(); }
});

test("卫星缺日需明确选择配对范围，多对象无基础表不得静默漏行", () => {
  const object = { field_ref: "A", crop_code: "potato", season_ref: "2025" }, second = { ...object, field_ref: "B" };
  const row = (object, business_date, values) => ({ object, business_date, values });
  const source = (code, rows) => ({ columns: [{ code, name: code, unit: "dimensionless", value_kind: "estimated" }], rows });
  const weather = source("weather", [row(object, "2025-01-01", { weather: 10 }), row(object, "2025-01-02", { weather: 20 })]);
  const satellite = source("red", [row(object, "2025-01-02", { red: .2 })]);
  const base = { columns: [{ code: "lai", unit: "m2_m2", name: "叶面积指数", value_kind: "observed" }], rows: [row(object,"2025-01-01",{ lai:1 }), row(object,"2025-01-02",{ lai:2 })] };
  const before = structuredClone(base);
  assert.throws(() => mergeSourceTables(base, [weather,satellite]), /未覆盖/);
  assert.deepEqual(base,before);
  const selection = commonSourceDates(base,[weather,satellite]);
  assert.equal(selection.total,2); assert.equal(selection.excluded,1);
  assert.deepEqual(selection.table.rows,[row(object,"2025-01-02",{ lai:2, weather:20, red:.2 })]);
  assert.deepEqual(base,before);
  const multi = mergeSourceTables(null, [source("red", [row(object,"2025-01-02",{ red:.2 })]), source("red", [row(second,"2025-01-02",{ red:.3 })])]);
  assert.equal(multi.rows.length,2);
  assert.deepEqual(splitAcquisitionRange({ object, start_date:"2025-01-01", end_date:"2025-03-05" },31).map((range) => [range.start_date,range.end_date]), [["2025-01-01","2025-01-31"],["2025-02-01","2025-03-03"],["2025-03-04","2025-03-05"]]);
});
