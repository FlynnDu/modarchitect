import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { JSDOM } from "jsdom";

// 以真实 DOM 事件驱动已部署页面；网络不替换成返回固定结果的桩。
const option = (name, fallback) => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : fallback;
const base = option("--base-url", "http://192.168.3.249:18925");
const output = option("--output", null);
const designOnly = process.argv.includes("--design-only");
const thirdParty = process.argv.includes("--third-party");
const methodsOnly = process.argv.includes("--methods-only");
const trainingMethod = option("--training-method", "multivariate_linear_training");
const openRun = option("--open-run", null);
const verifyInputProvision = process.argv.includes("--verify-input-provision");
const reopenStudy = option("--reopen-study", null);
const sessionFile = option("--session-file", null);
if (!output) throw new Error("--output is required");
if (designOnly && !sessionFile) throw new Error("--design-only requires --session-file in a private directory");
if (reopenStudy && !designOnly && !thirdParty && !methodsOnly) throw new Error("--reopen-study requires a design or third-party acceptance mode");
if (methodsOnly && (!sessionFile || designOnly || thirdParty)) throw new Error("--methods-only requires --session-file and cannot combine other modes");
if (openRun && (!thirdParty || !reopenStudy)) throw new Error("--open-run requires --third-party and --reopen-study");
if (verifyInputProvision && !designOnly) throw new Error("--verify-input-provision requires --design-only");
if (thirdParty && (!sessionFile || designOnly)) throw new Error("--third-party requires --session-file and cannot use --design-only");
const nativeFetch = globalThis.fetch;
const source = new URL("../modarchitect/web/designer/", import.meta.url);
const html = await (await nativeFetch(base + "/designer/")).text();
assert.equal(html, await readFile(new URL("index.html", source), "utf8"), "Deployed HTML differs from the acceptance source");
for (const name of ["studio.js", "http-path.js", "wizard.js", "research.js", "study-library.js", "system-inputs.js", "input-provision.js", "observation-curves.js", "continuous-research.js", "source-data.js", "methods.js", "method-picker.js", "schema-fields.js", "research.css", "wizard.css"]) {
  const response = await nativeFetch(base + "/designer/" + name + "?v=wizard1");
  assert.equal(response.status, 200);
  assert.equal(await response.text(), await readFile(new URL(name, source), "utf8"), "Deployed asset differs: " + name);
}
const pageUrl = new URL(base + "/designer/#select");
if (reopenStudy) { pageUrl.searchParams.set("study", reopenStudy); pageUrl.hash = "configure/basic"; }
const dom = new JSDOM(html, { url: pageUrl.href });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location,
  history: dom.window.history, localStorage: dom.window.localStorage, Option: dom.window.Option,
  matchMedia: () => ({ matches: false }), ResizeObserver: class { observe() {} } });
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
  throw new Error("UI acceptance timed out: " + label + " · " + id("workspace-status").textContent + " · " + id("wizard-error").textContent);
}
function section(name) { document.querySelector('[data-section="' + name + '"]').click(); events.push("configure/" + name); }

try {
  await import(new URL("studio.js?live-wizard-acceptance", source));
  if (methodsOnly) {
    if (!reopenStudy) {
      await until(() => id("workspace-status").textContent.includes("个人工作区已连接"), "workspace connected");
      click("select-model-next"); section("calculation"); click("start-direct");
      await until(() => saved?.design_id && !id("cloud-save").disabled, "editable engineering example adopted");
      click("choose-method");
      const methods = [...document.querySelectorAll("[data-method]")].map((card) => card.dataset.method);
      for (const name of ["random_forest", "xgboost", "gaussian_process", "lstm", "convlstm"]) assert.ok(methods.includes(name+"@1"), "Missing method from catalog: " + name);
      document.querySelector('[data-defer-method="random_forest@1"]').click();
      assert.match(id("method-detail").textContent, /待接入输入/); assert.equal(id("apply-method").disabled, false);
      document.querySelector('[data-method="historical_logistic_training@1"] button').click();
      assert.equal(id("apply-method").disabled, false); click("apply-method");
      await until(() => !id("method-dialog").open && id("wizard-method").textContent.includes("历史曲线训练"), "actual component replaced");
      change(id("wizard-name"), "生长曲线研究（方法配置验证）"); click("cloud-save");
      await until(() => saved?.configuration?.definition.composition.nodes[0].component.code === "historical_logistic_training" && !id("cloud-save").disabled, "replaced model saved");
      await mkdir(dirname(sessionFile), { recursive: true }); await writeFile(sessionFile, JSON.stringify({ base, cookie })+"\n", { mode: 0o600 });
    } else {
      await until(() => saved?.design_id === reopenStudy && id("workspace-status").textContent.includes("已打开云端方案") && !id("cloud-save").disabled, "new page reopened configured method");
    }
    const plan = saved.configuration.definition;
    assert.equal(plan.composition.nodes[0].component.code, "historical_logistic_training");
    assert.deepEqual(plan.evaluation.target_codes, ["height"]);
    assert.match(id("wizard-method-state").textContent, /运行待启用/);
    const proof = { service: base, method: "real DOM events and live server structure validation", native_browser_visual_check: false, engineering_demo_only: true, fresh_page: Boolean(reopenStudy), design_id: saved.design_id, revision: saved.revision, selected_component: plan.composition.nodes[0].component, output_ports: plan.composition.outputs.map((item) => item.source.port), target_codes: plan.evaluation.target_codes, runtime_enabled: false, run_started: false, configuration_sha256: saved.configuration_sha256, http_error_count: exchanges.filter((item) => item.status >= 400).length };
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
        click("open-indicator-library");
        document.querySelector('[data-category="platform_analysis"]').click();
        assert.match(document.querySelector('[data-category="platform_analysis"]').textContent, /已登记 21.*可添加 21/);
        for (const input of document.querySelectorAll(".input-catalog-card")) {
          assert.equal(input.querySelector("button").textContent, "加入研究输入");
          assert.equal(input.querySelector("button").disabled, false);
          assert.equal(input.querySelectorAll("select").length, 1);
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
    if (verifyInputProvision) {
      const row = (name) => [...id("wizard-role-table").querySelectorAll("tr")].find((line) => line.querySelector("td")?.textContent === name);
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
    click("select-model-next"); click("open-system-example");
    await until(() => saved?.design_id && id("data-summary").textContent.includes("60 条") && !id("cloud-save").disabled, "explicit synthetic standard-input example");
    change(id("wizard-name"), "原型界面：标准指标双目标工程验收");
    section("calculation"); click("choose-method");
  } else {
  click("select-model-next"); events.push("select/model");
  change(id("wizard-name"), "原型界面：标准指标双目标工程验收");
  change(id("wizard-question"), "研究冠层覆盖度、块茎干物质与叶面积指数、地上生物量的预测关系（构造数据工程验收）");
  click("wizard-next"); events.push("configure/inputs");
  click("open-indicator-library");
  for (const [name, code, role] of [["叶面积指数", "lai", "target"], ["地上生物量", "agb_kg_ha", "target"], ["冠层覆盖度", "canopy_cover", "covariate"], ["块茎干物质", "tuber_dm_kg_ha", "covariate"]]) {
    const card = [...document.querySelectorAll(".input-catalog-card")].find((element) => element.querySelector("h3").textContent === name);
    assert.ok(card, "Missing catalog indicator: " + name);
    card.querySelector("select").value = role;
    card.querySelector("button").click();
    await until(() => document.querySelector('[data-variable-role="' + code + '"]'), "adopted indicator " + code);
  }
  click("close-indicator-library");
  assert.equal(document.querySelectorAll("#wizard-role-table tr").length, 5);
  section("sources");
  const study = JSON.parse(await readFile(new URL("system-study.json", source), "utf8"));
  Object.defineProperty(id("observation-file"), "files", { configurable: true, value: [{ size: 100000, text: async () => JSON.stringify(study.observations) }] });
  id("observation-file").dispatchEvent(new dom.window.Event("change"));
  await until(() => id("data-summary").textContent.includes("60 条") && !id("wizard-save-draft").disabled, "uploaded engineering observations");
  section("calculation");
  change(id("input-training-end"), "2026-05-10"); click("build-input-model");
  }
  await until(() => id("method-dialog").open, "method picker opened");
  const chosenCard = document.querySelector('[data-method="' + trainingMethod + '@1"]');
  const chosenName = chosenCard.querySelector("strong").textContent;
  chosenCard.querySelector("button").click();
  assert.equal(id("apply-method").disabled, false); click("apply-method");
  await until(() => !id("method-dialog").open && id("wizard-method").textContent.includes(chosenName) && document.querySelectorAll("#modeling-flow > li").length === 1, "built actual model");
  assert.equal(id("input-training-end").disabled, true);
  section("outputs");
  assert.equal(document.querySelectorAll("#wizard-products .product-row").length, 2);
  change(id("wizard-success"), "以日期留出观测分别核对两个目标；本次构造数据仅验证工程闭环。");
  click("wizard-next"); events.push("review/check");
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
