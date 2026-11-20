import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import vm from "node:vm";
import { JSDOM } from "jsdom";

// 以真实 DOM 事件驱动已部署页面；网络不替换成返回固定结果的桩。
const option = (name, fallback) => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : fallback;
const base = option("--base-url", "http://127.0.0.1:8000");
const output = option("--output", null);
const designOnly = process.argv.includes("--design-only");
const thirdParty = process.argv.includes("--third-party");
const methodsOnly = process.argv.includes("--methods-only");
const inventoryOnly = process.argv.includes("--inventory-only");
const calendarOnly = process.argv.includes("--calendar-only");
const verifyModuleLinks = process.argv.includes("--verify-module-links");
const trainingMethod = option("--training-method", "multivariate_linear_training");
const openRun = option("--open-run", null);
const verifyInputProvision = process.argv.includes("--verify-input-provision");
const reopenStudy = option("--reopen-study", null);
const initialSection = option("--initial-section", "basic");
const sessionFile = option("--session-file", null);
if (!output) throw new Error("--output is required");
if (designOnly && !sessionFile) throw new Error("--design-only requires --session-file in a private directory");
if (reopenStudy && !designOnly && !thirdParty && !methodsOnly && !calendarOnly) throw new Error("--reopen-study requires a design or third-party acceptance mode");
if (calendarOnly && (!sessionFile || designOnly || thirdParty || methodsOnly || inventoryOnly)) throw new Error("--calendar-only requires --session-file and cannot combine other modes");
if (methodsOnly && (!sessionFile || designOnly || thirdParty)) throw new Error("--methods-only requires --session-file and cannot combine other modes");
if (openRun && (!thirdParty || !reopenStudy)) throw new Error("--open-run requires --third-party and --reopen-study");
if (verifyInputProvision && !designOnly) throw new Error("--verify-input-provision requires --design-only");
if (thirdParty && (!sessionFile || designOnly)) throw new Error("--third-party requires --session-file and cannot use --design-only");
const nativeFetch = globalThis.fetch;
const source = new URL("../modarchitect/web/designer/", import.meta.url);
const pageResponse = await nativeFetch(base + "/designer/");
const html = await pageResponse.text();
if (verifyModuleLinks) assert.equal(pageResponse.headers.get("cache-control"), "no-cache");
assert.equal(html, await readFile(new URL("index.html", source), "utf8"), "Deployed HTML differs from the acceptance source");
for (const name of ["startup.js", "studio.js", "http-path.js", "wizard.js", "research.js", "study-library.js", "research-flow.js", "flow-overview.js", "study-library.css", "system-inputs.js", "input-provision.js", "observation-curves.js", "continuous-research.js", "source-data.js", "methods.js", "method-picker.js", "schema-fields.js", "request-schema.js", "calendar-axis.js", "research.css", "wizard.css"]) {
  const response = await nativeFetch(base + "/designer/" + name + "?v=wizard1");
  assert.equal(response.status, 200);
  if (verifyModuleLinks) assert.equal(response.headers.get("cache-control"), "no-cache");
  assert.equal(await response.text(), await readFile(new URL(name, source), "utf8"), "Deployed asset differs: " + name);
}
if (verifyModuleLinks) {
  assert.equal(typeof vm.SourceTextModule, "function", "Use node --experimental-vm-modules for HTTP module linking");
  const cache = new Map();
  async function loadModule(url) {
    if (!cache.has(url)) cache.set(url, (async () => {
      const response = await nativeFetch(url); assert.equal(response.status, 200);
      return new vm.SourceTextModule(await response.text(), { identifier: url });
    })());
    return cache.get(url);
  }
  const root = new vm.SourceTextModule('import { requestProperties, variableCandidates } from "./schema-fields.js?v=continuous1"; import "./studio.js?v=loading2";', { identifier: base + "/designer/link-check.js" });
  await root.link((specifier, parent) => loadModule(new URL(specifier, parent.identifier).href));
  console.log("HTTP module linking passed", JSON.stringify({ modules: cache.size, cached_exports_compatible: true }));
}
const pageUrl = new URL(base + "/designer/#select");
if (reopenStudy) { pageUrl.searchParams.set("study", reopenStudy); pageUrl.hash = "configure/" + initialSection; }
const dom = new JSDOM(html, { url: pageUrl.href });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location,
  history: dom.window.history, localStorage: dom.window.localStorage, Option: dom.window.Option,
  matchMedia: () => ({ matches: false }), ResizeObserver: class { observe() {} disconnect() {} } });
document.fonts = { ready: Promise.resolve() };
dom.window.HTMLElement.prototype.scrollIntoView = function () {};
let cookie = "", saved, model, lastRun, readModel;
if (reopenStudy) {
  assert.ok(sessionFile, "Reopening requires a private session file");
  const session = JSON.parse(await readFile(sessionFile, "utf8"));
  assert.equal(session.base, base); cookie = session.cookie;
}
const exchanges = [], runs = new Map(), events = [];
globalThis.fetch = async (input, options = {}) => {
  const url = new URL(input, location.href), headers = new Headers(options.headers);
  const prefix = new URL(base).pathname.replace(/\/$/, "");
  assert.equal(url.origin, new URL(base).origin);
  assert.ok(url.pathname.startsWith(prefix + "/"), "Request escaped the application prefix: " + url.pathname);
  if (cookie) headers.set("Cookie", cookie);
  const response = await nativeFetch(url, { ...options, headers });
  const set = response.headers.getSetCookie?.() || [];
  if (set.length) cookie = set.map((value) => value.split(";")[0]).join("; ");
  const value = await response.clone().json();
  exchanges.push({ method: options.method || "GET", path: url.pathname, status: response.status });
  if (response.ok) {
    if (url.pathname.includes("/workspace/plans/") || (url.pathname.endsWith("/workspace/plans") && options.method === "POST")) saved = value;
    if (url.pathname.endsWith("/workspace/models") && options.method === "POST") model = value;
    if (url.pathname.includes("/workspace/models/")) readModel = value;
    if (value.run_id && value.status) { lastRun = value; runs.set(value.run_id, value); }
  }
  return response;
};
const id = (name) => document.getElementById(name);
function click(name) { const target = id(name); assert.ok(target && !target.disabled, "Control is unavailable: " + name); target.click(); }
function change(target, value) { target.value = value; target.dispatchEvent(new dom.window.Event("change", { bubbles: true })); }
async function until(condition, label, timeout = designOnly ? 15000 : 180000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (condition()) return;
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  throw new Error("UI acceptance timed out: " + label + " · " + id("workspace-status").textContent + " · " + id("wizard-error").textContent + " · " + id("method-message").textContent);
}
function section(name) { document.querySelector('[data-section="' + name + '"]').click(); events.push("configure/" + name); }
async function chooseMethod(code) {
  const selector = '[data-method="' + code + '@1"]';
  await until(() => document.querySelector(selector), "method cards loaded", 15000);
  const card = document.querySelector(selector);
  const name = card.querySelector("strong").textContent;
  card.click();
  assert.equal(id("method-detail").querySelector('input[type="date"]'), null);
  click("apply-method");
  await until(() => !id("method-dialog").open && id("wizard-method").textContent.includes(name), "configured method applied", 15000);
}

try {
  await import(new URL("studio.js?live-wizard-acceptance", source));
  if (calendarOnly) {
    if (reopenStudy) {
      await until(() => saved?.design_id === reopenStudy && id("workspace-status").textContent.includes("已打开云端方案") && !id("cloud-save").disabled, "calendar study reopened", 15000);
      assert.equal(document.querySelector('[data-section="' + initialSection + '"]').getAttribute("aria-current"), "step");
    } else {
      await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "calendar workspace connected", 15000);
      click("empty-example");
      await until(() => saved?.configuration?.definition.composition.nodes.some((node) => node.component.code === "research_calendar_axis") && !id("cloud-save").disabled, "platform calendar example saved", 15000);
    }
    section("inputs");
    assert.ok(document.querySelector('[data-platform-date-axis="platform_calendar_day"]'));
    assert.doesNotMatch(id("wizard-role-table").textContent, /未绑定来源/);
    const plan = saved.configuration.definition;
    assert.ok(plan.collection_requirements.every((requirement) => requirement.catalog_binding));
    assert.ok(!plan.collection_requirements.some((requirement) => requirement.variable_code === "platform_calendar_day"));
    document.querySelector('[data-stage="review"]').click(); click("wizard-check");
    await until(() => !id("wizard-check").disabled && id("wizard-check-result").querySelector(".check-success"), "calendar definition validated by API", 15000);
    assert.equal(exchanges.filter((request) => request.status >= 400).length, 0);
    await mkdir(dirname(sessionFile), { recursive: true }); await writeFile(sessionFile, JSON.stringify({ base, cookie }) + "\n", { mode: 0o600 });
    const proof = { service: base, method: "real DOM and live HTTP", native_browser_visual_check: false, design_id: saved.design_id,
      revision: saved.revision, fresh_page_reopened: Boolean(reopenStudy), initial_section: initialSection, date_source: "platform", external_inputs: plan.collection_requirements.map((item) => item.variable_code),
      definition_valid: true, http_error_count: 0, run_started: false };
    await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
    console.log("Platform calendar UI acceptance passed", JSON.stringify({ design_id: saved.design_id, fresh_page_reopened: Boolean(reopenStudy) }));
  } else if (inventoryOnly) {
    await until(() => id("workspace-status").textContent.includes("个人工作区已连接") && document.querySelectorAll("[data-study-template]").length === 20, "inventory loaded", 15000);
    const listing = await (await globalThis.fetch("/api/v1/workspace/study-templates")).json(), checked = [];
    for (const entry of listing.items) for (const method of entry.method_options || [{ id: entry.id }]) {
      const detail = await (await globalThis.fetch("/api/v1/workspace/study-templates/" + method.id)).json();
      const visibleDetail = (item, host) => {
        const selector = '[data-input-port="' + item.port + '"][data-variable-code="' + item.code + '"]';
        const field = host.querySelector(selector);
        assert.ok(field?.textContent.includes(item.name) && !field.closest("[hidden], details:not([open]), dialog"), "Hidden detail in wizard: " + method.id + ":" + item.code);
      };
      const card = document.querySelector('[data-study-template="' + entry.id + '"]');
      if (card.querySelector("select")) card.querySelector("select").value = method.id;
      card.querySelector("button").click();
      await until(() => id("wizard-name").value === detail.definition.name && id("workspace-status").textContent.includes("正在预览完整流程") && !id("cloud-save").disabled, "preview " + method.id, 15000);
      assert.equal(location.hash, "#configure/inputs", method.id);
      section("inputs");
      assert.ok(id("wizard-role-table").textContent.trim(), "Missing inputs: " + method.id);
      assert.equal(document.querySelector("#wizard-role-table [data-resource-input]"), null);
      for (const item of detail.input_requirements || []) {
        if (item.kind === "input") visibleDetail(item, id("wizard-role-table"));
        const stage = document.querySelector('[data-flow-kind="input"][data-input-code="' + item.port + '"]');
        assert.ok(stage?.textContent.includes(item.name) && stage.textContent.includes(item.use), "Missing detail in flow: " + method.id + ":" + item.code);
      }
      section("targets");
      assert.equal(document.querySelectorAll("#wizard-output-table [data-product]").length, 0);
      for (const outcome of detail.inspection.outputs) {
        const stages = [...document.querySelectorAll('[data-flow-kind="product"]')];
        assert.ok(stages.some((stage) => stage.textContent.includes(outcome.definition.name)), "Missing product in flow: " + method.id + ":" + outcome.definition.name);
      }
      for (const target of (detail.input_requirements || []).filter((item) => item.kind === "target")) visibleDetail(target, id("wizard-output-table"));
      document.querySelector('[data-stage="review"]').click(); click("wizard-check");
      await until(() => !id("wizard-check").disabled && id("wizard-check-result").querySelector(".check-success, .check-issues"), "check " + method.id, 15000);
      assert.ok(id("wizard-check-result").querySelector(".check-success"), id("wizard-check-result").textContent);
      assert.doesNotMatch(id("wizard-review-summary").textContent, /按组件合同|已选择该研究所需的数据/);
      checked.push({ id: method.id, input_ports: detail.definition.composition.inputs.length, input_details: detail.input_requirements?.length || 0, outputs: detail.definition.composition.outputs.length, valid: true });
    }
    assert.equal(checked.length, 22);
    const canopy = document.querySelector('[data-study-template="canopy-temperature-rf"]');
    canopy.querySelector("select").value = "canopy-temperature-rf";
    canopy.querySelectorAll("button")[1].click();
    await until(() => saved?.configuration?.definition.layout.study_template?.id === "canopy-temperature-rf" && !id("cloud-save").disabled, "canopy saved", 15000);
    assert.match(document.querySelector('#wizard-role-table table[aria-label="模型输入"]').textContent, /空气温度/);
    assert.equal(id("open-system-example").hidden, true);
    assert.equal(id("study-input-example").open, false);
    section("targets");
    assert.match(id("wizard-output-table").textContent, /模型输出.*冠层温度.*独立留出预测/);
    const oldPlan = saved;

    document.querySelector('[data-stage="select"]').click();
    const writes = () => exchanges.filter((call) => ["POST", "PUT"].includes(call.method) && call.path.includes("/workspace/plans"));
    const writeCount = writes().length;
    click("wizard-standard-example");
    await until(() => id("workspace-status").textContent.includes("已打开双目标合成示例") && !id("cloud-save").disabled, "new example preview", 15000);
    assert.match(id("wizard-role-table").textContent, /冠层覆盖度.*块茎干物质/);
    assert.equal(new URL(location.href).searchParams.has("study"), false);
    assert.equal(writes().length, writeCount);
    assert.equal(id("open-system-example").hidden, false);
    const exampleUrl = location.href, exampleFlow = id("public-research-flow").innerHTML, previousCalls = exchanges.length;
    click("open-system-example");
    assert.ok(id("study-input-example").open);
    assert.match(id("study-input-example-content").textContent, /合成示例值.*块茎干物质/);
    click("close-study-input-example");
    await new Promise(setImmediate);
    assert.equal(exchanges.length, previousCalls);
    assert.equal(location.href, exampleUrl);
    assert.equal(id("public-research-flow").innerHTML, exampleFlow);
    const original = await (await globalThis.fetch("/api/v1/workspace/plans/" + oldPlan.design_id)).json();
    assert.equal(original.revision, oldPlan.revision);
    assert.deepEqual(original.configuration.definition, oldPlan.configuration.definition);
    click("cloud-save");
    await until(() => saved?.design_id !== oldPlan.design_id && !id("cloud-save").disabled, "independent sample saved on request", 15000);
    assert.equal(writes().length, writeCount + 1);
    assert.equal(saved.configuration.definition.composition.nodes[0].component.code, "multivariate_linear_training");

    click("new-plan"); document.querySelector('[data-stage="review"]').click(); click("wizard-check");
    await until(() => !id("wizard-check").disabled && id("wizard-check-result").querySelector(".check-issues"), "blank custom rejected", 15000);
    assert.equal(id("wizard-check-result").querySelector(".check-success"), null);
    document.querySelector('[data-study-template="soil-weather-lai"] button').click();
    await until(() => location.hash === "#configure/inputs" && id("workspace-status").textContent.includes("正在预览完整流程") && !id("cloud-save").disabled, "catalog-bound example ready", 15000);
    section("calculation");
    click("choose-method");
    await chooseMethod("historical_logistic_training");
    document.querySelector('[data-stage="review"]').click(); click("wizard-check");
    await until(() => !id("wizard-check").disabled && id("wizard-check-result").querySelector(".check-success"), "logistic full API check", 15000);
    const proof = { service: base, method: "real DOM and live HTTP", native_browser_visual_check: false, checked_templates: checked, catalog_models: 5, canopy_inputs_and_outputs_visible: true, preview_kept_plan_and_flow: true, independent_sample_requires_explicit_save: true, blank_custom_rejected: true, logistic_valid_day_applied: true, run_started: false };
    await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
    console.log("Designer inventory acceptance passed", JSON.stringify({ templates: checked.length, models: 5, blank_custom_rejected: true, logistic_applied: true }));
  } else if (methodsOnly) {
    if (!reopenStudy) {
      await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "workspace connected");
      document.querySelector('[data-study-template="soil-weather-lai"] button').click();
      await until(() => id("workspace-status").textContent.includes("正在预览完整流程") && !id("cloud-save").disabled, "research example adopted", 15000);
      section("calculation"); click("choose-method");
      await until(() => document.querySelectorAll("[data-method]").length === 5, "reviewed methods listed", 15000);
      const methods = [...document.querySelectorAll("[data-method]")].map((card) => card.dataset.method);
      for (const name of ["multivariate_linear", "historical_logistic", "random_forest", "xgboost", "gaussian_process"]) assert.ok(methods.includes(name + "_training@1"), "Missing method from catalog: " + name);
      await chooseMethod("historical_logistic_training");
      change(id("wizard-name"), "生长曲线研究（方法配置验证）"); click("cloud-save");
      await until(() => saved?.configuration?.definition.composition.nodes.some((node) => node.component.code === "historical_logistic_training") && !id("cloud-save").disabled, "replaced model saved");
      await mkdir(dirname(sessionFile), { recursive: true }); await writeFile(sessionFile, JSON.stringify({ base, cookie })+"\n", { mode: 0o600 });
    } else {
      await until(() => saved?.design_id === reopenStudy && id("workspace-status").textContent.includes("已打开云端方案") && !id("cloud-save").disabled, "new page reopened configured method");
    }
    const plan = saved.configuration.definition;
    const trained = plan.composition.nodes.find((node) => node.component.code === "historical_logistic_training");
    assert.ok(trained);
    assert.deepEqual(plan.evaluation.target_codes, ["lai"]);
    assert.match(id("wizard-method-state").textContent, /运行待启用/);
    await until(() => id("research-inspection").querySelector("[data-inspection-node]") && !id("research-inspection").hasAttribute("aria-busy"), "method preview settled", 15000);
    const proof = { service: base, method: "real DOM events and live server structure validation", native_browser_visual_check: false, engineering_demo_only: true, fresh_page: Boolean(reopenStudy), design_id: saved.design_id, revision: saved.revision, selected_component: trained.component, output_ports: plan.composition.outputs.map((item) => item.source.port), target_codes: plan.evaluation.target_codes, runtime_enabled: false, run_started: false, configuration_sha256: saved.configuration_sha256, http_error_count: exchanges.filter((item) => item.status >= 400).length };
    assert.equal(proof.http_error_count, 0); await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2)+"\n");
    console.log("Method selection acceptance passed", JSON.stringify({ design_id: saved.design_id, component: proof.selected_component, fresh_page: Boolean(reopenStudy) }));
  } else if (thirdParty && reopenStudy) {
    await until(() => saved?.design_id === reopenStudy && id("workspace-status").textContent.includes("已打开云端方案"), "fresh page reopened third-party plan");
    assert.match(id("data-summary").textContent, /平台来源资料/);
    const sourceSnapshotIds = saved.source_snapshot_ids; assert.equal(sourceSnapshotIds.length, 1);
    document.querySelector('[data-stage="review"]').click();
    await until(() => [...id("cloud-runs").options].some((option) => option.value === openRun), "persisted run listed");
    change(id("cloud-runs"), openRun);
    await until(() => lastRun?.run_id === openRun && document.querySelectorAll("#run-curves circle").length === 7, "persisted result and curve reopened");
    await until(() => [...id("cloud-runs").options].some((option) => option.value === openRun && option.textContent.includes("计算完成")), "reopened terminal run refreshed");
    await until(() => !id("cloud-save").disabled, "reopened run finished its page update");
    assert.match(id("run-output").textContent, /参考阈值/); assert.equal(id("model-save-panel").hidden, true);
    const proof = { service: base, method: "new page with persisted cookie, real DOM and live HTTP", fresh_page: true, native_browser_visual_check: false, design_id: reopenStudy, run_id: openRun, scheduler_id: lastRun.scheduler_id, source_snapshot_ids: sourceSnapshotIds, curve_points: 7, report_visible: true, new_run_created: false, http_error_count: exchanges.filter((item) => item.status >= 400).length };
    assert.equal(proof.http_error_count, 0);
    change(id("wizard-name"), "修改后的研究草稿"); assert.equal(document.querySelectorAll("#run-curves circle").length, 0);
    proof.edited_draft_clears_old_curve = true;
    await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
    console.log("Third-party result reopen passed", JSON.stringify({ design_id: reopenStudy, run_id: openRun }));
  } else if (thirdParty) {
    await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "workspace connected");
    await until(() => document.querySelector('[data-study-template="crop-high-temperature"]'), "weather study available");
    document.querySelector('[data-study-template="crop-high-temperature"] button').click();
    await until(() => id("wizard-name").value === "作物高温暴露条件分析", "weather study adopted");
    change(id("wizard-name"), "参考位置七日高温条件分析");
    section("sources");
    const form = document.querySelector("#source-data-panel form");
    for (const [name, value] of Object.entries({ field_ref: "weather-reference-ui", crop_code: "potato", season_ref: "2026", start_date: "2026-07-01", end_date: "2026-07-07", latitude: "50.46", longitude: "119.85" })) form.elements.namedItem(name).value = value;
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    await until(() => id("source-data-panel").textContent.includes("已采用 7 条"), "live third-party records adopted");
    assert.doesNotMatch(id("source-data-panel").textContent, /实测目标仍需提供/);
    const previousRevision = saved?.revision || 0;
    click("cloud-save"); await until(() => saved?.design_id && saved.revision > previousRevision && !id("cloud-save").disabled, "third-party plan saved");
    const designId = saved.design_id; change(id("cloud-plans"), designId);
    await until(() => id("workspace-status").textContent.includes("已打开云端方案") && id("data-summary").textContent.includes("7 条"), "third-party plan reopened");
    const sourceSnapshotIds = saved.source_snapshot_ids; assert.equal(sourceSnapshotIds.length, 1);
    assert.match(id("data-summary").textContent, /平台来源资料/); assert.doesNotMatch(id("data-summary").textContent, /实测记录/);
    document.querySelector('[data-stage="review"]').click();
    click("study-run");
    await until(() => lastRun?.kind === "analyze" && lastRun.status === "succeeded", "real weather analysis succeeded");
    await until(() => id("run-output").textContent.includes("参考阈值"), "weather report displayed");
    assert.equal(id("model-save-panel").hidden, true);
    assert.equal(document.querySelectorAll("#run-curves svg circle").length, 7);
    await until(() => [...id("cloud-runs").options].some((option) => option.value === lastRun.run_id && option.textContent.includes("计算完成")), "terminal run refreshed before closing page");
    assert.equal(exchanges.filter((item) => item.status >= 400).length, 0);
    await mkdir(dirname(sessionFile), { recursive: true }); await writeFile(sessionFile, JSON.stringify({ base, cookie }) + "\n", { mode: 0o600 });
    const proof = { service: base, method: "real DOM events with live third-party provider and DolphinScheduler", native_browser_visual_check: false, design_id: designId, run_id: lastRun.run_id, scheduler_id: lastRun.scheduler_id, operation: lastRun.kind, source_snapshot_ids: sourceSnapshotIds, source_rows: 7, curve_points: 7, report_visible: true, model_save_hidden: true, http_error_count: 0, exchanges };
    await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
    console.log("Third-party designer acceptance passed", JSON.stringify({ design_id: designId, run_id: lastRun.run_id, scheduler_id: lastRun.scheduler_id }));
  } else if (designOnly) {
    const planName = "生长趋势研究（页面验证）";
    if (!reopenStudy) {
      await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "workspace connected");
      await until(() => document.querySelectorAll(".study-template-card").length === 20, "study library loaded");
      const card = document.querySelector('[data-study-template="crop-growth-prediction"]');
      assert.ok(card); card.querySelector("button").click();
      await until(() => id("workspace-status").textContent.includes("正在预览完整流程") && !id("cloud-save").disabled, "template preview");
      assert.ok(document.querySelectorAll(".research-stage-card").length > 0 || id("public-research-flow").children.length > 0);
      if (verifyInputProvision) {
        section("inputs"); click("open-indicator-library");
        document.querySelector('[data-category="platform_analysis"]').click();
        assert.match(document.querySelector('[data-category="platform_analysis"]').textContent, /已登记 21.*可添加 21/);
        for (const input of document.querySelectorAll(".input-catalog-card")) {
          assert.equal(input.querySelector("button").textContent, "添加为模型输入");
          assert.equal(input.querySelector("button").disabled, false);
          assert.equal(input.querySelectorAll("select").length, 0);
        }
        document.querySelector('[data-category="third_party"]').click();
        const weather = [...document.querySelectorAll(".input-catalog-card")].find((input) => input.querySelector("h3").textContent === "日最低气温");
        assert.ok(weather && !weather.querySelector("button").disabled); weather.querySelector("button").click();
        await until(() => id("wizard-role-table").textContent.includes("日最低气温"), "added weather input");
        click("close-indicator-library");
        events.push("inputs/pending-source-explained", "inputs/add-weather");
      }
      change(id("wizard-name"), planName); click("cloud-save");
      await until(() => saved?.design_id && !id("cloud-save").disabled, "saved design");
      events.push("library/preview", "design/edit", "design/save");
      assert.ok(sessionFile, "Design acceptance requires a private session file");
      await mkdir(dirname(sessionFile), { recursive: true });
      await writeFile(sessionFile, JSON.stringify({ base, cookie }) + "\n", { mode: 0o600 });
    } else {
      await until(() => saved?.design_id === reopenStudy && id("workspace-status").textContent.includes("已打开云端方案"), "fresh page reopened saved design");
      assert.equal(id("wizard-name").value, planName);
      assert.equal(saved.configuration.definition.name, planName);
      events.push("new-page/reopen");
    }
    section("inputs");
    assert.equal(document.querySelector('[data-wizard-section="inputs"]').hidden, false);
    assert.equal(document.querySelector('[data-wizard-section="targets"]').hidden, true);
    assert.equal(id("wizard-role-table").closest('[data-wizard-section]').dataset.wizardSection, "inputs");
    assert.equal(id("wizard-output-table").closest('[data-wizard-section]').dataset.wizardSection, "targets");
    click("open-indicator-library");
    assert.equal(document.querySelectorAll('.input-catalog-card [data-input-role="target"]').length, 0);
    click("close-indicator-library"); click("wizard-next");
    assert.equal(location.hash, "#configure/targets");
    assert.equal(document.querySelector('[data-wizard-section="inputs"]').hidden, true);
    assert.equal(document.querySelector('[data-wizard-section="targets"]').hidden, false);
    click("open-output-library");
    assert.equal(document.querySelectorAll('.input-catalog-card [data-input-role="covariate"]').length, 0);
    document.querySelector('[data-category="manual"]').click();
    assert.ok([...document.querySelectorAll('.input-catalog-card button:disabled')].some((button) => button.textContent.includes("已选为研究资料")), "Existing input must be disabled in the target step");
    click("close-indicator-library");
    events.push("inputs/separate-page", "targets/separate-page", "catalog/step-scoped-adoption");
    const overlap = structuredClone(saved.configuration.definition); overlap.schema_version = "1.5";
    const overlapRequest = Object.values(overlap.input_recipes).find((recipe) => recipe.kind === "configuration" && recipe.value?.features && recipe.value?.targets);
    overlapRequest.value.features.push(overlapRequest.value.targets[0]);
    const overlapResponse = await globalThis.fetch(new URL("./validate", location.href), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(overlap) });
    const overlapResult = await overlapResponse.json();
    assert.equal(overlapResult.check.valid, false);
    assert.equal(overlapResult.check.issues[0].type, "input_target_overlap");
    events.push("catalog/duplicate-disabled", "api/reject-input-target-overlap");
    if (verifyInputProvision) {
      const row = (name) => [...document.querySelectorAll("#wizard-role-table tr, #wizard-output-table tr")].find((line) => line.querySelector("td")?.textContent === name);
      assert.match(row("叶面积指数").textContent, /人工采集.*填写或导入/);
      assert.match(row("日最低气温").textContent, /气象.*Open-Meteo.*平台采集/);
      const requirement = saved.configuration.definition.collection_requirements.find((r) => r.variable_code === "temperature_minimum_daily");
      assert.equal(requirement.source, "third_party"); assert.ok(requirement.catalog_binding.contract_sha256);
      assert.ok(Object.values(saved.configuration.definition.input_recipes).some((recipe) => recipe.kind === "configuration" && recipe.value.features?.includes("temperature_minimum_daily")), "Added factor must be bound to actual model parameters");
      events.push("inputs/source-and-binding-preserved");
    }
    let exported, filename;
    const createObjectURL = URL.createObjectURL, anchorClick = dom.window.HTMLAnchorElement.prototype.click;
    try {
      URL.createObjectURL = (blob) => { exported = blob; return createObjectURL(blob); };
      dom.window.HTMLAnchorElement.prototype.click = function () { filename = this.download; };
      click("export-plan"); await until(() => exported && filename, "exported configuration");
      const configuration = JSON.parse(await exported.text());
      assert.equal(configuration.definition.name, planName); assert.ok(filename.endsWith(".json"));
      const imported = await globalThis.fetch(new URL("./import", location.href), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(configuration),
      });
      assert.equal(imported.status, 200); assert.deepEqual((await imported.json()).configuration, configuration);
      events.push("configuration/export-and-import");
    } finally { URL.createObjectURL = createObjectURL; dom.window.HTMLAnchorElement.prototype.click = anchorClick; }
    assert.equal(exchanges.filter((request) => request.status >= 400).length, 0);
    const proof = { service: base, method: "real DOM events with live HTTP", native_browser_visual_check: false,
      design_id: saved.design_id, revision: saved.revision, configuration_sha256: saved.configuration_sha256,
      template_count: document.querySelectorAll(".study-template-card").length, fresh_page: Boolean(reopenStudy),
      events, http_error_count: 0, exchanges };
    await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
    console.log("Designer access acceptance passed", JSON.stringify({ design_id: saved.design_id, revision: saved.revision, fresh_page: Boolean(reopenStudy) }));
  } else {
  await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "workspace connected");
  if (process.argv.includes("--training-method")) {
    click("wizard-standard-example");
    await until(() => id("workspace-status").textContent.includes("已打开双目标合成示例") && !id("cloud-save").disabled, "explicit new synthetic example");
    click("cloud-save");
    await until(() => saved?.design_id && id("data-summary").textContent.includes("60 条") && !id("cloud-save").disabled, "explicit synthetic standard-input example");
    change(id("wizard-name"), "原型界面：标准指标双目标工程验收");
    section("calculation"); click("choose-method");
  } else {
  click("select-model-next"); events.push("select/model");
  change(id("wizard-name"), "原型界面：标准指标双目标工程验收");
  change(id("wizard-question"), "研究冠层覆盖度、块茎干物质与叶面积指数、地上生物量的预测关系（构造数据工程验收）");
  click("wizard-next"); events.push("configure/inputs");
  for (const [page, opener, role, indicators] of [
    ["inputs", "open-indicator-library", "covariate", [["冠层覆盖度", "canopy_cover"], ["块茎干物质", "tuber_dm_kg_ha"]]],
    ["targets", "open-output-library", "target", [["叶面积指数", "lai"], ["地上生物量", "agb_kg_ha"]]],
  ]) {
    section(page); click(opener);
    for (const [name, code] of indicators) {
      const card = [...document.querySelectorAll(".input-catalog-card")].find((element) => element.querySelector("h3").textContent === name);
      assert.ok(card, "Missing catalog indicator: " + name);
      card.querySelector('[data-input-role="' + role + '"]').click();
      await until(() => document.querySelector('[data-variable-code="' + code + '"]'), "adopted indicator " + code);
    }
    click("close-indicator-library");
  }
  assert.equal(document.querySelectorAll("#wizard-role-table tbody tr, #wizard-output-table tbody tr").length, 4);
  section("sources");
  const study = JSON.parse(await readFile(new URL("system-study.json", source), "utf8"));
  Object.defineProperty(id("observation-file"), "files", { configurable: true, value: [{ size: 100000, text: async () => JSON.stringify(study.observations) }] });
  id("observation-file").dispatchEvent(new dom.window.Event("change"));
  await until(() => id("data-summary").textContent.includes("60 条") && !id("wizard-save-draft").disabled, "uploaded engineering observations");
  section("calculation");
  click("choose-method");
  }
  await chooseMethod(trainingMethod);
  click("wizard-next"); events.push("review/check");
  assert.equal(location.hash, "#review");
  change(id("wizard-success"), "以日期留出观测分别核对两个目标；本次构造数据仅验证工程闭环。");
  click("wizard-check"); await until(() => document.querySelector(".check-success"), "server compilation");
  click("wizard-save-draft");
  await until(() => saved?.design_id && !id("wizard-save-draft").disabled, "saved plan");
  const savedId = saved.design_id;
  change(id("cloud-plans"), savedId);
  await until(() => id("workspace-status").textContent.includes("已打开云端方案") && !id("study-run").disabled, "reopened persisted plan");
  assert.equal(id("wizard-name").value, "原型界面：标准指标双目标工程验收");
  click("study-run");
  await until(() => lastRun?.kind === "train" && lastRun.status === "succeeded" && !id("model-save-panel").hidden, "trained via DolphinScheduler");
  const training = structuredClone(lastRun);
  if (process.argv.includes("--training-method")) assert.equal(training.result_json.data_kind, "synthetic");
  assert.ok(training.scheduler_id);
  assert.equal(training.result_json.metrics.length, 2);
  assert.ok(training.result_json.metrics.every((metric) => Number.isFinite(metric.rmse)));
  if (trainingMethod === "multivariate_linear_training") assert.ok(training.result_json.metrics.every((metric) => metric.rmse < 0.0001));
  const published = saved.configuration.definition;
  assert.ok(published.collection_requirements.every((requirement) => requirement.catalog_binding));
  const request = Object.values(published.input_recipes).find((recipe) => recipe.kind === "configuration").value;
  assert.deepEqual(new Set(request.targets), new Set(["lai", "agb_kg_ha"]));
  assert.deepEqual(new Set(request.features), new Set(["canopy_cover", "tuber_dm_kg_ha"]));
  change(id("trained-model-name"), "原型界面双目标候选模型（工程验收）"); click("save-trained-model");
  await until(() => model?.model_id && !id("prediction-panel").hidden && !id("run-prediction").disabled, "saved reusable model");
  const modelSha = model.model_sha256, states = structuredClone(model.model_json.states);
  const form = id("prediction-form");
  change(form.elements.namedItem("business_date"), "2026-06-02");
  change(form.elements.namedItem("canopy_cover"), "0.5"); change(form.elements.namedItem("tuber_dm_kg_ha"), "1600");
  assert.equal(form.elements.namedItem("lai"), null); assert.equal(form.elements.namedItem("agb_kg_ha"), null);
  click("run-prediction"); events.push("model/predict");
  await until(() => lastRun?.kind === "predict" && lastRun.status === "succeeded", "prediction without refit");
  const prediction = structuredClone(lastRun);
  assert.deepEqual(prediction.result_json.pipeline.states, states);
  assert.ok(prediction.result_json.receipts.every((receipt) => !receipt.component.code.includes("training")));
  const values = prediction.result_json.outputs.predictions.rows[0].values;
  assert.ok(Object.values(values).every(Number.isFinite));
  if (trainingMethod === "multivariate_linear_training") { assert.ok(Math.abs(values.lai - 2.48) < 0.0001); assert.ok(Math.abs(values.agb_kg_ha - 4000) < 0.0001); }
  await until(() => [...id("cloud-models").options].some((option) => option.value === model.model_id), "model list refreshed");
  change(id("cloud-models"), model.model_id);
  await until(() => readModel?.model_id === model.model_id, "reopened exact model");
  assert.equal(readModel.model_sha256, modelSha);
  await until(() => !id("cloud-save").disabled && [...id("cloud-runs").options].some((item) => item.value === prediction.run_id && item.textContent.includes("计算完成")), "terminal run refreshed before closing");
  if (sessionFile) { await mkdir(dirname(sessionFile), { recursive: true }); await writeFile(sessionFile, JSON.stringify({ base, cookie }) + "\n", { mode: 0o600 }); }
  assert.equal(exchanges.filter((request) => request.status >= 400).length, 0);
  const proof = { service: base, method: "real DOM events with live HTTP and DolphinScheduler", native_browser_visual_check: false,
    engineering_fixture_only: true, events, design_id: savedId, training_run_id: training.run_id,
    training_scheduler_id: training.scheduler_id, prediction_run_id: prediction.run_id, prediction_scheduler_id: prediction.scheduler_id,
    model_id: model.model_id, model_sha256: modelSha, training_method: trainingMethod, metrics: training.result_json.metrics, expected_prediction: trainingMethod === "multivariate_linear_training" ? { lai: 2.48, agb_kg_ha: 4000 } : null, actual_prediction: values,
    state_unchanged: true, no_refit: true, reopened_plan: true, reopened_model: true, http_error_count: 0 };
  await mkdir(dirname(output), { recursive: true }); await writeFile(output, JSON.stringify(proof, null, 2) + "\n");
  console.log("Designer UI acceptance passed", JSON.stringify({ design_id: savedId, scheduler_ids: [training.scheduler_id, prediction.scheduler_id], model_id: model.model_id }));
  }
} finally { globalThis.fetch = nativeFetch; dom.window.close(); }
