import { element } from "./visuals.js?v=continuous1";
import { editStudy, formatUnit, studySettings, variableLabel, inputUsageRows } from "./modeling.js?v=continuous1";
export { inputUsageRows } from "./modeling.js?v=continuous1";
import { issueMessage } from "./panels.js?v=continuous1";
import { researchTitle, researchQuestion } from "./study-library.js?v=continuous1";
import { inputProvision } from "./input-provision.js?v=continuous1";

const sections = ["basic", "inputs", "sources", "calculation", "outputs"];
const sectionNames = ["基础信息", "输入与建模关系", "数据来源", "计算与评价", "结果与版本"];
const byId = (id) => document.getElementById(id);

export function changeInputRole(plan, code, role, records = new Map()) {
  const draft = structuredClone(plan), row = inputUsageRows(draft, records).find((r) => r.variable.code === code);
  if (!row?.editable || !["target", "covariate"].includes(role)) throw new Error("此用途由当前组件合同决定，请在组件设置中修改。");
  const binding = draft.collection_requirements.find((r) => r.variable_code === code)?.catalog_binding;
  if (role === "target" && binding && binding.value_nature !== "observed") throw new Error("预测目标必须采用实测来源。");
  const context = studySettings(draft, records);
  if (context) {
    const targets = context.parameters.targets.filter((c) => c !== code), features = context.parameters.features.filter((c) => c !== code);
    (role === "target" ? targets : features).push(code);
    return editStudy(draft, { targets, features }, records);
  }
  row.variable.role = role;
  draft.evaluation.target_codes = draft.variables.filter((v) => v.role === "target").map((v) => v.code);
  return draft;
}

export function mountWizard({ getDefinition, getRecords, getInputCatalog, onEdit, onExample, onTechnical, validate }) {
  const initial = location.hash.slice(1).split("/");
  let stage = ["select", "configure", "review"].includes(initial[0]) ? initial[0] : "select";
  let section = sections.includes(initial[1]) ? initial[1] : "basic";
  let template = "growth", table = null, dataKind = "user_supplied", checkedPlan = null, checking = false;

  function error(message) {
    byId("wizard-error").textContent = message || "";
    byId("wizard-error").hidden = !message;
  }
  function navigate(nextStage, nextSection = section) {
    stage = nextStage; section = nextSection; error("");
    for (const name of ["select", "configure", "review"]) byId("wizard-" + name).hidden = stage !== name;
    for (const button of document.querySelectorAll("[data-stage]")) {
      if (button.dataset.stage === stage) button.setAttribute("aria-current", "step"); else button.removeAttribute("aria-current");
    }
    for (const button of document.querySelectorAll("[data-section]")) {
      if (button.dataset.section === section) button.setAttribute("aria-current", "step"); else button.removeAttribute("aria-current");
    }
    for (const panel of document.querySelectorAll("[data-wizard-section]")) panel.hidden = panel.dataset.wizardSection !== section;
    byId("wizard-position").textContent = sectionNames[sections.indexOf(section)];
    byId("wizard-next").textContent = section === "outputs" ? "下一步：检查与确认 →" : "下一步 →";
    const url = new URL(location.href); url.hash = stage + (stage === "configure" ? "/" + section : "");
    history.replaceState(history.state, "", url);
    render();
  }
  function draftField(key, value) {
    const draft = structuredClone(getDefinition());
    if (key === "success_criteria") draft.evaluation[key] = value;
    else draft[key] = value;
    onEdit(draft);
  }
  function roleTable(plan) {
    const host = byId("wizard-role-table"), rows = inputUsageRows(plan, getRecords()); host.replaceChildren();
    if (!rows.length) { host.append(element("p", "information-note", "从指标库选择实测预测目标，再选择预测时已知的因素。")); return; }
    if (dataKind === "synthetic") host.append(element("p", "input-channel-pending", "当前数据为合成示例；下列说明是正式研究的数据提供要求，不表示已经获取真实资料。"));
    const view = element("table", "research-table"), header = element("tr");
    for (const name of ["数据项", "数据提供方式", "当前用途", "训练时使用", "应用时使用", "科学单位"]) {
      const heading = element("th", "", name); heading.scope = "col"; header.append(heading);
    }
    view.append(header);
    for (const row of rows) {
      const line = element("tr"), roleCell = element("td"); line.append(element("td", "", row.variable.name));
      const requirement = plan.collection_requirements.find((r) => r.variable_code === row.variable.code);
      const provision = inputProvision(requirement, getInputCatalog?.());
      const sourceCell = element("td", "input-provision");
      sourceCell.append(element("strong", "", provision.label));
      for (const detail of provision.details) sourceCell.append(element("small", "", detail));
      line.append(sourceCell);
      if (row.editable) {
        const select = element("select", "wizard-role-select"); select.setAttribute("aria-label", row.variable.name + "的用途"); select.dataset.variableRole = row.variable.code;
        select.add(new Option("已知因素 X", "covariate"));
        const binding = plan.collection_requirements.find((r) => r.variable_code === row.variable.code)?.catalog_binding;
        if (!binding || binding.value_nature === "observed") select.add(new Option("实测预测目标 Y", "target"));
        select.value = row.role === "target" ? "target" : "covariate";
        select.addEventListener("change", () => {
          try { onEdit(changeInputRole(getDefinition(), row.variable.code, select.value, getRecords())); }
          catch (exc) { error(exc.message); roleTable(getDefinition()); }
        }); roleCell.append(select);
      } else roleCell.append(element("span", "usage-chip", plan.purpose === "explore" ? "分析指标" : row.role === "target" ? "实测目标 Y" : row.role === "covariate" ? "已知因素 X" : "按组件绑定"));
      line.append(roleCell,
        element("td", "", plan.purpose === "explore" ? "分析样本（不训练）" : row.train ? row.role === "target" ? "作为标签 Y" : "作为因素 X" : "按组件合同"),
        element("td", "", plan.purpose === "explore" ? "不进行预测" : row.application ? "需要提供" : row.role === "target" ? "模型产出，无需填写" : "按组件合同"),
        element("td", "", formatUnit(row.variable.unit)));
      view.append(line);
    }
    host.append(view);
  }
  function products(plan) {
    const host = byId("wizard-products"); host.replaceChildren();
    for (const output of plan.composition.outputs) {
      const node = plan.composition.nodes.find((n) => n.code === output.source.node);
      const record = node && getRecords().get(node.component.code + "@" + node.component.revision);
      const port = record?.definition.outputs.find((p) => p.code === output.source.port);
      const card = element("div", "product-row");
      card.append(element("strong", "", port?.name || output.code), element("p", "", port?.description || "准确组件声明的成果")); host.append(card);
    }
    if (!plan.composition.outputs.length) host.append(element("p", "information-note", "建立计算关系后，系统会列出这个方法实际产出的成果。"));
  }
  function review(plan) {
    const host = byId("wizard-review-summary"); host.replaceChildren();
    const context = studySettings(plan, getRecords()), used = inputUsageRows(plan, getRecords()), targets = context?.parameters.targets || plan.evaluation.target_codes;
    const records = plan.composition.nodes.map((n) => getRecords().get(n.component.code + "@" + n.component.revision));
    const native = plan.layout?.study_template && !Object.values(plan.input_recipes).some((r) => r.kind === "observations");
    const data = native ? "已选择该研究所需的数据，请核对其对象和时间范围" : table ? (dataKind === "synthetic" ? "示例观测数据" : "标准观测记录") + " · " + table.rows.length + " 条 · " + table.columns.length + " 项指标" : "尚未提供观测数据";
    for (const [label, value] of [
      ["研究问题", plan.question || "尚未填写"], ["当前方法", records.map((r) => r?.definition.name || "准确组件").join(" → ") || "尚未建立模型"],
      ["预测目标", targets.map((c) => variableLabel(plan, c)).join("、") || (plan.purpose === "explore" ? "非训练分析" : "尚未选择")],
      ["已知因素", used.filter((r) => r.role === "covariate").map((r) => variableLabel(plan, r.variable.code)).join("、") || "按组件合同"],
      ["输入数据", data], ["评价方式", context ? "按日期留出；截至 " + context.parameters.training_end + " 训练，之后的实测用于评价" : "按准确方案与组件声明"],
    ]) {
      const row = element("dl"); row.append(element("dt", "", label), element("dd", "", value)); host.append(row);
    }
  }
  function render() {
    const plan = getDefinition(); if (!plan) return;
    for (const [id, value] of [["wizard-name", researchTitle(plan)], ["wizard-question", researchQuestion(plan)], ["wizard-success", plan.evaluation.success_criteria]]) {
      if (document.activeElement !== byId(id)) byId(id).value = value || "";
    }
    const native = plan.layout?.study_template && !Object.values(plan.input_recipes).some((r) => r.kind === "observations");
    byId("wizard-purpose").value = { train: "多指标预测研究", explore: "分析研究（不保存预测模型）", simulate: "模拟研究", fit: "拟合 / 标定" }[plan.purpose] || plan.purpose;
    const context = studySettings(plan, getRecords()), names = context?.parameters.targets || plan.evaluation.target_codes;
    byId("wizard-goal").textContent = native ? plan.question : names.length ? "预测「" + names.map((c) => plan.variables.find((v) => v.code === c)?.name || c).join("、") + "」与已知因素之间的关系" : plan.purpose === "explore" ? "对已选指标进行描述统计" : "从指标库选择要预测的实测指标";
    const records = plan.composition.nodes.map((n) => getRecords().get(n.component.code + "@" + n.component.revision));
    byId("wizard-method").textContent = records.length ? records.map((r) => r?.definition.name || "准确组件").join(" → ") : "尚未选择计算方法";
    byId("wizard-method-note").textContent = native ? "按所选研究范围分析数据；成果与适用条件见上方说明。" : plan.purpose === "explore" ? "统计已选指标，不拟合预测模型。" : "训练后可以保存模型，继续输入新因素进行预测。";
    document.querySelector(".modeling-workspace").hidden = Boolean(native && plan.purpose !== "train");
    const enabled = records.length && records.every((record) => record?.research_contract.execution.status === "available");
    byId("wizard-method-state").textContent = !records.length ? "待选择" : enabled ? "运行已启用" : "可设计 · 运行待启用";
    byId("wizard-method-state").dataset.state = enabled ? "ready" : "pending";
    if (checkedPlan && checkedPlan !== JSON.stringify(plan)) { checkedPlan = null; byId("wizard-check-result").replaceChildren(); }
    roleTable(plan); products(plan); review(plan);
    byId("study-run").textContent = plan.purpose === "explore" ? "检查并开始分析" : plan.purpose === "simulate" ? "检查并开始模拟" : "检查并开始训练";
  }
  async function check() {
    if (checking) return false;
    checking = true; byId("wizard-check").disabled = true; error("");
    const snapshot = getDefinition(), fingerprint = JSON.stringify(snapshot), host = byId("wizard-check-result");
    checkedPlan = fingerprint;
    host.replaceChildren(element("p", "information-note", "正在核对准确组件、变量用途与连接…"));
    try {
      const result = await validate(snapshot);
      if (fingerprint !== JSON.stringify(getDefinition())) throw new Error("检查期间方案已变化，请重新检查当前方案。");
      host.replaceChildren();
      if (!result.valid) {
        const list = element("div", "check-issues");
        list.append(element("strong", "", "请先补齐以下配置"));
        for (const issue of result.issues) list.append(element("p", "", issueMessage(issue)));
        host.append(list); return false;
      }
      host.append(element("p", "check-success", "方案结构检查通过。启动时还会核对实际输入、科学单位与来源，并封存本次版本。"));
      return true;
    } catch (exc) { error(exc.message); return false; }
    finally { checking = false; byId("wizard-check").disabled = false; }
  }
  function canLeave() {
    const plan = getDefinition();
    if (section === "basic" && (!plan.name.trim() || !plan.question.trim())) throw new Error("请填写研究方案名称和研究问题。");
    if (section === "inputs" && plan.purpose === "train" && !plan.composition.nodes.length) {
      const rows = inputUsageRows(plan);
      if (!rows.some((r) => r.role === "target") || !rows.some((r) => r.role === "covariate")) throw new Error("请从指标库选择至少一个实测目标和一个已知因素。");
    }
    if (section === "calculation" && !plan.composition.nodes.length) throw new Error("请从模型目录选择适合本研究的方法并完成参数配置。");
  }
  for (const button of document.querySelectorAll("[data-stage]")) button.addEventListener("click", () => navigate(button.dataset.stage));
  for (const button of document.querySelectorAll("[data-section]")) button.addEventListener("click", () => navigate("configure", button.dataset.section));
  for (const button of document.querySelectorAll("[data-template]:not(:disabled)")) button.addEventListener("click", () => {
    template = button.dataset.template;
    for (const item of document.querySelectorAll("[data-template]")) { item.classList.toggle("selected", item === button); item.setAttribute("aria-pressed", String(item === button)); }
  });
  byId("select-model-next").addEventListener("click", () => { navigate("configure", "basic"); if (template === "custom") onTechnical(); });
  byId("wizard-back").addEventListener("click", () => section === "basic" ? navigate("select") : navigate("configure", sections[sections.indexOf(section) - 1]));
  byId("wizard-next").addEventListener("click", () => {
    try { canLeave(); section === "outputs" ? navigate("review") : navigate("configure", sections[sections.indexOf(section) + 1]); }
    catch (exc) { error(exc.message); }
  });
  byId("wizard-edit-again").addEventListener("click", () => navigate("configure", "basic"));
  byId("wizard-save-draft").addEventListener("click", () => byId("cloud-save").click());
  byId("wizard-check").addEventListener("click", check);
  byId("wizard-name").addEventListener("change", (event) => draftField("name", event.target.value));
  byId("wizard-question").addEventListener("change", (event) => draftField("question", event.target.value));
  byId("wizard-success").addEventListener("change", (event) => draftField("success_criteria", event.target.value));
  byId("wizard-standard-example").addEventListener("click", async () => {
    try { await onExample("system"); navigate("configure", "inputs"); }
    catch (exc) { error(exc.message); }
  });
  byId("nav-data").addEventListener("click", (event) => { event.preventDefault(); navigate("configure", "sources"); });
  document.querySelector('a[href="#saved-studies"]').addEventListener("click", (event) => { event.preventDefault(); navigate("review"); byId("cloud-plans").focus(); });
  const dialog = byId("indicator-dialog");
  byId("open-indicator-library").addEventListener("click", () => { if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", ""); });
  byId("close-indicator-library").addEventListener("click", () => { if (dialog.close) dialog.close(); else dialog.removeAttribute("open"); });
  navigate(stage, section);
  return { render, showError: error, check,
    loaded() { checkedPlan = null; byId("wizard-check-result").replaceChildren(); if (getDefinition()?.composition.nodes.length && stage === "select") navigate("configure", "inputs"); else render(); },
    reset() { checkedPlan = null; byId("wizard-check-result").replaceChildren(); navigate("select", "basic"); },
    setData(value, kind) { table = value; dataKind = kind; render(); },
    setRun(run) { if (run) navigate("review"); },
    openReview() { navigate("review"); },
    openCalculation() { navigate("configure", "calculation"); },
    async beforeRun() { navigate("review"); if (!await check()) throw new Error("方案检查未通过，请返回配置补齐问题。"); },
  };
}
