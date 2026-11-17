import { dependencyLayers } from "./graph-layout.js?v=continuous1";
import { inputUsageRows, formatUnit, flowDataset } from "./modeling.js?v=continuous1";

function componentFlow(host, plan, records = new Map(), externalCodes = null) {
  const ns = "http://www.w3.org/2000/svg", parameters = new Set(plan.composition.inputs.filter((input) => input.role === "parameter" || plan.input_recipes[input.code]?.kind === "configuration").map((input) => input.code));
  const items = plan.composition.inputs.filter((input) => !parameters.has(input.code)).map((input) => {
    const recipe = plan.input_recipes[input.code], codes = recipe?.kind === "observations" ? recipe.variable_codes.filter((code) => externalCodes === null || externalCodes.has(code)) : null;
    return { key: "input:" + input.code, name: codes ? "观测表 · " + codes.length + " 项指标" : input.name, kind: "data",
      description: codes ? "观测表：" + codes.map((code) => plan.variables.find((variable) => variable.code === code)?.name || code).join("、") : input.name };
  });
  for (const node of plan.composition.nodes) {
    const definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
    items.push({ key: "node:" + node.code, name: plan.layout?.node_labels?.[node.code] || definition?.name || "研究方法", kind: "method" });
  }
  for (const output of plan.composition.outputs) {
    const node = plan.composition.nodes.find((item) => item.code === output.source.node), definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
    items.push({ key: "output:" + output.code, name: definition?.outputs.find((port) => port.code === output.source.port)?.name || "研究结果", kind: "result" });
  }
  const edges = plan.composition.nodes.flatMap((node) => node.bindings.filter((binding) => binding.source.node || !parameters.has(binding.source.port)).map((binding) => [binding.source.node ? "node:" + binding.source.node : "input:" + binding.source.port, "node:" + node.code]));
  edges.push(...plan.composition.outputs.map((output) => ["node:" + output.source.node, "output:" + output.code]));
  const { layers } = dependencyLayers(items, edges), width = layers.length * 240, height = Math.max(...layers.map((layer) => layer.length), 1) * 96 + 24, positions = new Map();
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "研究流程：数据、分析方法与成果");
  layers.forEach((layer, depth) => layer.forEach((item, index) => positions.set(item.key, { x: 12 + depth * 240, y: 16 + index * 96 })));
  for (const [from, to] of edges) {
    const start = positions.get(from), end = positions.get(to), path = document.createElementNS(ns, "path"), a = start.x + 204, b = end.x, y1 = start.y + 31, y2 = end.y + 31, mid = (a + b) / 2;
    path.setAttribute("d", `M${a},${y1} H${mid} V${y2} H${b} m-6,-4 l6,4 l-6,4`); path.setAttribute("class", "research-flow-edge"); svg.append(path);
  }
  for (const item of items) {
    const position = positions.get(item.key), group = document.createElementNS(ns, "g"), rect = document.createElementNS(ns, "rect"), title = document.createElementNS(ns, "title");
    title.textContent = item.description || item.name;
    for (const [key, value] of Object.entries({ x: position.x, y: position.y, width: 204, height: 62, rx: 8 })) rect.setAttribute(key, value);
    rect.setAttribute("class", "research-flow-" + item.kind); group.append(title, rect);
    const chars = [...item.name], lines = chars.length > 14 ? [chars.slice(0, 14).join(""), chars.slice(14, 28).join("")] : [item.name];
    for (const [index, line] of lines.entries()) {
      const text = document.createElementNS(ns, "text"); text.setAttribute("x", position.x + 102); text.setAttribute("y", position.y + (lines.length === 1 ? 36 : 27 + index * 18)); text.setAttribute("text-anchor", "middle"); text.textContent = line; group.append(text);
    } svg.append(group);
  }
  host.replaceChildren(svg);
}

const element = (tag, text = "", className = "") => {
  const node = document.createElement(tag); node.textContent = text;
  if (className) node.className = className; return node;
};

const STATUS = { queued: "等待调度", dispatching: "正在提交", submitted: "调度已接受", running: "正在计算", succeeded: "计算完成", failed: "计算失败", uncertain: "提交待核对" };
const PURPOSE = { train: "训练模型", predict: "进行预测", explore: "开展分析", simulate: "运行模拟", fit: "进行标定" };
const POLICY = { user_observations: "允许增删、替换记录，并从系统目录调整输入、因素和目标；每次修改后需重新检查。", synthetic_demo_only: "当前方案仅可使用合成演示数据；调整输入不会自动取得真实地块数据资格。", approved_dataset: "使用本方案指定的示例资料；可调整列出的研究设置，不能增删或替换底层资料。" };

function information(items) {
  const list = element("dl", "", "research-stage-values");
  for (const [label, value] of items) list.append(element("dt", label), element("dd", value));
  return list;
}

export function researchFlow(host, plan, records = new Map(), context = {}) {
  const opened = new Set([...host.querySelectorAll("details[open]")].map((node) => node.dataset.detail)); host.replaceChildren();
  const { template, data, dataKind, run, model } = context, info = template?.researcher || {}, policy = template?.input_policy;
  const inputs = plan.composition.inputs.filter((port) => plan.input_recipes[port.code]?.kind !== "configuration");
  const tables = inputs.filter((port) => plan.input_recipes[port.code]?.kind === "observations");
  let indicators = inputUsageRows(plan, records);
  const unused = indicators.filter((row) => !row.used);
  if (indicators.some((row) => row.used)) indicators = indicators.filter((row) => row.used);
  if (run?.kind === "predict") {
    const codes = new Set((run.result_json?.input_sources?.inputs || []).map((input) => input.variable?.code).filter(Boolean));
    if (codes.size) indicators = indicators.filter((row) => codes.has(row.variable.code));
    else if (indicators.some((row) => row.application)) indicators = indicators.filter((row) => row.application);
  }
  const ordered = dependencyLayers(plan.composition.nodes.map((node) => ({ ...node, key: node.code })), plan.composition.nodes.flatMap((node) => node.bindings.filter((binding) => binding.source.node).map((binding) => [binding.source.node, node.code]))).layers.flat();
  const methods = ordered.map((node) => plan.layout?.node_labels?.[node.code] || records.get(node.component.code + "@" + node.component.revision)?.definition.name || "研究方法");
  const outputNames = new Map(plan.composition.outputs.map((port) => {
    const source = plan.composition.nodes.find((node) => node.code === port.source.node), definition = records.get(source.component.code + "@" + source.component.revision)?.definition;
    return [port.code, definition?.outputs.find((output) => output.code === port.source.port)?.name || "研究成果"];
  }));
  const settings = [], names = new Map(plan.variables.map((variable) => [variable.code, variable.name]));
  for (const recipe of Object.values(plan.input_recipes).filter((value) => value.kind === "configuration")) {
    for (const [key, value] of Object.entries(recipe.value || {})) {
      const title = { as_of: "分析截止日", start_date: "开始日期", end_date: "结束日期", training_end: "训练截止日", fit_through: "拟合截止日" }[key];
      if (title) settings.push([title, value]);
      if (["features", "targets", "variables"].includes(key) && Array.isArray(value)) settings.push([{ features: "候选因素", targets: "预测目标", variables: "分析指标" }[key], value.every((code) => names.has(code)) ? value.map((code) => names.get(code)).join("、") : value.length + " 项"]);
    }
  }
  const result = run?.result_json, outputs = result?.outputs || {}, metrics = (result?.metrics || []).filter((metric) => metric.status === "evaluated");
  const example = dataKind === "synthetic" || result?.data_kind === "synthetic" || ["approved_dataset", "synthetic_demo_only"].includes(policy?.mode);
  const nativeInputs = template?.input_requirements || [];
  const inputItems = indicators.map((row) => [row.variable.name, (row.application ? "已知输入 · " : row.train ? "训练实测 · " : row.analysis ? "分析指标 · " : "待绑定方法 · ") + formatUnit(row.variable.unit)]);
  if (!indicators.length && nativeInputs.length) inputItems.push(...nativeInputs.map((row) => [row.name, formatUnit(row.unit) + " · " + row.use]));
  if (!inputItems.length) inputItems.push(["资料内容", inputs.map((port) => port.name).join("、")]);
  const rowCount = data?.rows?.length ?? result?.input_sources?.row_count;
  const inputDescription = tables.length ? tables.length + " 张观测表" + (Number.isInteger(rowCount) ? " · " + rowCount + " 条记录" : "") + (inputs.length > tables.length ? " · " + (inputs.length - tables.length) + " 组其他资料" : "") : info.data_description || "按实际资料组展示";
  const split = flowDataset(plan, data, run, records);
  const prediction = Object.values(outputs).find((output) => Array.isArray(output.rows) && output.columns?.some((column) => column.value_kind === "predicted"));
  const evaluationItems = metrics.flatMap((metric) => {
    const name = names.get(metric.target) || metric.target, unit = formatUnit(metric.unit);
    const rows = [[name + " RMSE", Number(metric.rmse.toPrecision(4)) + " " + unit + " · " + metric.rows + " 条配对"]];
    if (Number.isFinite(metric.mae)) rows.push([name + " MAE", Number(metric.mae.toPrecision(4)) + " " + unit]);
    return rows;
  });
  const stages = [
    { code: "inputs", title: "研究输入", status: example ? "示例资料" : run ? "已提交输入" : "待校验", tone: "warning", headline: indicators.length || nativeInputs.length ? (indicators.length || nativeInputs.length) + " 项输入指标" : inputs.length + " 组输入资料", description: inputDescription, items: inputItems, note: example ? "当前使用示例资料。" : "", details: [info.needed, POLICY[policy?.mode], ...nativeInputs.map((row) => row.name + "：" + row.source), unused.length ? "当前未参与方法：" + unused.map((row) => row.variable.name).join("、") : "", "上游派生指标由模型计算，不计入外部输入。"] },
    { code: "method", title: "方法与设置", status: "已配置", headline: methods[0] || "待选择方法", description: "", items: methods.slice(1).map((name) => ["后续方法", name]).concat(settings), details: [info.method] },
    { code: "execution", title: "研究执行", status: run ? STATUS[run.status] : "待启动", tone: run?.status === "succeeded" ? "success" : run?.status === "failed" ? "error" : run ? "info" : "neutral", headline: PURPOSE[run?.kind === "predict" ? "predict" : plan.purpose] || "开展研究", description: "", items: [["执行方法", methods.join("、")]], note: run?.status === "failed" ? "计算失败，查看运行记录。" : "", details: ["单次研究在此查看结果；需要持续跟踪时，在每日研究中设置观察期。每日批次分别封存输入与结果。"] },
    { code: "products", title: "研究成果", status: Object.keys(outputs).length ? "已产出" : "等待产出", tone: Object.keys(outputs).length ? "success" : "neutral", headline: prediction ? prediction.rows.length + " 条预测" : Object.keys(outputs).length ? Object.keys(outputs).length + " 项成果" : "运行后生成", description: "", items: [...outputNames].map(([code, name]) => [name, code in outputs ? "已生成" : "待产出"]), details: [info.outcome] },
    { code: "evaluation", title: "评价与解读", status: metrics.length ? "已有误差评价" : "待研究者判断", tone: "info", headline: metrics.length ? "实测与预测对照" : "结果分析", description: "", items: evaluationItems.length ? evaluationItems : [["评价结果", "运行后查看"]], details: info.limits || [] },
  ];
  if (split) {
    const config = split.context, periods = split.periods, datasetItems = [];
    if (periods) {
      if (periods.history !== null) datasetItems.push(["历史拟合", periods.history + " 条"]);
      datasetItems.push(["模型训练", periods.training + " 条"], ["时间留出", periods.holdout + " 条"]);
    } else if (split.holdout !== null) {
      if (split.rows !== null && split.rows >= split.holdout) datasetItems.push(["建模期记录", split.rows - split.holdout + " 条"]);
      datasetItems.push(["留出期记录", split.holdout + " 条"]);
    }
    stages[1] = { code: "dataset", title: "数据集", status: split.rows === null ? "待载入" : "已载入", headline: split.rows === null ? "待提供观测" : split.rows + " 条观测", description: periods ? periods.first + " 至 " + periods.last : "", items: datasetItems, note: split.hasHoldout ? "留出实测不参与训练。" : "", details: ["以业务日期划分，当前未设置独立地块测试或开发验证集。"] };
    stages[2].title = "模型训练";
    stages[2].headline = config.parameters.targets.map((code) => names.get(code) || code).join("、") + "预测";
    stages[2].items = [["计算方法", config.kind === "chain" ? "历史趋势 → 多因素回归" : "多因素回归"], ...settings];
    stages[3].title = "预测成果";
    if (result?.pipeline?.states && Object.keys(result.pipeline.states).length) stages[3].items.push(["预测模型", model ? "已保存" : "待保存"]);
    stages[4].title = "时间留出评价";
    const unitMismatch = (result?.metrics || []).some((metric) => metric.status === "reference_unit_mismatch");
    stages[4].status = unitMismatch ? "单位不一致" : metrics.length ? "已计算" : split.holdout === 0 ? "缺少留出数据" : "待计算";
    if (unitMismatch || split.holdout === 0) stages[4].tone = "warning";
    stages[4].headline = metrics.length && split.holdout !== null ? split.holdout + " 条留出实测" : "留出实测对照";
    stages[4].note = unitMismatch ? "核对实测与预测的科学单位。" : "训练截止 " + config.parameters.training_end + "；之后的实测用于评价。";
  }
  host.append(element("p", run ? "本次运行" : "方案预览", "research-flow-context"), element("p", "向右查看后续步骤 →", "research-flow-hint"));
  const scroll = element("div", "", "research-stages-scroll"); scroll.tabIndex = 0; scroll.setAttribute("role", "region"); scroll.setAttribute("aria-label", "研究流程五个阶段，可滚动查看");
  const diagram = element("div", "", "research-stages-diagram" + (split?.hasHoldout ? " has-branch" : ""));
  const list = element("ol", "", "research-stage-list");
  for (const [index, stage] of stages.entries()) {
    const step = element("li", "", "research-stage-step"), card = element("article", "", "research-stage-card"); card.dataset.flowStage = stage.code; card.dataset.tone = stage.tone || "neutral";
    const header = element("header"); header.append(element("span", String(index + 1).padStart(2, "0"), "research-stage-number"), element("h3", stage.title), element("span", stage.status, "research-stage-status"));
    const body = element("div", "", "research-stage-body"); body.append(element("strong", stage.headline, "research-stage-headline"));
    if (stage.description) body.append(element("p", stage.description, "research-stage-description"));
    body.append(information(stage.items.slice(0, 5)));
    const details = element("details"); details.dataset.detail = stage.code; details.open = opened.has(stage.code); details.append(element("summary", stage.items.length > 5 ? "查看全部 " + stage.items.length + " 项" : "查看明细"), information(stage.items));
    for (const note of stage.details || []) if (note) details.append(element("p", note));
    body.append(details); card.append(header, body);
    if (stage.note) { const footer = element("footer"); footer.append(element("p", stage.note)); card.append(footer); } step.append(card);
    if (index < 4) { const arrow = element("span", (split ? ["整理", "建模记录", "预测", "预测值"] : ["检查", "执行", "产出", "解读"])[index], "research-stage-connector"); arrow.setAttribute("aria-hidden", "true"); step.append(arrow); } list.append(step);
  }
  diagram.append(list);
  if (split?.hasHoldout) {
    const branch = element("div", "", "research-data-branch"); branch.dataset.branchSource = "dataset"; branch.dataset.branchTarget = "evaluation";
    branch.style.setProperty("--branch-from", stages.findIndex((stage) => stage.code === "dataset")); branch.style.setProperty("--branch-to", stages.findIndex((stage) => stage.code === "evaluation"));
    branch.setAttribute("role", "img"); branch.setAttribute("aria-label", "数据集中的时间留出实测不参与训练，直接进入评价，与预测值对照");
    branch.append(element("span", "留出实测（不参与训练）", "research-data-branch-label")); diagram.append(branch);
  }
  scroll.append(diagram); host.append(scroll);
  const connections = element("details", "", "research-component-flow"); connections.dataset.detail = "connections"; connections.open = opened.has("connections"); connections.append(element("summary", "查看模型连接关系"), element("p", "这里展示方案定义中的数据依赖；预测时复用已保存模型。"));
  const graph = element("div", "", "research-component-graph"); componentFlow(graph, plan, records, new Set(indicators.map((row) => row.variable.code))); connections.append(graph); host.append(connections);
}
