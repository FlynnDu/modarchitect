const observationType = {
  semantic: "research_observation_table", version: 1, shape: "table",
  unit: "column_definitions", alignment: "business_date",
};

export const recordKey = (ref) => ref.code + "@" + ref.revision;
export const nodeRecord = (node, records) => records.get(recordKey(node.component));

export function blankPlan() {
  return {
    schema_version: "1.5", name: "未命名研究方案", question: "",
    objective: "prediction", purpose: "train", variables: [], collection_requirements: [],
    composition: { schema_version: "1.0", object_scope: "field_crop_season", inputs: [], nodes: [], outputs: [] },
    input_recipes: {},
    evaluation: {
      target_codes: [], purpose: "exploratory", split_unit: "time",
      success_criteria: "按各目标的观测值分别评价", update_policy: "manual_candidate",
    },
    layout: {},
  };
}

function availableCode(entries, prefix) {
  prefix = prefix.slice(0, 90);
  const used = new Set(entries.map((item) => item.code));
  let code = prefix;
  for (let index = 2; used.has(code); index++) code = prefix + "_" + index;
  return code;
}

export function sourceFor(node, port) {
  return node.bindings.find((binding) => binding.port === port)?.source;
}

export const sourceKey = (source) => source ? [source.node || "", source.port].join(":") : "";
export const sourceFromKey = (key) => {
  const [node, port] = key.split(":");
  return key ? { node: node || null, port } : null;
};

export function inputChoices(definition, records, node, port) {
  const type = nodeRecord(node, records)?.definition.inputs.find((item) => item.code === port)?.data_type;
  const configuration = port === "request" && nodeRecord(node, records)?.research_contract?.request_schema;
  const candidates = definition.composition.inputs.map((item) => ({
    name: item.name, type: item.data_type, node: null, port: item.code,
  }));
  if (!configuration) {
    for (const other of definition.composition.nodes.filter((item) => item.code !== node.code)) {
      const model = nodeRecord(other, records).definition;
      candidates.push(...model.outputs.map((item) => ({
        name: model.name + " · " + item.name, type: item.data_type, node: other.code, port: item.code,
      })));
    }
  }
  return candidates.filter((item) => type && Object.keys(type).every((key) => item.type?.[key] === type[key]));
}

export function connectInput(definition, records, node, port, source) {
  if (source && !inputChoices(definition, records, node, port).some((item) => sourceKey(item) === sourceKey(source))) {
    throw new Error("两个端口的数据类型不匹配，请选择对应输入。");
  }
  const dependsOn = (code, visited) => {
    if (code === node.code) return true;
    if (!code || visited.has(code)) return false;
    visited.add(code);
    return definition.composition.nodes.find((item) => item.code === code)?.bindings
      .some((binding) => dependsOn(binding.source.node, visited));
  };
  if (source?.node && dependsOn(source.node, new Set())) throw new Error("这条连线会形成循环。");
  node.bindings = node.bindings.filter((binding) => binding.port !== port);
  if (source) node.bindings.push({ port, source });
}

export function addObservationInput(definition) {
  const code = availableCode(definition.composition.inputs, "observations");
  definition.composition.inputs.push({ code, name: "观测表", data_type: { ...observationType }, role: "context" });
  definition.input_recipes[code] = {
    kind: "observations",
    variable_codes: [...new Set(definition.collection_requirements
      .filter((item) => item.required_for.includes(definition.purpose))
      .map((item) => item.variable_code))],
  };
  return code;
}

export function addDeferredInput(definition, node, port) {
  const code = availableCode(definition.composition.inputs, node.code + "_" + port.code);
  definition.composition.inputs.push({ code, name: port.name + "（待接入）", data_type: structuredClone(port.data_type), role: port.code === "request" ? "parameter" : "context" });
  definition.input_recipes[code] = { kind: "deferred", variable_codes: definition.collection_requirements.filter((r) => r.required_for.includes(definition.purpose)).map((r) => r.variable_code) };
  return { node: null, port: code };
}

export function addModel(definition, record, parameters) {
  const composition = definition.composition;
  const model = record.definition;
  const code = availableCode(composition.nodes, model.code);
  const node = { code, component: { code: model.code, revision: model.revision }, bindings: [], selections: {} };
  if (parameters) addConfiguration(definition, node, record, parameters);
  composition.nodes.push(node);
  return node;
}

export function addConfiguration(definition, node, record, parameters) {
  const model = record.definition;
  const request = model.inputs.find((port) => port.code === "request");
  if (!request) return;
  const inputs = definition.composition.inputs;
  const code = availableCode(inputs, node.code + "_request");
  inputs.push({ code, name: model.name + " · 配置", data_type: request.data_type, role: "parameter" });
  definition.input_recipes[code] = { kind: "configuration", value: parameters };
  node.bindings = node.bindings.filter((binding) => binding.port !== request.code);
  node.bindings.push({ port: request.code, source: { node: null, port: code } });
}

export function setOutput(definition, node, port, enabled) {
  const outputs = definition.composition.outputs;
  const index = outputs.findIndex((item) => item.source.node === node && item.source.port === port);
  if (!enabled && index >= 0) outputs.splice(index, 1);
  if (enabled && index < 0) outputs.push({
    code: availableCode(outputs, port), source: { node, port },
  });
}

export function removeNode(definition, key) {
  const [kind, code] = key.split(":");
  const composition = definition.composition;
  if (kind === "node") {
    const node = composition.nodes.find((item) => item.code === code);
    composition.nodes = composition.nodes.filter((item) => item.code !== code);
    composition.outputs = composition.outputs.filter((item) => item.source.node !== code);
    for (const other of composition.nodes) {
      other.bindings = other.bindings.filter((item) => item.source.node !== code);
    }
    const request = sourceFor(node, "request");
    if (request && !request.node && definition.input_recipes[request.port]?.kind === "configuration"
      && !composition.nodes.some((item) => item.bindings.some((binding) => sourceKey(binding.source) === sourceKey(request)))) {
      removeNode(definition, "input:" + request.port);
    }
  } else if (kind === "input") {
    composition.inputs = composition.inputs.filter((item) => item.code !== code);
    delete definition.input_recipes[code];
    for (const node of composition.nodes) {
      node.bindings = node.bindings.filter((item) => item.source.node || item.source.port !== code);
    }
  } else if (kind === "output") {
    composition.outputs = composition.outputs.filter((item) => item.code !== code);
  }
  if (definition.layout?.designer_positions) delete definition.layout.designer_positions[key];
}

export function requestInput(definition, node) {
  const source = sourceFor(node, "request");
  return source && !source.node && definition.input_recipes[source.port]?.kind === "configuration" ? source.port : null;
}
