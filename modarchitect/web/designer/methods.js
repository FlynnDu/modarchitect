import { addConfiguration, addDeferredInput, addModel, addObservationInput, connectInput, inputChoices, nodeRecord, recordKey, requestInput, setOutput, sourceKey } from "./editor.js?v=continuous1";
import { defaults, requestProperties, variableCandidates } from "./request-schema.js?v=continuous1";
import { ensureCalendarAxis } from "./calendar-axis.js?v=continuous1";

const capability = (record) => record?.research_contract.capabilities || record?.definition.configuration.research_model?.execution;
const sameType = (expected, actual) => Object.entries(expected).every(([key, value]) => actual?.[key] === value);

export function methodNodes(plan, records) {
  return plan.composition.nodes.filter((node) => {
    const record = nodeRecord(node, records);
    return record && !record.definition.configuration.research_model?.automatic_date_axis;
  });
}

export function selectableMethodNodes(plan, records) {
  const nodes = methodNodes(plan, records);
  if (plan.purpose !== "train") return nodes;
  return nodes.filter((node) => {
    const execution = capability(nodeRecord(node, records));
    return execution?.operations.includes("train") && execution.state_output;
  });
}

export function methodRestriction(record) {
  if (!record.available_for_new_design || !record.definition.composable) return "此版本不能用于新设计。";
  return null;
}

export function synchronizeLabels(plan, records) {
  let configured = false;
  const targets = [...new Set(plan.composition.nodes.flatMap((node) => {
    const record = nodeRecord(node, records), request = requestInput(plan, node);
    const value = request && plan.input_recipes[request].value;
    return requestProperties(record?.research_contract.request_schema, value).filter(([field, property]) => {
      const label = capability(record)?.input_uses?.[field]?.role === "label" || property["x-research-variables"]?.roles?.join() === "target";
      if (label && value) configured = true;
      return label;
    })
      .flatMap(([field]) => value?.[field] === undefined ? [] : Array.isArray(value[field]) ? value[field] : [value[field]]);
  }))];
  if (configured) plan.evaluation.target_codes = targets;
}

export function prepareMethodDraft(plan, records, key, nodeCode = null, trainingEnd = "", { deferParameters = false, configuration } = {}) {
  const record = records.get(key);
  if (!record?.available_for_new_design) throw new Error("请选择当前目录允许采用的准确方法版本。");
  const restriction = methodRestriction(record); if (restriction) throw new Error(restriction);
  const draft = structuredClone(plan), initialInputs = new Set(plan.composition.inputs.map((input) => input.code));
  const old = draft.composition.nodes.find((node) => node.code === nodeCode);
  if (nodeCode && !old) throw new Error("原计算步骤已变化，请重新打开方法选择。");
  const previousRequest = old && requestInput(draft, old);
  const previous = previousRequest ? draft.input_recipes[previousRequest].value : {};
  const oldSources = old?.bindings.filter((binding) => binding.port !== "request") || [];
  const changed = !old || recordKey(old.component) !== key;
  const node = old || addModel(draft, record);
  node.component = { code: record.definition.code, revision: record.definition.revision };
  node.bindings = []; node.selections = {};
  draft.schema_version = "1.5";
  if (!Object.values(draft.input_recipes).some((recipe) => recipe.kind === "observations") && draft.collection_requirements.length) addObservationInput(draft);
  for (const port of record.definition.inputs.filter((item) => item.code !== "request")) {
    const choices = inputChoices(draft, records, node, port.code);
    const retained = choices.filter((choice) => oldSources.some((binding) => sourceKey(binding.source) === sourceKey(choice)));
    let selected = retained.length === 1 ? retained[0] : choices.length === 1 ? choices[0] : null;
    if (!selected && port.required === false) continue;
    if (!selected && !choices.length) selected = addDeferredInput(draft, node, port);
    if (!selected) throw new Error("需要明确的「" + port.name + "」；当前输入不是该方法要求的资料，或有多组输入待选择。");
    connectInput(draft, records, node, port.code, { node: selected.node, port: selected.port });
  }
  for (const consumer of draft.composition.nodes.filter((item) => item.code !== node.code)) {
    for (const binding of consumer.bindings.filter((item) => item.source.node === node.code)) {
      const output = record.definition.outputs.find((item) => item.code === binding.source.port);
      const input = nodeRecord(consumer, records).definition.inputs.find((item) => item.code === binding.port);
      if (!output || !sameType(input.data_type, output.data_type)) throw new Error("新方法的成果不能直接接入「" + nodeRecord(consumer, records).definition.name + "」，请先调整该连接。");
    }
  }
  const schema = configuration?.parameter_schema || record.research_contract.request_schema || {};
  const values = configuration ? structuredClone(configuration.defaults) : defaults(schema) || {};
  for (const [field] of requestProperties(schema)) if (Object.hasOwn(previous, field)) values[field] = structuredClone(previous[field]);
  if (!deferParameters) for (const [field, property] of requestProperties(schema, values)) {
    const spec = property["x-research-variables"];
    if (spec?.roles?.join() === "driver" && spec.unit === "day" && !spec.new_column && !variableCandidates(draft, node, spec).some((variable) => variable.code === values[field])) {
      const code = ensureCalendarAxis(draft, records, node, spec);
      if (code) values[field] = code;
    }
  }
  for (const [field, property] of deferParameters ? [] : requestProperties(schema, values)) {
    if (property["x-research-variables"] && !property["x-research-variables"].new_column) {
      const spec = property["x-research-variables"];
      const use = configuration?.input_uses?.[field] || record.research_contract.input_uses?.[field] || capability(record)?.input_uses?.[field];
      const role = use?.role || (spec.roles?.join() === "target" ? "label" : spec.roles?.join() === "driver" ? "driver" : "feature");
      const allowed = variableCandidates(draft, node, spec);
      const preferred = Object.hasOwn(values, field) ? (Array.isArray(values[field]) ? values[field] : [values[field]]) : role === "label" ? previous.targets || plan.evaluation.target_codes
        : ["driver", "analysis"].includes(role) ? allowed.map((v) => v.code) : previous.features || allowed.filter((v) => !plan.evaluation.target_codes.includes(v.code)).map((v) => v.code);
      const chosen = preferred.filter((code) => allowed.some((v) => v.code === code));
      if (property.type === "array") values[field] = chosen;
      else values[field] = configuration && chosen.length !== 1 ? undefined : chosen[0];
    } else if (property.format === "date" && !values[field]) values[field] = trainingEnd || previous.training_end || previous.fit_through || "";
  }
  if (previousRequest && !draft.composition.nodes.some((item) => item.bindings.some((binding) => !binding.source.node && binding.source.port === previousRequest))) {
    draft.composition.inputs = draft.composition.inputs.filter((input) => input.code !== previousRequest);
    delete draft.input_recipes[previousRequest];
    if (draft.layout?.designer_positions) delete draft.layout.designer_positions["input:" + previousRequest];
  }
  const parameterPort = record.definition.inputs.find((port) => port.code === "request");
  if (deferParameters && parameterPort) connectInput(draft, records, node, "request", addDeferredInput(draft, node, parameterPort));
  else addConfiguration(draft, node, record, values);
  const request = requestInput(draft, node);
  if (configuration && request) useMethodDefaults(draft, node, configuration);
  if (changed) {
    draft.composition.outputs = draft.composition.outputs.filter((output) => output.source.node !== node.code);
    for (const output of record.definition.outputs) setOutput(draft, node.code, output.code, true);
    if (draft.layout) delete draft.layout.study_template;
  }
  const used = new Set(draft.composition.nodes.flatMap((item) => item.bindings.filter((b) => !b.source.node).map((b) => b.source.port)));
  for (const output of draft.composition.outputs) if (!output.source.node) used.add(output.source.port);
  const oldInputs = new Set(oldSources.filter((binding) => !binding.source.node).map((binding) => binding.source.port));
  draft.composition.inputs = draft.composition.inputs.filter((input) => {
    if (used.has(input.code) || initialInputs.has(input.code) && !oldInputs.has(input.code)) return true;
    delete draft.input_recipes[input.code];
    if (draft.layout?.designer_positions) delete draft.layout.designer_positions["input:" + input.code];
    return false;
  });
  if (methodNodes(draft, records).length === 1) {
    const operation = { explore: "analyze", simulate: "simulate", fit: "calibrate", train: "train", predict: "predict", evaluate: "analyze" }[draft.purpose];
    const operations = capability(record)?.operations;
    if (operations?.length && !operations.includes(operation)) {
      draft.purpose = { train: "train", analyze: "explore", simulate: "simulate", predict: "predict", calibrate: "fit" }[operations[0]];
      for (const requirement of draft.collection_requirements) requirement.required_for = [draft.purpose];
      if (draft.purpose !== "train") {
        draft.evaluation.target_codes = [];
        delete draft.evaluation.training_percent;
        delete draft.evaluation.metrics;
      }
    }
  }
  synchronizeLabels(draft, records);
  return { definition: draft, node, record, request };
}

export function useMethodDefaults(definition, node, configuration) {
  const request = requestInput(definition, node);
  if (!request) return;
  const recipe = definition.input_recipes[request];
  for (const [field, value] of Object.entries(configuration.defaults)) {
    if (!(field in recipe.value)) recipe.value[field] = structuredClone(value);
  }
  // 上游历史拟合有不同时间窗，保留原边界。自动切分用于最终训练。
  const feedsAnother = definition.composition.nodes.some((consumer) => consumer.bindings.some((binding) => binding.source.node === node.code));
  if (feedsAnother || definition.evaluation.split_unit !== "time") return;
  for (const [field, slot] of Object.entries(configuration.runtime_fields)) {
    delete recipe.value[field];
    recipe.runtime_fields = { ...recipe.runtime_fields, [field]: slot };
  }
}
