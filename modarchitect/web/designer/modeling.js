import { requestInput, sourceFor } from "./editor.js?v=continuous1";
import { dependencyLayers } from "./graph-layout.js?v=continuous1";
import { requestProperties } from "./request-schema.js?v=continuous1";

const is = (node, code) => node?.component.code === code && node.component.revision === 1;
const reference = (source) => source ? `${source.node || ""}:${source.port}` : "";
const variableName = (plan, code) => plan.variables.find((v) => v.code === code)?.name || code;
export const formatUnit = (unit) => ({ cm2: "cm²", cm2_plant: "cm²/株", m2_m2: "m²/m²", kg_ha: "kg/ha", fraction: "比例", celsius: "°C", kj_m2: "kJ/m²", "m3/m3": "m³/m³", deg_c: "°C", day: "天", "1": "无量纲" })[unit] || unit;
export const variableLabel = (plan, code) => {
  const value = plan.variables.find((v) => v.code === code);
  return value ? `${value.name} · ${formatUnit(value.unit)}` : code;
};

export function nodeSettings(plan, node) {
  const recipe = requestInput(plan, node);
  return recipe ? plan.input_recipes[recipe].value : null;
}

export function inputUsageRows(plan, records = new Map(), inspection) {
  const context = studySettings(plan, records);
  const external = new Set(Object.values(plan.input_recipes).filter((r) => r.kind === "observations").flatMap((r) => r.variable_codes));
  const projected = new Map();
  const origins = (source, code, visited = new Set()) => {
    if (!source) return [];
    if (!source.node) return plan.input_recipes[source.port]?.variable_codes?.includes(code) ? [code] : [];
    const key = source.node+":"+source.port+":"+code;
    if (visited.has(key)) return [];
    const next = new Set(visited); next.add(key);
    const upstream = plan.composition.nodes.find((node) => node.code === source.node);
    if (!upstream) return [];
    const contract = records.get(upstream.component.code+"@"+upstream.component.revision)?.definition.configuration?.research_model;
    const declaration = contract?.table_outputs?.[source.port], value = nodeSettings(plan, upstream);
    if (!declaration || !value || !declaration.inherit) return [];
    if ((declaration.computed || []).some((field) => value[field] === code)) return [];
    const append = declaration.append;
    if (append && value[append.as] === code) return origins(sourceFor(upstream, append.port), value[append.column], next);
    return [...new Set([declaration.inherit, ...(declaration.merge || [])].flatMap((port) => origins(sourceFor(upstream, port), code, next)))];
  };
  for (const node of plan.composition.nodes) {
    if (inspection) {
      for (const use of inspection.nodes.find((item) => item.code === node.code)?.input_usages || []) {
        for (const original of origins(sourceFor(node, use.port), use.variable_code)) {
          if (!projected.has(original)) projected.set(original, []);
          projected.get(original).push(use);
        }
      }
      continue;
    }
    const record = records.get(node.component.code+"@"+node.component.revision);
    for (const [field, property] of requestProperties(record?.research_contract?.request_schema)) {
      const spec = property["x-research-variables"];
      const use = record.research_contract.input_uses?.[field] || record.research_contract.capabilities?.input_uses?.[field]
        || (spec?.roles?.join() === "target" ? { role: "label", phases: ["training"] } : spec ? { role: "feature", phases: ["application"] } : null);
      if (!spec || spec.new_column) continue;
      const value = nodeSettings(plan, node)?.[field];
      for (const code of (Array.isArray(value) ? value : [value])) for (const original of origins(sourceFor(node, spec.table_port), code)) {
        if (!projected.has(original)) projected.set(original, []);
        projected.get(original).push(use);
      }
    }
  }
  return plan.variables.filter((v) => external.has(v.code) || plan.collection_requirements.some((r) => r.variable_code === v.code)).map((variable) => {
    const usages = projected.get(variable.code) || [];
    if ((!context || inspection) && usages.length) return { variable, role: usages.some((u) => u.role === "label") ? "target" : "covariate", train: usages.some((u) => u.phases.includes("training")), application: usages.some((u) => u.phases.includes("application")), analysis: usages.some((u) => u.phases.includes("analysis")), used: true, editable: Boolean(context) };
    const pending = !plan.composition.nodes.length;
    const target = context ? context.parameters.targets.includes(variable.code) : pending && variable.role === "target";
    const feature = context ? context.parameters.features.includes(variable.code) || variable.code === context.history?.x_code : pending && ["covariate", "driver"].includes(variable.role);
    const historical = context?.history && [context.history.x_code, context.history.target_code].includes(variable.code);
    return { variable, role: target ? "target" : feature ? "covariate" : "other", train: target || feature || historical, used: Boolean(target || feature || historical),
      application: Boolean(feature || variable.code === context?.history?.x_code),
      editable: plan.purpose === "train" && (!plan.composition.nodes.length || Boolean(context)) && !historical };
  });
}

export function resourceInputs(plan, records = new Map()) {
  return plan.composition.inputs.filter((port) => plan.input_recipes[port.code]?.kind !== "observations").map((port) => {
    const recipe = plan.input_recipes[port.code], consumers = plan.composition.nodes.flatMap((node) => node.bindings.filter((binding) => !binding.source.node && binding.source.port === port.code)
      .map((binding) => ({ node, port: binding.port, record: records.get(node.component.code + "@" + node.component.revision) })));
    return { port, recipe, consumers, parameter: consumers.every((consumer) => consumer.port === "request") };
  });
}

export function matchesStudyTemplate(plan, template) {
  const marker = plan.layout?.study_template;
  return Boolean(marker && template?.id === marker.id && template.sha256 === marker.sha256);
}

export function studyInputDetails(plan, template) {
  const byPort = new Map();
  if (!matchesStudyTemplate(plan, template)) return byPort;
  const sources = resourceInputs(plan).filter(({ recipe }) => recipe.kind === "artifact");
  for (const { port, consumers } of sources) {
    const selections = consumers.filter((consumer) => consumer.port === "series")
      .map(({ node }) => nodeSettings(plan, node)?.variables).filter(Array.isArray);
    const selected = selections.length ? new Set(selections.flat()) : null;
    const details = (template.input_requirements || []).filter((item) => item.port === port.code && (!selected || selected.has(item.code)));
    if (details.length) byPort.set(port.code, details);
  }
  return byPort;
}

export function inputDetailLabel(item) {
  return [formatUnit(item.unit), item.use, item.source].filter(Boolean).join(" · ");
}

export function productRows(plan, records = new Map()) {
  return plan.composition.outputs.map((output) => {
    const node = plan.composition.nodes.find((node) => node.code === output.source.node);
    const record = node && records.get(node.component.code + "@" + node.component.revision);
    const port = record?.definition.outputs.find((port) => port.code === output.source.port);
    return { code: output.code, name: port?.name || output.code, description: port?.description || "准确组件声明的成果" };
  });
}

// 首批引导只编辑已验收结构；自定义图保留全部真实步骤，避免改坏未知方案。
export function studySettings(plan, records = new Map()) {
  if (plan.objective !== "prediction" || plan.purpose !== "train" || plan.evaluation.split_unit !== "time"
      || plan.evaluation.numeric_gate || plan.evaluation.holdout_unit_refs?.length
      || plan.variables.some((value) => !["driver", "target", "covariate", "validation"].includes(value.role))) return null;
  if (Object.values(plan.input_recipes).some((recipe) => recipe.kind === "configuration" && Object.keys(recipe.runtime_fields || {}).length)) return null;
  const nodes = plan.composition.nodes;
  const model = nodes.find((node) => {
    if (is(node, "multivariate_linear_training")) return true;
    const record = records.get(node.component.code + "@" + node.component.revision);
    const research = record?.definition.configuration.research_model, capability = record?.research_contract.capabilities || research?.execution;
    const schema = record?.research_contract.request_schema;
    return research?.kind === "regression" && capability?.operations.includes("train") && capability.state_output && capability.inference
      && capability.input_uses?.features?.role === "feature" && capability.input_uses?.targets?.role === "label"
      && schema?.properties.features?.["x-research-variables"]?.table_port === "observations"
      && schema?.properties.targets?.["x-research-variables"]?.table_port === "observations"
      && schema?.properties.training_end?.format === "date";
  });
  if (!model) return null;
  const parameters = nodeSettings(plan, model);
  if (!Array.isArray(parameters?.features) || !Array.isArray(parameters?.targets)) return null;
  const baseline = nodes.find((n) => is(n, "historical_logistic_training"));
  const join = nodes.find((n) => is(n, "research_forecast_feature_join"));
  const observed = sourceFor(model, "observations");
  if (nodes.length === 1 && !observed?.node && plan.input_recipes[observed?.port]?.kind === "observations") {
    return { model, parameters, kind: "direct", observed: observed.port };
  }
  if (nodes.length !== 3 || !baseline || !join || observed?.node !== join.code || observed.port !== "table") return null;
  if (reference(sourceFor(join, "forecast")) !== `${baseline.code}:forecast`
      || reference(sourceFor(baseline, "observations")) !== reference(sourceFor(join, "observations"))) return null;
  const history = nodeSettings(plan, baseline), alignment = nodeSettings(plan, join);
  if (!history || !alignment || alignment.feature_code !== history.target_code || !parameters.features.includes(alignment.output_code)) return null;
  const upstream = plan.variables.find((v) => v.code === history.target_code);
  const derived = plan.variables.find((v) => v.code === alignment.output_code);
  if (!upstream || !derived || upstream.unit !== derived.unit) return null;
  const input = sourceFor(join, "observations");
  if (input?.node || plan.input_recipes[input?.port]?.kind !== "observations") return null;
  return { model, parameters, baseline, history, join, alignment, kind: "chain", observed: input.port };
}

export function editStudy(plan, changes, records = new Map()) {
  const draft = structuredClone(plan), context = studySettings(draft, records);
  if (!context) throw new Error("这个自定义结构请在组件视图中编辑，系统不会替换现有模型。");
  const { parameters, history, alignment } = context;
  const targets = [...new Set(changes.targets ?? parameters.targets)];
  const derived = alignment?.output_code;
  let features = [...new Set(changes.features ?? parameters.features)].filter((code) => !targets.includes(code));
  if (derived && !features.includes(derived)) features.unshift(derived);
  const observed = new Set(draft.input_recipes[context.observed].variable_codes);
  if (!targets.length || targets.some((code) => !observed.has(code))) throw new Error("至少选择一个有实测数据的预测目标。");
  if (targets.includes(derived)) throw new Error("历史模型的估计值只能作为因素，不能代替实测目标。");
  if (draft.collection_requirements.some((r) => targets.includes(r.variable_code) && r.catalog_binding && r.catalog_binding.value_nature !== "observed")) {
    throw new Error("预测目标需要实测来源，第三方估计值只能作为因素。");
  }
  if (!features.length || features.some((code) => !observed.has(code) && code !== derived)) throw new Error("至少选择一个有来源的已知因素。");
  if (history && (targets.includes(history.x_code) || features.includes(history.target_code))) {
    throw new Error("历史模型的时间轴及实测目标需保留原用途，请选择其他因素或使用组件视图。");
  }
  const trainingEnd = changes.trainingEnd ?? parameters.training_end;
  const fitThrough = changes.fitThrough ?? history?.fit_through;
  const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value || "") && Number.isFinite(Date.parse(value));
  if (!validDate(trainingEnd) || (history && (!validDate(fitThrough) || fitThrough >= trainingEnd))) {
    throw new Error("请填写有效截止日期；历史拟合必须早于最终模型的训练截止日。");
  }
  Object.assign(parameters, { targets, features, training_end: trainingEnd });
  if (history) history.fit_through = fitThrough;
  draft.evaluation.target_codes = [...targets];
  for (const variable of draft.variables) {
    if (targets.includes(variable.code) || variable.code === history?.target_code) variable.role = "target";
    else if (variable.code === history?.x_code || variable.role === "driver") variable.role = "driver";
    else if (observed.has(variable.code) || variable.code === derived) variable.role = "covariate";
  }
  return draft;
}

export function modelingSteps(plan, records) {
  const context = studySettings(plan, records), list = (codes) => codes.map((code) => variableLabel(plan, code));
  if (context) {
    const { parameters, history, alignment, model, baseline } = context;
    const subscript = (number) => String(number).replace(/\d/g, (digit) => "₀₁₂₃₄₅₆₇₈₉"[Number(digit)]);
    const terms = parameters.features.slice(0, 4).map((code, index) => `权重${subscript(index + 1)} × ${variableName(plan, code)}`);
    if (parameters.features.length > 4) terms.push(`…（共 ${parameters.features.length} 项）`);
    const linear = is(model, "multivariate_linear_training"), method = records.get(model.component.code + "@" + model.component.revision)?.definition.name;
    const formula = parameters.targets.map((code) => linear ? `${variableName(plan, code)} = 截距 + ${terms.join(" + ")}` : `${variableName(plan, code)} = f(${parameters.features.map((factor) => variableName(plan, factor)).join("，")})`);
    const final = { key: model.code, title: "建立最终预测关系", method: (linear ? "多变量线性回归" : method) + " · 各目标分别训练",
      inputs: list(parameters.features), outputs: list(parameters.targets), formula,
      note: `每个目标分别学习。使用截至 ${parameters.training_end} 的实测目标训练；之后的观测用于留出评价。预测关系及其参数随模型保存。` };
    if (!history) return { context, steps: [final] };
    return { context, steps: [{ key: baseline.code, title: "先计算生长趋势", method: "历史逻辑斯蒂生长模型",
      inputs: list([history.x_code, history.target_code]), outputs: list([alignment.output_code]),
      formula: [`${variableName(plan, alignment.output_code)} = 生长曲线(${variableName(plan, history.x_code)})`],
      note: `仅用 ${history.fit_through} 及以前的历史数据拟合；输出是估计值。` }, final] };
  }
  const nodes = plan.composition.nodes.map((node) => ({ key: node.code, node }));
  const edges = plan.composition.nodes.flatMap((node) => node.bindings.filter((b) => b.source.node).map((b) => [b.source.node, node.code]));
  const { layers } = dependencyLayers(nodes, edges);
  return { context: null, steps: layers.flat().map(({ node }) => {
    const record = records.get(`${node.component.code}@${node.component.revision}`)?.definition;
    const boundPorts = new Set(node.bindings.map((binding) => binding.port));
    return { key: node.code, title: record?.name || node.component.code, method: "当前方案的实际计算步骤",
      inputs: (record?.inputs || []).filter((p) => p.code !== "request" && boundPorts.has(p.code)).map((p) => p.name),
      outputs: (record?.outputs || []).map((p) => p.name), formula: [], note: "该自定义方法的参数与连接可在组件视图中查看。" };
  }) };
}

export function predictionColumns(pipeline, records = new Map()) {
  const context = studySettings(pipeline.plan, records);
  const needed = context ? new Set([
    ...context.parameters.features.filter((code) => code !== context.alignment?.output_code),
    ...(context.history ? [context.history.x_code] : []),
  ]) : null;
  const declared = inputUsageRows(pipeline.plan, records);
  const actual = pipeline.plan.composition.nodes.every((node) => records.has(node.component.code + "@" + node.component.revision)) && declared.some((row) => row.used)
    ? new Set(declared.filter((row) => row.application).map((row) => row.variable.code)) : null;
  return pipeline.input_columns.filter((column) => needed ? needed.has(column.code) : actual ? actual.has(column.code)
    : !pipeline.plan.variables.some((v) => v.code === column.code && ["target", "validation"].includes(v.role)));
}

export function dataPeriods(plan, table, records = new Map()) {
  const context = studySettings(plan, records);
  if (!context || !table?.rows?.length) return null;
  const dates = table.rows.map((r) => r.business_date).sort();
  const fit = context.history?.fit_through, end = context.parameters.training_end;
  return { first: dates[0], last: dates.at(-1), rows: dates.length,
    objects: new Set(table.rows.map((r) => JSON.stringify([r.object.field_ref, r.object.crop_code, r.object.season_ref]))).size,
    history: fit ? dates.filter((day) => day <= fit).length : null,
    training: dates.filter((day) => (!fit || day > fit) && day <= end).length,
    holdout: dates.filter((day) => day > end).length };
}

export function flowDataset(plan, table, run = null, records = new Map()) {
  const context = studySettings(plan, records);
  if (!context || run?.kind === "predict" || plan.evaluation.split_unit !== "time") return null;
  const periods = dataPeriods(plan, table, records);
  const outputCodes = new Set(plan.composition.outputs.filter((output) => output.source.node === context.model.code).map((output) => output.code));
  const evaluated = (run?.result_json?.metrics || []).filter((metric) => metric.status === "evaluated" && outputCodes.has(metric.output));
  const expected = new Set(evaluated.map((metric) => metric.expected_rows).filter((value) => Number.isInteger(value) && value >= 0));
  const holdout = periods?.holdout ?? (expected.size === 1 ? [...expected][0] : null);
  const rows = periods?.rows ?? run?.result_json?.input_sources?.row_count ?? null;
  return { context, periods, rows, holdout, hasHoldout: holdout !== null && holdout > 0 };
}
