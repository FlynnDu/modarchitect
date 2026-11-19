import { dependencyLayers } from "./graph-layout.js?v=continuous1";
import { inputUsageRows, formatUnit, flowDataset, nodeSettings, inputDetailLabel, matchesStudyTemplate, productRows, studyInputDetails } from "./modeling.js?v=continuous1";
import { inputProvision, inputGroup } from "./input-provision.js?v=continuous1";
import { calendarAxes } from "./calendar-axis.js?v=continuous1";
import { requestProperties } from "./request-schema.js?v=continuous1";

const CATEGORY = { manual: "人工采集", third_party: "第三方数据", platform: "平台分析成果", iot: "物联网监测" };
const value = (number) => Number.isFinite(number) ? Number(number.toPrecision(4)) : null;

function sources(plan, rows, catalog, data, synthetic) {
  const groups = new Map(), present = new Set(data?.columns?.map((column) => column.code));
  for (const row of rows) {
    const requirement = plan.collection_requirements.find((item) => item.variable_code === row.variable.code);
    const provision = inputProvision(requirement, catalog), entry = provision.entry;
    const category = CATEGORY[requirement?.source] || "研究资料";
    if (!groups.has(category)) groups.set(category, new Map());
    const children = groups.get(category), name = entry ? inputGroup(catalog, entry) || category : category === "研究资料" ? "方案资料" : "已选指标";
    if (!children.has(name)) children.set(name, []);
    children.get(name).push({ name: row.variable.name, code: row.variable.code, unit: formatUnit(row.variable.unit), used: row.used,
      status: synthetic ? "示例资料" : entry?.execution.available === false ? "待适配" : present.has(row.variable.code) ? "已载入" : "未提供" });
  }
  return [...groups].map(([name, children]) => ({ name, count: [...children.values()].reduce((total, items) => total + items.length, 0),
    children: [...children].map(([name, variables]) => ({ name, variables })) }));
}

// 只投影已有证据，不把目录可用、配置修订或时间留出转换成采集成功、模型版本或独立验证。
export function flowOverview(plan, records = new Map(), context = {}) {
  const { data, dataKind, run, inputCatalog = { items: [], categories: [] } } = context;
  const template = matchesStudyTemplate(plan, context.template) ? context.template : null;
  const result = run?.result_json, info = template?.researcher || {}, outputs = result?.outputs || {};
  const metrics = (result?.metrics || []).filter((metric) => metric.status === "evaluated");
  let rows = inputUsageRows(plan, records);
  if (run?.kind === "predict") {
    const sealed = new Set((result?.input_sources?.inputs || []).map((item) => item.variable?.code));
    rows = rows.filter((row) => sealed.size ? sealed.has(row.variable.code) : row.application);
  }
  const split = flowDataset(plan, data, run, records);
  const usageKnown = Boolean(split) || plan.composition.nodes.every((node) => records.has(node.component.code + "@" + node.component.revision));
  const active = rows.filter((row) => row.used), unused = usageKnown ? rows.filter((row) => !row.used) : [];
  const inputs = plan.composition.inputs.filter((port) => !["configuration"].includes(plan.input_recipes[port.code]?.kind));
  const tables = inputs.filter((port) => plan.input_recipes[port.code]?.kind === "observations");
  const axes = calendarAxes(plan);
  const fixed = template?.input_policy?.mode === "approved_dataset";
  const synthetic = dataKind === "synthetic" || result?.data_kind === "synthetic" || template?.data_kind === "synthetic" || template?.input_policy?.mode === "synthetic_demo_only";
  const count = data?.rows?.length ?? result?.input_sources?.row_count;
  const names = new Map(plan.variables.map((variable) => [variable.code, variable.name]));
  const sourceItems = rows.map((row) => [row.variable.name, formatUnit(row.variable.unit) + " · " + (!usageKnown ? "按方法合同" : row.used ? "当前方法采用" : "尚未用于计算")]);
  const datasetItems = [], segments = [];
  if (split?.periods) {
    for (const [label, number, tone] of [["历史拟合", split.periods.history, "history"], ["模型训练", split.periods.training, "training"], ["时间留出", split.periods.holdout, "holdout"]]) {
      if (number === null) continue;
      datasetItems.push([label, number + " 条"]); segments.push({ label, count: number, tone });
    }
  } else if (split?.rows !== null && split?.rows !== undefined && split.holdout !== null) {
    datasetItems.push(["建模期记录", split.rows - split.holdout + " 条"], ["留出期记录", split.holdout + " 条"]);
    segments.push({ label: "建模期记录", count: split.rows - split.holdout, tone: "training" }, { label: "留出期记录", count: split.holdout, tone: "holdout" });
  } else if (data) {
    datasetItems.push(["数据列", data.columns.length + " 项"], ["研究对象", new Set(data.rows.map((row) => JSON.stringify(row.object))).size + " 个"]);
  } else if (template?.execution_mode === "frozen_case") datasetItems.push(["资料类型", "指定方法示例"], ["输入资料", inputs.length + " 组"]);
  else datasetItems.push(["观测记录", "尚未提供"], ["研究对象与周期", "发起研究时绑定"]);
  if (axes.length) datasetItems.push(["时间驱动", "平台按观测日期生成"]);
  const evaluationItems = metrics.flatMap((metric) => {
    const title = names.get(metric.target) || metric.target, unit = formatUnit(metric.unit);
    return [[title + " RMSE", value(metric.rmse) + " " + unit + " · " + metric.rows + " 条配对"],
      ...(Number.isFinite(metric.mae) ? [["平均绝对误差（MAE）", value(metric.mae) + " " + unit]] : []),
      ...(Number.isFinite(metric.r2) ? [["拟合优度（R²）", value(metric.r2)]] : [])];
  });
  const mismatch = (result?.metrics || []).some((metric) => metric.status === "reference_unit_mismatch");
  const cards = {
    input: { code: "inputs", title: "数据来源", icon: "database", accent: "amber", status: synthetic ? "示例资料" : fixed ? "指定资料" : data || result?.input_sources ? "已载入" : "待提供", tone: "warning",
      headline: rows.length ? rows.length + (unused.length ? " 项已选指标" : " 项输入指标") : inputs.length + " 组输入资料",
      description: tables.length ? tables.length + " 张观测表" + (Number.isInteger(count) ? " · " + count + " 条记录" : "") : info.data_description || "按实际资料组展示",
      highlight: unused.length ? active.length + " 项参与计算 · " + unused.length + " 项尚未使用" : synthetic ? "示例数据，不代表真实田间观测" : "指标定义与来源由系统目录约定",
      groups: sources(plan, rows, inputCatalog, data, synthetic), items: sourceItems,
      note: unused.length ? "候选资料已保留，当前方法未采用的指标不进入计算。" : "各来源保留原始采样尺度，运行时核对资料。",
      detailTitle: "查看来源与指标", details: [info.needed] },
    partition: { code: "dataset", title: "数据集", icon: "monitor", accent: "green", status: Number.isInteger(count) ? "已载入" : template?.execution_mode === "frozen_case" ? "指定资料" : "待建立", tone: "neutral",
      headline: Number.isInteger(count) ? count + " 条观测记录" : template?.execution_mode === "frozen_case" ? "采用指定示例" : "尚未提供数据", description: tables.length ? "按研究对象 × 观测日期对齐" : "保留原生资料结构与采样尺度",
      highlight: Number.isInteger(count) ? synthetic ? "合成示例观测 · " + count + " 条" : "当前研究观测 · " + count + " 条" : template?.execution_mode === "frozen_case" ? "原生资料按方案登记的准确版本提供" : "保存的是研究设计，尚无当次观测",
      items: datasetItems, segments, note: split ? "训练与时间留出按实际记录划分；新增数据进入下一次运行。" : "运行时封存本次输入；不补造缺测日期。", detailTitle: "查看数据构成",
      details: axes.length ? ["平台日期坐标由每条实际观测日期生成，不是播种后天数，也不表示每天都有实测。"] : [] },
    evaluation: { code: "evaluation", title: split ? "时间留出评价" : "验证与评价", icon: "shield", accent: "blue", status: mismatch ? "单位不一致" : metrics.length ? "已计算" : split?.holdout === 0 ? "缺少留出数据" : "待评价", tone: mismatch ? "warning" : "info",
      headline: metrics.length && split?.holdout !== null && split?.holdout !== undefined ? split.holdout + " 条留出实测" : metrics.length ? "实测与预测对照" : "尚无评价结果",
      description: split ? "训练之后的实测与预测值配对" : "按实际方法与可用实测进行评价", highlight: metrics.length ? "仅表示当前配对记录的误差" : "运行并取得有效配对后显示评价",
      items: evaluationItems.length ? evaluationItems : [["误差指标", "尚未计算"], ["验证结论", "尚未形成"]],
      note: mismatch ? "实测与预测科学单位不一致，不能计算可比误差。" : split ? "时间留出不是独立地块验证，不据此声明跨地块泛化。" : "拟合诊断与独立验证含义不同，按实际证据解读。", detailTitle: "查看评价说明", details: info.limits || [] },
    product: { code: "products", icon: "sparkles", accent: "blue", tone: "info", highlight: "产物以当前方法声明的输出为准",
      note: "已保存方案不代表已生成模型；产出状态以实际运行记录为准。", detailTitle: "查看成果清单", details: [info.outcome] },
  };
  return assembleFlow(plan, records, context, { cards, rows, split, count, synthetic, outputs, metrics, mismatch, native: studyInputDetails(plan, template) });
}

function nodeCard(plan, node, records, context) {
  const original = records.get(node.component.code + "@" + node.component.revision);
  const capability = original?.research_contract?.capabilities || original?.definition.configuration.research_model?.execution;
  const receipt = context.run?.result_json?.receipts?.find((item) => item.node === node.code);
  const inference = context.run?.kind === "predict" && capability?.inference;
  const record = inference ? records.get(inference) || original : original;
  const parameters = nodeSettings(plan, node) || {}, automatic = original?.definition.configuration.research_model?.automatic_date_axis;
  const transform = automatic || original?.definition.category === "transform";
  const operation = transform ? "transform" : parameters.operation || (inference ? "predict" : capability?.operations?.includes(context.run?.kind) ? context.run.kind : capability?.operations?.[0]);
  const idle = { train: "待训练", predict: "待预测", analyze: "待分析", simulate: "待模拟", fit: "待拟合", calibrate: "待标定", transform: "待处理" }[operation] || "待运行";
  const name = plan.layout?.node_labels?.[node.code] || record?.definition.name || "计算步骤";
  const items = [], details = [], names = new Map(plan.variables.map((variable) => [variable.code, variable.name + " · " + formatUnit(variable.unit)]));
  for (const binding of node.bindings) {
    const recipe = !binding.source.node && plan.input_recipes[binding.source.port];
    if (recipe?.kind === "configuration") continue;
    const port = original?.definition.inputs.find((input) => input.code === binding.port);
    const sourceNode = binding.source.node && plan.composition.nodes.find((item) => item.code === binding.source.node);
    const sourceName = sourceNode ? plan.layout?.node_labels?.[sourceNode.code] || records.get(sourceNode.component.code + "@" + sourceNode.component.revision)?.definition.name || "上游计算结果"
      : plan.composition.inputs.find((input) => input.code === binding.source.port)?.name || "研究资料";
    items.push([port?.name || "输入资料", sourceName]);
  }
  for (const [field, property] of requestProperties(original?.research_contract?.request_schema, parameters)) {
    if (parameters[field] === undefined || parameters[field] === null) continue;
    const variable = property["x-research-variables"], title = property.title || field;
    if (automatic) continue;
    if (variable) {
      const codes = Array.isArray(parameters[field]) ? parameters[field] : [parameters[field]];
      items.push([title, codes.map((code) => names.get(code) || code).join("、")]);
    } else if (property.format === "date" || property.type === "boolean") {
      items.push([title, typeof parameters[field] === "boolean" ? parameters[field] ? "是" : "否" : parameters[field]]);
    }
  }
  if (!original?.research_contract?.request_schema) {
    for (const [field, title] of [["fit_through", "历史拟合截止"], ["training_end", "训练截止"], ["cutoff", "拟合截止"]]) if (parameters[field]) items.push([title, parameters[field]]);
  }
  if (automatic) {
    items.push(["生成依据", "每条资料的观测日期"], ["输出坐标", "精确日期坐标（天）"]);
    details.push("这是平台自动处理，无需人工采集天数；不代表播种后天数或积温。");
  }
  if (inference) items.push(["模型状态", "复用已保存的训练状态"]);
  const completed = Boolean(receipt) || context.run?.status === "succeeded";
  const status = completed ? "已完成" : context.run?.status === "running" ? "等待步骤回执" : context.run?.status === "failed" ? "结果待核对" : "待启动";
  const inputPorts = (original?.definition.inputs || []).filter((port) => node.bindings.some((binding) => binding.port === port.code && (binding.source.node || plan.input_recipes[binding.source.port]?.kind !== "configuration")));
  const outputPorts = original?.definition.outputs || [];
  details.push(...outputPorts.map((port) => "输出：" + port.name), ...items.slice(6).map(([label, content]) => label + "：" + content));
  return { code: "node:" + node.code, nodeCode: node.code, kind: "calculation", title: name, icon: transform ? "monitor" : "cpu", accent: "green", tone: completed ? "success" : "neutral", status,
    headline: completed ? "该步骤已完成" : automatic ? "自动日期处理" : idle,
    description: "准确组件版本 " + node.component.revision + " · " + inputPorts.length + " 组资料 → " + outputPorts.length + " 项输出",
    highlight: automatic ? "平台按实际观测日期生成驱动" : inference ? "沿用模型进行预测，不重新训练" : record?.definition.summary || "按当前步骤的准确合同计算",
    items, note: completed ? "步骤完成状态依据本次运行回执。" : context.run?.status === "failed" ? "本次运行失败；未收到的步骤回执不能视为已完成。" : "依赖资料与配置就绪后，由实际运行生成本步骤结果。",
    detailTitle: "查看步骤输入与输出", details };
}

function assembleFlow(plan, records, context, facts) {
  const { rows, split, count, synthetic, outputs, metrics, mismatch, native } = facts;
  const stages = [], edges = [], sourceIds = new Map(), productIds = new Map();
  const addEdge = (from, to, label, kind = "data", port = null) => {
    const previous = edges.find((edge) => edge.from === from && edge.to === to && edge.kind === kind);
    if (previous) { if (!previous.labels.includes(label)) previous.labels.push(label); if (port) previous.ports.push(port); }
    else edges.push({ from, to, label, labels: [label], kind, ports: port ? [port] : [] });
  };
  const inputs = plan.composition.inputs.filter((port) => plan.input_recipes[port.code]?.kind !== "configuration");
  for (const port of inputs) {
    const recipe = plan.input_recipes[port.code], selected = rows.filter((row) => recipe.variable_codes?.includes(row.variable.code));
    const details = native.get(port.code) || [];
    const code = inputs.length === 1 ? "inputs" : "input:" + port.code;
    sourceIds.set(port.code, code);
    const items = details.length ? details.map((item) => [item.name, inputDetailLabel(item)])
      : selected.length ? facts.cards.input.items.filter(([name]) => selected.some((row) => row.variable.name === name)) : [["资料类型", port.name]];
    const stage = { ...facts.cards.input, code, kind: "input", inputCode: port.code, title: inputs.length === 1 && recipe.kind === "observations" ? "研究资料" : port.name,
      groups: sources(plan, selected, context.inputCatalog || { items: [], categories: [] }, context.data, synthetic), items };
    if (inputs.length > 1) {
      const active = selected.filter((row) => row.used).length;
      stage.headline = selected.length ? selected.length + " 项已选指标" : "指定输入资料";
      stage.description = recipe.kind === "observations" ? "1 张观测表 · 保留实际采样尺度" : "保留原生资料结构与采样尺度";
      stage.highlight = selected.length ? active === selected.length ? "所选指标均由当前计算步骤采用" : active + " 项参与计算 · " + (selected.length - active) + " 项尚未使用" : "按该资料的准确合同提供";
      stage.note = "本资料仅连接方案中实际引用它的计算步骤。";
      stage.details = ["本项资料：" + port.name, "具体结构与必填内容按消费它的计算步骤端口合同核对。"];
    }
    if (recipe.kind !== "observations") {
      const pending = recipe.kind === "deferred";
      stage.headline = details.length > 1 ? details.length + " 项资料与参数" : port.name;
      stage.status = pending ? "待接入" : facts.cards.input.status === "示例资料" ? "示例资料" : "指定资料";
      stage.description = "按实际资料组提供";
      stage.highlight = pending ? "运行前需接入相应来源" : "";
      stage.note = pending ? "来源就绪后方可运行。" : "资料与当前方法及版本绑定。";
      stage.details = [];
    }
    stages.push(stage);
  }
  if (split && sourceIds.has(split.context.observed)) {
    stages.push({ ...facts.cards.partition, kind: "partition", title: "建模与留出数据" });
    addEdge(sourceIds.get(split.context.observed), "dataset", "按已配置日期划分");
  }
  const sourceId = (source) => source.node ? "node:" + source.node : split && source.port === split.context.observed ? "dataset" : sourceIds.get(source.port);
  for (const node of plan.composition.nodes) {
    stages.push(nodeCard(plan, node, records, context));
    const definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
    for (const binding of node.bindings) {
      const from = sourceId(binding.source);
      if (!from) continue;
      const label = definition?.inputs.find((input) => input.code === binding.port)?.name || "输入资料";
      addEdge(from, "node:" + node.code, label, "data", { source: binding.source.port, target: binding.port });
    }
  }
  const productNames = new Map(productRows(plan, records).map((product) => [product.code, product.name]));
  const groups = new Map();
  for (const output of plan.composition.outputs) {
    const origin = output.source.node || "input:" + output.source.port;
    if (!groups.has(origin)) groups.set(origin, []);
    groups.get(origin).push(output);
  }
  for (const [origin, ports] of groups) {
    const code = groups.size === 1 ? "products" : "products:" + origin;
    const items = ports.map((port) => [productNames.get(port.code), port.code in outputs ? "已生成" : "待产出"]);
    const available = ports.filter((port) => port.code in outputs);
    const from = ports[0].source.node ? "node:" + ports[0].source.node : sourceIds.get(ports[0].source.port);
    const prediction = available.map((port) => outputs[port.code]).find((item) => item?.rows && item.columns?.some((column) => column.value_kind === "predicted"));
    const savedModel = context.model?.run_id && context.model.run_id === context.run?.run_id && Object.hasOwn(context.model.model_json?.states || {}, origin) ? context.model : null;
    stages.push({ ...facts.cards.product, code, kind: "product", outputCodes: ports.map((port) => port.code), title: groups.size === 1 ? "研究成果" : ports.length === 1 ? items[0][0] : "步骤成果",
      items, status: available.length ? "已产出" : "等待产出", headline: prediction ? prediction.rows.length + " 条预测" : available.length ? available.length + " 项成果" : "运行后生成", description: savedModel ? savedModel.name : "来自：" + (stages.find((stage) => stage.code === from)?.title || "研究资料"),
      ...(savedModel ? { highlight: "模型已保存 · 可沿用训练状态继续预测", note: "预测沿用本模型的输入定义与已保存训练状态；发布状态另行确认。" } : {}) });
    for (const port of ports) { productIds.set(port.code, code); addEdge(from, code, items[ports.indexOf(port)][0], "data", { source: port.source.port, target: port.code }); }
  }
  if (split || metrics.length || mismatch) {
    const evaluation = { ...facts.cards.evaluation, kind: "evaluation" };
    stages.push(evaluation);
    const evaluated = new Set(metrics.map((metric) => metric.output).filter((code) => productIds.has(code)));
    if (split) for (const output of plan.composition.outputs) if (output.source.node === split.context.model.code) {
      const node = plan.composition.nodes.find((item) => item.code === output.source.node);
      const definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
      const port = definition?.outputs.find((item) => item.code === output.source.port);
      if (port?.data_type.shape === "table" || output.source.port === "predictions") evaluated.add(output.code);
    }
    for (const code of evaluated) addEdge(productIds.get(code), "evaluation", "预测结果");
    if (split) addEdge("dataset", "evaluation", split.holdout === null ? "计划留出实测" : split.holdout === 0 ? "待补留出实测" : split.holdout + " 条留出实测", "validation");
    else for (const port of inputs) if (metrics.some((metric) => plan.input_recipes[port.code].variable_codes?.includes(metric.target))) addEdge(sourceIds.get(port.code), "evaluation", "配对实测", "validation");
    if (!evaluated.size && !split) { evaluation.status = "来源待核对"; evaluation.note = "该历史评价缺少准确成果关联，不推测其计算依赖。"; }
  }
  const { layers, depth } = dependencyLayers(stages.map((stage) => ({ ...stage, key: stage.code })), edges.map((edge) => [edge.from, edge.to]));
  const ordered = layers.flat();
  return { stages: ordered, edges: edges.map((edge) => ({ ...edge, label: edge.labels.join("、") })), layers: layers.map((layer) => layer.map((stage) => stage.code)), depth,
    rows, split, branch: Boolean(split?.hasHoldout), alignmentTitle: inputs.some((port) => plan.input_recipes[port.code].kind === "observations") ? "对象与观测日期匹配" : "资料与计算依赖",
    alignment: Number.isInteger(count) ? count + " 条记录 · 保留实际资料的采样尺度" : "按方案中的准确输入、计算步骤和成果展示", context: context.run ? "本次运行" : "方案预览" };
}
