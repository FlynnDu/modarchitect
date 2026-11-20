import { element } from "./visuals.js?v=continuous1";
import { dataPeriods, editStudy, modelingSteps, studySettings, variableLabel } from "./modeling.js?v=continuous1";

const byId = (id) => document.getElementById(id);
const button = (text, action, className = "button button-secondary") => {
  const value = element("button", className, text);
  value.type = "button"; value.addEventListener("click", action); return value;
};

export function mountModeling({ getDefinition, getRecords, onEdit, onExample, onTechnical, notify }) {
  let data = null;
  function change(values) {
    try { onEdit(editStudy(getDefinition(), values, getRecords())); }
    catch (error) { notify(error.message); render(); }
  }
  function checkboxGroup(title, variables, selected, action, plan) {
    const group = element("fieldset", "modeling-fieldset");
    group.append(element("legend", "", title));
    const choices = element("div", "modeling-variable-choices");
    for (const code of variables) {
      const label = element("label", "modeling-variable");
      const input = element("input"); input.type = "checkbox"; input.value = code; input.checked = selected.includes(code);
      input.addEventListener("change", () => action([...choices.querySelectorAll("input:checked")].map((value) => value.value)));
      label.append(input, element("span", "", variableLabel(plan, code))); choices.append(label);
    }
    group.append(choices); return group;
  }
  function dateField(label, value, action) {
    const wrapper = element("label", "modeling-date", label), input = element("input");
    input.type = "date"; input.value = value; input.required = true;
    input.addEventListener("change", () => action(input.value)); wrapper.append(input); return wrapper;
  }
  function settings(plan, context) {
    const host = byId("modeling-settings"); host.replaceChildren();
    if (!context) {
      host.append(element("h3", "", "保留你的自定义结构"), element("p", "modeling-muted", "下方展示实际计算步骤。这个结构尚未接入引导式设置，可展开组件视图编辑原参数与连线。"),
        button("打开组件视图", () => onTechnical()));
      return;
    }
    const { parameters, history, alignment } = context;
    const observed = plan.input_recipes[context.observed].variable_codes;
    const targets = observed.filter((code) => code !== history?.x_code && !plan.collection_requirements.some((r) => r.variable_code === code && r.catalog_binding && r.catalog_binding.value_nature !== "observed"));
    const factors = observed.filter((code) => !parameters.targets.includes(code) && code !== history?.target_code);
    host.append(element("h3", "", "定义这项研究"), element("p", "modeling-muted", "配置模型输入和预测输出，底层连接保持同步。"));
    for (const [key, title] of [["name", "研究名称"], ["question", "想回答的研究问题"]]) {
      const wrapper = element("label", "modeling-date", title), input = element(key === "name" ? "input" : "textarea");
      input.value = plan[key]; input.maxLength = key === "name" ? 128 : 2000;
      input.addEventListener("change", () => {
        if (!input.value.trim()) { notify("请填写研究名称和问题，方便重新打开时识别。"); render(); return; }
        const draft = structuredClone(getDefinition()); draft[key] = input.value; onEdit(draft);
      });
      wrapper.append(input); host.append(wrapper);
    }
    host.append(checkboxGroup("预测输出（可多选）", targets, parameters.targets, (values) => change({ targets: values }), plan));
    host.append(checkboxGroup("模型输入（预测时可提供）", factors, parameters.features, (values) => change({ features: values }), plan));
    if (alignment) host.append(element("p", "modeling-derived", "另一个因素来自上一步：" + variableLabel(plan, alignment.output_code) + "。它是模型估计值。"));
    const model = getRecords().get(context.model.component.code + "@" + context.model.component.revision);
    host.append(element("p", "modeling-muted", "方法：" + (model?.definition.name || "当前训练方法") + "。每个目标分别训练；增加因素不需要增加模型节点。"));
    if (history) host.append(dateField("历史趋势用到哪一天的实测？", history.fit_through, (value) => change({ fitThrough: value })));
    if (parameters.training_end) host.append(dateField("最终模型用到哪一天的实测？", parameters.training_end, (value) => change({ trainingEnd: value })));
    else host.append(element("p", "modeling-muted", "训练时由平台根据实际观测日期划分。"));
  }
  function renderPeriods() {
    const host = byId("modeling-periods"), plan = getDefinition(); host.replaceChildren();
    if (plan?.purpose === "explore") {
      host.append(element("p", "modeling-muted", "本次分析统计所选指标的全部输入观测，不训练预测模型；记录数与统计范围以运行成果为准。"));
      return;
    }
    const summary = plan && dataPeriods(plan, data, getRecords());
    if (!summary) { host.append(element("p", "modeling-muted", "载入观测后，这里会显示训练与留出评价的数据范围。")); return; }
    host.append(element("p", "modeling-data-range", `${summary.first} — ${summary.last} · ${summary.rows} 条观测 · ${summary.objects} 个地块作物种植季`));
    const list = element("ol", "modeling-period-list");
    for (const [label, count] of [["历史趋势拟合", summary.history], ["最终模型训练", summary.training], ["留出评价", summary.holdout]]) {
      if (count === null) continue;
      const item = element("li"); item.append(element("span", "", label), element("strong", "", count + " 条")); list.append(item);
    }
    host.append(list, element("p", "modeling-muted", "这里统计当前观测，实际有效样本以运行结果为准。多天观测不等于多个独立地块。"));
    if (!summary.holdout || !summary.training) host.append(element("p", "modeling-warning", "当前日期切分缺少训练或留出观测，请调整截止日期或补充数据。"));
  }
  function render() {
    const plan = getDefinition(), host = byId("modeling-flow"); host.replaceChildren();
    const empty = !plan?.composition.nodes.length;
    byId("modeling-empty").hidden = !empty;
    byId("modeling-current").hidden = empty;
    if (empty) return;
    try {
      const { context, steps } = modelingSteps(plan, getRecords());
      byId("modeling-explanation").textContent = context?.kind === "chain"
        ? "先得到一个有意义的中间指标，再把它与当日因素一起用于最终预测。箭头表示上一步结果成为下一步的因素。"
        : context ? "用多个已知因素建立预测关系。多个目标共用这些因素，各自得到一个模型。"
          : "按实际依赖顺序阅读计算步骤；分支模型不应被理解为一个固定的线性公式。";
      for (const [index, step] of steps.entries()) {
        const row = element("li", "modeling-step"); row.dataset.step = step.key;
        const sequence = element("span", "modeling-step-number", String(index + 1));
        const card = element("article", "modeling-step-card");
        card.append(element("p", "modeling-method", step.method), element("h3", "", step.title));
        const input = element("div", "modeling-step-input"); input.append(element("span", "modeling-small-label", "使用"));
        for (const label of step.inputs) input.append(element("span", "modeling-chip", label));
        card.append(input);
        for (const text of step.formula) card.append(element("p", "modeling-formula", text));
        const output = element("p", "modeling-step-output", "得到：" + step.outputs.join("、"));
        card.append(output, element("p", "modeling-muted", step.note), button(context ? "修改研究设置" : "查看这个步骤的设置", () => {
          if (context) { byId("modeling-settings").scrollIntoView({ behavior: "smooth", block: "nearest" }); byId("modeling-settings").focus(); }
          else onTechnical("node:" + step.key);
        }, "text-button"));
        row.append(sequence, card);
        if (context?.kind === "chain" && index === 0) row.append(element("p", "modeling-transfer", "↓  将趋势估计作为下一步的一个因素；按同一对象、同一天配对"));
        host.append(row);
      }
      settings(plan, context);
      byId("modeling-alignment").hidden = context?.kind !== "chain";
      renderPeriods();
    } catch (error) {
      host.append(element("li", "modeling-warning", error.message));
      settings(plan, null);
    }
  }
  for (const [id, kind] of [["start-direct", "system"], ["start-chain", "chain"]]) {
    byId(id).addEventListener("click", async () => {
      try { await onExample(kind); } catch (error) { notify(error.message); }
    });
  }
  byId("technical-toggle").addEventListener("click", () => onTechnical());
  return { render, setData(value) { data = value; renderPeriods(); }, setRun(run) {
    byId("modeling-run-state").textContent = run?.status === "succeeded" ? ({ train: "训练完成，可保存为模型", predict: "已用保存的模型完成预测", analyze: "分析完成，可重新打开统计成果", simulate: "模拟完成", calibrate: "标定完成" }[run.kind] || "计算完成") : "";
  } };
}
