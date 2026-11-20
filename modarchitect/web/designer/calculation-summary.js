import { element } from "./visuals.js?v=continuous1";
import { evaluationLabels } from "./result-views.js?v=calculation1";

const strategies = {
  automatic_dates: "按观测日期划分",
  configured_window: "按方案指定的验证窗口",
  saved_policy: "沿用方案已保存的评价规则",
};

function dataTokens(values) {
  const list = element("ul", "method-data-tokens");
  for (const value of values) list.append(element("li", "", value));
  return list;
}

function resourceGroup(title, values, descriptions, empty, note) {
  const card = element("section", "calculation-part calculation-resources");
  card.append(element("h4", "", title + "（" + values.length + " 项）"));
  card.append(values.length ? dataTokens(values) : element("p", "modeling-muted", empty));
  if (values.length) {
    const details = element("details", "calculation-details");
    const control = element("summary", "", "查看详情");
    control.dataset.calculationDetail = "";
    control.setAttribute("aria-label", "查看" + title + "详情");
    const list = element("ul");
    for (const description of descriptions) list.append(element("li", "", description));
    details.append(control, list);
    if (note) details.append(element("p", "modeling-muted", note));
    card.append(details);
  }
  return card;
}

function editEvaluation(host, evaluation, section, onEdit, opener) {
  const editingRatio = section === "训练策略";
  const dialog = element("dialog", "indicator-dialog calculation-editor");
  dialog.setAttribute("aria-label", "编辑" + section);
  const form = element("form");
  form.append(element("h3", "", "编辑" + section));
  let ratio, validation;
  if (editingRatio) {
    ratio = element("input"); ratio.type = "number"; ratio.min = "1"; ratio.max = "99";
    ratio.step = "1"; ratio.required = true; ratio.value = evaluation.training_percent;
    const label = element("label", "calculation-ratio", "训练集比例（%）");
    label.append(ratio);
    validation = element("p", "modeling-muted");
    const sync = () => { validation.textContent = ratio.validity.valid ? "验证集比例 " + (100 - ratio.valueAsNumber) + "%" : "请输入 1 到 99 的整数。"; };
    ratio.addEventListener("input", sync);
    sync();
    form.append(label, validation);
  } else {
    const choices = element("div", "evaluation-choices");
    for (const metric of evaluation.metrics) {
      const choice = element("label");
      const check = element("input"); check.type = "checkbox"; check.name = "metric"; check.value = metric.code;
      check.checked = metric.selected !== false; check.disabled = metric.required === true;
      const abbreviation = evaluationLabels[metric.code];
      const title = abbreviation && !metric.name.includes(abbreviation) ? abbreviation + " · " + metric.name : metric.name;
      choice.append(check, element("span", "", title + (metric.required ? "（评价门槛必选）" : "")));
      choices.append(choice);
    }
    form.append(choices);
  }
  const message = element("p", "wizard-error"); message.hidden = true; message.setAttribute("role", "status");
  const actions = element("div", "method-dialog-actions");
  const cancel = element("button", "button button-secondary", "取消"); cancel.type = "button";
  const save = element("button", "button button-primary", "应用设置"); save.type = "submit";
  const close = () => {
    if (dialog.open && dialog.close) dialog.close();
    dialog.remove(); opener.focus();
  };
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const metrics = [...form.querySelectorAll("input[name='metric']:checked")].map((field) => field.value);
    if (!editingRatio && !metrics.length) {
      message.textContent = "请至少选择一项评价指标。"; message.hidden = false; return;
    }
    close();
    onEdit(editingRatio ? { training_percent: ratio.valueAsNumber } : { metrics });
  });
  actions.append(cancel, save); form.append(message, actions); dialog.append(form); host.append(dialog);
  if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
}

function evaluationCards(host, evaluation, onEdit) {
  const createCard = (title, editable) => {
    const card = element("section", "calculation-part");
    const head = element("div", "calculation-heading");
    head.append(element("h4", "", title));
    if (editable && onEdit) {
      const button = element("button", "text-button", "编辑");
      button.type = "button";
      button.setAttribute("aria-label", "编辑" + title);
      button.setAttribute("aria-haspopup", "dialog");
      button.addEventListener("click", () => editEvaluation(host, evaluation, title, onEdit, button));
      head.append(button);
    }
    card.append(head);
    host.append(card);
    return card;
  };
  const percent = evaluation.training_percent;
  const strategy = createCard("训练策略", percent != null);
  const fields = element("dl", "calculation-split");
  const items = [["数据划分方式", strategies[evaluation.strategy]]];
  if (percent != null) items.push(["训练集比例", percent + "%"], ["验证集比例", 100 - percent + "%"]);
  for (const [label, value] of items) {
    const field = element("div");
    field.append(element("dt", "", label), element("dd", "", value));
    fields.append(field);
  }
  strategy.append(fields);
  if (percent != null) strategy.append(element("p", "modeling-muted", "较早日期用于训练，较晚日期用于验证。"));
  const metrics = createCard("评价指标", true);
  const options = element("ul", "calculation-metrics");
  for (const metric of evaluation.metrics) {
    const label = evaluationLabels[metric.code] || metric.name, selected = metric.selected !== false;
    const item = element("li", selected ? "is-selected" : "");
    const mark = element("span", "metric-mark", selected ? "✓" : "");
    mark.setAttribute("aria-hidden", "true");
    item.title = metric.name;
    item.setAttribute("aria-label", metric.name + (selected ? "，已选" : "，未选"));
    item.append(mark, element("span", "", label));
    options.append(item);
  }
  metrics.append(options);
}

export function updateObservationSummary(host, table, dataKind, requiredCodes) {
  if (!host) return;
  const rows = table?.rows || [];
  const title = element("h4", "", "观测数据");
  host.replaceChildren(title);
  if (!rows.length) {
    host.append(element("p", "modeling-muted", "未载入观测。时间匹配、完整性和缺失值将在运行前核验。"));
    return;
  }
  const dates = rows.map((row) => row.business_date).filter(Boolean).sort();
  const range = dates.length ? dates[0] + " 至 " + dates.at(-1) : "日期待核对";
  const missing = rows.reduce((count, row) => count + requiredCodes.filter((key) => !Number.isFinite(row.values?.[key])).length, 0);
  const kind = dataKind === "synthetic" ? "合成示例" : "已载入";
  host.append(element("p", "", `${kind} · ${rows.length} 条 · ${range}`));
  host.append(element("p", "modeling-muted", missing ? `必需列中有 ${missing} 个值未提供或无效。` : "已载入表的所需列齐全。"));
  host.append(element("p", "modeling-muted", "来源与时间匹配在运行前核验。"));
}

export function calculationSummary(inspection, names, descriptions, onEdit) {
  const grid = element("div", "calculation-overview");
  const resources = element("section", "method-preview-card calculation-card");
  const settings = element("section", "method-preview-card calculation-card");
  resources.append(element("h3", "", "数据资源"));
  settings.append(element("h3", "", "计算配置"));

  const uses = inspection.nodes.flatMap((node) => node.input_usages);
  const inputs = inspection.prediction?.input_codes || inspection.materials.flatMap((material) => material.variable_codes);
  const drivers = uses.filter((use) => use.role === "driver").map((use) => use.variable_code);
  const targets = inspection.prediction?.target_codes || uses.filter((use) => use.role === "label").map((use) => use.variable_code);
  const targetSet = new Set(targets);
  const inputCodes = [...new Set([...inputs, ...drivers])].filter((code) => !targetSet.has(code));
  const otherMaterials = inspection.materials.filter((material) => !material.variable_codes.length);
  const materialNames = [...new Set(otherMaterials.flatMap((material) =>
    material.indicators.length ? material.indicators.map((indicator) => indicator.name) : [material.name]))];
  const sources = [...new Set(inspection.materials.flatMap((material) => material.sources.map((source) => source.source_name)))];
  resources.append(resourceGroup("输入变量", [...inputCodes.map((code) => names.get(code) || code), ...materialNames],
    [...inputCodes.map((code) => descriptions.get(code) || code), ...materialNames],
    "按当前方法的资料要求配置。", sources.length ? "资料来源：" + sources.join("、") : ""));
  if (inspection.operation === "train") {
    const codes = [...targetSet];
    resources.append(resourceGroup("预测目标", codes.map((code) => names.get(code) || code),
      codes.map((code) => descriptions.get(code) || code), "待选择实测目标。", "训练和验证需要这些目标的实测值。"));
  }
  const observations = element("div", "calculation-part"); observations.dataset.calculationObservations = "";
  resources.append(observations);

  if (inspection.evaluation) evaluationCards(settings, inspection.evaluation, onEdit);
  for (const node of inspection.nodes) {
    if (!node.settings?.length) continue;
    const values = element("dl", "calculation-settings");
    for (const setting of node.settings) {
      const item = element("div");
      const value = typeof setting.value === "boolean" ? (setting.value ? "是" : "否") : String(setting.value);
      item.append(element("dt", "", setting.name), element("dd", "", value)); values.append(item);
    }
    settings.append(element("h4", "", node.method_name || node.name), values);
  }
  grid.append(resources, settings);
  return grid;
}

export function observationCodes(inspection) {
  return [...new Set(inspection.materials.flatMap((material) => material.variable_codes))];
}
