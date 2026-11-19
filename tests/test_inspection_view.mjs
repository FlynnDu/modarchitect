import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { mountInspection, renderInspection } from "../modarchitect/web/designer/inspection-view.js";
import { mountWizard } from "../modarchitect/web/designer/wizard.js";

const html = readFileSync(new URL("../modarchitect/web/designer/index.html", import.meta.url), "utf8");
// 直接使用服务端实际响应，避免前端与测试各自发明一份兼容的假合同。
const python = process.env.MODARCHITECT_TEST_PYTHON || fileURLToPath(new URL(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python", import.meta.url));
const result = spawnSync(python, ["-c", `
import json
from modarchitect.inspection import inspect_definition
from modarchitect.study_templates import template_view, template
rows = [template_view(template(name), include_definition=True) for name in ('crop-growth-prediction', 'field-indicator-summary')]
print(json.dumps([{'definition': row['definition'], 'inspection': inspect_definition(row['definition']).model_dump(mode='json')} for row in rows]))
`], { encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
assert.equal(result.status, 0, result.stderr);
const fixtures = JSON.parse(result.stdout);

function environment() {
  const dom = new JSDOM(html, { url: "http://localhost/designer/#configure/calculation" });
  for (const key of ["document", "window", "location", "history", "Option"]) globalThis[key] = dom.window[key];
  return dom;
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 10));

test("真实训练与分析响应由同一入口显示用途、参数、成果和分离的检查状态", () => {
  for (const fixture of fixtures) {
    const dom = environment(); let plan = structuredClone(fixture.definition);
    try {
      const host = document.getElementById("research-inspection"), callbacks = { getDefinition: () => plan, onEdit(next) { plan = next; }, onTechnical() {}, notify() {} };
      renderInspection(host, fixture.inspection, callbacks);
      mountWizard({ getDefinition: () => plan, getRecords: () => new Map(), getInspection: () => fixture.inspection, onEdit() {}, validate() {} }).render();
      assert.equal(document.querySelector(".modeling-workspace").hidden, true);
      assert.equal(host.querySelectorAll("[data-inspection-node]").length, plan.composition.nodes.length);
      assert.match(host.querySelector('[data-check="execution"]').textContent, /尚未检查/);
      assert.doesNotMatch(host.textContent, /用留出观测检验|保存模型，输入新因素预测/);
      const node = fixture.inspection.nodes[0];
      for (const output of node.outputs) assert.ok(host.textContent.includes(output.name));
      if (fixture.inspection.operation === "analyze") {
        assert.match(host.textContent, /分析资料/);
        assert.equal(host.querySelector('[data-field="training_end"]'), null);
      } else {
        const date = host.querySelector('[data-field="training_end"]');
        date.value = "2026-05-12"; date.dispatchEvent(new dom.window.Event("input"));
        assert.equal(plan.input_recipes[node.request_input].value.training_end, "2026-05-12");
      }
    } finally { dom.window.close(); }
  }
});

test("新组件名称和未识别规则均可展示，定位使用服务端返回的节点", () => {
  const dom = environment(), fixture = structuredClone(fixtures[0]), locations = [];
  try {
    fixture.inspection.nodes[0].component.code = "new_component_from_catalog";
    fixture.inspection.nodes[0].name = "新登记计算方法";
    fixture.inspection.checks.operation = { status: "blocked", issues: [{ code: "future_rule", path: ["composition", "nodes", 0], node: "regression", port: null, message: "新规则的准确说明" }] };
    const host = document.getElementById("research-inspection");
    renderInspection(host, fixture.inspection, { getDefinition: () => fixture.definition, onEdit() {}, onTechnical(key) { locations.push(key); }, notify() {} });
    assert.match(host.textContent, /新登记计算方法/); assert.match(host.textContent, /新规则的准确说明/);
    host.querySelector('[data-rule="future_rule"] button').click();
    assert.deepEqual(locations, ["node:regression"]);
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
    view.setExecutionChecks({ execution: { status: "blocked", issues: [{ code: "operation", path: [], node: null, port: null, message: "当前执行被拒绝" }] } });
    assert.match(document.querySelector('[data-check="execution"]').textContent, /当前执行被拒绝/);
    plan.question = "修改后的问题"; view.schedule();
    assert.equal(view.get(), null);
    assert.equal(document.querySelector('[data-check="execution"]'), null);
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

test("连续编辑参数在重新核对期间保留焦点，切换方案立即清除旧控件", async () => {
  const dom = environment(), pending = []; let plan = structuredClone(fixtures[0].definition);
  try {
    const view = mountInspection({ getDefinition: () => plan, inspect: () => new Promise((resolve) => pending.push(resolve)), onEdit(next) { plan = next; view.schedule(); }, onTechnical() {}, notify() {}, onChange() {}, delay: 0 });
    view.schedule(); await tick(); pending[0](fixtures[0].inspection); await tick();
    const field = document.querySelector('#research-inspection [data-field="training_end"]'); field.focus();
    for (const day of ["2026-05-11", "2026-05-12"]) {
      field.value = day; field.dispatchEvent(new dom.window.Event("input"));
      assert.equal(field.isConnected, true); assert.equal(document.activeElement, field);
    }
    assert.equal(plan.input_recipes.regression_config.value.training_end, "2026-05-12");
    plan = structuredClone(fixtures[1].definition); view.schedule();
    assert.equal(field.isConnected, false);
    await tick();
  } finally { dom.window.close(); }
});
