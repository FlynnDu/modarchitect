import { addConfiguration, addDeferredInput, addModel, addObservationInput, connectInput, inputChoices, nodeRecord, recordKey, requestInput, setOutput, sourceKey } from "./editor.js?v=continuous1";
import { defaults } from "./schema-fields.js?v=continuous1";

const capability = (record) => record?.research_contract.capabilities || record?.definition.configuration.research_model?.execution;
const sameType = (expected, actual) => Object.entries(expected).every(([key, value]) => actual?.[key] === value);

export function methodRecords(records) {
  return [...records.values()].filter((record) => record.available_for_new_design && record.definition.composable);
}

export function methodRestriction(record) {
  if (!record.available_for_new_design || !record.definition.composable) return "此版本不能用于新设计。";
  return null;
}

export function synchronizeLabels(plan, records) {
  if (plan.purpose !== "train") return;
  const targets = [...new Set(plan.composition.nodes.flatMap((node) => {
    const record = nodeRecord(node, records), request = requestInput(plan, node);
    const value = request && plan.input_recipes[request].value;
    return Object.entries(capability(record)?.input_uses || {}).filter(([, use]) => use.role === "label")
      .flatMap(([field]) => value?.[field] === undefined ? [] : Array.isArray(value[field]) ? value[field] : [value[field]]);
  }))];
  if (targets.length) plan.evaluation.target_codes = targets;
}

export function prepareMethodDraft(plan, records, key, nodeCode = null, trainingEnd = "", { deferParameters = false } = {}) {
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
  const schema = record.research_contract.request_schema || {}, values = defaults(schema) || {};
  for (const [field, property] of Object.entries(deferParameters ? {} : schema.properties || {})) {
    if (Object.hasOwn(previous, field)) values[field] = structuredClone(previous[field]);
    else if (property["x-research-variables"] && !property["x-research-variables"].new_column) {
      const spec = property["x-research-variables"], use = capability(record)?.input_uses?.[field];
      const binding = node.bindings.find((item) => item.port === spec.table_port)?.source;
      const recipe = binding && !binding.node && draft.input_recipes[binding.port];
      const allowed = draft.variables.filter((v) => (!recipe || recipe.variable_codes.includes(v.code)) && (!spec.unit || v.unit === spec.unit)
        && (!spec.observed || !draft.collection_requirements.some((r) => r.variable_code === v.code && r.catalog_binding?.value_nature && r.catalog_binding.value_nature !== "observed")));
      const preferred = use?.role === "label" ? previous.targets || plan.evaluation.target_codes
        : use?.role === "driver" ? allowed.map((v) => v.code) : previous.features || allowed.filter((v) => !plan.evaluation.target_codes.includes(v.code)).map((v) => v.code);
      const chosen = preferred.filter((code) => allowed.some((v) => v.code === code));
      if (!allowed.length && schema.required?.includes(field)) throw new Error("「" + (property.title || field) + "」没有符合单位、来源与输入要求的指标。");
      if (property.type === "array") values[field] = chosen;
      else if (chosen.length) values[field] = chosen[0];
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
  synchronizeLabels(draft, records);
  return { definition: draft, node, record, request: requestInput(draft, node) };
}
