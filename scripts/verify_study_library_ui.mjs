import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { JSDOM } from "jsdom";

const option = (key, fallback) => process.argv.includes(key) ? process.argv[process.argv.indexOf(key) + 1] : fallback;
const base = option("--base-url", "http://127.0.0.1:8000"), output = option("--output", null);
if (!output) throw new Error("--output is required");
const nativeFetch = globalThis.fetch, source = new URL("../modarchitect/web/designer/", import.meta.url);
const snapshot = option("--snapshot-html", null);
const nativeTimeout = globalThis.setTimeout, timers = new Set();
globalThis.setTimeout = (fn, delay, ...args) => { const timer = nativeTimeout(fn, delay, ...args); timers.add(timer); return timer; };
const html = await (await nativeFetch(base + "/designer/")).text();
assert.equal(html, await readFile(new URL("index.html", source), "utf8"));
for (const name of ["studio.js", "research.js", "wizard.js", "modeling.js", "study-library.js", "research-flow.js", "study-settings.js", "agronomic-results.js", "result-views.js", "study-library.css"]) {
  const response = await nativeFetch(base + "/designer/" + name + "?v=studies1");
  assert.equal(response.status, 200); assert.equal(await response.text(), await readFile(new URL(name, source), "utf8"));
}
const dom = new JSDOM(html, { url: base + "/designer/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location,
  history: dom.window.history, localStorage: dom.window.localStorage, Option: dom.window.Option,
  matchMedia: () => ({ matches: false }), ResizeObserver: class { observe() {} } });
document.fonts = { ready: Promise.resolve() };
dom.window.HTMLElement.prototype.scrollIntoView = function () {};
let cookie = "", saved = null, run = null, reopened = false, model = null;
const exchanges = [], pageErrors = [];
dom.window.addEventListener("error", (event) => pageErrors.push(event.message));
globalThis.fetch = async (input, options = {}) => {
  const url = new URL(input, location.href), headers = new Headers(options.headers);
  if (cookie) headers.set("Cookie", cookie);
  const response = await nativeFetch(url, { ...options, headers });
  const set = response.headers.getSetCookie?.() || [];
  if (set.length) cookie = set.map((value) => value.split(";")[0]).join("; ");
  const value = await response.clone().json();
  exchanges.push({ method: options.method || "GET", path: url.pathname, status: response.status });
  if (response.ok) {
    if ((url.pathname.endsWith("/workspace/plans") && options.method === "POST") || (/\/workspace\/plans\/[^/]+$/.test(url.pathname) && options.method === "PUT")) saved = value;
    if (saved && url.pathname === "/api/v1/workspace/plans/" + saved.design_id && (!options.method || options.method === "GET")) reopened = true;
    if (value.run_id && value.status) run = value;
    if (value.model_id && value.model_json) model = value;
  } return response;
};
const id = (name) => document.getElementById(name);
async function until(check, label, timeout = 180000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (check()) return; await new Promise((resolve) => setTimeout(resolve, 80)); }
  throw new Error("Study UI timed out: " + label + " · " + id("workspace-status").textContent + " · " + id("wizard-error").textContent);
}
try {
  await import(new URL("studio.js?live-study-library", source));
  await until(() => id("workspace-status").textContent.includes("个人工作区已连接") && document.querySelectorAll("[data-study-template]").length === 16, "library ready");
  assert.equal(document.querySelector('[data-study-template="survey-658b"]'), null);
  const card = document.querySelector('[data-study-template="crop-low-temperature"]');
  card.querySelectorAll("button")[0].click();
  await until(() => !id("study-template-summary").hidden && id("public-research-flow") && !card.querySelector("button").disabled, "preview graph");
  assert.equal(exchanges.filter((e) => e.method === "POST" && e.path.endsWith("/workspace/plans")).length, 0);
  assert.equal(document.querySelectorAll("#public-research-flow rect").length, 3);
  assert.equal(document.querySelectorAll(".research-stage-card").length, 5);
  assert.equal(document.querySelector(".research-component-flow").open, false);
  assert.equal(id("technical-workspace").hidden, true);
  document.querySelector('[data-stage="select"]').click();
  card.querySelectorAll("button")[1].click();
  await until(() => saved && !id("wizard-save-draft").disabled, "adopt and save");
  const parameter = document.querySelector('[data-study-parameter="as_of"]'); parameter.value = "2026-10-20"; parameter.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  id("wizard-save-draft").click(); await until(() => saved.revision === 2 && !id("wizard-save-draft").disabled, "saved research date");
  const select = id("cloud-plans"); select.value = saved.design_id; select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await until(() => reopened && id("workspace-status").textContent.includes("已打开云端方案") && !id("study-run").disabled, "reopen exact study");
  assert.equal(id("technical-workspace").hidden, true);
  assert.equal(document.querySelector('[data-study-parameter="as_of"]').value, "2026-10-20");
  document.querySelector('[data-stage="review"]').click();
  id("study-run").click();
  await until(() => run?.status === "succeeded" && run.result_json.outputs.report?.format === "research_weather_conditions_v1" && id("run-output").textContent.includes("合格日"), "real independent research execution");
  await until(() => [...id("cloud-runs").options].some((option) => option.value === run.run_id && option.textContent.includes("计算完成")), "terminal run list refreshed");
  assert.ok(run.scheduler_id);
  assert.equal(run.result_json.receipts[0].component.code, "research_weather_conditions");
  assert.equal(run.result_json.outputs.report.as_of, "2026-10-20");
  assert.equal(id("model-save-panel").hidden, true);
  assert.match(document.querySelector('[data-flow-stage="execution"]').textContent, /计算完成/);
  assert.match(document.querySelector('[data-flow-stage="products"]').textContent, /1 项成果/);
  assert.match(document.querySelector('[data-flow-stage="evaluation"]').textContent, /待研究者判断/);
  assert.ok(exchanges.some((entry) => entry.path.endsWith("/check-execution") && entry.status === 200));
  const publicText = ["plan-name", "plan-question", "study-template-summary", "run-status", "run-evidence", "run-output"].map((name) => id(name).textContent).join(" ");
  assert.doesNotMatch(publicText, /658b|冻结|封存|工程验收|SHA-256|制品/);
  assert.equal(exchanges.filter((e) => e.status >= 400).length, 0); assert.deepEqual(pageErrors, []);
  const proof = { service: base, method: "real DOM events, live HTTP and DolphinScheduler", native_browser_visual_check: false,
    preview_did_not_save: true, adopted_and_reopened: true, workflow_visible_by_default: true, public_topics: 16,
    design_id: saved.design_id, run_id: run.run_id, scheduler_id: run.scheduler_id, result_sha256: run.result_sha256,
    edited_date_reopened_and_executed: "2026-10-20", independent_analysis_component: true, researcher_language_verified: true,
    no_fake_predictive_model: true, card_stages: 5, server_preflight_passed: true, real_run_updates_cards: true,
    http_error_count: 0, page_error_count: 0 };
  document.querySelector('[data-stage="select"]').click();
  const chainCard = document.querySelector('[data-study-template="growth-trend-and-environment"]'), previousDesign = saved.design_id;
  chainCard.querySelectorAll("button")[1].click();
  await until(() => saved.design_id !== previousDesign && !id("study-run").disabled, "chain adopted");
  const primary = (code) => document.querySelector('[data-flow-stage="' + code + '"] .research-stage-body > dl');
  assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-headline').textContent, "5 项输入指标");
  assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-description').textContent, "1 张观测表 · 90 条记录");
  assert.match(primary("dataset").textContent, /历史拟合45 条/); assert.match(primary("dataset").textContent, /模型训练25 条/); assert.match(primary("dataset").textContent, /时间留出20 条/);
  assert.equal(document.querySelector(".research-data-branch").dataset.branchSource, "dataset");
  assert.equal(document.querySelector(".research-data-branch").dataset.branchTarget, "evaluation");
  document.querySelector('[data-section="inputs"]').click();
  const configuredNames = [...id("wizard-role-table").querySelectorAll("tr td:first-child")].map((node) => node.textContent);
  const cardNames = [...primary("inputs").querySelectorAll("dt")].map((node) => node.textContent);
  assert.deepEqual(cardNames, configuredNames); assert.equal(cardNames.length, 5);
  assert.ok(!cardNames.includes("历史曲线估计株高"));
  document.querySelector('[data-section="calculation"]').click();
  const cutoff = () => [...id("modeling-settings").querySelectorAll("label.modeling-date")].find((node) => node.textContent.startsWith("最终模型用到哪一天")).querySelector("input");
  const change = (node, value) => { node.value = value; node.dispatchEvent(new dom.window.Event("change", { bubbles: true })); };
  change(cutoff(), "2026-06-08"); assert.match(primary("dataset").textContent, /时间留出21 条/);
  id("wizard-save-draft").click(); await until(() => saved.revision === 2 && !id("wizard-save-draft").disabled, "edited chain saved");
  const chainDesign = saved.design_id;
  reopened = false; select.value = chainDesign; select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await until(() => reopened && !id("study-run").disabled, "chain reopened");
  assert.match(primary("dataset").textContent, /时间留出21 条/);
  change(cutoff(), "2026-06-09"); assert.match(primary("dataset").textContent, /时间留出20 条/);
  document.querySelector('[data-stage="review"]').click(); id("study-run").click();
  await until(() => run?.design_id === chainDesign && run.status === "succeeded", "chain calculation");
  const trained = structuredClone(run), metric = run.result_json.metrics.find((value) => value.target === "height" && value.status === "evaluated");
  assert.equal(metric.rows, 20); assert.equal(metric.expected_rows, 20);
  assert.match(primary("dataset").textContent, /历史拟合45 条/); assert.match(primary("dataset").textContent, /模型训练25 条/);
  assert.match(primary("evaluation").textContent, /20 条配对/);
  id("save-trained-model").click(); await until(() => model?.run_id === trained.run_id && !id("run-prediction").disabled, "chain model saved");
  const states = structuredClone(model.model_json.states);
  id("run-prediction").click();
  await until(() => run?.kind === "predict" && run.status === "succeeded", "chain prediction without refit");
  const predicted = structuredClone(run);
  assert.deepEqual(predicted.result_json.pipeline.states, states);
  assert.ok(predicted.result_json.receipts.every((receipt) => !receipt.component.code.includes("training")));
  assert.equal(document.querySelector('[data-flow-stage="inputs"] .research-stage-headline').textContent, "4 项输入指标");
  assert.equal(document.querySelector(".research-data-branch"), null);
  await until(() => [...id("cloud-runs").options].some((entry) => entry.value === trained.run_id), "training record available");
  id("cloud-runs").value = trained.run_id; id("cloud-runs").dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await until(() => document.querySelector(".research-data-branch") && primary("dataset").textContent.includes("历史拟合45 条"), "returned to exact training flow");
  const face = [...document.querySelectorAll(".research-stage-card > header, .research-stage-body > strong, .research-stage-body > p, .research-stage-body > dl, .research-stage-card > footer")].map((node) => node.textContent).join(" ");
  assert.doesNotMatch(face, /研究概况|建议：|独立地块验证通过|658b|冻结|封存|SHA-256/);
  assert.equal(exchanges.filter((entry) => entry.status >= 400).length, 0); assert.deepEqual(pageErrors, []);
  proof.chain_flow = { design_id: chainDesign, run_id: trained.run_id, scheduler_id: trained.scheduler_id,
    prediction_run_id: predicted.run_id, prediction_scheduler_id: predicted.scheduler_id, model_id: model.model_id,
    indicators: cardNames, data_rows: 90, history_rows: 45, training_rows: 25, holdout_rows: 20,
    edited_holdout_rows_reopened: 21, source: "dataset", target: "evaluation", matched_rows: metric.rows,
    prediction_input_count: 4, same_indicator_list: true, no_refit: true, compact_content: true };
  if (snapshot) {
    const css = await Promise.all([...document.querySelectorAll('link[rel="stylesheet"]')].map(async (link) => (await nativeFetch(link.href)).text()));
    await mkdir(dirname(snapshot), { recursive: true });
    await writeFile(snapshot, '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>研究流程</title><style>' + css.join("\n") + '</style><body style="display:block;margin:0;background:#f5f7f6"><div style="padding:24px">' + id("research-flow-section").outerHTML + '</div></body></html>');
  }
  await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
  console.log("Study library UI acceptance passed", JSON.stringify(proof));
} finally { for (const timer of timers) clearTimeout(timer); globalThis.setTimeout = nativeTimeout; globalThis.fetch = nativeFetch; dom.window.close(); }
