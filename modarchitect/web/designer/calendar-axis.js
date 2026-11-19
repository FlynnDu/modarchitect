import { addConfiguration, addModel, connectInput, requestInput, sourceFor } from "./editor.js?v=continuous1";

export function calendarAxes(plan) {
  return plan.composition.nodes.filter((node) => node.component.code === "research_calendar_axis" && node.component.revision === 1).flatMap((node) => {
    const port = requestInput(plan, node), value = port && plan.input_recipes[port].value;
    return value?.output_code ? [{ node, code: value.output_code, origin: value.origin_date }] : [];
  });
}

export function ensureCalendarAxis(plan, records, consumer, spec) {
  const source = sourceFor(consumer, spec.table_port);
  if (!source) throw new Error("日期驱动需要先连接带观测日期的研究资料。");
  const previous = calendarAxes(plan).find((axis) => axis.node.code === source.node && source.port === "table");
  if (previous) return previous.code;
  const record = [...records.values()].find((record) => record.available_for_new_design && record.definition.configuration.research_model?.automatic_date_axis?.variable.unit === spec.unit);
  if (!record) return null;
  const declaration = record.definition.configuration.research_model.automatic_date_axis;
  const variable = structuredClone(declaration.variable);
  let suffix = 2;
  while (plan.variables.some((item) => item.code === variable.code)) variable.code = declaration.variable.code + "_" + suffix++;
  plan.variables.push(variable);
  const axis = addModel(plan, record);
  const request = record.research_contract.request_schema || record.definition.configuration.research_model.request_schema;
  addConfiguration(plan, axis, record, { output_code: variable.code, origin_date: request.properties.origin_date.const });
  connectInput(plan, records, axis, declaration.input_port, source);
  connectInput(plan, records, consumer, spec.table_port, { node: axis.code, port: declaration.output_port });
  return variable.code;
}
