import { element } from "./visuals.js?v=continuous1";
import { editStudy, formatUnit, studySettings, variableLabel, inputUsageRows, resourceInputs, productRows, matchesStudyTemplate, studyInputDetails } from "./modeling.js?v=continuous1";
export { inputUsageRows } from "./modeling.js?v=continuous1";
import { issueMessage } from "./panels.js?v=continuous1";
import { researchTitle, researchQuestion } from "./study-library.js?v=continuous1";
import { inputProvision } from "./input-provision.js?v=continuous1";
import { calendarAxes } from "./calendar-axis.js?v=continuous1";

const sections = ["basic", "inputs", "targets", "sources", "calculation"];
const sectionNames = ["基础信息", "研究资料与候选因素", "目标指标", "数据来源", "计算与评价"];
const byId = (id) => document.getElementById(id);

function reviewSection(issue, plan) {
  const [section, index] = issue.path || [];
  if (["name", "question", "responsible_user_id"].includes(section)) return "basic";
  if (section === "variables") return plan.variables[index]?.role === "target" ? "targets" : "inputs";
  if (section === "collection_requirements") return "sources";
  if (section === "evaluation" && index === "success_criteria") return "review";
  if (section === "evaluation" && index === "target_codes") return "targets";
  return "calculation";
}

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

function ioTable(title, labels) {
  const view = element("table", "research-table"); view.setAttribute("aria-label", title);
  const head = element("thead"), heading = element("tr"), body = element("tbody");
  for (const label of labels) { const cell = element("th", "", label); cell.scope = "col"; heading.append(cell); }
  head.append(heading); view.append(head, body);
  const wrap = element("div", "research-table-wrap"); wrap.append(view);
  return { wrap, body };
}

function readonlyInputTable(title, items, sample = null) {
  const labels = ["数据项", "数据提供方式", "科学单位", "当前用途"];
  if (sample) labels.push("合成示例值");
  const { wrap, body } = ioTable(title, labels);
  for (const item of items) {
    const line = element("tr"); line.dataset.variableCode = item.code; if (item.port) line.dataset.inputPort = item.port;
    for (const content of [item.name, item.source, formatUnit(item.unit) || "—", item.use]) line.append(element("td", "", content));
    if (sample) line.append(element("td", "", String(sample[item.code] ?? "—")));
    body.append(line);
  }
  return wrap;
}

export function mountWizard({ getDefinition, getRecords, getMethod, getInputCatalog, getInspection, onEdit, onExample, onTechnical, onChooseIndicators, onSave, validate }) {
  const initial = location.hash.slice(1).split("/");
  const previousResultsPage = initial[0] === "configure" && initial[1] === "outputs";
  let stage = previousResultsPage ? "review" : ["select", "configure", "review"].includes(initial[0]) ? initial[0] : "select";
  let section = previousResultsPage ? "calculation" : sections.includes(initial[1]) ? initial[1] : "basic";
  let template = "growth", table = null, dataKind = "user_supplied", checkedPlan = null, checking = false;
  let templateInfo = null, saving = false;
  const saveControl = byId("wizard-save-design");
  saveControl.disabled = !onSave;

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
    byId("wizard-next").textContent = section === "calculation" ? "前往检查与确认 →" : "下一步 →";
    const url = new URL(location.href); url.hash = stage + (stage === "configure" ? "/" + section : "");
    history.replaceState(history.state, "", url);
    render();
  }
  function draftField(key, value) {
    const draft = structuredClone(getDefinition());
    if (key === "success_criteria") draft.evaluation[key] = value;
    else if (value === undefined) delete draft[key];
    else draft[key] = value;
    onEdit(draft);
  }
  function roleTable(plan) {
    const inputHost = byId("wizard-role-table"), outputHost = byId("wizard-output-table"), rows = inputUsageRows(plan, getRecords(), getInspection?.());
    const details = [...studyInputDetails(plan, templateInfo).values()].flat();
    const nativeInputs = details.filter((item) => item.kind === "input");
    const nativeTargets = details.filter((item) => item.kind === "target");
    inputHost.replaceChildren(); outputHost.replaceChildren();
    if (dataKind === "synthetic") for (const host of [inputHost, outputHost]) host.append(element("p", "input-channel-pending", "当前数据为合成示例；下列说明是正式研究的数据提供要求，不表示已经获取真实资料。"));
    const training = plan.purpose === "train";
    const groups = training ? [
      ["input", "模型输入", "预测时能够提供的已知条件。", rows.filter((r) => r.role === "covariate")],
      ["output", "预测输出", "希望模型预测的指标。训练和验证时需要提供对应实测值；预测时由模型生成。", rows.filter((r) => r.role === "target")],
      ["other", "尚未用于计算的资料", "通过上方“添加研究资料”采用；当前方法尚未使用这些指标。请在计算与评价中选择其用途，或移除不需要的资料。", rows.filter((r) => !["target", "covariate"].includes(r.role))],
    ] : [["input", "研究输入", "提供给当前方法分析、拟合或模拟的资料。", rows]];
    for (const [code, title, description, items] of groups) {
      if (code === "other" && !items.length) continue;
      if (code === "input" && !items.length && (nativeInputs.length || calendarAxes(plan).length)) continue;
      const host = code === "output" ? outputHost : inputHost;
      const group = element("section", "model-io-group"); group.dataset.ioGroup = code;
      const heading = element("h3", "", title); heading.id = "model-io-" + code;
      group.setAttribute("aria-labelledby", heading.id);
      group.append(heading, element("p", "modeling-muted", description));
      if (!items.length) { group.append(element("p", "information-note", code === "output" ? "点击上方添加目标指标，选择希望预测的生长指标。" : "点击上方添加研究资料，选择本研究可提供的已知条件。")); host.append(group); continue; }
      const { wrap, body } = ioTable(title, ["数据项", "数据提供方式", "科学单位", training ? "训练时提供" : "当前用途", training ? "预测时提供" : "计算时提供", "调整"]);
      for (const row of items) {
        const line = element("tr"), action = element("td"); line.dataset.variableCode = row.variable.code;
        const requirement = plan.collection_requirements.find((r) => r.variable_code === row.variable.code);
        const provision = inputProvision(requirement, getInputCatalog?.()), source = element("td", "input-provision");
        source.append(element("strong", "", provision.label));
        for (const detail of provision.details) source.append(element("small", "", detail));
        const observed = !requirement?.catalog_binding || requirement.catalog_binding.value_nature === "observed";
        if (training && row.editable && ["target", "covariate"].includes(row.role) && (row.role === "target" || observed)) {
          const nextRole = row.role === "target" ? "covariate" : "target";
          const move = element("button", "text-button", nextRole === "target" ? "设为预测输出" : "设为模型输入");
          move.type = "button"; move.dataset.variableRole = row.variable.code;
          move.setAttribute("aria-label", "将" + row.variable.name + move.textContent);
          move.addEventListener("click", () => {
            try { error(""); onEdit(changeInputRole(getDefinition(), row.variable.code, nextRole, getRecords())); }
            catch (exc) { error(exc.message); roleTable(getDefinition()); }
          }); action.append(move);
        } else if (!row.used) {
          const configure = element("button", "text-button", "配置用途"); configure.type = "button";
          configure.addEventListener("click", () => navigate("configure", "calculation")); action.append(configure);
          const referenced = Object.values(plan.input_recipes).some((recipe) => recipe.kind === "configuration" && Object.values(recipe.value).some((value) => value === row.variable.code || Array.isArray(value) && value.includes(row.variable.code)));
          const remove = element("button", "text-button", "移除资料"); remove.type = "button";
          remove.disabled = referenced || plan.composition.nodes.some((node) => !getRecords().has(node.component.code + "@" + node.component.revision));
          if (referenced) remove.title = "当前参数仍引用此指标，请先在计算与评价中调整引用。";
          remove.addEventListener("click", () => {
            const draft = structuredClone(getDefinition()), code = row.variable.code;
            draft.variables = draft.variables.filter((variable) => variable.code !== code);
            draft.collection_requirements = draft.collection_requirements.filter((requirement) => requirement.variable_code !== code);
            draft.evaluation.target_codes = draft.evaluation.target_codes.filter((target) => target !== code);
            for (const recipe of Object.values(draft.input_recipes)) if (recipe.variable_codes) recipe.variable_codes = recipe.variable_codes.filter((item) => item !== code);
            onEdit(draft);
          }); action.append(remove);
        } else action.append(element("span", "usage-chip", training && !observed ? "仅可作为输入" : "当前方法已采用"));
        line.append(element("td", "", row.variable.name), source, element("td", "", formatUnit(row.variable.unit)),
          element("td", "", !training ? row.used ? row.analysis ? "分析资料" : row.role === "target" ? "实测目标" : "计算输入" : "尚未用于计算" : row.train ? row.role === "target" ? "实测值" : "输入记录" : "不参与训练"),
          element("td", "", !training ? row.used ? "需要提供" : "不参与计算" : row.application ? "需要提供" : row.role === "target" ? "模型生成" : "不参与预测"), action);
        body.append(line);
      }
      group.append(wrap); host.append(group);
    }
    if (nativeInputs.length) {
      const title = nativeTargets.length || training ? "模型输入" : "研究输入";
      const label = rows.length ? "指定资料中的" + title : title;
      const group = element("section", "model-io-group"); group.dataset.ioGroup = "input";
      group.append(element("h3", "", label), readonlyInputTable(label, nativeInputs)); inputHost.append(group);
    }
    for (const axis of calendarAxes(plan)) {
      const card = element("section", "model-io-group"); card.dataset.platformDateAxis = axis.code;
      card.append(element("h3", "", "平台日期驱动"), element("p", "", "来源：平台根据每条资料的观测日期自动换算。无需手工采集或重复选择，不补齐没有观测的日期，也不代表播种后天数。"));
      inputHost.append(card);
    }
    if (nativeTargets.length) {
      const group = element("section", "model-io-group"); group.dataset.ioGroup = "output";
      group.append(element("h3", "", "目标指标（实测参照）"), readonlyInputTable("目标指标（实测参照）", nativeTargets));
      outputHost.append(group);
    } else if (!training) {
      outputHost.append(element("p", "modeling-muted", "预期成果可在「检查与确认」中查看。"));
    }
  }
  function sampleRecord() {
    return dataKind === "synthetic" ? table?.rows[0] ?? null : null;
  }
  function viewInputExample() {
    const sample = sampleRecord();
    if (!sample) return;
    const plan = getDefinition();
    const dialog = byId("study-input-example"), content = byId("study-input-example-content");
    content.replaceChildren();
    content.append(element("p", "modeling-muted", researchTitle(plan)));
    const observations = new Set(Object.values(plan.input_recipes).filter((recipe) => recipe.kind === "observations").flatMap((recipe) => recipe.variable_codes));
    const rows = inputUsageRows(plan, getRecords()).filter((row) => observations.has(row.variable.code));
    if (rows.length) {
      const items = rows.map(({ variable, role, used }) => ({ ...variable,
        source: inputProvision(plan.collection_requirements.find((requirement) => requirement.variable_code === variable.code), getInputCatalog?.()).label,
        use: role === "target" ? "实测目标" : used ? "计算输入" : "候选资料",
      }));
      content.append(element("p", "information-note", "合成记录 · " + sample.business_date));
      content.append(readonlyInputTable("标准观测字段", items, sample.values));
    }
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
  }
  function review(plan, methodNames) {
    const host = byId("wizard-review-summary"); host.replaceChildren();
    byId("wizard-view-flow").hidden = !plan.composition.nodes.length;
    const context = studySettings(plan, getRecords()), used = inputUsageRows(plan, getRecords()), targets = context?.parameters.targets || plan.evaluation.target_codes;
    const resources = resourceInputs(plan, getRecords()).filter((item) => item.recipe.kind !== "configuration"), products = productRows(plan, getRecords());
    const data = table ? (dataKind === "synthetic" ? "示例观测数据" : "标准观测记录") + " · " + table.rows.length + " 条 · " + table.columns.length + " 项指标" : resources.some((item) => item.recipe.kind === "artifact") ? "已引用方案资料，尚未核验本次运行数据；请核对项目的数据来源" : "尚未提供本次运行观测数据（不影响检查设计定义）";
    const evaluation = getInspection?.()?.evaluation;
    const percent = evaluation?.training_percent;
    const strategy = percent != null ? `按观测日期划分 · 训练 ${percent}% / 验证 ${100 - percent}%`
      : evaluation?.strategy === "configured_window" ? "按方案指定的验证窗口"
      : context?.parameters.training_end ? "按已保存日期留出，训练至 " + context.parameters.training_end
      : "按方案与组件声明";
    const metrics = evaluation?.metrics.filter((metric) => metric.selected !== false).map((metric) => metric.name);
    for (const [label, value] of [
      ["研究问题", plan.question || "尚未填写"], ["当前方法", methodNames || "尚未建立模型"],
      ["目标指标与成果", [...targets.map((c) => variableLabel(plan, c)), ...products.map((product) => product.name)].join("、") || "尚未配置成果"],
      ["研究资料", [...used.map((r) => variableLabel(plan, r.variable.code)), ...resources.map((item) => item.port.name + (item.recipe.kind === "deferred" ? "（待配置/接入）" : ""))].join("、") || "尚未配置研究资料"],
      ["输入数据", data], ["评价方式", strategy],
      ...(metrics?.length ? [["评价指标", metrics.join("、")]] : []),
    ]) {
      const row = element("dl"); row.append(element("dt", "", label), element("dd", "", value)); host.append(row);
    }
  }
  function render() {
    const plan = getDefinition(); if (!plan) return;
    for (const [id, value] of [["wizard-name", researchTitle(plan)], ["wizard-question", researchQuestion(plan)], ["wizard-responsible-user-id", plan.responsible_user_id], ["wizard-success", plan.evaluation.success_criteria]]) {
      if (document.activeElement !== byId(id)) byId(id).value = value || "";
    }
    const marker = plan.layout?.study_template;
    const matches = matchesStudyTemplate(plan, templateInfo);
    byId("wizard-template-version").value = !marker ? "自定义" : matches ? templateInfo.title + " · v" + templateInfo.revision : "模板版本待加载";
    const fixed = matches && templateInfo.input_policy?.mode === "approved_dataset";
    byId("open-indicator-library").hidden = fixed;
    byId("open-system-example").hidden = !sampleRecord();
    byId("open-output-library").hidden = fixed || plan.purpose !== "train";
    const records = plan.composition.nodes.map((n) => getRecords().get(n.component.code + "@" + n.component.revision));
    const methods = plan.composition.nodes.map((node) => getMethod?.(node.component));
    const stepNames = records.map((record, index) => methods[index]?.name || record?.definition.name || "准确组件");
    const methodNames = stepNames.filter((_, index) => !records[index]?.definition.configuration.research_model?.automatic_date_axis).join("、");
    byId("wizard-method").textContent = methodNames || "尚未选择计算方法";
    const reusable = records.some((record) => (record?.research_contract.capabilities || record?.definition.configuration.research_model?.execution)?.state_output);
    byId("wizard-method-note").textContent = reusable
      ? "可以先保存方案，收集到观测资料后再开始训练。" : "在下方查看这项研究如何从资料得到结果。";
    const inspection = getInspection?.();
    const enabled = records.length && records.every((record, index) => (methods[index]?.execution || record?.research_contract.execution.status) === "available");
    byId("wizard-method-state").textContent = !records.length ? "待选择" : inspection?.checks.operation.status === "blocked" ? "操作不兼容" : enabled ? "制品已登记 · 启动前检查" : "可设计 · 运行待启用";
    byId("wizard-method-state").dataset.state = enabled ? "ready" : "pending";
    if (checkedPlan && checkedPlan !== JSON.stringify(plan)) { checkedPlan = null; byId("wizard-check-result").replaceChildren(); }
    roleTable(plan); review(plan, stepNames.join("、"));
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
        for (const issue of result.issues) {
          const node = snapshot.composition.nodes.find((node) => node.code === issue.node);
          const item = element("div", "review-issue"), section = reviewSection(issue, snapshot);
          const edit = element("button", "text-button", section === "review" ? "修改评价说明" : "前往" + sectionNames[sections.indexOf(section)]);
          edit.type = "button";
          edit.addEventListener("click", () => {
            if (section === "review") { byId("wizard-success").focus(); return; }
            navigate("configure", section);
            document.querySelector('[data-section="' + section + '"]')?.focus();
          });
          const message = section === "review" ? "请填写评价与结论适用范围。" : issueMessage(issue, node && getRecords().get(node.component.code + "@" + node.component.revision));
          item.append(element("span", "", message), edit);
          list.append(item);
        }
        host.append(list); return false;
      }
      host.append(element("p", "check-success", "方案配置检查通过，可以保存。发起研究时会再次核对本次资料和执行条件。"));
      return true;
    } catch (exc) { error(exc.message); return false; }
    finally { checking = false; byId("wizard-check").disabled = false; }
  }
  function canLeave() {
    const plan = getDefinition();
    if (section === "basic" && (!plan.name.trim() || !plan.question.trim())) throw new Error("请填写研究方案名称和研究问题。");
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
    try { canLeave(); section === "calculation" ? navigate("review") : navigate("configure", sections[sections.indexOf(section) + 1]); }
    catch (exc) { error(exc.message); }
  });
  byId("wizard-edit-again").addEventListener("click", () => navigate("configure"));
  byId("wizard-save-draft").addEventListener("click", () => byId("cloud-save").click());
  byId("wizard-check").addEventListener("click", check);
  byId("wizard-view-flow").addEventListener("click", (event) => {
    event.preventDefault(); byId("research-flow-section").scrollIntoView({ block: "start" });
  });
  saveControl.addEventListener("click", async () => {
    if (saving || !onSave) return;
    saving = true; saveControl.disabled = true;
    try {
      if (!await check()) return;
      const saved = await onSave();
      if (saved) byId("wizard-check-result").replaceChildren(element("p", "check-success", "研究方案已保存 · " + (saved.version_name || "修订 " + saved.revision) + "。可从已保存的方案重新打开。"));
    } catch (exc) { error(exc.message); }
    finally { saving = false; saveControl.disabled = false; }
  });
  byId("wizard-name").addEventListener("change", (event) => draftField("name", event.target.value));
  byId("wizard-question").addEventListener("change", (event) => draftField("question", event.target.value));
  byId("wizard-responsible-user-id").addEventListener("change", (event) => draftField("responsible_user_id", event.target.value || undefined));
  byId("wizard-success").addEventListener("change", (event) => draftField("success_criteria", event.target.value));
  byId("wizard-standard-example").addEventListener("click", async () => {
    try { await onExample("system"); }
    catch (exc) { error(exc.message); }
  });
  byId("open-system-example").addEventListener("click", viewInputExample);
  byId("close-study-input-example").addEventListener("click", (event) => {
    event.preventDefault();
    const dialog = byId("study-input-example");
    if (dialog.close) dialog.close(); else dialog.removeAttribute("open");
    byId("open-system-example").focus();
  });
  byId("nav-data").addEventListener("click", (event) => { event.preventDefault(); navigate("configure", "sources"); });
  document.querySelector('a[href="#saved-studies"]').addEventListener("click", (event) => { event.preventDefault(); navigate("review"); byId("cloud-plans").focus(); });
  const dialog = byId("indicator-dialog");
  for (const [id, role, title] of [["open-indicator-library", "covariate", "选择研究资料与候选因素"], ["open-output-library", "target", "选择希望研究或预测的目标指标"]]) {
    byId(id).addEventListener("click", () => {
      onChooseIndicators?.(role); byId("indicator-dialog-title").textContent = title;
      if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
    });
  }
  byId("close-indicator-library").addEventListener("click", () => { if (dialog.close) dialog.close(); else dialog.removeAttribute("open"); });
  navigate(stage, section);
  return { render, showError: error, check,
    setTemplate(value) { templateInfo = value; render(); },
    loaded() { checkedPlan = null; byId("wizard-check-result").replaceChildren(); if (getDefinition()?.composition.nodes.length && stage === "select") navigate("configure", "inputs"); else render(); },
    reset() { checkedPlan = null; byId("wizard-check-result").replaceChildren(); navigate("select", "basic"); },
    setData(value, kind) { table = value; dataKind = kind; render(); },
    setRun(run) { if (run) navigate("review"); },
    openReview() { navigate("review"); },
    openInputs() { navigate("configure", "inputs"); },
    async beforeRun() { navigate("review"); if (!await check()) throw new Error("方案检查未通过，请返回配置补齐问题。"); },
  };
}
