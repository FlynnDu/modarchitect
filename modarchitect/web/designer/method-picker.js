import { element } from "./visuals.js?v=continuous1";
import { recordKey, nodeRecord } from "./editor.js?v=continuous1";
import { parameters } from "./schema-fields.js?v=continuous1";
import { methodNodes, methodRecords, methodRestriction, prepareMethodDraft, synchronizeLabels } from "./methods.js?v=continuous1";
import { issueMessage } from "./panels.js?v=continuous1";

export function mountMethodPicker({ getDefinition, getRecords, onEdit, validate, notify }) {
  const dialog = document.getElementById("method-dialog"), list = document.getElementById("method-list"), detail = document.getElementById("method-detail");
  const target = document.getElementById("method-target"), message = document.getElementById("method-message"), apply = document.getElementById("apply-method");
  let proposal = null, fingerprint = "", checking = false, generation = 0;
  const error = (text) => { message.textContent = text || ""; message.hidden = !text; };
  const close = () => { generation += 1; if (dialog.close) dialog.close(); else dialog.removeAttribute("open"); };
  function choose(record, deferParameters = false) {
    generation += 1;
    detail.replaceChildren(); proposal = null; apply.disabled = true; error("");
    detail.append(element("h3", "", record.definition.name));
    detail.append(element("p", "modeling-muted", record.research_contract.execution.status === "available" ? "本环境已登记运行制品；启动时仍需检查当次资料。" : "此版本可用于设计；本环境尚未启用运行，保存不代表可执行。"));
    try {
      proposal = prepareMethodDraft(getDefinition(), getRecords(), recordKey(record.definition), target.value || null, document.getElementById("input-training-end").value, { deferParameters });
      proposal.pendingParameters = deferParameters;
      apply.textContent = deferParameters ? "保留到编辑草稿（待配置）" : "检查并应用方法";
      if (proposal.request) detail.append(parameters(proposal.definition, proposal.node, record.research_contract.request_schema, proposal.request,
        (port, field, value) => { generation += 1; proposal.definition.input_recipes[port].value[field] = value; error(""); }));
      if (record.research_contract.request_schema?.properties?.target_code) detail.append(element("p", "modeling-muted", "此版本每个计算步骤拟合一个目标；请在目标变量中明确选择，其他候选指标不会自动参与该曲线。"));
      const pending = proposal.node.bindings.map((b) => b.source.node ? null : proposal.definition.input_recipes[b.source.port]).filter((r) => r?.kind === "deferred");
      if (pending.length) detail.append(element("p", "modeling-muted", deferParameters ? "可先保留待配置步骤继续编辑。必须补齐方法参数，才能通过完整检查并正式保存研究方案。" : "资料类型已保留为待接入输入；参数完整时可保存设计，实际运行前仍需接通对应资料。"));
      detail.append(element("p", "modeling-muted", "应用后使用此方法实际声明的输入、参数与成果。已有资料保留；未参与的指标不自动进入计算。"));
      apply.disabled = checking;
    } catch (exc) { error(exc.message); }
  }
  function render() {
    generation += 1;
    list.replaceChildren(); detail.replaceChildren(); proposal = null; apply.disabled = true; error("");
    const records = methodRecords(getRecords()), compatible = records.filter((record) => !methodRestriction(record));
    list.append(element("h3", "", "可用于设计的方法 · " + compatible.length));
    const other = element("details", "method-other");
    other.append(element("summary", "", "其他用途和指定资料方法 · " + (records.length - compatible.length)));
    for (const record of [...compatible, ...records.filter((item) => !compatible.includes(item))]) {
      const card = element("article", "method-choice"); card.dataset.method = recordKey(record.definition);
      card.append(element("strong", "", record.definition.name), element("small", "", "版本 " + record.definition.revision + " · " + (record.research_contract.execution.status === "available" ? "运行已启用" : "可设计 · 运行待启用")));
      const restriction = methodRestriction(record);
      if (restriction) card.append(element("p", "modeling-muted", restriction));
      const button = element("button", "button button-secondary", restriction ? "查看条件" : "选择并配置"); button.type = "button";
      button.addEventListener("click", () => choose(record)); card.append(button);
      const planned = element("button", "text-button", "先保留为待配置步骤"); planned.type = "button"; planned.dataset.deferMethod = recordKey(record.definition);
      planned.addEventListener("click", () => choose(record, true)); card.append(planned);
      (restriction ? other : list).append(card);
    }
    if (records.length > compatible.length) list.append(other);
  }
  function open() {
    const plan = getDefinition(), records = getRecords(); if (!plan) return;
    target.replaceChildren();
    const nodes = methodNodes(plan, records);
    for (const [index, node] of nodes.entries()) target.add(new Option((index + 1) + " · " + nodeRecord(node, records).definition.name, node.code));
    if (!nodes.length) target.add(new Option("建立第一个计算步骤", ""));
    target.value = nodes.at(-1)?.code || ""; target.disabled = nodes.length < 2;
    fingerprint = JSON.stringify(plan); render();
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
  }
  document.getElementById("choose-method").addEventListener("click", open);
  document.getElementById("close-method-picker").addEventListener("click", close);
  dialog.addEventListener("close", () => { generation += 1; });
  target.addEventListener("change", render);
  apply.addEventListener("click", async () => {
    if (!proposal || checking) return;
    checking = true; apply.disabled = true; target.disabled = true;
    const token = generation, selected = proposal, candidate = structuredClone(proposal.definition);
    try {
      if (fingerprint !== JSON.stringify(getDefinition())) throw new Error("研究方案已变化，请重新打开方法选择。");
      synchronizeLabels(candidate, getRecords());
      const result = await validate(candidate);
      if (fingerprint !== JSON.stringify(getDefinition())) throw new Error("检查期间方案已变化，原方案已保留，请重新选择。");
      if (token !== generation || !dialog.hasAttribute("open")) throw new Error("方法设置已变化或窗口已关闭，原方案已保留，请重新检查。");
      const pendingOnly = selected.pendingParameters && result.issues?.length && result.issues.every((issue) => issue.type === "incomplete_configuration");
      if (!result.valid && !pendingOnly) throw new Error(result.issues.map((issue) => issue.path ? issueMessage(issue, issue.node ? nodeRecord(candidate.composition.nodes.find((node) => node.code === issue.node), getRecords()) : selected.record) : issue.message).join("；"));
      const record = selected.record; onEdit(candidate); close();
      notify(pendingOnly ? "已保留「" + record.definition.name + "」为待配置步骤；完整检查尚未通过，请补齐参数。" : "已采用「" + record.definition.name + "」及其实际参数。" + (record.research_contract.execution.status === "available" ? "" : "当前环境尚待启用运行。"));
    } catch (exc) { error(exc.message); }
    finally { checking = false; apply.disabled = !proposal; target.disabled = target.options.length < 2; }
  });
  return { open };
}
