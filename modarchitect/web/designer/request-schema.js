import { sourceFor } from "./editor.js?v=continuous1";

// 旧合同按准确表单身份补读展示声明，不改写已登记的组件版本或科学单位。
const legacyFields = {
  operation: { title: "操作", default: "fit", labels: { fit: "拟合", evaluate: "求值" } },
  axis_kind: { title: "时间轴", default: "elapsed_days", labels: { elapsed_days: "天数（按驱动指标的起点）", growing_degree_days: "生长度日" } },
  x_code: { title: "驱动变量", "x-research-variables": { table_port: "observations", roles: ["driver"] } },
  target_code: { title: "目标变量", "x-research-variables": { table_port: "observations", roles: ["target"], observed: true } },
  cutoff: { title: "拟合截止日期" },
  degree_day_definition: { title: "积温定义" },
  allow_extrapolation: { title: "允许外推" },
  simulation_only: { title: "仅用于模拟" },
};

export function requestProperties(schema, value = {}) {
  return Object.entries(schema?.properties || {}).map(([name, field]) => {
    const reference = field.$ref?.match(/^#\/\$defs\/([\w]+)$/)?.[1];
    const resolved = reference ? { ...schema.$defs[reference], ...field } : field;
    const property = schema.title === "LogisticGrowthRequest" ? { ...resolved, ...legacyFields[name] } : resolved;
    if (schema.title === "LogisticGrowthRequest" && name === "x_code") {
      return [name, { ...property, "x-research-variables": { ...property["x-research-variables"], unit: value?.axis_kind === "growing_degree_days" ? "deg_c_day" : "day" } }];
    }
    return [name, property];
  });
}

export function defaults(schema) {
  if (!schema) return null;
  return Object.fromEntries(requestProperties(schema).filter(([, field]) => field.default !== undefined)
    .map(([name, field]) => [name, structuredClone(field.default)]));
}

export function variableCandidates(definition, node, spec) {
  const binding = node && sourceFor(node, spec.table_port);
  const table = binding && !binding.node && definition.input_recipes[binding.port];
  return definition.variables.filter((item) =>
    (definition.schema_version === "1.5" || spec.roles?.includes(item.role)) && (!spec.unit || item.unit === spec.unit)
    && (!spec.observed || spec.roles?.join() === "driver" || definition.collection_requirements.some((requirement) => requirement.variable_code === item.code))
    && (!spec.observed || !definition.collection_requirements.some((requirement) => requirement.variable_code === item.code && requirement.catalog_binding?.value_nature && requirement.catalog_binding.value_nature !== "observed")) && (!table || (spec.new_column
      ? !(table.variable_codes || []).includes(item.code) : (table.variable_codes || []).includes(item.code))));
}
