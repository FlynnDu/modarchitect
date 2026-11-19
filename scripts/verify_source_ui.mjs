import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { JSDOM } from "jsdom";
import { mountSourceData } from "../modarchitect/web/designer/source-data.js";

const base = process.env.MODARCHITECT_UI_BASE || "http://127.0.0.1:8000";
const output = process.env.MODARCHITECT_SOURCE_UI_PROOF || ".ops/source-ui-proof.json";
let cookie = "";
const exchanges = [];
async function api(path, { method = "GET", body } = {}) {
  const headers = { "X-Workspace-Request": "1" };
  if (cookie) headers.Cookie = cookie;
  if (body) { headers["Content-Type"] = "application/json"; headers["Idempotency-Key"] = randomUUID(); }
  const response = await fetch(base + (path.startsWith("/api/") ? path : "/api/v1/workspace" + path), { method, headers, body: body ? JSON.stringify(body) : undefined });
  const set = response.headers.getSetCookie?.() || [];
  if (set.length) cookie = set.map((s) => s.split(";")[0]).join("; ");
  const value = await response.json();
  exchanges.push({ method, path, status: response.status });
  assert.ok(response.ok, path + ": " + response.status + " " + JSON.stringify(value));
  return value;
}
await api("/session");
const html = await (await fetch(base + "/designer/")).text();
assert.equal(await (await fetch(base + "/designer/source-data.js?v=source1")).text(), await readFile(new URL("../modarchitect/web/designer/source-data.js", import.meta.url), "utf8"));
const plan = (await api("/examples/system")).definition;
const configurations = await Promise.all([
  api("/api/v1/model-center/research-inputs/configure", { method: "POST", body: { key: "sampling_indicator:lai@1.0.0", selectors: {}, role: "target" } }),
  api("/api/v1/model-center/research-inputs/configure", { method: "POST", body: { key: "variable_source:temperature_mean_daily@1.0.0", selectors: {}, role: "covariate" } }),
]);
plan.name = "平台资料采集交互验收";
plan.variables = configurations.map((c) => c.variable); plan.collection_requirements = configurations.map((c) => c.requirement);
plan.input_recipes.observations.variable_codes = plan.variables.map((v) => v.code);
plan.input_recipes.regression_config.value = { features: ["temperature_mean_daily"], targets: ["lai"], training_end: "2025-04-20" };
plan.evaluation.target_codes = ["lai"];
const object = { field_ref: "source-ui-reference", crop_code: "potato", season_ref: "2025" };
let table = { columns: [{ code: "lai", name: configurations[0].variable.name, unit: configurations[0].variable.unit, value_kind: "observed" }],
  rows: Array.from({ length: 30 }, (_, i) => ({ object, business_date: "2025-04-" + String(i + 1).padStart(2, "0"), values: { lai: 1.5 } })) };
let saved, adopted, issue;
const dom = new JSDOM(html, { url: base + "/designer/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document });
const view = mountSourceData({ api, getDefinition: () => plan, getData: () => table, getDataKind: () => "user_supplied",
  async saveDefinition() { saved = await api("/plans", { method: "POST", body: { definition: plan } }); return saved; },
  adopt(ids, value) { adopted = ids; table = value; }, report(message, error) { if (error) issue = message; } });
try {
  view.render();
  const form = document.querySelector("#source-data-panel form");
  form.elements.namedItem("latitude").value = "50.46";
  form.elements.namedItem("longitude").value = "119.85";
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(form.elements.namedItem("latitude").disabled, true);
  const deadline = Date.now() + 600000;
  while (!adopted && !issue && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 100));
  assert.ifError(issue);
  assert.equal(adopted?.length, 1);
  assert.equal(table.rows.length, 30);
  assert.ok(table.rows.every((row) => row.values.lai === 1.5 && Number.isFinite(row.values.temperature_mean_daily)));
  saved = await api("/plans/" + saved.design_id, { method: "PUT", body: { definition: plan, expected_revision: saved.revision, observations: table, source_snapshot_ids: adopted } });
  const opened = await api("/plans/" + saved.design_id);
  assert.deepEqual(opened.source_snapshot_ids, adopted);
  assert.equal(opened.observations.columns.find((c) => c.code === "temperature_mean_daily").value_kind, "estimated");
  const created = exchanges.find((r) => r.path.endsWith("/input-acquisitions"));
  assert.ok(created && created.status === 202);
  await writeFile(output, JSON.stringify({ all_success: true, source_snapshot_ids: adopted, design_id: saved.design_id, rows: 30,
    real_provider_acquisition: true, manual_values_preserved: true, source_values_estimated: true, location_locked_while_pending: true,
    browser_scope: "JSDOM interactions with live HTTP; no native pixel acceptance", exchanges }, null, 2) + "\n");
  console.log("Verified live source collection UI, preserved labels and reopened source references");
} finally { dom.window.close(); }
