import { element } from "./visuals.js?v=continuous1";
import { parameters } from "./schema-fields.js?v=continuous1";
import { synchronizeLabels } from "./methods.js?v=continuous1";
import { issueMessage } from "./panels.js?v=continuous1";

const operations = { train: "训练", predict: "预测", analyze: "分析", simulate: "模拟", calibrate: "标定" };
const phases = { training: "训练", application: "应用", analysis: "分析", evaluation: "评价" };
const roles = { feature: "因素", label: "实测目标", driver: "驱动", derived: "派生指标", analysis: "分析资料" };
const statuses = { passed: "已通过", blocked: "未通过", not_checked: "尚未检查", unsupported: "尚未支持" };
const kinds = { observations: "观测资料", artifact: "指定成果资料", deferred: "待接入资料", configuration: "方法参数" };
const shapes = { table: "表格", raster: "栅格", geometry: "空间资料", scalar: "单值", bundle: "结构化资料", model: "模型制品" };

export function renderChecks(host, checks, onLocate = () => {}) {
  host.replaceChildren();
  for (const [key, title] of [["configuration", "方案配置"], ["operation", "操作兼容"], ["execution", "本次执行条件"]]) {
    const check = checks[key], row = element("section", "product-row"); row.dataset.check = key;
    row.append(element("strong", "", title + " · " + statuses[check.status]));
    for (const issue of check.issues) {
      const item = element("p", ""); item.dataset.rule = issue.code;
      item.append(element("span", "", issueMessage(issue)));
      if (issue.node || issue.path.length) {
        const locate = element("button", "text-button", "查看位置"); locate.type = "button";
        locate.addEventListener("click", () => onLocate(issue)); item.append(locate);
      }
      row.append(item);
    }
    host.append(row);
  }
}

export function renderInspection(host, inspection, { getDefinition, getRecords, onEdit, onTechnical, notify }) {
  const plan = getDefinition(), names = new Map(plan.variables.map((v) => [v.code, v.name + " · " + v.unit]));
  const labels = new Map(inspection.materials.map((m) => [m.code, m.name]));
  for (const node of inspection.nodes) labels.set(node.code, node.name);
  const active = document.activeElement, activeNode = active?.closest("[data-inspection-node]")?.dataset.inspectionNode;
  const activeField = active?.dataset.field, selection = active && "selectionStart" in active ? active.selectionStart : null;
  host.replaceChildren();
  const heading = element("div", "section-heading");
  heading.append(element("h3", "", "研究资料、计算与规则"));
  const technical = element("button", "button button-secondary", "查看组件与连线"); technical.type = "button";
  technical.addEventListener("click", () => onTechnical()); heading.append(technical); host.append(heading);
  for (const material of inspection.materials) {
    const card = element("section", "product-row"); card.dataset.inspectionMaterial = material.code;
    card.append(element("h4", "", material.name), element("p", "modeling-muted", kinds[material.kind] + " · " + shapes[material.data_type.shape]));
    for (const code of material.variable_codes) card.append(element("p", "", names.get(code) || code));
    for (const source of material.sources) card.append(element("p", "modeling-muted", source.source_name + " · " + (source.execution.available ? "取数通道已接通；本次数据待核验" : source.execution.reason || "取数待接通")));
    for (const item of material.indicators) card.append(element("p", "", [item.name, item.unit, item.use, item.source].filter(Boolean).join(" · ")));
    host.append(card);
  }
  for (const node of inspection.nodes) {
    const card = element("section", "product-row"); card.dataset.inspectionNode = node.code;
    card.append(element("h4", "", node.name), element("p", "modeling-muted", "支持操作：" + (node.operations.map((op) => operations[op]).join("、") || "尚未声明执行能力")));
    for (const binding of node.bindings.filter((b) => b.port !== "request")) card.append(element("p", "", "输入「" + (node.inputs.find((port) => port.code === binding.port)?.name || binding.port) + "」：" + (labels.get(binding.source.node || binding.source.port) || binding.source.port)));
    for (const use of node.input_usages) card.append(element("p", "", (names.get(use.variable_code) || use.variable_code) + " · " + roles[use.role] + " · " + use.phases.map((phase) => phases[phase]).join("、")));
    if (node.request_input && node.parameter_schema && node.parameters !== null) {
      const schema = structuredClone(node.parameter_schema);
      for (const key of Object.keys(node.runtime_fields)) delete schema.properties?.[key];
      const formPlan = { ...plan, input_recipes: { ...plan.input_recipes, [node.request_input]: structuredClone(plan.input_recipes[node.request_input]) } };
      const form = parameters(formPlan, plan.composition.nodes.find((n) => n.code === node.code), schema, node.request_input, (port, field, value) => {
        const draft = structuredClone(getDefinition());
        if (draft.input_recipes[port]?.kind !== "configuration") { notify("参数来源已变化，请等待重新检查。"); return; }
        if (value === undefined) { delete draft.input_recipes[port].value[field]; delete formPlan.input_recipes[port].value[field]; }
        else { draft.input_recipes[port].value[field] = value; formPlan.input_recipes[port].value[field] = value; }
        if (getRecords) synchronizeLabels(draft, getRecords());
        onEdit(draft);
      });
      card.append(form);
      for (const key of Object.keys(node.runtime_fields)) card.append(element("p", "modeling-muted", (node.parameter_schema.properties?.[key]?.title || key) + "：由实际运行上下文提供"));
    } else if (node.request_input) card.append(element("p", "modeling-muted", "参数尚待配置，或由方案指定资料提供；可在方法选择和组件视图中查看。"));
    for (const output of node.outputs) card.append(element("p", "", "声明成果：" + output.name + " · " + shapes[output.data_type.shape]));
    host.append(card);
  }
  const checks = element("div"); checks.setAttribute("aria-label", "研究规则检查");
  renderChecks(checks, inspection.checks, (issue) => onTechnical(issue.node ? "node:" + issue.node : "plan")); host.append(checks);
  if (activeNode && activeField) {
    const target = [...host.querySelectorAll("[data-field]")].find((field) => field.dataset.field === activeField && field.closest("[data-inspection-node]")?.dataset.inspectionNode === activeNode);
    target?.focus();
    if (selection !== null && target && ["text", "search"].includes(target.type)) target.setSelectionRange(selection, selection);
  }
}

export function mountInspection({ getDefinition, getRecords, inspect, onEdit, onTechnical, notify, onChange, delay = 200 }) {
  const host = document.getElementById("research-inspection"), message = document.getElementById("inspection-status"), retry = document.getElementById("inspection-retry");
  let generation = 0, timer, current, displayed, supported = false;
  function schedule() {
    const token = ++generation, definition = structuredClone(getDefinition()), fingerprint = JSON.stringify(definition);
    const editing = document.activeElement?.closest("[data-inspection-node]")?.dataset.inspectionNode;
    const previous = displayed?.nodes.find((node) => node.code === editing), next = definition.composition.nodes.find((node) => node.code === editing);
    const keepForm = previous && next && JSON.stringify(previous.component) === JSON.stringify(next.component);
    if (!keepForm) { host.replaceChildren(); displayed = null; }
    clearTimeout(timer); current = supported ? null : undefined; onChange(current);
    retry.hidden = true;
    message.textContent = "正在核对当前资料与规则…"; host.setAttribute("aria-busy", "true");
    // 编辑期间保留输入焦点，但清除上次的通过/阻断状态。
    host.querySelector('[aria-label="研究规则检查"]')?.replaceChildren();
    timer = setTimeout(async () => {
      try {
        const result = await inspect(definition);
        if (token !== generation || fingerprint !== JSON.stringify(getDefinition())) return;
        if (!result) { current = undefined; host.replaceChildren(); message.textContent = ""; onChange(current); return; }
        if (result.schema_version !== "1.0") throw new Error("Unsupported inspection schema");
        supported = true; current = result;
        renderInspection(host, result, { getDefinition, getRecords, onEdit, onTechnical, notify });
        displayed = result;
        message.textContent = "资料与规则已按当前方案核对；本次执行条件须在启动前检查。";
        onChange(current);
      } catch {
        if (token !== generation) return;
        current = null; displayed = null; host.replaceChildren(); message.textContent = "暂时无法核对当前资料与规则，请重新检查。";
        retry.hidden = false;
        onChange(current);
      } finally { if (token === generation) host.removeAttribute("aria-busy"); }
    }, delay);
  }
  retry.addEventListener("click", schedule);
  return { schedule, get: () => current, setExecutionChecks(checks) {
    if (!current) return;
    current = { ...current, checks: { ...current.checks, execution: checks.execution } };
    const target = host.querySelector('[aria-label="研究规则检查"]');
    if (target) renderChecks(target, current.checks, (issue) => onTechnical(issue.node ? "node:" + issue.node : "plan"));
    onChange(current);
  } };
}
