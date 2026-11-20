import { element } from "./visuals.js?v=continuous1";
import { requestProperties } from "./request-schema.js?v=continuous1";
import { formatUnit } from "./modeling.js?v=continuous1";
import { calculationSummary, observationCodes, updateObservationSummary } from "./calculation-summary.js?v=calculation1";

export function parameterPreview(plan, schema, values, runtimeFields = {}) {
  const list = element("dl", "method-facts");
  const variableNames = new Map(plan.variables.map((variable) => [variable.code, variable.name]));
  for (const [field, property] of requestProperties(schema, values)) {
    const value = values?.[field], slot = runtimeFields[field];
    if (value == null && !slot && !schema.required?.includes(field)) continue;
    const display = (item) => property.labels?.[item] || (property["x-research-variables"] && variableNames.get(item)) || String(item);
    const content = slot === "training_holdout_cutoff_date" ? "开始训练时按观测日期与评价规则划分训练和验证资料"
      : slot ? "开始运行时由平台提供" : value == null || Array.isArray(value) && !value.length ? "待选择"
      : Array.isArray(value) ? value.map(display).join("、") : typeof value === "boolean" ? value ? "是" : "否"
      : typeof value === "object" ? JSON.stringify(value) : display(value);
    list.append(element("dt", "", slot === "training_holdout_cutoff_date" ? "训练与评价" : property.title || field), element("dd", "", content));
  }
  return list;
}

export function renderInspection(host, inspection, { getDefinition, observations, dataKind, onEdit }) {
  const plan = getDefinition();
  host.replaceChildren();
  if (!inspection.nodes.length) {
    host.append(element("p", "information-note", "选择计算方式后查看所需资料和计算配置。"));
    return;
  }
  const names = new Map(plan.variables.map((v) => [v.code, v.name]));
  const descriptions = new Map(plan.variables.map((v) => [v.code, `${v.name}（${formatUnit(v.unit)}）`]));
  const summary = calculationSummary(inspection, names, descriptions, onEdit);
  if (inspection.operation !== "train") {
    const settings = summary.lastElementChild;
    for (const node of inspection.nodes) {
      if (!node.parameters || !node.parameter_schema) continue;
      const details = element("details", "method-advanced");
      details.append(element("summary", "", node.settings?.length ? "查看完整参数" : (node.method_name || node.name) + "参数"),
        parameterPreview(plan, node.parameter_schema, node.parameters, node.runtime_fields));
      settings.append(details);
    }
  }
  updateObservationSummary(summary.querySelector("[data-calculation-observations]"), observations, dataKind, observationCodes(inspection));
  host.append(summary);
}

export function mountInspection({ getDefinition, inspect, onChange, onEdit, delay = 200 }) {
  const host = document.getElementById("research-inspection"), message = document.getElementById("inspection-status"), retry = document.getElementById("inspection-retry");
  let generation = 0, timer, current, supported = false, observations, dataKind;
  function schedule() {
    const token = ++generation, definition = structuredClone(getDefinition()), fingerprint = JSON.stringify(definition);
    host.replaceChildren();
    clearTimeout(timer); current = supported ? null : undefined; onChange(current);
    retry.hidden = true;
    message.textContent = "正在核对当前资料与规则…"; host.setAttribute("aria-busy", "true");
    timer = setTimeout(async () => {
      try {
        const result = await inspect(definition);
        if (token !== generation || fingerprint !== JSON.stringify(getDefinition())) return;
        if (!result) { current = undefined; host.replaceChildren(); message.textContent = ""; onChange(current); return; }
        if (result.schema_version !== "1.0") throw new Error("Unsupported inspection schema");
        supported = true; current = result;
        renderInspection(host, result, { getDefinition, observations, dataKind, onEdit: onEdit && ((settings) => {
          if (token !== generation || fingerprint !== JSON.stringify(getDefinition())) return;
          const draft = structuredClone(getDefinition());
          Object.assign(draft.evaluation, settings);
          onEdit(draft);
        }) });
        message.textContent = "";
        onChange(current);
      } catch {
        if (token !== generation) return;
        current = null; host.replaceChildren(); message.textContent = "暂时无法核对当前资料与规则，请重新检查。";
        retry.hidden = false;
        onChange(current);
      } finally { if (token === generation) host.removeAttribute("aria-busy"); }
    }, delay);
  }
  retry.addEventListener("click", schedule);
  return { schedule, get: () => current, setObservations(table, kind) {
    observations = table; dataKind = kind;
    if (current) updateObservationSummary(host.querySelector("[data-calculation-observations]"), table, kind, observationCodes(current));
  } };
}
