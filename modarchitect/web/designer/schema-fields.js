import { element } from "./visuals.js?v=continuous1";
import { requestProperties, variableCandidates } from "./request-schema.js?v=continuous1";
import { calendarAxes } from "./calendar-axis.js?v=continuous1";
// 已打开的旧页面仍会从此模块导入这些函数，保留出口以兼容浏览器缓存。
export { defaults, requestProperties, variableCandidates } from "./request-schema.js?v=continuous1";

export function field(title, name, control, wide = false) {
  const label = element("label", "field" + (wide ? " wide" : ""), title);
  control.dataset.field = name;
  label.append(control);
  return label;
}

export function selectField(options, value, change) {
  const select = element("select", "");
  for (const [id, label] of options) {
    const option = element("option", "", label);
    option.value = id;
    select.append(option);
  }
  select.value = value ?? "";
  select.addEventListener("change", () => change(select.value));
  return select;
}

export function choices(options, update, attribute) {
  const list = element("div", "choices");
  for (const [code, label, enabled] of options) {
    const row = element("label", "");
    const input = element("input", "");
    input.type = "checkbox";
    input.dataset[attribute] = code;
    input.checked = enabled;
    input.addEventListener("change", () => update(code, input.checked));
    row.append(input, element("span", "", label));
    list.append(row);
  }
  return list;
}

function variableControl(grid, definition, node, spec, title, name, shape, value, change) {
  const variables = variableCandidates(definition, node, spec);
  if (spec.roles?.join() === "driver" && calendarAxes(definition).some((axis) => axis.code === value)) {
    const control = element("input"); control.type = "text"; control.readOnly = true; control.value = "平台观测日期（自动使用）";
    grid.append(field("时间驱动", name, control), element("p", "field-note", "由平台根据实际观测日期生成，无需采集或选择天数；不表示播种后天数或积温。"));
    return control;
  }
  const options = variables.map((item) => [item.code, item.name + " · " + item.unit]);
  if (shape === "array") {
    const group = element("fieldset", "variable-picks");
    group.dataset.field = name;
    group.append(element("legend", "", title));
    const selected = new Set(Array.isArray(value) ? value : []);
    const rows = options.map(([code, label]) => [code, label, selected.has(code)]);
    for (const code of selected) {
      if (!options.some(([id]) => id === code)) rows.push([code, code + "（不在可用观测列中）", true]);
    }
    group.append(rows.length ? choices(rows, (code, enabled) => {
      if (enabled) selected.add(code);
      else selected.delete(code);
      change([...selected]);
    }, name) : element("p", "field-note", "请先添加此角色的观测变量。"));
    grid.append(group);
    return group;
  }
  if (value && !options.some(([id]) => id === value)) options.push([value, value + "（不在可用观测列中）"]);
  const control = selectField([["", "请选择"], ...options], value, (next) => change(next || undefined));
  grid.append(field(title, name, control));
  if (!variables.length) grid.append(element("p", "field-note", spec.unit === "day" ? "平台日期驱动尚未连接，请先连接带观测日期的研究资料，再重新选择此计算方法；无需人工添加天数。" : spec.unit === "deg_c_day" ? "当前没有符合条件的积温资料（deg_c_day）。可采用已有天数轴；积温指标及其计算来源须由系统登记后使用，普通气温不能代替积温。" : "当前没有符合该参数单位和来源要求的指标，请先补充研究资料。"));
  return control;
}

export function parameters(definition, node, schema, requestPort, update, issue) {
  const grid = element("div", "field-grid");
  const value = definition.input_recipes[requestPort].value;
  function render() {
    grid.replaceChildren();
    for (const [name, property] of requestProperties(schema, value)) {
      if (schema.title === "LogisticGrowthRequest" && name === "degree_day_definition" && value.axis_kind !== "growing_degree_days") continue;
      const title = property.title || name;
      const change = (next) => {
        update(requestPort, name, next);
        if (schema.title === "LogisticGrowthRequest" && name === "axis_kind") {
          const spec = requestProperties(schema, value).find(([field]) => field === "x_code")[1]["x-research-variables"];
          if (!variableCandidates(definition, node, spec).some((variable) => variable.code === value.x_code)) update(requestPort, "x_code", undefined);
          if (spec.unit === "day" && !value.x_code) {
            const automatic = calendarAxes(definition).find((axis) => variableCandidates(definition, node, spec).some((variable) => variable.code === axis.code));
            if (automatic) update(requestPort, "x_code", automatic.code);
          }
          render(); grid.querySelector('[data-field="axis_kind"]')?.focus();
        }
      };
      let control;
      if (property["x-research-variables"]) {
        control = variableControl(grid, definition, node, property["x-research-variables"], title, name, property.type, value[name], change);
      } else {
        const shape = property.type || property.anyOf?.find((option) => option.type !== "null")?.type;
        if (property.enum) {
          const options = property.enum.map((key) => [String(key), property.labels?.[key] || String(key)]);
          control = selectField([["", "请选择"], ...options], value[name], (next) =>
            change(property.enum.find((item) => String(item) === next)));
        } else {
          const structured = ["array", "object"].includes(shape) || !shape;
          control = element(structured ? "textarea" : "input", "");
          const kind = property.format === "date" ? "date" : { boolean: "checkbox", number: "number", integer: "number" }[shape] || "text";
          if (!structured) control.type = kind;
          if (property.const !== undefined) control.readOnly = true;
          if (kind === "number") control.step = shape === "integer" ? "1" : "any";
          if (kind === "checkbox") control.checked = value[name] ?? property.default ?? false;
          else control.value = structured && value[name] !== undefined ? JSON.stringify(value[name]) : value[name] ?? "";
          control.addEventListener("input", () => {
            if (kind === "checkbox") change(control.checked);
            else if (!control.value.trim()) change(property.anyOf?.some((item) => item.type === "null") ? null : undefined);
            else if (kind === "number") change(control.valueAsNumber);
            else if (structured) {
              try { change(JSON.parse(control.value)); control.removeAttribute("aria-invalid"); }
              catch { change(undefined); control.setAttribute("aria-invalid", "true"); }
            } else change(control.value);
          });
        }
        grid.append(field(title, name, control, true));
      }
      if (issue?.path?.[1] === requestPort && issue.path.at(-1) === name) control.setAttribute("aria-invalid", "true");
      if (property.description) grid.append(element("p", "field-note schema-note", property.description));
    }
  }
  render();
  return grid;
}
