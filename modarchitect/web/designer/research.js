import { formatUnit, predictionColumns } from "./modeling.js?v=continuous1";
import { applicationPath } from "./http-path.js?v=proxy1";
import { renderTableCurves } from "./observation-curves.js?v=continuous1";
import { renderSummary, runOperation } from "./result-views.js?v=continuous1";
import { researchTitle } from "./study-library.js?v=continuous1";
import { mountSourceData } from "./source-data.js?v=continuous1";
import { mountContinuousResearch } from "./continuous-research.js?v=continuous1";

const byId = (id) => document.getElementById(id);
const BASE = "/api/v1/workspace";
const TERMINAL = new Set(["succeeded", "failed", "uncertain"]);
const STATUS = { queued: "等待调度", dispatching: "正在提交调度", submitted: "调度已接受", running: "正在计算", succeeded: "计算完成", failed: "计算失败", uncertain: "提交结果待核对" };
const OPERATION = { train: "训练", predict: "预测", analyze: "分析", simulate: "模拟", calibrate: "标定" };

export function observationTemplate(plan, data = null) {
  const codes = new Set(Object.values(plan.input_recipes).filter((r) => r.kind === "observations").flatMap((r) => r.variable_codes));
  const columns = plan.variables.filter((v) => codes.has(v.code)).map((v) => ({ code: v.code, name: v.name, unit: v.unit, value_kind: plan.collection_requirements.find((r) => r.variable_code === v.code)?.catalog_binding?.value_nature || "observed" }));
  const rows = data?.rows || [{ object: { field_ref: "填写地块编号", crop_code: "wheat", season_ref: "填写种植季编号" }, business_date: "YYYY-MM-DD", values: {} }];
  return { columns, rows: rows.map((row) => ({ ...structuredClone(row), values: Object.fromEntries(columns.map((column) => [column.code, row.values[column.code] ?? null])) })) };
}

function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [value.slice(0, 8), value.slice(8, 12), value.slice(12, 16), value.slice(16, 20), value.slice(20)].join("-");
}

function node(tag, text = "", className = "") {
  const value = document.createElement(tag);
  value.textContent = text;
  if (className) value.className = className;
  return value;
}

function tableView(target, table, editable, onEdit = () => {}) {
  target.replaceChildren();
  if (!table) return;
  const view = node("table", "", "research-table");
  const head = node("tr");
  head.append(node("th", "日期"));
  for (const column of table.columns) head.append(node("th", column.name + " · " + formatUnit(column.unit)));
  view.append(head);
  for (const row of table.rows.slice(0, 12)) {
    const line = node("tr");
    line.append(node("td", row.business_date));
    for (const column of table.columns) {
      const cell = node("td");
      const value = row.values[column.code];
      if (editable && column.value_kind === "observed") {
        const input = document.createElement("input");
        input.type = "number"; input.step = "any"; input.value = value;
        input.setAttribute("aria-label", row.business_date + " " + column.name);
        input.addEventListener("change", () => {
          if (input.value !== "" && Number.isFinite(input.valueAsNumber)) { row.values[column.code] = input.valueAsNumber; onEdit(); }
          else input.value = row.values[column.code];
        });
        cell.append(input);
      } else cell.textContent = typeof value === "number" ? Number(value.toFixed(6)).toString() : "—";
      line.append(cell);
    }
    view.append(line);
  }
  target.append(view);
}

export function mountResearch({ getDefinition, getRecords = () => new Map(), openDefinition, notify, onDataChange = () => {}, onRunChange = () => {}, onFlowChange = () => {}, onModelChange = () => {}, onTemplateChange = () => {}, onError = () => {}, beforeRun = async () => {} }) {
  const state = { saved: null, data: null, dataKind: "user_supplied", sourceSnapshotIds: [], template: null, run: null, model: null, prediction: null, poll: null, busy: false, pending: new Map(), flowRun: null, runData: null, generation: 0, plans: new Map(), templates: new Map(), rules: new Map() };
  const sourceBody = () => state.sourceSnapshotIds.length ? { source_snapshot_ids: state.sourceSnapshotIds } : {};
  byId("wizard-study-version").addEventListener("input", (event) => { event.target.dataset.edited = "true"; });
  const continuous = mountContinuousResearch({ api, save: () => save(true), getModel: () => state.model, report: feedback, follow });
  const sourcePanel = mountSourceData({ api, getDefinition, getData: () => state.data, getDataKind: () => state.dataKind, saveDefinition: () => save(true),
    adopt(ids, table) { state.sourceSnapshotIds = ids; state.data = table; state.flowRun = null; state.generation += 1; dataView(); if (state.model) predictionForm(state.model); }, report: feedback });

  async function inputBody(table = state.data, dataKind = state.dataKind) {
    if (state.sourceSnapshotIds.length <= 36) return { observations: table, data_kind: dataKind, ...sourceBody() };
    if (!state.saved) throw new Error("请先保存当前方案，再采用多对象来源资料。");
    const manualCodes = new Set(getDefinition().collection_requirements.filter((r) => r.source === "manual").map((r) => r.variable_code));
    const columns = table.columns.filter((column) => manualCodes.has(column.code));
    const manual = columns.length ? { columns, rows: table.rows.map((row) => ({ ...row, values: Object.fromEntries(columns.map((c) => [c.code, row.values[c.code]])) })) } : null;
    const dataset = await api("/plans/"+state.saved.design_id+"/datasets", { method: "POST", body: { source_snapshot_ids: state.sourceSnapshotIds, data_kind: dataKind, ...(manual ? { observations: manual } : {}) } });
    return { dataset_snapshot_id: dataset.dataset_snapshot_id };
  }

  async function api(path, { method = "GET", body, idempotent = false } = {}) {
    const encoded = body === undefined ? undefined : JSON.stringify(body);
    const headers = { "X-Workspace-Request": "1" };
    if (encoded !== undefined) headers["Content-Type"] = "application/json";
    const token = path + ":" + encoded;
    if (idempotent) {
      if (!state.pending.has(token)) state.pending.set(token, requestId());
      headers["Idempotency-Key"] = state.pending.get(token);
    }
    const response = await fetch(applicationPath(path.startsWith("/api/") ? path : BASE + path), { method, headers, body: encoded, credentials: "same-origin", signal: AbortSignal.timeout(30000) });
    const result = await response.json();
    if (!response.ok) {
      if (result.issues?.some((issue) => issue.rule === "study_version_conflict")) throw new Error("该方案已使用这个版本名称，请修改名称或留空自动生成。");
      if (response.status === 422 && result.issues?.some((issue) => issue.path?.at(-1) === "version_name")) throw new Error("请填写不超过 128 字符的单行版本名称。");
      if (response.status === 409) throw new Error("方案或请求已变化，请刷新云端方案后重试。");
      if (response.status === 401) throw new Error("工作区会话已失效，请刷新页面。");
      if (response.status === 404 && /^\/plans\/[^/]+$/.test(path)) throw new Error("当前工作区中找不到该研究方案。请使用保存时的工作区打开，或由业务系统确认访问权限。");
      if (result.issues?.length && state.rules.has(result.issues[0].rule)) throw new Error(state.rules.get(result.issues[0].rule).guidance);
      if (typeof result.detail === "string" && /Frozen study scientific definition/.test(result.detail)) throw new Error("研究方法或数据来源已改变，请重新选择研究方案并检查设置。");
      if (typeof result.detail === "string" && /frozen study inputs.*(unavailable|not configured)/i.test(result.detail)) throw new Error("请先补齐本研究所需的数据，再开始分析。");
      if (typeof result.detail === "string" && /system input|system catalog|external input|external observation/i.test(result.detail)) throw new Error("普通研究需要从系统输入目录选择指标，并使用固定单位与来源；历史私有输入只保留作演示或历史读取。");
      if (typeof result.detail === "string" && /channel or scientific-unit/i.test(result.detail)) throw new Error("此输入尚缺取数通道或科学单位适配，请在「数据从哪里来」中查看原因。上传数值不能替代该来源。");
      if (typeof result.detail === "string" && /Daily report.*schedul/i.test(result.detail)) throw new Error("每日调度尚未就绪，或日程未覆盖所选观察期，请联系平台维护人员核对。");
      if (typeof result.detail === "string" && /Daily reports require explicit|Daily report input channels/i.test(result.detail)) throw new Error("此研究版本尚不支持每日跟踪。请使用指标、单位和来源均已接通的方案。");
      if (typeof result.detail === "string" && /Series range/i.test(result.detail)) throw new Error("请选择观察期内、不超过90天的曲线范围。");
      if (typeof result.detail === "string" && /does not require manual/i.test(result.detail)) throw new Error("此方案由平台自动取数，无需补充人工观测。");
      if (typeof result.detail === "string" && /5000 object-date/i.test(result.detail)) throw new Error("单次每日批次目前最多5000条对象日期记录，请缩小研究对象或观察范围。");
      if (typeof result.detail === "string" && /Daily prediction must follow/i.test(result.detail)) throw new Error("每日预测的观察开始日必须晚于模型的训练截止日。");
      throw new Error(typeof result.detail === "string" ? result.detail : "请核对数据列、单位和方案配置。");
    }
    if (idempotent) state.pending.delete(token);
    return result;
  }

  function feedback(message, error = false) {
    byId("workspace-status").textContent = message;
    byId("workspace-status").dataset.error = String(error);
  }

  function dataView() {
    sourcePanel.render();
    onDataChange(state.data, state.dataKind);
    tableView(byId("observation-table"), state.data, true, () => {
      state.flowRun = null; state.generation += 1; clearTimeout(state.poll); flowView();
    });
    const hasObserved = state.data?.columns.some((column) => column.value_kind === "observed");
    const dataLabel = state.dataKind === "synthetic" ? "合成演示观测" : state.sourceSnapshotIds.length ? hasObserved ? "实测记录与平台资料" : "平台来源资料" : "自有观测（待服务端校验来源）";
    const editHint = state.dataKind === "synthetic" ? "示例数值可编辑。" : state.sourceSnapshotIds.length && !hasObserved ? "平台资料只读。" : "可修改实测值，平台资料只读。";
    byId("data-summary").textContent = state.data
      ? dataLabel + " · " + state.data.rows.length + " 条 · 显示前 12 条；" + editHint
      : "先从系统目录选择输入，再下载模板填写记录；也可打开明确标注的合成演示。";
    const required = observationTemplate(getDefinition()).columns;
    const missing = required.filter((c) => !state.data?.columns.some((v) => v.code === c.code));
    if (state.data && missing.length) byId("data-summary").textContent += " 当前缺少：" + missing.map((c) => c.name).join("、") + "。请下载新模板，填完空值后重新上传。";
    const native = state.template?.execution_mode === "frozen_case";
    if (native) byId("data-summary").textContent = (state.template.researcher?.data_description || "已选择研究数据") + "。" + (state.template.researcher?.data_usage || "请核对数据是否适用于当前研究对象。");
    byId("upload-observations").disabled = native; byId("download-observations").disabled = native;
    byId("study-run").disabled = state.busy || (!native && (!state.data || missing.length > 0));
    flowView();
  }

  function flowView() {
    onFlowChange(state.flowRun ? { ...state.flowRun, model: state.model?.run_id === state.flowRun.run.run_id ? state.model : null } : { definition: getDefinition(), template: state.template, data: state.data, dataKind: state.dataKind });
  }

  async function guard(action) {
    if (state.busy) return;
    state.busy = true;
    for (const id of ["cloud-save", "wizard-save-draft", "study-run", "study-multivariable", "study-chain", "study-analysis", "run-prediction", "save-trained-model"]) byId(id).disabled = true;
    try { return await action(); }
    catch (error) { feedback(error.message || "操作未完成，请重试。", true); onError(error.message || "操作未完成，请重试。"); }
    finally {
      state.busy = false;
      for (const id of ["cloud-save", "wizard-save-draft", "study-multivariable", "study-chain", "study-analysis", "run-prediction", "save-trained-model"]) byId(id).disabled = false;
      dataView();
    }
  }

  async function refresh() {
    const [plans, runs, models] = await Promise.all([api("/plans"), api("/runs"), api("/models")]);
    for (const [id, items, key, label] of [
      ["cloud-plans", plans.items, "design_id", (row) => researchTitle(row.configuration.definition)],
      ["cloud-runs", runs.items, "run_id", (row) => (OPERATION[row.kind] || row.kind) + " · " + STATUS[row.status] + " · " + new Date(row.created_at).toLocaleString("zh-CN")],
      ["cloud-models", models.items, "model_id", (row) => row.name],
    ]) {
      const select = byId(id), selected = select.value;
      while (select.options.length > 1) select.remove(1);
      for (const row of items) select.add(new Option(label(row), row[key]));
      select.value = selected;
    }
  }

  function showStudyVersion(version) {
    byId("wizard-study-version-current").textContent = version ? "最近保存的可应用版本 · " + version : "保存为可应用版本后显示名称";
  }

  async function save(definitionOnly = false) {
    const definition = getDefinition();
    const fingerprint = JSON.stringify(definition);
    const field = byId("wizard-study-version");
    const versionText = field.value, version = versionText.trim();
    const name = version || field.dataset.edited === "true" ? { version_name: version || null } : {};
    const body = { definition, ...name, ...(definitionOnly ? { data_kind: state.dataKind } : await inputBody()) };
    const result = state.saved
      ? await api("/plans/" + state.saved.design_id, { method: "PUT", body: { ...body, expected_revision: state.saved.revision } })
      : await api("/plans", { method: "POST", body, idempotent: true });
    state.saved = result;
    if (field.value === versionText) { field.value = ""; delete field.dataset.edited; }
    const url = new URL(location.href);
    url.searchParams.delete("research"); url.searchParams.set("study", result.design_id);
    history.replaceState({}, "", url);
    feedback("已保存到个人工作区 · 修订 " + result.revision);
    await refresh();
    if (JSON.stringify(getDefinition()) !== fingerprint) throw new Error("保存期间方案发生变化，请再次保存当前编辑。");
    return result;
  }

  async function publishConfiguration() {
    const saved = await save(true);
    const version = await api("/plans/" + saved.design_id + "/publish", { method: "POST", body: { expected_revision: saved.revision } });
    showStudyVersion(version.version_name);
    feedback("已保存可应用版本 · " + version.version_name);
    return { ...saved, version_name: version.version_name, design_version_id: version.design_version_id };
  }

  async function openStudy(id) {
    const saved = await api("/plans/" + id);
    await openDefinition(saved.configuration.definition);
    state.saved = saved; state.data = saved.observations; state.dataKind = saved.data_kind;
    showStudyVersion(saved.latest_version?.version_name);
    byId("wizard-study-version").value = saved.version_name === saved.latest_version?.version_name ? "" : saved.version_name || "";
    state.sourceSnapshotIds = saved.source_snapshot_ids || [];
    state.prediction = null;
    const marker = saved.configuration.definition.layout?.study_template;
    if (marker) {
      state.template = await api("/study-templates/" + marker.id + "?sha256=" + encodeURIComponent(marker.sha256));
      if (state.template.sha256 !== marker.sha256) throw new Error("原方案模板版本已变化，请保留当前草稿并重新选择准确版本。");
      onTemplateChange(state.template);
    }
    dataView(); feedback("已打开云端方案 · 修订 " + saved.revision);
    const url = new URL(location.href); url.searchParams.set("study", id); url.searchParams.delete("research");
    history.replaceState({}, "", url);
  }

  async function example(kind, persist = true) {
    state.sourceSnapshotIds = [];
    const result = await api("/examples/" + kind);
    await openDefinition(result.definition);
    state.data = result.observations; state.dataKind = "synthetic"; state.prediction = result.prediction_observations;
    dataView();
    if (persist) {
      await save();
      return;
    }
    const url = new URL(location.href);
    for (const parameter of ["study", "research", "template"]) url.searchParams.delete(parameter);
    history.replaceState({}, "", url);
    feedback("已打开双目标合成示例。点击保存草稿可保留这份新方案。");
  }

  async function openTemplate(id, persist) {
    state.sourceSnapshotIds = [];
    await api("/session");
    const result = await api("/study-templates/" + id);
    await openDefinition(result.definition);
    state.template = result; state.data = result.observations; state.dataKind = result.data_kind === "synthetic" ? "synthetic" : "user_supplied";
    state.prediction = result.prediction_observations;
    onTemplateChange(result, { preview: true }); dataView();
    if (persist) await save();
    else feedback("正在预览完整流程；点击保存草稿即可采用到个人工作区。");
  }

  function resultView(run) {
    state.run = run;
    onRunChange(run);
    flowView();
    byId("run-status").dataset.state = run.status;
    byId("run-status").textContent = STATUS[run.status] + (run.error ? " · 请核对观测与模型设置，具体原因见运行依据。" : "");
    byId("run-evidence").textContent = "研究数据与所选方法分别记录，保存后可以重新查看。";
    byId("run-metrics").replaceChildren(); byId("run-output").replaceChildren(); byId("run-curves").replaceChildren();
    byId("model-save-panel").hidden = !(run.status === "succeeded" && run.kind === "train");
    if (!run.result_json) return;
    const result = run.result_json;
    if (result.data_kind === "synthetic") byId("run-status").append(node("span", " · 示例数据结果"));
    const sources = result.input_sources;
    if (sources) byId("run-evidence").append(node("span", state.template?.researcher ? " 数据：" + state.template.researcher.data_description : " 输入来源与单位已检查。"));
    for (const metric of result.metrics) {
      const item = node("div", "", "research-metric");
      item.append(node("span", result.pipeline?.plan.variables.find((value) => value.code === metric.target)?.name || metric.target));
      if (metric.status === "evaluated") {
        item.append(node("strong", "预测误差 " + metric.rmse.toFixed(4) + " " + formatUnit(metric.unit)), node("span", "RMSE · " + metric.rows + " 条配对 · 覆盖 " + (metric.coverage * 100).toFixed(0) + "%"));
      } else item.append(node("strong", "待实测评价"));
      byId("run-metrics").append(item);
    }
    const prediction = Object.values(result.outputs).find((output) => Array.isArray(output.rows) && Array.isArray(output.columns));
    renderTableCurves(byId("run-curves"), prediction);
    tableView(byId("run-output"), prediction, false);
    for (const output of Object.values(result.outputs)) renderSummary(byId("run-output"), output);
    if (run.kind === "train") byId("trained-model-name").value = result.pipeline.plan.name + " · 模型";
  }

  async function follow(run) {
    clearTimeout(state.poll);
    const generation = state.generation;
    if (state.flowRun?.run.run_id !== run.run_id) { state.flowRun = null; flowView(); }
    state.run = run;
    let definition = run.result_json?.pipeline?.plan || state.plans.get(run.design_version_id);
    if (!definition) definition = await api("/runs/" + run.run_id + "/plan");
    state.plans.set(run.design_version_id, definition);
    const marker = definition.layout?.study_template;
    let template = null;
    if (marker) {
      const key = marker.id + "@" + marker.sha256;
      template = state.templates.get(key);
      if (!template) { template = await api("/study-templates/" + marker.id + "?sha256=" + encodeURIComponent(marker.sha256)); state.templates.set(key, template); }
    }
    if (generation !== state.generation || state.run?.run_id !== run.run_id) return;
    state.flowRun = { definition, template, run, data: state.runData?.runId === run.run_id ? state.runData.table : null, dataKind: run.result_json?.data_kind ?? (state.runData?.runId === run.run_id ? state.runData.dataKind : null) };
    resultView(run);
    if (TERMINAL.has(run.status)) { await refresh(); return; }
    state.poll = setTimeout(async () => {
      try {
        const next = await api("/runs/" + run.run_id);
        if (state.run?.run_id === run.run_id) await follow(next);
      } catch (error) { feedback(error.message, true); }
    }, 1800);
  }

  function predictionForm(model) {
    state.model = model;
    onModelChange(model);
    const pipeline = model.model_json;
    const form = byId("prediction-form"); form.replaceChildren();
    byId("prediction-panel").hidden = false;
    byId("model-source").textContent = model.name + " · 使用已保存训练状态" + (pipeline.training_data_kind === "synthetic" ? " · 合成演示数据训练" : "");
    const columns = predictionColumns(pipeline, getRecords());
    const template = pipeline.plan.name === getDefinition().name && columns.every((column) => state.prediction?.columns.some((value) => value.code === column.code)) ? state.prediction : null;
    const thirdParty = new Set(pipeline.plan.collection_requirements.filter((item) => item.source === "third_party").map((item) => item.variable_code));
    const sourced = thirdParty.size && state.sourceSnapshotIds.length && state.data?.rows[0];
    const last = sourced || template?.rows[0] || pipeline.last_input;
    const field = (label, name, type, value) => {
      const wrapper = node("label", label), input = document.createElement("input");
      input.name = name; input.type = type; input.value = value; input.required = true;
      if (type === "number") input.step = "any";
      if (thirdParty.has(name)) input.readOnly = true;
      wrapper.append(input); form.append(wrapper);
    };
    field("预测数据日期", "business_date", "date", last.business_date);
    for (const column of columns) field(column.name + " · " + formatUnit(column.unit), column.code, "number", last.values[column.code]);
    if (thirdParty.size) {
      const note = node("p", "平台因素从已采集资料读取；更换日期前请在数据来源中采集覆盖日期的资料。", "research-caption"); form.append(note);
      form.elements.namedItem("business_date").addEventListener("change", (event) => {
        const record = state.data?.rows.find((row) => row.business_date === event.target.value && ["field_ref", "crop_code", "season_ref"].every((key) => row.object[key] === last.object[key]));
        for (const code of thirdParty) if (form.elements.namedItem(code)) form.elements.namedItem(code).value = record?.values[code] ?? "";
      });
    }
    state.prediction = { columns, rows: [structuredClone(last)] };
  }

  byId("study-multivariable").addEventListener("click", () => guard(() => example("multivariable")));
  byId("study-chain").addEventListener("click", () => guard(() => example("chain")));
  byId("study-analysis").addEventListener("click", () => guard(() => example("analysis")));
  byId("cloud-save").addEventListener("click", () => guard(save));
  byId("refresh-research").addEventListener("click", () => guard(async () => {
    await refresh(); if (state.run) await follow(await api("/runs/" + state.run.run_id));
  }));
  byId("study-run").addEventListener("click", () => guard(async () => {
    const native = state.template?.execution_mode === "frozen_case";
    if (!native && !state.data) throw new Error("请先提供观测数据。");
    await beforeRun();
    const checked = await api("/check-execution", { method: "POST", body: { definition: getDefinition(), ...(state.saved ? { design_id: state.saved.design_id } : {}), operation: native ? state.template.operation : (runOperation(getDefinition())?.operation || "train"), ...(!native ? await inputBody() : {}) } });
    if (!checked.can_execute) throw new Error(state.rules.get(checked.issues[0]?.rule)?.guidance || "当前输入或模型设置未满足执行条件，请核对后重试。");
    const saved = await save();
    const body = native ? { design_id: saved.design_id, expected_revision: saved.revision, template_id: state.template.id, template_sha256: state.template.sha256 } : { design_id: saved.design_id, expected_revision: saved.revision, ...await inputBody(), ...runOperation(getDefinition()) };
    const submitted = !native && state.data ? structuredClone(state.data) : null;
    const started = await api(native ? "/template-runs" : "/runs", { method: "POST", idempotent: true, body });
    state.runData = submitted ? { runId: started.run_id, table: submitted, dataKind: state.dataKind } : null;
    await follow(started);
  }));
  byId("cloud-plans").addEventListener("change", (event) => { if (event.target.value) guard(() => openStudy(event.target.value)); });
  byId("cloud-runs").addEventListener("change", (event) => { if (event.target.value) guard(async () => follow(await api("/runs/" + event.target.value))); });
  byId("cloud-models").addEventListener("change", (event) => { if (event.target.value) guard(async () => predictionForm(await api("/models/" + event.target.value))); });
  byId("save-trained-model").addEventListener("click", () => guard(async () => {
    const model = await api("/models", { method: "POST", body: { run_id: state.run.run_id, name: byId("trained-model-name").value } });
    predictionForm(model); await refresh(); feedback("模型已保存，可以输入新数据进行预测。");
  }));
  byId("run-prediction").addEventListener("click", () => guard(async () => {
    const form = byId("prediction-form");
    if (!form.reportValidity()) return;
    const table = structuredClone(state.prediction), row = table.rows[0];
    row.business_date = form.elements.namedItem("business_date").value;
    row.values = Object.fromEntries(table.columns.map((column) => [column.code, form.elements.namedItem(column.code).valueAsNumber]));
    await follow(await api("/predictions", { method: "POST", idempotent: true, body: { model_id: state.model.model_id, ...await inputBody(table, state.model.model_json.training_data_kind || "user_supplied") } }));
  }));
  byId("upload-observations").addEventListener("click", () => byId("observation-file").click());
  byId("observation-file").addEventListener("change", (event) => guard(async () => {
    const file = event.target.files[0]; event.target.value = "";
    if (!file || file.size > 4000000) throw new Error("请选择 4MB 以内的观测 JSON。");
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data.columns) || !Array.isArray(data.rows) || !data.rows.length) throw new Error("观测文件需要 columns 和非空 rows，可先下载数据模板。");
    state.data = data; state.dataKind = state.template?.input_policy?.mode === "synthetic_demo_only" ? "synthetic" : "user_supplied";
    state.flowRun = null; state.generation += 1;
    dataView(); feedback(state.dataKind === "synthetic" ? "已载入演示记录，仅用于合成数据研究。" : "已载入自有观测，保存后运行。");
  }));
  byId("download-observations").addEventListener("click", () => {
    const template = observationTemplate(getDefinition(), state.data);
    if (!template.columns.length) { notify("请先从系统目录选择输入并建立模型。"); return; }
    const url = URL.createObjectURL(new Blob([JSON.stringify(template, null, 2)], { type: "application/json" }));
    const link = node("a"); link.href = url; link.download = "研究观测模板.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  guard(async () => {
    await api("/session");
    const rules = await api("/api/v1/model-center/research-rules"); state.rules = new Map(rules.rules.map((rule) => [rule.code, rule]));
    await refresh();
    await continuous.refresh();
    const url = new URL(location.href), study = url.searchParams.get("study"), sample = url.searchParams.get("research"), template = url.searchParams.get("template");
    if (study) await openStudy(study);
    else if (template) await openTemplate(template, true);
    else if (["multivariable", "chain", "system", "analysis", "calendar"].includes(sample)) await example(sample);
    else feedback("个人工作区已连接 · 云端方案与模型可重新访问。");
  });
  return { publishConfiguration() { return guard(publishConfiguration); }, openExample(kind, { persist = true } = {}) { return guard(() => example(kind, persist)); }, openTemplate(id, persist = true) { return guard(() => openTemplate(id, persist)); }, onDefinitionChange() {
    state.flowRun = null; state.generation += 1; clearTimeout(state.poll); byId("run-curves").replaceChildren(); dataView();
  }, onLoad() {
    clearTimeout(state.poll);
    state.saved = null; state.data = null; state.prediction = null; state.model = null; state.run = null;
    byId("wizard-study-version").value = "";
    delete byId("wizard-study-version").dataset.edited;
    showStudyVersion(null);
    state.sourceSnapshotIds = [];
    state.template = null; onTemplateChange(null);
    state.runData = null;
    state.flowRun = null; state.generation += 1;
    onRunChange(null);
    byId("prediction-panel").hidden = true; byId("model-save-panel").hidden = true;
    byId("run-status").textContent = "运行研究后查看计算结果。";
    byId("run-evidence").textContent = "尚未启动研究。";
    byId("run-metrics").replaceChildren(); byId("run-output").replaceChildren(); byId("run-curves").replaceChildren(); dataView();
  } };
}
