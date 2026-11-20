import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { mountInspection, renderInspection } from "../modarchitect/web/designer/inspection-view.js";
import { mountMethodPicker } from "../modarchitect/web/designer/method-picker.js";
import { mountWizard } from "../modarchitect/web/designer/wizard.js";

const html = readFileSync(new URL("../modarchitect/web/designer/index.html", import.meta.url), "utf8");
// 直接使用服务端实际响应，避免前端与测试各自发明一份兼容的假合同。
const python = process.env.MODARCHITECT_TEST_PYTHON || fileURLToPath(new URL(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python", import.meta.url));
const result = spawnSync(python, ["-c", `
import json
from modarchitect.inspection import inspect_definition
from modarchitect.catalog import catalog
from modarchitect.research_methods import method_directory
from modarchitect.runtime.service import component_record
from modarchitect.study_templates import template_view, template
rows = [template_view(template(name), include_definition=True) for name in ('crop-growth-prediction', 'field-indicator-summary', 'soil-weather-satellite-lai')]
definition = rows[0]['definition']
request_port = next(binding['source']['port'] for binding in definition['composition']['nodes'][-1]['bindings'] if binding['port'] == 'request')
request = definition['input_recipes'][request_port]
request['value'].pop('training_end', None)
request['runtime_fields'] = {'training_end': 'training_holdout_cutoff_date'}
print(json.dumps({
    'fixtures': [{'definition': row['definition'], 'inspection': inspect_definition(row['definition']).model_dump(mode='json')} for row in rows],
    'directory': method_directory({}).model_dump(mode='json'),
    'catalog': {f'{code}@{rev}': component_record(entry) for (code, rev), entry in catalog().items()},
}))
`], { encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
assert.equal(result.status, 0, result.stderr);
const { fixtures, directory, catalog } = JSON.parse(result.stdout);

function environment() {
  const dom = new JSDOM(html, { url: "http://localhost/designer/#configure/calculation" });
  for (const key of ["document", "window", "location", "history", "Option"]) globalThis[key] = dom.window[key];
  return dom;
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 10));

test("训练与分析共用配置卡，按操作展示实际资源与训练设置", () => {
  for (const fixture of fixtures.slice(0, 2)) {
    const dom = environment(), plan = fixture.definition;
    try {
      const host = document.getElementById("research-inspection");
      renderInspection(host, fixture.inspection, { getDefinition: () => plan });
      mountWizard({ getDefinition: () => plan, getRecords: () => new Map(), getInspection: () => fixture.inspection, onEdit() {}, validate() {} }).render();
      assert.equal(document.querySelector(".modeling-workspace").closest("#technical-workspace").hidden, true);
      assert.equal(host.querySelector(".method-preview-flow, .method-prediction, input[type=date]"), null);
      assert.match(host.querySelector(".calculation-overview").textContent, /数据资源.*观测数据.*计算配置/);
      assert.doesNotMatch(host.textContent, /现在准备到哪一步/);
      const cards = host.querySelectorAll(".calculation-resources");
      if (fixture.inspection.operation === "analyze") {
        assert.equal(cards.length, 1);
        assert.doesNotMatch(host.textContent, /预测目标|训练策略|RMSE|R²/);
        assert.ok(host.querySelector(".method-advanced"));
      } else {
        assert.equal(cards.length, 2);
        assert.match(cards[0].textContent, /输入变量（[0-9]+ 项）.*冠层覆盖度.*块茎干物质.*查看详情/);
        assert.doesNotMatch(cards[0].textContent, /叶面积指数|地上生物量/);
        assert.match(cards[1].textContent, /预测目标（2 项）.*叶面积指数.*地上生物量.*查看详情/);
        assert.match(host.querySelector(".calculation-split").textContent, /数据划分方式.*按观测日期划分.*训练集比例80%.*验证集比例20%/);
        assert.equal(host.querySelectorAll(".calculation-metrics .is-selected").length, fixture.inspection.evaluation.metrics.length);
        assert.match(host.textContent, /评价指标.*R².*RMSE.*MAE.*普通最小二乘.*拟合截距/);
      }
    } finally { dom.window.close(); }
  }
});

test("调整比例和评价指标进入可保存的方案，空指标不改配置", async () => {
  const dom = environment(), fixture = fixtures[0];
  let definition = structuredClone(fixture.definition);
  try {
    const view = mountInspection({
      getDefinition: () => definition, inspect: async () => fixture.inspection, onChange() {}, delay: 0,
      onEdit(next) { definition = next; },
    });
    view.schedule(); await tick();
    document.querySelector('[aria-label="编辑训练策略"]').click();
    const ratio = document.querySelector(".calculation-editor input[type=number]");
    ratio.value = "65";
    ratio.dispatchEvent(new window.Event("input"));
    assert.match(document.querySelector(".calculation-editor").textContent, /验证集比例 35%/);
    document.querySelector(".calculation-editor button[type=submit]").click();
    assert.equal(definition.evaluation.training_percent, 65);
    view.schedule(); await tick();
    document.querySelector('[aria-label="编辑评价指标"]').click();
    const checks = [...document.querySelectorAll(".calculation-editor input[type=checkbox]")];
    for (const check of checks) check.checked = false;
    document.querySelector(".calculation-editor button[type=submit]").click();
    assert.match(document.querySelector(".calculation-editor [role=status]").textContent, /至少选择一项/);
    assert.equal(definition.evaluation.metrics, undefined);
    checks.find((check) => check.value === "mae").checked = true;
    document.querySelector(".calculation-editor button[type=submit]").click();
    assert.deepEqual(definition.evaluation.metrics, ["mae"]);
  } finally { dom.window.close(); }
});

test("未登记的展示名称使用接口返回值，规则检查详情不进入预览", () => {
  const dom = environment(), fixture = structuredClone(fixtures[0]);
  try {
    fixture.inspection.nodes[0].component.code = "new_component_from_catalog";
    fixture.inspection.nodes[0].name = "新登记计算方法";
    fixture.inspection.nodes[0].method_name = null;
    fixture.inspection.checks.operation = { status: "blocked", issues: [{ code: "future_rule", path: ["composition", "nodes", 0], node: "regression", port: null, message: "新规则的准确说明" }] };
    const host = document.getElementById("research-inspection");
    renderInspection(host, fixture.inspection, { getDefinition: () => fixture.definition });
    assert.match(host.textContent, /新登记计算方法/);
    assert.doesNotMatch(host.textContent, /新规则的准确说明/);
  } finally { dom.window.close(); }
});

test("方案变更和请求乱序不会复用上次通过结果，失败后清空旧资料", async () => {
  const dom = environment(), pending = []; let plan = structuredClone(fixtures[0].definition);
  try {
    const view = mountInspection({ getDefinition: () => plan, inspect: () => new Promise((resolve, reject) => pending.push({ resolve, reject })), onEdit() {}, onTechnical() {}, notify() {}, onChange() {}, delay: 0 });
    view.schedule(); await tick();
    plan.name = "新的方案"; view.schedule(); await tick();
    pending[1].resolve(fixtures[1].inspection); await tick();
    pending[0].resolve(fixtures[0].inspection); await tick();
    assert.equal(view.get().operation, "analyze");
    assert.equal(view.get().checks.execution.status, "not_checked");
    plan.question = "修改后的问题"; view.schedule();
    assert.equal(view.get(), null);
    assert.equal(document.querySelector(".calculation-overview"), null);
    await tick(); pending[2].reject(new Error("offline")); await tick();
    assert.equal(document.getElementById("research-inspection").textContent, "");
    assert.match(document.getElementById("inspection-status").textContent, /暂时无法核对/);
    assert.equal(document.getElementById("inspection-retry").hidden, false);
    document.getElementById("inspection-retry").click(); await tick();
    pending[3].resolve(fixtures[0].inspection); await tick();
    assert.equal(document.getElementById("inspection-retry").hidden, true);
    assert.equal(view.get().operation, "train");
  } finally { dom.window.close(); }
});

test("真实方法目录由同一套卡片渲染，自动沿用指标及默认配置，无手填日期", async () => {
  const dom = environment(); let plan = structuredClone(fixtures[0].definition);
  try {
    const view = mountMethodPicker({
      getDefinition: () => plan, getRecords: () => new Map(Object.entries(catalog)), loadMethods: async () => directory,
      onEdit(next) { plan = next; }, validate: async () => ({ valid: true }), notify() {},
    });
    await view.open();
    assert.equal(document.querySelectorAll("#method-list button").length, 5);
    assert.match(document.getElementById("method-list").textContent, /作物生长机理模拟.*WOFOST.*待接入.*APSIM/);
    assert.doesNotMatch(document.getElementById("method-list").textContent, /标准观测描述统计/);
    document.querySelector('[data-method="random_forest_training@1"]').click();
    const detail = document.getElementById("method-detail");
    assert.equal(detail.querySelector('input[type="date"]'), null);
    assert.equal(detail.querySelector('[data-field="seed"]').value, "17");
    assert.match(detail.textContent, /开始训练时按观测日期/);
    assert.equal(detail.querySelector("details").open, false);
    document.getElementById("apply-method").click(); await new Promise(setImmediate);
    const configured = Object.values(plan.input_recipes).find((recipe) => recipe.kind === "configuration");
    assert.equal(configured.value.seed, 17);
    assert.equal("training_end" in configured.value, false);
    assert.equal(configured.runtime_fields.training_end, "training_holdout_cutoff_date");
    assert.deepEqual(configured.value.targets, fixtures[0].definition.evaluation.target_codes);
  } finally { dom.window.close(); }
});

test("卫星 NDVI 配对是上游资料步骤，普通选择直接配置训练模型", async () => {
  const dom = environment(); let plan = structuredClone(fixtures[2].definition);
  try {
    const alignment = plan.composition.nodes.find((node) => node.component.code === "sentinel_ndvi_features");
    const picker = mountMethodPicker({
      getDefinition: () => plan, getRecords: () => new Map(Object.entries(catalog)), loadMethods: async () => directory,
      onEdit(next) { plan = next; }, validate: async () => ({ valid: true }), notify() {},
    });
    await picker.open();
    const steps = document.getElementById("method-target");
    assert.equal(steps.options.length, 1);
    assert.equal(steps.closest("label").hidden, true);
    assert.equal(plan.composition.nodes.find((node) => node.code === steps.value).component.code, "multivariate_linear_training");
    document.querySelector('[data-method="random_forest_training@1"]').click();
    document.getElementById("apply-method").click(); await new Promise(setImmediate);
    assert.deepEqual(plan.composition.nodes.find((node) => node.code === alignment.code), alignment);
    const trained = plan.composition.nodes.find((node) => node.component.code === "random_forest_training");
    assert.ok(trained.bindings.some((binding) => binding.source.node === alignment.code));
  } finally { dom.window.close(); }
});
