const element = (tag, text = "") => { const item = document.createElement(tag); item.textContent = text; return item; };
const cropNames = { potato: "马铃薯", wheat: "小麦", maize: "玉米", tomato: "番茄" };

export function studySettings(host, row, { getDefinition, getRecords, onEdit } = {}) {
  if (!onEdit || !getDefinition) return;
  const allowed = row.editable_parameters || {};
  if (!Object.keys(allowed).length) return;
  host.append(element("h3", "设置研究范围"));
  const form = element("div"); form.className = "study-research-settings";
  const issue = element("p"); issue.setAttribute("role", "alert"); issue.className = "wizard-error"; issue.hidden = true;
  function edit(port, field, value) {
    const definition = getDefinition(); definition.input_recipes[port].value[field] = value;
    issue.hidden = true; onEdit(definition);
  }
  for (const [port, fields] of Object.entries(allowed)) {
    const plan = getDefinition(), value = plan.input_recipes[port].value, node = plan.composition.nodes.find((node) => node.bindings.some((binding) => !binding.source.node && binding.source.port === port));
    const schema = getRecords?.().get(node.component.code + "@" + node.component.revision)?.research_contract.request_schema;
    for (const field of fields) {
      const property = schema?.properties?.[field];
      if (field === "variables") {
        const set = element("fieldset"), legend = element("legend", "选择研究指标"); set.append(legend);
        for (const variable of row.indicator_options || []) {
          const label = element("label"), input = document.createElement("input"); input.type = "checkbox"; input.checked = value.variables.includes(variable.code); input.value = variable.code;
          input.addEventListener("change", () => {
            const selected = [...set.querySelectorAll("input:checked")].map((item) => item.value);
            if (!selected.length) { input.checked = true; issue.textContent = "请至少选择一项研究指标。"; issue.hidden = false; return; }
            edit(port, field, selected);
          }); label.append(input, element("span", variable.name)); set.append(label);
        } form.append(set); continue;
      }
      const label = element("label", property?.title || ({ as_of: "分析截止日期", crop_code: "研究作物", start_date: "开始日期", end_date: "结束日期" }[field]));
      const input = property?.enum ? document.createElement("select") : document.createElement("input");
      if (property?.enum) for (const option of property.enum) input.add(new Option(cropNames[option] || option, option));
      else input.type = "date";
      input.value = value[field]; input.dataset.studyParameter = field; input.required = true;
      input.addEventListener("change", () => edit(port, field, input.value)); label.append(input); form.append(label);
    }
  }
  host.append(form, issue);
}
