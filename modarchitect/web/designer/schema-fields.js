import { element } from "./visuals.js?v=continuous1";
import { sourceFor } from "./editor.js?v=continuous1";

const legacyFields = {
  operation: { title: "操作", default: "fit", labels: { fit: "拟合", evaluate: "求值" } },
  axis_kind: { title: "时间轴", default: "elapsed_days", labels: { elapsed_days: "播种后天数", growing_degree_days: "生长度日" } },
  x_code: { title: "驱动变量", "x-research-variables": { table_port: "observations", roles: ["driver"] } },
  target_code: { title: "目标变量", "x-research-variables": { table_port: "observations", roles: ["target"] } },
  cutoff: { title: "拟合截止日期" },
  degree_day_definition: { title: "积温定义" },
  allow_extrapolation: { title: "允许外推" },
  simulation_only: { title: "仅用于模拟" },
};

function properties(schema) {
  return Object.entries(schema?.properties || {}).map(([name, field]) => {
    const reference = field.$ref?.match(/^#\/\$defs\/([\w]+)$/)?.[1];
    const resolved = reference ? { ...schema.$defs[reference], ...field } : field;
    return [name, schema.title === "LogisticGrowthRequest" ? { ...resolved, ...legacyFields[name] } : resolved];
  });
}

export function defaults(schema) {
  if (!schema) return null;
  return Object.fromEntries(properties(schema).filter(([, field]) => field.default !== undefined)
    .map(([name, field]) => [name, structuredClone(field.default)]));
}

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
  const binding = node && sourceFor(node, spec.table_port);
  const table = binding && !binding.node && definition.input_recipes[binding.port];
  const variables = definition.variables.filter((item) =>
    (definition.schema_version === "1.5" || spec.roles.includes(item.role)) && (!spec.unit || item.unit === spec.unit)
    && (!spec.observed || !definition.collection_requirements.some((requirement) => requirement.variable_code === item.code && requirement.catalog_binding?.value_nature && requirement.catalog_binding.value_nature !== "observed")) && (!table || (spec.new_column
      ? !table.variable_codes.includes(item.code) : table.variable_codes.includes(item.code))));
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
  return control;
}

export function parameters(definition, node, schema, requestPort, update, issue) {
  const grid = element("div", "field-grid");
  const value = definition.input_recipes[requestPort].value;
  for (const [name, property] of properties(schema)) {
    if (schema.title === "LogisticGrowthRequest" && name === "degree_day_definition" && value.axis_kind !== "growing_degree_days") continue;
    const title = property.title || name;
    const change = (next) => update(requestPort, name, next);
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
  return grid;
}
