import {
  addConfiguration, addModel, addObservationInput, blankPlan, connectInput,
  recordKey, removeNode, requestInput, setOutput, sourceKey,
} from "./editor.js?v=continuous1";
import { describe, inspect, issueMessage, renderFlowSummary, resources } from "./panels.js?v=continuous1";
import { defaults } from "./schema-fields.js?v=continuous1";
import { createGraph, element } from "./visuals.js?v=continuous1";
import { mountResearch } from "./research.js?v=calculation1";
import { applicationPath } from "./http-path.js?v=proxy1";
import { mountModeling } from "./modeling-view.js?v=continuous1";
import { mountSystemInputs } from "./system-inputs.js?v=continuous1";
import { mountWizard } from "./wizard.js?v=method-role1";
import { mountMethodPicker } from "./method-picker.js?v=method-role1";
import { mountInspection } from "./inspection-view.js?v=calculation1";
import { useMethodDefaults } from "./methods.js?v=method-role1";
import { mountStudyLibrary, showTemplateSummary, showStudyFlow, researchTitle, researchQuestion } from "./study-library.js?v=study-icons1";

const byId = (id) => document.getElementById(id);
const DRAFT_KEY = "modarchitect.designer.draft.v1";
const REQUEST_BUDGET = 1_048_576;
const CATALOG = "/api/v1/model-center/components";
const state = {
  definition: null, records: new Map(), methods: new Map(), catalog: [], inputCatalog: { items: [], categories: [] }, flow: null,
  selected: "plan", tab: "connections", library: "components", zoom: 1,
  generation: 0, issue: null, busy: true, source: null, saved: null,
};
const graph = createGraph(byId("board-stage"), byId("graph"), byId("connections"), {
  onSelect: select, onSource: chooseSource, onTarget: chooseTarget, onMove: moveNode,
  onConfigure(code) { technical(true); state.tab = "parameters"; select("node:" + code); },
});
let noticeTimer;
let researchWorkspace;
let modelingWorkspace;
let inputWorkspace;
let wizardWorkspace;
let methodWorkspace;
let inspectionWorkspace;
let methodRequest;

function loadResearchMethods() {
  methodRequest ??= request("/api/v1/model-center/research-methods").then((directory) => {
    if (directory.schema_version !== "1.0") throw new Error("暂时无法读取计算方式，请刷新设计器。");
    state.methods = new Map(directory.items.map((method) => [recordKey(method.component), method]));
    return directory;
  }).catch((error) => {
    methodRequest = undefined;
    throw error;
  });
  return methodRequest;
}

function technical(force) {
  const expanded = force ?? byId("technical-workspace").hidden;
  byId("technical-workspace").hidden = !expanded;
  byId("technical-toggle").setAttribute("aria-expanded", String(expanded));
  byId("technical-toggle").textContent = expanded ? "收起组件与连线" : "查看组件与连线";
  if (expanded) { graph.refresh(); byId("technical-workspace").scrollIntoView({ behavior: "smooth", block: "start" }); }
}

function notify(message) {
  clearTimeout(noticeTimer);
  const notice = byId("notice");
  notice.textContent = message;
  notice.hidden = false;
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 4500);
}

async function request(url, payload) {
  const options = payload === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: typeof payload === "string" ? payload : JSON.stringify(payload),
  };
  let response;
  let value;
  try {
    response = await fetch(applicationPath(url), { ...options, signal: AbortSignal.timeout(10000) });
    value = await response.json();
  } catch {
    throw new Error("暂时无法连接设计服务，请稍后重试。");
  }
  if (!response.ok) {
    if (response.status === 413 || (typeof value.detail === "string" && value.detail.includes("size budget"))) {
      throw new Error("方案文件超过大小预算，请缩减配置后重试。");
    }
    if (typeof value.detail === "string" && value.detail.toLowerCase().includes("checksum")) {
      throw new Error("文件摘要不匹配，请使用完整导出的 JSON 文件。");
    }
    if (typeof value.detail === "string" && value.detail.includes("selectors")) throw new Error("请明确选择来源所需的全部属性，如土层深度和统计方式。");
    throw new Error("无法读取方案配置，请核对 JSON 格式和组件版本。");
  }
  return value;
}

function status(text, kind = "") {
  const target = byId("validation-status");
  target.dataset.state = kind;
  const dot = element("span", "status-dot");
  dot.setAttribute("aria-hidden", "true");
  target.replaceChildren(dot, element("span", "", text));
}

function buttons() {
  const ready = Boolean(state.definition);
  for (const id of ["export-plan", "validate-plan", "save-plan", "new-plan", "reset-plan", "chain-plan", "import-plan", "edit-plan"]) {
    byId(id).disabled = state.busy || !ready;
  }
  byId("open-local").hidden = !state.saved;
  byId("open-local").disabled = state.busy;
  byId("add-variable").hidden = state.library !== "variables";
}

function heading() {
  byId("plan-name").textContent = researchTitle(state.definition);
  byId("plan-question").textContent = researchQuestion(state.definition) || "定义研究问题、观测变量与目标，再选择研究方法。";
}

function resourceGroups() {
  if (state.library === "variables") {
    return [["研究变量", state.definition.variables.map((variable) => ({
      key: "variable:" + variable.code, name: variable.name,
      subtitle: variable.role === "target" ? "目标 · " + variable.unit : variable.code + " · " + variable.unit,
      kind: "observation", glyph: "x",
    }))]];
  }
  const inputs = [{ key: "add:observations", kind: "observation", name: "观测表", subtitle: "选择采集列", glyph: "▦", add: true }];
  const models = state.catalog.map(({ definition }) => ({
    key: "add:model:" + recordKey(definition), name: definition.name,
    subtitle: "V" + definition.revision + " · " + definition.code, kind: "model", glyph: "ƒ", add: true,
  }));
  return [["添加数据", inputs], ["添加组件", models],
    ["当前方案", [...state.flow.inputs, ...state.flow.models, ...state.flow.outputs]]];
}

function renderResources() {
  if (!state.definition) return;
  resources(byId("resource-list"), resourceGroups(), byId("library-search").value, state.selected, activateResource);
}

const inspectorCallbacks = {
  updateParameter(input, name, value) {
    const parameters = state.definition.input_recipes[input].value;
    if (value === undefined) delete parameters[name];
    else parameters[name] = value;
    modified();
    if (name === "axis_kind") {
      renderInspector();
      byId("inspector-content").querySelector('[data-field="axis_kind"]')?.focus();
    }
  },
  updatePlan(name, value) {
    const previous = state.definition[name];
    state.definition[name] = value;
    if (name === "purpose") {
      for (const requirement of state.definition.collection_requirements) {
        if (requirement.required_for.length === 1 && requirement.required_for[0] === previous) {
          requirement.required_for = [value];
        }
      }
    }
    heading();
    modified();
  },
  setObservationColumn(input, code, enabled) {
    const recipe = state.definition.input_recipes[input];
    recipe.variable_codes = recipe.variable_codes.filter((item) => item !== code);
    if (enabled) recipe.variable_codes.push(code);
    modified();
  },
  addObservation: createObservation,
  addConfiguration(node, record) {
    addConfiguration(state.definition, node, record, defaults(record.research_contract.request_schema));
    rebuild("node:" + node.code);
    modified();
  },
  removeNode(key) {
    removeNode(state.definition, key);
    state.source = null;
    rebuild("plan");
    modified();
  },
  connectInput: writeConnection,
  setOutput(node, port, enabled) {
    setOutput(state.definition, node, port, enabled);
    rebuild(state.selected);
    modified();
    byId("inspector-content").querySelector('[data-output="' + port + '"]')?.focus();
  },
  setTab(tab) {
    state.tab = tab;
    renderInspector();
    byId("inspector-content").querySelector('.segments [aria-pressed="true"]')?.focus();
  },
};

function renderInspector() {
  byId("inspector-context").textContent = inspect(byId("inspector-content"), state, inspectorCallbacks);
}

function select(key) {
  state.selected = key;
  graph.select(key);
  for (const button of byId("resource-list").querySelectorAll("[data-resource]")) {
    button.setAttribute("aria-pressed", String(button.dataset.resource === key));
  }
  renderInspector();
}

function modified() {
  state.generation += 1;
  state.issue = null;
  for (const field of byId("inspector-content").querySelectorAll('[aria-invalid="true"]')) field.removeAttribute("aria-invalid");
  status("已修改，待校验");
  byId("plan-state").textContent = "未保存修改";
  byId("sample-preview").hidden = true;
  modelingWorkspace?.render();
  inputWorkspace?.render();
  researchWorkspace?.onDefinitionChange();
  wizardWorkspace?.render();
  inspectionWorkspace?.schedule();
}

function counts() {
  const { inputs, models, outputs } = state.flow;
  const source = state.source;
  const port = source && (source.node
    ? models.find((item) => item.code === source.node)?.outgoing.find((item) => item.code === source.port)
    : inputs.find((item) => item.code === source.port));
  const tip = byId("connection-tip");
  tip.hidden = !models.length;
  tip.textContent = port ? "已选择「" + port.name + "」。点击下游输入完成连线。"
    : "点击上游输出，再点击要连接的下游输入。";
  tip.toggleAttribute("data-pending", Boolean(port));
  byId("graph-counts").textContent = inputs.filter((item) => item.kind !== "parameter").length + " 个数据输入 · " + models.length + " 个计算步骤 · " + outputs.length + " 个输出 · 参数在节点设置中";
}

function rebuild(selected, flow = describe(state.definition, state.records)) {
  state.flow = flow;
  const empty = !(state.flow.inputs.length + state.flow.models.length + state.flow.outputs.length);
  byId("graph").hidden = empty;
  byId("stage-empty").hidden = !empty;
  graph.render(state.flow, state.definition.layout?.designer_positions);
  graph.connectFrom(state.source);
  renderFlowSummary(byId("flow-summary"), byId("flow-links"), state.flow);
  counts();
  renderResources();
  select(selected);
  buttons();
  modelingWorkspace?.render();
  inputWorkspace?.render();
  wizardWorkspace?.render();
}

function load(definition, isSample = false) {
  researchWorkspace?.onLoad();
  const draft = structuredClone(definition);
  const flow = describe(draft, state.records);
  Object.assign(state, {
    definition: draft, tab: isSample ? "parameters" : "connections",
    issue: null, source: null, generation: state.generation + 1,
  });
  heading();
  byId("stage-loading").hidden = true;
  byId("sample-preview").hidden = !isSample;
  byId("plan-state").textContent = isSample ? "逻辑斯蒂样例" : "研究草稿";
  rebuild(isSample ? flow.models[0].key : "plan", flow);
  status("待校验");
  wizardWorkspace?.loaded();
  inspectionWorkspace?.schedule();
}

function activateResource(key) {
  if (key === "add:observations") addTable();
  else if (key.startsWith("add:model:")) {
    const record = state.records.get(key.slice("add:model:".length));
    const node = addModel(state.definition, record, defaults(record.research_contract.request_schema));
    state.tab = "connections";
    rebuild("node:" + node.code);
    modified();
  } else select(key);
}

function addTable() {
  const code = addObservationInput(state.definition);
  rebuild("input:" + code);
  modified();
}

function createObservation() {
  byId("system-input-workspace").scrollIntoView({ behavior: "smooth", block: "start" });
  byId("input-catalog-search").focus();
}

function chooseSource(source) {
  state.source = sourceKey(state.source) === sourceKey(source) ? null : source;
  graph.connectFrom(state.source);
  counts();
}

function writeConnection(nodeCode, port, source) {
  try {
    const node = state.definition.composition.nodes.find((item) => item.code === nodeCode);
    connectInput(state.definition, state.records, node, port, source);
    state.source = null;
    state.tab = "connections";
    rebuild("node:" + nodeCode);
    modified();
    notify(source ? "已连接输入端口" : "已断开输入连接");
    return true;
  } catch (error) {
    notify(error.message);
    return false;
  }
}

function chooseTarget(nodeCode, port) {
  if (!state.source) {
    state.tab = "connections";
    select("node:" + nodeCode);
    notify("先点击来源的输出端口。");
    return;
  }
  if (writeConnection(nodeCode, port, state.source)) graph.focusInput("node:" + nodeCode, port);
}

function moveNode(key, position) {
  const layout = state.definition.layout;
  state.definition.layout = {
    ...layout, designer_positions: { ...layout?.designer_positions, [key]: position },
  };
  modified();
}

function showCheck(result) {
  const issue = result.issues[0];
  state.issue = issue || null;
  const configIssue = issue?.path?.[0] === "input_recipes";
  const model = issue?.node ? state.flow.models.find((item) => item.code === issue.node)
    : configIssue ? state.flow.models.find((item) => requestInput(state.definition, item.node) === issue.path[1]) : null;
  if (issue?.path?.[0] === "question") select("plan");
  else if (issue?.path?.[0] === "variables" && state.definition.variables[issue.path[1]]) {
    select("variable:" + state.definition.variables[issue.path[1]].code);
  } else if (model) {
    state.tab = "parameters";
    select(model.key);
  } else renderInspector();
  const record = model && state.records.get(recordKey(model.node.component));
  const message = issueMessage(issue, record);
  status(message, result.valid ? "valid" : "error");
  if (matchMedia("(max-width: 670px)").matches) notify(message);
}

function download(configuration) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(configuration) + "\n"], { type: "application/json" }));
  const anchor = element("a", "");
  anchor.href = url;
  anchor.download = (state.definition.name || "研究方案").replace(/[<>:"/\\|?*]/g, "_").slice(0, 50) + ".json";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function loadRecords(definition) {
  const graph = definition.composition;
  if (![graph?.nodes, graph?.inputs, graph?.outputs, definition.variables, definition.collection_requirements,
    definition.evaluation?.target_codes].every(Array.isArray) || !definition.input_recipes) {
    throw new Error("无法读取方案结构，请核对配置文件。");
  }
  const pending = new Map();
  for (const node of graph.nodes) {
    const ref = node.component;
    if (!/^[a-z][a-z0-9_]{0,95}$/.test(ref?.code) || !Number.isInteger(ref.revision)) {
      throw new Error("组件版本格式无效。");
    }
    const key = recordKey(ref);
    if (!state.records.has(key) && !pending.has(key)) {
      pending.set(key, request(CATALOG + "/" + ref.code + "?revision=" + ref.revision));
    }
  }
  await Promise.all([...pending].map(async ([key, result]) => state.records.set(key, await result)));
}

async function apply(action, file) {
  const generation = state.generation;
  const reading = action === "import" || action === "restore";
  state.busy = true;
  buttons();
  status(reading ? "正在读取草稿…" : "正在校验方案…");
  try {
    const result = reading
      ? await request("./import", action === "restore" ? state.saved : await file.text())
      : await request("./validate", state.definition);
    if (reading) await loadRecords(result.configuration.definition);
    if (generation !== state.generation) {
      notify("方案已更新，请重试操作。");
      return;
    }
    if (reading) {
      load(result.configuration.definition);
      byId("plan-state").textContent = action === "restore" ? "已保存到浏览器" : "已导入草稿";
    }
    showCheck(result.check);
    if (action === "export") {
      download(result.configuration);
      notify("已导出 JSON 草稿");
    }
    if (action === "save") {
      const draft = JSON.stringify(result.configuration);
      try { localStorage.setItem(DRAFT_KEY, draft); }
      catch { throw new Error("浏览器无法保存草稿，请使用导出 JSON。"); }
      state.saved = draft;
      byId("plan-state").textContent = "已保存到浏览器";
      notify(result.check.valid ? "草稿已保存到浏览器" : "未完成的草稿已保存到浏览器");
    }
  } catch (error) {
    status(error.message || "操作未完成，请重试。", "error");
  } finally {
    state.busy = false;
    buttons();
  }
}
async function boot() {
  try {
    const first = await request(CATALOG + "?page_size=100");
    const pages = Math.ceil(first.total / first.page_size);
    const other = await Promise.all(Array.from({ length: Math.max(0, pages - 1) }, (_, index) =>
      request(CATALOG + "?page_size=100&page=" + (index + 2))));
    state.catalog = [first, ...other].flatMap(({ items }) => items).filter((item) =>
      item.available_for_new_design && item.definition.composable);
    for (const item of state.catalog) state.records.set(recordKey(item.definition), item);
    load(blankPlan());
    const inputCatalog = await request("/api/v1/model-center/research-inputs");
    state.inputCatalog = inputCatalog;
    inputWorkspace = mountSystemInputs({
      catalog: inputCatalog, getDefinition: () => state.definition, getRecords: () => state.records, notify,
      configure: (value) => request("/api/v1/model-center/research-inputs/configure", value),
      onEdit(definition) { state.definition = definition; heading(); rebuild("plan"); modified(); },
    });
    byId("plan-state").textContent = "新建方案";
    try { state.saved = localStorage.getItem(DRAFT_KEY); }
    catch { state.saved = null; }
    const url = new URL(location.href);
    if (url.searchParams.get("example") === "chain") {
      if (await openChain()) {
        url.searchParams.delete("example");
        history.replaceState(history.state, "", url);
      } else if (state.saved) await apply("restore");
    } else if (state.saved) await apply("restore");
  } catch (error) {
    byId("stage-loading").textContent = "组件目录加载失败，请刷新重试。";
    status(error.message, "error");
  } finally {
    state.busy = false;
    buttons();
  }
}

async function openExample() {
  if (!researchWorkspace) { notify("正在连接研究工作区，请稍后重试。"); return; }
  await researchWorkspace.openExample("system");
}

async function openChain(focusBoard = false) {
  const generation = state.generation;
  state.busy = true;
  buttons();
  try {
    const definition = await request("./chain-example.json");
    await loadRecords(definition);
    if (generation !== state.generation) throw new Error("方案已更新，请重试操作。");
    load(definition);
    byId("plan-state").textContent = "串联样例";
    zoom(1);
    if (focusBoard) byId("board-title").focus();
    return true;
  } catch (error) {
    notify(error.message);
  } finally {
    state.busy = false;
    buttons();
  }
}

function showLibrary(kind) {
  state.library = kind;
  byId("show-components").setAttribute("aria-pressed", String(kind === "components"));
  byId("show-variables").setAttribute("aria-pressed", String(kind === "variables"));
  byId("library-search").placeholder = kind === "components" ? "搜索组件" : "搜索变量";
  byId("library-search").value = "";
  renderResources();
  buttons();
}

function zoom(value) {
  state.zoom = Math.max(.7, Math.min(1.1, Math.round(value * 10) / 10));
  graph.zoom(state.zoom);
  byId("zoom-reset").textContent = Math.round(state.zoom * 100) + "%";
  byId("zoom-out").disabled = state.zoom <= .7;
  byId("zoom-in").disabled = state.zoom >= 1.1;
}

byId("show-components").addEventListener("click", () => showLibrary("components"));
byId("component-library-link").addEventListener("click", (event) => {
  event.preventDefault(); technical(true); byId("library-search").focus();
});
byId("show-variables").addEventListener("click", () => showLibrary("variables"));
byId("library-search").addEventListener("input", renderResources);
byId("zoom-out").addEventListener("click", () => zoom(state.zoom - .1));
byId("zoom-in").addEventListener("click", () => zoom(state.zoom + .1));
byId("zoom-reset").addEventListener("click", () => zoom(1));
byId("edit-plan").addEventListener("click", () => {
  wizardWorkspace?.reset();
  document.querySelector('[data-stage="configure"]').click();
  byId("wizard-name").focus();
});
byId("new-plan").addEventListener("click", () => {
  load(blankPlan());
  wizardWorkspace?.reset();
  byId("plan-state").textContent = "新建方案";
  zoom(1);
});
byId("reset-plan").addEventListener("click", openExample);
byId("chain-plan").addEventListener("click", () => researchWorkspace ? researchWorkspace.openExample("chain") : openChain(true));
byId("empty-example").addEventListener("click", openExample);
byId("empty-add").addEventListener("click", () => byId("edit-plan").click());
byId("add-variable").addEventListener("click", createObservation);
byId("auto-layout").addEventListener("click", () => {
  if (state.definition.layout) delete state.definition.layout.designer_positions;
  zoom(1); rebuild(state.selected); modified();
});
byId("open-local").addEventListener("click", () => apply("restore"));
byId("import-plan").addEventListener("click", () => byId("plan-file").click());
byId("plan-file").addEventListener("change", (event) => {
  const [file] = event.target.files;
  event.target.value = "";
  if (!file) return;
  if (file.size > REQUEST_BUDGET) { status("方案文件超过大小预算。", "error"); return; }
  apply("import", file);
});
byId("validate-plan").addEventListener("click", () => apply("validate"));
byId("export-plan").addEventListener("click", () => apply("export"));
byId("save-plan").addEventListener("click", () => apply("save"));
modelingWorkspace = mountModeling({
  getDefinition: () => state.definition, getRecords: () => state.records, notify,
  onEdit(definition) { state.definition = definition; heading(); rebuild(state.selected); modified(); },
  onExample(kind) {
    if (!researchWorkspace) throw new Error("正在连接工作区，请稍后重试。");
    return researchWorkspace.openExample(kind);
  },
  onTechnical(key) { technical(true); if (key) { state.tab = "parameters"; select(key); } },
});
wizardWorkspace = mountWizard({
  getDefinition: () => state.definition && structuredClone(state.definition), getRecords: () => state.records,
  getMethod: (component) => state.methods.get(recordKey(component)),
  getInputCatalog: () => state.inputCatalog,
  getInspection: () => inspectionWorkspace?.get(),
  onEdit(definition) { state.definition = definition; heading(); rebuild(state.selected); modified(); },
  onExample(kind) {
    if (!researchWorkspace) throw new Error("正在连接工作区，请稍后重试。");
    return researchWorkspace.openExample(kind, { persist: false });
  },
  onTechnical: () => technical(true),
  onSave() {
    if (!researchWorkspace) throw new Error("个人工作区仍在连接，请稍后保存。");
    return researchWorkspace.publishConfiguration();
  },
  onChooseIndicators: (role) => inputWorkspace?.setAdoptionRole(role),
  validate: async (definition) => (await request("./validate", definition)).check,
});
methodWorkspace = mountMethodPicker({
  getDefinition: () => state.definition && structuredClone(state.definition), getRecords: () => state.records, notify,
  loadMethods: loadResearchMethods,
  onEdit(definition) { state.definition = definition; heading(); rebuild("plan"); modified(); },
  validate: async (definition) => (await request("./validate", definition)).check,
});
inspectionWorkspace = mountInspection({
  getDefinition: () => state.definition,
  inspect: async (definition) => (await request("./validate", definition)).inspection,
  onChange() { wizardWorkspace?.render(); },
  onEdit(definition) { state.definition = definition; modified(); },
});
// 公开目录独立读取，个人工作区或本地草稿初始化失败不会阻断目录展示。
const libraryReady = mountStudyLibrary({ openTemplate: (id, persist) => {
  if (!researchWorkspace) throw new Error("设计器尚未准备好，请等待初始化完成或重新加载页面。当前方案目录仍可浏览。");
  return researchWorkspace.openTemplate(id, persist);
} });
await boot().then(() => {
  researchWorkspace = mountResearch({
    getDefinition: () => structuredClone(state.definition), getRecords: () => state.records, notify,
    async configureTemplate(definition) {
      if (definition.purpose !== "train" || Object.values(definition.input_recipes).some((recipe) => recipe.kind === "artifact")) return definition;
      await loadResearchMethods();
      const configured = structuredClone(definition);
      for (const node of configured.composition.nodes) {
        const method = state.methods.get(recordKey(node.component));
        if (method) useMethodDefaults(configured, node, method.configuration);
      }
      return configured;
    },
    onDataChange(table, dataKind) {
      modelingWorkspace.setData(table); wizardWorkspace.setData(table, dataKind);
      inspectionWorkspace.setObservations(table, dataKind);
    },
    onRunChange(run) { modelingWorkspace.setRun(run); wizardWorkspace.setRun(run); },
    onFlowChange(context) { showStudyFlow({ ...context, inputCatalog: state.inputCatalog }, state.records); },
    onModelChange: () => wizardWorkspace.openReview(),
    onTemplateChange(value, { preview = false } = {}) {
      wizardWorkspace.setTemplate(value);
      showTemplateSummary(value, { getDefinition: () => structuredClone(state.definition), getRecords: () => state.records,
        onEdit(definition) { state.definition = definition; heading(); rebuild(state.selected); modified(); } });
      if (value) technical(false);
      if (value && preview) { wizardWorkspace.openInputs(); byId("study-template-summary").scrollIntoView({ behavior: "smooth", block: "start" }); }
    },
    onError: (message) => wizardWorkspace.showError(message),
    beforeRun: () => wizardWorkspace.beforeRun(),
    openDefinition: async (definition) => {
      await loadRecords(definition);
      load(definition);
      showCheck((await request("./validate", definition)).check);
    },
  });
});
await libraryReady;
