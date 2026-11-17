import { element } from "./visuals.js?v=continuous1";
import { inputChoices, nodeRecord, requestInput, sourceFor, sourceFromKey, sourceKey } from "./editor.js?v=continuous1";
import { choices, field, parameters, selectField } from "./schema-fields.js?v=continuous1";

const roles = { driver: "驱动变量", target: "目标变量", validation: "验证变量", covariate: "候选因子" };
const objectives = { prediction: "训练与预测", association: "探索变量关系", treatment_effect: "处理效应", mechanistic: "机理模拟" };
const purposes = { train: "训练", explore: "探索", fit: "拟合", simulate: "模拟", predict: "预测", evaluate: "评价" };

export function describe(definition, records) {
  const { inputs, nodes, outputs } = definition.composition;
  const models = nodes.map((node) => {
    const { definition: model } = nodeRecord(node, records);
    return {
      key: "node:" + node.code, code: node.code, kind: "model", name: model.name,
      subtitle: model.code, glyph: "ƒ", revision: "V" + model.revision,
      sockets: model.inputs, outgoing: model.outputs, node,
      configurationPorts: node.bindings.filter((binding) => !binding.source.node && definition.input_recipes[binding.source.port]?.kind === "configuration").map((binding) => binding.port),
    };
  });
  const edges = nodes.flatMap((node) => node.bindings.map(({ source, port }) =>
    [source.node ? "node:" + source.node : "input:" + source.port, "node:" + node.code, port, source.port]));
  return {
    inputs: inputs.map((input) => {
      const observation = definition.input_recipes[input.code]?.kind === "observations";
      const configuration = definition.input_recipes[input.code]?.kind === "configuration";
      return { ...input, key: "input:" + input.code, kind: observation ? "observation" : configuration ? "parameter" : "artifact",
        subtitle: observation ? "按对象与日期对齐" : configuration ? "研究设置" : "已选择的研究数据", glyph: observation ? "▦" : configuration ? "≡" : "→" };
    }),
    models,
    outputs: outputs.map((output) => {
      const model = models.find((item) => item.code === output.source.node);
      const port = model?.outgoing.find((item) => item.code === output.source.port);
      return { ...output, key: "output:" + output.code, kind: "output", glyph: "→",
        name: port?.name || output.source.port, subtitle: model?.name || output.code, port };
    }),
    edges: edges.concat(outputs.map(({ code, source }) => ["node:" + source.node, "output:" + code, null, source.port])),
  };
}

export function renderFlowSummary(summary, list, flow) {
  const models = new Map(flow.models.map((model) => [model.key, model]));
  const links = [];
  for (const [from, to, inputCode, outputCode] of flow.edges) {
    const upstream = models.get(from);
    const downstream = models.get(to);
    const output = upstream?.outgoing.find((port) => port.code === outputCode);
    const input = downstream?.sockets.find((port) => port.code === inputCode);
    if (!output || !input) continue;
    const row = element("li", "flow-link");
    const end = (model, port) => {
      const label = element("span", "flow-end");
      label.append(element("strong", "", port.name), element("small", "", model.name));
      return label;
    };
    row.append(end(upstream, output), element("span", "flow-arrow", "→"), end(downstream, input));
    links.push(row);
  }
  list.replaceChildren(...links);
  summary.hidden = !links.length;
}

function chip(kind, glyph) {
  const item = element("span", "resource-chip " + kind, glyph);
  item.setAttribute("aria-hidden", "true");
  return item;
}

export function resources(list, groups, search, selected, select) {
  const query = search.trim().toLowerCase();
  const sections = groups.map(([title, items]) => {
    const group = element("section", "resource-group");
    group.append(element("h3", "resource-heading", title));
    for (const item of items) {
      if (query && !(item.name + " " + item.subtitle).toLowerCase().includes(query)) continue;
      const button = element("button", "resource");
      button.type = "button";
      button.dataset.resource = item.key;
      button.setAttribute("aria-pressed", String(selected === item.key));
      const text = element("span", "");
      text.append(element("strong", "resource-title", item.name), element("small", "", item.subtitle));
      const caret = element("span", "resource-caret", item.add ? "＋" : "›");
      caret.setAttribute("aria-hidden", "true");
      button.append(chip(item.kind, item.glyph), text, caret);
      button.addEventListener("click", () => select(item.key));
      group.append(button);
    }
    return group;
  }).filter((group) => group.childElementCount > 1);
  list.replaceChildren(...(sections.length ? sections : [element("p", "resource-empty", "没有匹配的资源。")]));
}

function detailList(rows) {
  const list = element("dl", "detail-list");
  for (const [label, value] of rows) {
    const row = element("div", "");
    row.append(element("dt", "", label), element("dd", "", value));
    list.append(row);
  }
  return list;
}

function header(item, subtitle = item.subtitle) {
  const node = element("div", "inspector-node");
  const text = element("div", "");
  text.append(element("h3", "", item.name), element("p", "", subtitle));
  node.append(chip(item.kind, item.glyph), text);
  return node;
}

function tabs(current, setTab, hasParameters) {
  const group = element("div", "segments");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "组件属性");
  const entries = [["connections", "连线与成果"], ...(hasParameters ? [["parameters", "组件参数"]] : []), ["contract", "组件合同"]];
  for (const [key, text] of entries) {
    const button = element("button", "", text);
    button.type = "button";
    button.setAttribute("aria-pressed", String(key === current));
    button.addEventListener("click", () => setTab(key));
    group.append(button);
  }
  return group;
}

function planFields(definition, update) {
  const grid = element("div", "field-grid");
  for (const [name, title, maxLength] of [["name", "方案名称", 128], ["question", "研究问题", 2000]]) {
    const control = element(name === "name" ? "input" : "textarea", "");
    control.maxLength = maxLength;
    control.value = definition[name] ?? "";
    control.addEventListener("input", () => update(name, control.value));
    grid.append(field(title, name, control, true));
  }
  for (const [name, title, options] of [["objective", "研究目标", objectives], ["purpose", "研究用途", purposes]]) {
    grid.append(field(title, name, selectField(Object.entries(options), definition[name], (value) => update(name, value)), true));
  }
  const targets = definition.variables.filter((item) => definition.evaluation.target_codes.includes(item.code));
  grid.append(element("p", "field-note schema-note", "目标变量 · " + (targets.map((item) => item.name).join("、") || "请添加要研究或预测的变量。")));
  return grid;
}

function variableFields(variable, requirement, callbacks) {
  const grid = element("div", "field-grid");
  for (const [name, title] of [["name", "变量名称"], ["unit", "单位"]]) {
    const control = element("input", "");
    control.maxLength = 128;
    control.value = variable[name];
    control.readOnly = Boolean(requirement);
    control.addEventListener("input", () => callbacks.updateVariable(variable.code, name, control.value));
    grid.append(field(title, "variable-" + name, control, name === "name"));
  }
  const options = Object.entries(roles);
  if (!roles[variable.role]) options.push([variable.role, variable.role]);
  grid.append(field("变量角色", "variable-role", selectField(
    options, variable.role, (value) => callbacks.updateVariable(variable.code, "role", value),
  )));
  if (requirement) {
    grid.append(element("p", "field-note schema-note", "固定观测单位 · " + requirement.unit_kind + "；来源与单位在研究输入中查看。"));
    for (const [name, title, max] of [["interval_days", "采样间隔（天）", 366],
      ["minimum_observations_per_unit", "每地块最低记录数", 10000],
      ["minimum_independent_units", "最低独立单位数", 10000]]) {
      const control = element("input", "");
      control.type = "number";
      control.min = "1";
      control.max = String(max);
      control.value = requirement[name] ?? "";
      control.addEventListener("input", () => callbacks.updateRequirement(requirement.code, name, control.valueAsNumber));
      grid.append(field(title, name, control, true));
    }
  }
  return grid;
}

function connectionFields(definition, records, model, callbacks) {
  const fields = element("div", "field-grid");
  for (const port of model.sockets) {
    const options = inputChoices(definition, records, model.node, port.code).map((item) => [sourceKey(item), item.name]);
    const select = selectField([["", "未连接"], ...options], sourceKey(sourceFor(model.node, port.code)),
      (source) => callbacks.connectInput(model.code, port.code, sourceFromKey(source)));
    fields.append(field(port.name, "link-" + port.code, select, true));
  }
  const outputChoices = model.outgoing.map((port) => [
    port.code, port.name,
    definition.composition.outputs.some((output) => output.source.node === model.code && output.source.port === port.code),
  ]);
  return [fields, element("p", "field-note", "保留成果"),
    choices(outputChoices, (port, enabled) => callbacks.setOutput(model.code, port, enabled), "output")];
}

function action(label, handler, className = "button button-secondary inspector-action") {
  const button = element("button", className, label);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

export function inspect(container, state, callbacks) {
  const { definition, records, flow, selected, tab, issue } = state;
  const item = [...flow.inputs, ...flow.models, ...flow.outputs].find((entry) => entry.key === selected);
  if (selected === "plan") {
    container.replaceChildren(planFields(definition, callbacks.updatePlan),
      action("从系统目录选择输入", callbacks.addObservation),
      action("新增预测因子", callbacks.addDerived));
    return "方案信息";
  }
  const remove = item && action("移除" + item.name, () => callbacks.removeNode(item.key), "text-button remove-node");
  if (item?.kind === "model" || item?.kind === "parameter") {
    const isModel = item.kind === "model";
    const model = isModel ? item : flow.models.find((entry) => requestInput(definition, entry.node) === item.code);
    const record = model && nodeRecord(model.node, records);
    const schema = record?.research_contract?.request_schema;
    const request = model && requestInput(definition, model.node);
    const current = isModel ? (!schema && tab === "parameters" ? "connections" : tab) : "parameters";
    const parts = [header(item, isModel ? item.revision + " · " + item.subtitle : item.subtitle)];
    if (isModel) parts.push(tabs(current, callbacks.setTab, Boolean(schema)));
    if (current === "connections") {
      parts.push(...connectionFields(definition, records, model, callbacks));
    } else if (current === "contract") {
      parts.push(element("p", "inspector-description", record.definition.summary), detailList([
        ["输入", model.sockets.map((port) => port.name).join("、")],
        ["输出", model.outgoing.map((port) => port.name).join("、")],
        ["摘要", record.contract_sha256],
      ]));
    } else if (schema && request) {
      parts.push(parameters(definition, model.node, schema, request, callbacks.updateParameter, issue));
    } else if (isModel) {
      parts.push(action("添加组件配置", () => callbacks.addConfiguration(model.node, record)));
    } else {
      parts.push(element("p", "field-note", "连接到组件后可以编辑此输入的配置。"));
    }
    container.replaceChildren(...parts, remove);
    return isModel ? "计算组件" : "配置输入";
  }
  if (item?.kind === "observation") {
    const codes = definition.input_recipes[item.code]?.variable_codes || [];
    container.replaceChildren(header(item), element("p", "field-note", "纳入观测表的变量"),
      choices(definition.variables.filter((variable) => codes.includes(variable.code)
        || definition.collection_requirements.some((entry) => entry.variable_code === variable.code
          && entry.required_for.includes(definition.purpose))).map((variable) => [
        variable.code, variable.name + " · " + variable.unit, codes.includes(variable.code),
      ]), (code, included) => callbacks.setObservationColumn(item.code, code, included), "column"),
      action("从系统目录选择输入", callbacks.addObservation), remove);
    return "数据输入";
  }
  if (item?.kind === "output") {
    container.replaceChildren(header(item), element("p", "inspector-description", item.port?.description),
      detailList([["上游组件", item.subtitle], ["输出端口", item.source.port],
        ["数据类型", item.port?.data_type.semantic || item.source.port]]), remove);
    return "成果输出";
  }
  const variable = definition.variables.find((entry) => "variable:" + entry.code === selected);
  const requirement = definition.collection_requirements.find((entry) => entry.variable_code === variable.code);
  container.replaceChildren(element("p", "field-note", "变量代码 · " + variable.code),
    variableFields(variable, requirement, callbacks));
  return "研究变量";
}

export function issueMessage(issue, record) {
  if (!issue) return "方案通过合同校验";
  const name = issue.path?.at(-1);
  const node = record?.definition.name || issue.node || "当前组件";
  const port = record?.definition.inputs.find((item) => item.code === issue.port)?.name || issue.port || "输入";
  if (issue.type === "missing_input") return node + "的「" + port + "」尚未连接，请补齐该输入。";
  if (issue.type === "incompatible_connection") return node + "的「" + port + "」资料类型、单位或对齐规则不匹配。";
  if (["unresolved_source", "invalid_port"].includes(issue.type)) return node + "的「" + port + "」引用不存在或重复，请检查这条连接。";
  if (issue.type === "unknown_component") return "该计算步骤引用了未登记的模型版本，请从模型目录重新选择。";
  if (issue.type === "dependency_cycle") return "计算步骤形成了循环依赖，请检查这些节点的前后连接。";
  if (issue.type === "invalid_indicator") return "研究输入的「" + ({ unit: "科学单位", name: "指标名称" }[name] || name) + "」与系统指标库不一致。";
  if (issue.type === "invalid_source") return "研究输入的来源、版本或取数属性与系统目录不一致，请重新选择该指标。";
  if (issue.path?.[0] === "question") return "请填写研究问题。";
  if (name === "nodes") return "请从资源库添加计算组件。";
  if (issue.path?.includes("outputs")) return "请选择至少一个成果输出。";
  if (issue.path?.includes("target_codes") || issue.message.includes("Evaluation targets")) return "请设置至少一个目标变量，并核对其角色。";
  if (issue.message.includes("Required input bindings")) return "组件输入尚未连齐，请核对画布上的端口。";
  if (issue.message.includes("unused external inputs")) return "有未使用的输入，请连接或移除。";
  if (issue.message.includes("unrelated to its outputs")) return "有组件未连到成果，请选择成果或连到下游组件。";
  if (issue.message.includes("Logistic driver must use unit")) return "驱动变量的单位与时间轴不匹配。";
  if (issue.message.includes("upstream table does not supply")) return "上游输出缺少配置所选变量，请核对输出列或先合并观测表。";
  if (issue.message.includes("training target requires an observed")) return "训练目标必须来自实测。请把模型预测作为因子与观测表合并。";
  if (issue.message.includes("same unit")) return "预测因子需要独立列名，并且单位须与上游变量相同。";
  if (issue.message.includes("must follow the baseline")) return "回归训练截止日期须晚于历史基线的训练截止日期。";
  if (issue.message.includes("historical designs only")) return "此版本用于历史方案，新设计请选择已采用版本。";
  const property = record?.research_contract?.request_schema?.properties?.[name];
  if (property) return (property.title || name) + "未填写或不符合组件合同，请核对观测列和参数。";
  return "方案未通过校验，请核对变量、采样要求和组件合同。";
}
