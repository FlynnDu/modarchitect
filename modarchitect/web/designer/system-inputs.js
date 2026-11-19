import { element } from "./visuals.js?v=continuous1";
import { addModel, addObservationInput, connectInput, recordKey, setOutput } from "./editor.js?v=continuous1";
import { editStudy, formatUnit, inputUsageRows, studySettings } from "./modeling.js?v=continuous1";
import { canAddInput, inputGroup, inputProvision } from "./input-provision.js?v=continuous1";

const units = { field_season: "地块种植季", point: "采样点", plant: "单株", quadrat: "样方", soil_layer: "土层" };

export function addSystemInput(definition, configuration, inputPort = null, records = new Map()) {
  const { variable, requirement } = configuration;
  if (definition.variables.some((v) => v.code === variable.code)) throw new Error("这个指标已在方案中，不能重复添加；需要更换用途时，请先调整原选择。");
  const ports = Object.entries(definition.input_recipes).filter(([, recipe]) => recipe.kind === "observations");
  if (ports.length > 1 && !inputPort) throw new Error("请明确将指标加入哪一组研究数据。");
  const selected = inputPort ? ports.find(([port]) => port === inputPort) : ports[0];
  if (inputPort && !selected) throw new Error("请选择当前方案已有的观测输入组。");
  if (definition.schema_version !== "1.5") definition.schema_version = "1.4";
  definition.variables.push(structuredClone(variable));
  definition.collection_requirements.push({ ...structuredClone(requirement), required_for: [definition.purpose] });
  if (selected) selected[1].variable_codes.push(variable.code);
  if (variable.role === "target") definition.evaluation.target_codes.push(variable.code);
  const context = studySettings(definition, records);
  if (context && selected?.[0] === context.observed) {
    const changes = variable.role === "target" ? { targets: [...context.parameters.targets, variable.code] }
      : { features: [...context.parameters.features, variable.code] };
    Object.assign(definition, editStudy(definition, changes, records));
  }
}

export function buildInputModel(definition, records, trainingEnd) {
  if (definition.composition.nodes.length) throw new Error("当前已有模型，请在研究设置中选择新增因素。");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trainingEnd)) throw new Error("请明确训练截止日期。");
  const inputs = new Set(definition.collection_requirements.filter((r) => r.catalog_binding).map((r) => r.variable_code));
  const targets = definition.variables.filter((v) => inputs.has(v.code) && v.role === "target").map((v) => v.code);
  const features = definition.variables.filter((v) => inputs.has(v.code) && ["driver", "covariate"].includes(v.role)).map((v) => v.code);
  if (!targets.length || !features.length) throw new Error("请从系统目录选择至少一个实测目标和一个已知因素。");
  const record = records.get(recordKey({ code: "multivariate_linear_training", revision: 1 }));
  if (!record) throw new Error("多变量训练组件尚未加载。");
  const code = Object.keys(definition.input_recipes).find((c) => definition.input_recipes[c].kind === "observations") || addObservationInput(definition);
  const node = addModel(definition, record, { features, targets, training_end: trainingEnd });
  connectInput(definition, records, node, "observations", { node: null, port: code });
  for (const port of record.definition.outputs) setOutput(definition, node.code, port.code, true);
  if (!definition.question.trim()) definition.question = "研究" + targets.map((c) => definition.variables.find((v) => v.code === c).name).join("、") + "与所选因素的预测关系";
}

export function mountSystemInputs({ catalog, getDefinition, getRecords, onEdit, configure, notify, onChooseMethod }) {
  let category = "manual", subcategory = "", query = "", adoptionRole = null;
  const host = document.getElementById("input-catalog-list"), chosen = document.getElementById("selected-system-inputs");
  const subtabs = element("div", "input-subcategories"); subtabs.setAttribute("role", "group"); subtabs.setAttribute("aria-label", "细分输入类别");
  document.getElementById("input-categories").after(subtabs);
  const groupName = (entry) => inputGroup(catalog, entry);
  const selectedVariable = (entry) => getDefinition().variables.find((variable) => variable.code === entry.variable.code);
  const canAdopt = (entry) => canAddInput(entry) && !selectedVariable(entry) && (adoptionRole !== "target" || entry.source.binding?.value_nature === "observed");
  const counts = (items) => "已登记 " + items.length + " · 可添加 " + items.filter(canAdopt).length;
  function selected() {
    const plan = getDefinition(); chosen.replaceChildren();
    const items = plan.collection_requirements;
    if (!items.length) chosen.append(element("p", "modeling-muted", "从指标库添加模型输入和希望预测的输出指标。"));
    for (const requirement of items) {
      const variable = plan.variables.find((v) => v.code === requirement.variable_code);
      const provision = inputProvision(requirement, catalog), entry = provision.entry;
      const row = element("div", "input-selected");
      row.append(element("strong", "", variable.name), element("span", "", formatUnit(variable.unit) + " · " + (units[requirement.unit_kind] || requirement.unit_kind)),
        element("span", "", provision.label));
      // 来源只说明取数定义；同一指标在不同节点的用途由建模关系展示。
      for (const detail of provision.details) row.append(element("small", "", detail));
      if (entry && !plan.composition.nodes.length) {
        const remove = element("button", "text-button", "移除此输入"); remove.type = "button";
        remove.addEventListener("click", () => {
          const draft = structuredClone(getDefinition());
          draft.variables = draft.variables.filter((v) => v.code !== variable.code);
          draft.collection_requirements = draft.collection_requirements.filter((r) => r.variable_code !== variable.code);
          draft.evaluation.target_codes = draft.evaluation.target_codes.filter((c) => c !== variable.code);
          for (const recipe of Object.values(draft.input_recipes).filter((r) => r.kind === "observations")) recipe.variable_codes = recipe.variable_codes.filter((c) => c !== variable.code);
          onEdit(draft); render();
        });
        row.append(remove);
      }
      chosen.append(row);
    }
  }
  function render() {
    selected(); host.replaceChildren();
    for (const button of document.querySelectorAll('#input-categories [data-category]')) {
      const item = catalog.categories.find((entry) => entry.code === button.dataset.category);
      button.textContent = item.name + " · " + counts(catalog.items.filter((entry) => entry.category === item.code));
    }
    subtabs.replaceChildren();
    const children = catalog.categories.find((parent) => parent.code === category)?.children || [];
    subtabs.hidden = !children.length;
    for (const child of [{ code: "", name: "全部", count: null }, ...children]) {
      const items = catalog.items.filter((entry) => entry.category === category && (!child.code || entry.subcategory === child.code));
      const button = element("button", "button button-secondary", child.name + " · " + counts(items)); button.type = "button";
      button.dataset.subcategory = child.code; button.setAttribute("aria-pressed", String(child.code === subcategory));
      if (child.count === 0) button.title = "暂无已登记指标，分类不代表来源已接通";
      button.addEventListener("click", () => { subcategory = child.code; render(); }); subtabs.append(button);
    }
    const filtered = catalog.items.filter((entry) => entry.category === category && (!subcategory || entry.subcategory === subcategory) && (entry.variable.name + entry.variable.code + entry.source.name + groupName(entry)).toLowerCase().includes(query));
    for (const entry of filtered) {
      const card = element("article", "input-catalog-card"), variable = entry.variable;
      card.append(element("h3", "", variable.name), element("p", "", formatUnit(variable.unit) + " · " + (units[entry.unit_kind] || "报告覆盖范围")),
        element("p", "modeling-muted", [groupName(entry), "来源：" + entry.source.name].filter(Boolean).join(" · ")), element("small", "modeling-muted", variable.description));
      const note = element("p", entry.execution.available ? "input-channel-ready" : "input-channel-pending", entry.execution.available
        ? entry.execution.channel === "source_snapshot" ? "由平台采集并引用来源快照；不能用手工填写替代。" : "本工作区可按标准填写或导入；未接入业务系统自动同步。" : entry.execution.reason);
      card.append(note);
      if (entry.source.binding?.value_nature === "estimated") card.append(element("small", "modeling-muted", "提供方估计值，可作为因素，不能替代实测训练目标。"));
      if (entry.source.definition?.support?.temporal_support === "static") card.append(element("small", "modeling-muted", "静态网格参考；用于多个日期不等于每天独立实测。"));
      if (entry.source.definition?.support?.temporal_support === "scene_observation") card.append(element("small", "modeling-muted", "仅实际清晰过境日期有记录；不是逐日都有影像，缺日不填补。"));
      const existingVariable = selectedVariable(entry);
      if (existingVariable) {
        const usage = inputUsageRows(getDefinition(), getRecords()).find((row) => row.variable.code === variable.code);
        const role = usage?.role === "target" ? "target" : usage?.role === "covariate" ? "covariate" : existingVariable.role;
        const label = role === "target" ? "已选为目标指标（第03步）" : ["covariate", "driver"].includes(role) ? "已选为研究资料（第02步）" : "已在方案中采用";
        const selected = element("button", "button button-secondary", label); selected.type = "button"; selected.disabled = true;
        selected.dataset.inputRole = adoptionRole || role;
        card.append(element("p", "input-channel-pending", "不能重复添加；需要更换用途时，请先调整原选择。"), selected);
        host.append(card); continue;
      }
      if (!canAddInput(entry)) {
        const unavailable = element("button", "button button-secondary", entry.selectable ? "采样尺度待适配" : "待接入");
        unavailable.type = "button"; unavailable.disabled = true;
        card.append(unavailable); host.append(card); continue;
      }
      if (!canAdopt(entry)) {
        card.append(element("p", "input-channel-pending", "该来源不是实测，不能作为训练目标；可在研究资料步骤采用为模型输入。"));
        host.append(card); continue;
      }
      const selectors = {};
      for (const [name, schema] of Object.entries(entry.source.selection_schema.properties)) {
        const label = element("label", "", name === "depth" ? "土层深度" : name === "statistic" ? "统计方式" : name), select = element("select");
        select.add(new Option("请选择", ""));
        for (const value of schema.enum) select.add(new Option(value === "mean" ? "均值" : value, value));
        select.addEventListener("change", () => { selectors[name] = select.value; });
        label.append(select); card.append(label);
      }
      const inputPorts = getDefinition().composition.inputs.filter((port) => getDefinition().input_recipes[port.code]?.kind === "observations");
      let destination = null;
      if (inputPorts.length > 1) {
        const label = element("label", "", "加入哪组数据"), select = element("select"); select.add(new Option("请选择输入组", ""));
        for (const port of inputPorts) select.add(new Option(port.name, port.code)); label.append(select); card.append(label); destination = select;
      }
      const actions = element("div", "input-adopt-actions");
      const roles = adoptionRole ? [adoptionRole] : entry.source.binding?.value_nature === "observed" ? ["covariate", "target"] : ["covariate"];
      for (const role of roles) {
        const add = element("button", "button button-secondary", role === "target" ? "添加为预测输出" : "添加为模型输入");
        add.type = "button"; add.dataset.inputRole = role;
        add.setAttribute("aria-label", "将" + variable.name + add.textContent);
        add.addEventListener("click", async () => {
          if (selectedVariable(entry)) { notify("该指标已在研究资料或目标指标中，不能重复添加。"); render(); return; }
          for (const button of actions.children) button.disabled = true;
          try {
            const configured = await configure({ key: entry.key, selectors, role });
            const plan = structuredClone(getDefinition()); addSystemInput(plan, configured, destination?.value || null, getRecords()); onEdit(plan); render();
            notify("已加入「" + variable.name + "」，单位与来源已固定。");
          } catch (error) { notify(error.message); }
          finally { for (const button of actions.children) button.disabled = !canAddInput(entry); }
        }); actions.append(add);
      }
      card.append(actions); host.append(card);
    }
    if (!filtered.length) host.append(element("p", "modeling-muted", children.find((child) => child.code === subcategory)?.count === 0 ? "此分类暂时没有可选指标，待真实来源和科学单位确认后提供。" : "此类别中没有匹配指标。"));
    const plan = getDefinition(), existing = Boolean(plan.composition.nodes.length);
    document.getElementById("build-input-model").disabled = existing;
    const cutoff = document.getElementById("input-training-end");
    cutoff.disabled = existing;
    const context = studySettings(plan, getRecords());
    if (context) cutoff.value = context.parameters.training_end;
    document.querySelector(".input-model-build").hidden = existing || plan.purpose !== "train";
  }
  const tabs = document.getElementById("input-categories");
  for (const item of catalog.categories) {
    const button = element("button", "button button-secondary", item.name + " · " + counts(catalog.items.filter((entry) => entry.category === item.code))); button.type = "button";
    button.dataset.category = item.code; button.setAttribute("aria-pressed", String(category === item.code));
    button.addEventListener("click", () => { category = item.code; subcategory = ""; for (const tab of tabs.children) tab.setAttribute("aria-pressed", String(tab === button)); render(); });
    tabs.append(button);
  }
  document.getElementById("input-catalog-search").addEventListener("input", (event) => { query = event.target.value.toLowerCase().trim(); render(); });
  document.getElementById("build-input-model").addEventListener("click", () => {
    if (onChooseMethod) { onChooseMethod(); return; }
    try {
      const plan = structuredClone(getDefinition()); buildInputModel(plan, getRecords(), document.getElementById("input-training-end").value); onEdit(plan);
    } catch (error) { notify(error.message); }
  });
  for (const id of ["open-indicator-library", "open-output-library"]) document.getElementById(id).disabled = false;
  render(); return { render, setAdoptionRole(role) { adoptionRole = role; render(); } };
}
