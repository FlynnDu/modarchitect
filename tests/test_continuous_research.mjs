import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { mountContinuousResearch, renderDailyCurve } from "../modarchitect/web/designer/continuous-research.js";
import { renderTableCurves } from "../modarchitect/web/designer/observation-curves.js";

test("单次结果曲线切换对象和指标，保持来源性质、单位及缺日", () => {
  const dom = new JSDOM("<main></main>"), previous = globalThis.document; globalThis.document = dom.window.document;
  const a = { field_ref: "A", crop_code: "potato", season_ref: "2026" }, b = { ...a, field_ref: "B" };
  const table = { columns: [{ code: "temperature", name: "日最高气温", unit: "celsius", value_kind: "estimated" }, { code: "height", name: "株高", unit: "cm", value_kind: "predicted" }], rows: [
    { object: a, business_date: "2026-07-01", values: { temperature: 28, height: 11 } },
    { object: a, business_date: "2026-07-03", values: { temperature: 30, height: 13 } },
    { object: b, business_date: "2026-07-02", values: { temperature: 42, height: 99 } },
  ] };
  try {
    const host = document.querySelector("main"); renderTableCurves(host, table);
    assert.equal(host.querySelectorAll("circle").length, 2); assert.equal(host.querySelectorAll("path").length, 1);
    assert.match(host.querySelector(".observation-curve").textContent, /来源估计.*2 条结果记录/);
    assert.doesNotMatch(host.querySelector(".observation-curve").textContent, /99/);
    const variable = host.querySelector('[aria-label="选择曲线指标"]'); variable.value = "height"; variable.dispatchEvent(new dom.window.Event("change"));
    assert.match(host.querySelector(".observation-curve").textContent, /cm.*模型预测/);
    const object = host.querySelector('[aria-label="选择曲线研究对象"]'); object.selectedIndex = 1; object.dispatchEvent(new dom.window.Event("change"));
    assert.equal(host.querySelectorAll("circle").length, 1); assert.match(host.querySelector(".observation-curve").textContent, /99/);
    renderTableCurves(host, null); assert.equal(host.children.length, 0);
  } finally { globalThis.document = previous; dom.window.close(); }
});

test("每日曲线保留对象、单位和资料缺口，不跨缺日连线", () => {
  const dom = new JSDOM("<main></main>"); globalThis.document = dom.window.document;
  const object = { field_ref: "A", crop_code: "wheat", season_ref: "2026" };
  const series = { start: "2026-11-01", end: "2026-11-04", columns: [{ output: "predictions", code: "height", name: "株高", unit: "cm", value_kind: "predicted" }], rows: [
    { output: "predictions", business_date: "2026-11-01", object, values: { height: 12 } },
    { output: "predictions", business_date: "2026-11-02", object, values: { height: 13 } },
    { output: "predictions", business_date: "2026-11-04", object, values: { height: 16 } },
    { output: "predictions", business_date: "2026-11-03", object: { ...object, field_ref: "B" }, values: { height: 99 } },
  ] };
  const host = document.querySelector("main");
  renderDailyCurve(host, series, "predictions", "height", JSON.stringify(["A", "wheat", "2026"]));
  assert.equal(host.querySelectorAll("circle").length, 3);
  assert.equal(host.querySelectorAll("path").length, 2); // 一条坐标轴、一段连续日期。
  assert.match(host.textContent, /模型预测/); assert.match(host.textContent, /cm/);
  assert.doesNotMatch(host.textContent, /99/);
  renderDailyCurve(host, { ...series, rows: [] }, "predictions", "height", "missing");
  assert.equal(host.querySelector("svg"), null); assert.match(host.textContent, /尚无/);
  delete globalThis.document;
});

test("加载每日研究时锁定选择，暂停始终作用于当前可见研究", async (t) => {
  const dom = new JSDOM('<section id="continuous-research"></section>');
  const previousDocument = globalThis.document, previousOption = globalThis.Option;
  globalThis.document = dom.window.document; globalThis.Option = dom.window.Option;
  t.after(() => {
    if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument;
    if (previousOption === undefined) delete globalThis.Option; else globalThis.Option = previousOption;
    dom.window.close();
  });
  const tasks = ["A", "B", "C"].map((id) => ({ task_id: id, name: id, status: "active", revision: 1, observation_start: "2026-01-01", observation_end: "2026-01-03", objects: [] }));
  let releaseB, beganB, delayB = true;
  const started = new Promise((resolve) => { beganB = resolve; });
  const mutations = [], failures = [];
  const api = async (path, options) => {
    if (options?.method === "POST") {
      mutations.push(path);
      const selected = tasks.find((item) => path === "/report-tasks/" + item.task_id + "/pause");
      assert.ok(selected, "只应提交所选研究的暂停请求"); selected.status = "paused"; selected.revision += 1;
      return selected;
    }
    if (path === "/report-tasks") return { items: tasks };
    if (path.endsWith("/batches?page=1")) return { items: [] };
    if (path.endsWith("/series")) return { start: "2026-01-01", end: "2026-01-03", columns: [], rows: [] };
    if (path === "/report-tasks/B" && delayB) {
      delayB = false;
      return new Promise((resolve) => { releaseB = () => resolve(tasks[1]); beganB(); });
    }
    const selected = tasks.find((item) => path === "/report-tasks/" + item.task_id);
    assert.ok(selected, "只应读取已列出的研究"); return selected;
  };
  const view = mountContinuousResearch({ api, save: async () => {}, getModel: () => null, report: (message) => failures.push(message), follow: async () => {} });
  await view.refresh();
  const select = document.querySelector('[aria-label="选择每日研究"]');
  const chooseAsUser = (value) => {
    if (select.disabled) return false;
    select.value = value; select.dispatchEvent(new dom.window.Event("change")); return true;
  };
  assert.equal(chooseAsUser("B"), true); await started;
  assert.equal(select.disabled, true);
  assert.equal(chooseAsUser("C"), false, "普通用户不能更改禁用的选择框");
  assert.equal(select.value, "B");
  releaseB(); await new Promise(setImmediate);
  assert.equal(select.disabled, false);
  const pause = [...document.querySelectorAll("button")].find((button) => button.textContent === "暂停每日研究");
  assert.ok(pause && !pause.disabled); pause.click(); await new Promise(setImmediate);
  assert.deepEqual(mutations, ["/report-tasks/B/pause"]);
  assert.equal(chooseAsUser("C"), true); await new Promise(setImmediate);
  pause.click(); await new Promise(setImmediate);
  assert.deepEqual(mutations, ["/report-tasks/B/pause", "/report-tasks/C/pause"]);
  assert.deepEqual(failures, []);
});
