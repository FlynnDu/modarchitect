import { element } from "./visuals.js?v=continuous1";
import { recordKey, nodeRecord } from "./editor.js?v=continuous1";
import { parameters } from "./schema-fields.js?v=guided2";
import { selectableMethodNodes, prepareMethodDraft, synchronizeLabels } from "./methods.js?v=calculation1";
import { issueMessage } from "./panels.js?v=continuous1";
import { parameterPreview } from "./inspection-view.js?v=calculation1";

export function mountMethodPicker({ getDefinition, getRecords, loadMethods, onEdit, validate, notify }) {
  const byId = (id) => document.getElementById(id);
  const dialog = byId("method-dialog"), list = byId("method-list"), detail = byId("method-detail");
  const target = byId("method-target"), message = byId("method-message"), apply = byId("apply-method");
  const back = byId("back-to-methods"), opener = byId("choose-method");
  let proposal = null, directory, fingerprint = "", checking = false, generation = 0;
  const error = (text) => { message.textContent = text || ""; message.hidden = !text; };
  const close = () => {
    generation += 1;
    if (dialog.close) dialog.close(); else dialog.removeAttribute("open");
    opener.focus();
  };

  function showCards() {
    generation += 1;
    proposal = null; detail.hidden = true; list.hidden = false; back.hidden = true; apply.hidden = true;
    error(""); list.replaceChildren();
    if (!directory) {
      list.append(element("p", "modeling-muted", "正在读取可采用的计算方式…"));
      return;
    }
    const current = getDefinition().composition.nodes.find((node) => node.code === target.value);
    for (const family of directory.families || [{ operation: "train", name: "关系训练与预测", planned: [] }]) {
      const grid = element("div", "method-list");
      for (const method of directory.items.filter((item) => (item.operation || "train") === family.operation)) {
        const key = recordKey(method.component), card = element("button", "method-choice");
        card.type = "button"; card.dataset.method = key;
        const currentMethod = current && recordKey(current.component) === key;
        card.append(element("strong", "", method.name), element("span", "method-description", method.relationship),
          element("small", "", currentMethod ? "当前方法 · 查看配置" : method.execution === "available" ? "可配置与运行" : "可配置 · 运行待启用"));
        card.addEventListener("click", () => choose(method));
        grid.append(card);
      }
      for (const method of family.planned) {
        const card = element("div", "method-choice method-planned");
        card.dataset.plannedMethod = method.code;
        card.append(element("strong", "", method.name), element("span", "", "待接入"));
        grid.append(card);
      }
      if (grid.childElementCount) list.append(element("h3", "method-family-title", family.name), grid);
    }
  }

  function choose(method) {
    generation += 1;
    proposal = null; list.hidden = true; detail.hidden = false; back.hidden = false; apply.hidden = false; apply.disabled = true;
    error(""); detail.replaceChildren();
    detail.append(element("h3", "", method.name), element("p", "modeling-muted", method.relationship));
    try {
      const config = method.configuration;
      proposal = prepareMethodDraft(getDefinition(), getRecords(), recordKey(method.component), target.value || null, "", { configuration: config });
      const { definition, node, request } = proposal;
      const recipe = definition.input_recipes[request];
      const schema = structuredClone(config.parameter_schema);
      for (const field of Object.keys(config.runtime_fields)) delete schema.properties[field];
      const settings = element("details", "method-advanced");
      settings.append(element("summary", "", "调整指标与高级参数"));
      const userSchema = { ...schema, properties: Object.fromEntries(Object.entries(schema.properties)
        .filter(([field]) => !(field in config.defaults) || config.advanced_fields?.includes(field))) };
      const form = parameters(definition, node, userSchema, request, (port, field, value) => {
        generation += 1;
        const values = definition.input_recipes[port].value;
        if (value === undefined) delete values[field]; else values[field] = value;
        preview(); error("");
      });
      const defaults = element("div", "method-summary");
      const preview = () => {
        defaults.replaceChildren(parameterPreview(definition, config.parameter_schema, recipe.value, recipe.runtime_fields));
      };
      preview();
      settings.open = schema.required?.some((field) => {
        const value = recipe.value[field];
        return field in userSchema.properties && (value == null || value === "" || Array.isArray(value) && !value.length);
      }) || false;
      settings.append(form);
      detail.append(defaults, settings);
      apply.disabled = checking;
    } catch (exception) { error(exception.message); }
    back.focus();
  }

  async function open() {
    const plan = getDefinition();
    if (!plan) return;
    target.replaceChildren();
    const nodes = selectableMethodNodes(plan, getRecords());
    for (const node of nodes) target.add(new Option(nodeRecord(node, getRecords()).definition.name, node.code));
    if (!nodes.length) target.add(new Option("新计算步骤", ""));
    target.value = nodes.at(-1)?.code || "";
    target.closest("label").hidden = nodes.length < 2;
    target.disabled = nodes.length < 2;
    fingerprint = JSON.stringify(plan);
    showCards();
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
    const token = generation;
    try {
      if (!directory) directory = await loadMethods();
      if (token === generation && dialog.hasAttribute("open")) showCards();
    } catch (exception) { if (token === generation) error(exception.message); }
  }

  opener.addEventListener("click", open);
  byId("close-method-picker").addEventListener("click", close);
  back.addEventListener("click", () => { showCards(); list.querySelector("button")?.focus(); });
  dialog.addEventListener("close", () => { generation += 1; });
  target.addEventListener("change", showCards);
  apply.addEventListener("click", async () => {
    if (!proposal || checking) return;
    checking = true; apply.disabled = true;
    const token = generation, selected = proposal, candidate = structuredClone(proposal.definition);
    try {
      if (fingerprint !== JSON.stringify(getDefinition())) throw new Error("研究方案已变化，请重新打开方法选择。");
      synchronizeLabels(candidate, getRecords());
      const result = await validate(candidate);
      if (token !== generation) {
        if (proposal === selected && dialog.hasAttribute("open")) error("方法设置已变化，请重新应用。");
        return;
      }
      if (!dialog.hasAttribute("open") || fingerprint !== JSON.stringify(getDefinition())) return;
      if (!result.valid) throw new Error(result.issues.map((issue) => issue.path ? issueMessage(issue, selected.record) : issue.message).join("；"));
      onEdit(candidate); close(); notify("已应用计算方式。请核对下方预览后保存方案。");
    } catch (exception) { if (token === generation) error(exception.message); }
    finally { checking = false; apply.disabled = !proposal; }
  });
  return { open };
}
