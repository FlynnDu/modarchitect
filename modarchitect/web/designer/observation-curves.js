import { formatUnit } from "./modeling.js?v=continuous1";

const node = (tag, text = "", className = "") => {
  const value = document.createElement(tag); value.textContent = text;
  if (className) value.className = className;
  return value;
};
const objectKey = (value) => JSON.stringify([value.field_ref, value.crop_code, value.season_ref]);

export function renderSeriesCurve(host, series, output, code, object, recordLabel = "条真实批次记录") {
  host.replaceChildren();
  const column = series.columns.find((c) => c.output === output && c.code === code);
  const points = series.rows.filter((r) => r.output === output && objectKey(r.object) === object && Number.isFinite(r.values[code])).sort((a, b) => a.business_date.localeCompare(b.business_date));
  if (!column || !points.length) { host.append(node("p", "所选日期尚无该指标的已完成记录。缺资料或未完成批次不会生成曲线。")); return; }
  const kind = { observed: "实测", predicted: "模型预测", simulated: "模型模拟", estimated: "来源估计" }[column.value_kind] || "来源资料";
  host.append(node("p", column.name + " · " + formatUnit(column.unit) + " · " + kind + " · " + points.length + " " + recordLabel));
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 760 250"); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", column.name + "逐日变化，" + formatUnit(column.unit));
  const xmin = Date.parse(series.start), xmax = Math.max(xmin + 86400000, Date.parse(series.end));
  const values = points.map((p) => p.values[code]), low = Math.min(...values), high = Math.max(...values);
  const pad = (high - low) * .1 || Math.max(Math.abs(low) * .05, 1), ymin = low - pad, ymax = high + pad;
  const x = (day) => 65 + (Date.parse(day) - xmin) / (xmax - xmin) * 660;
  const y = (value) => 202 - (value - ymin) / (ymax - ymin) * 175;
  const draw = (tag, attributes, text = "") => {
    const shape = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attributes)) shape.setAttribute(key, value);
    shape.textContent = text; svg.append(shape); return shape;
  };
  draw("path", { d: "M65,20 V202 H725", fill: "none", stroke: "#a5b8ad" });
  for (const [label, value] of [[ymin, ymin], [(ymin+ymax)/2, (ymin+ymax)/2], [ymax, ymax]]) draw("text", { x: 56, y: y(value)+4, "text-anchor": "end", "font-size": 12 }, Number(label.toPrecision(4)).toString());
  draw("text", { x: 65, y: 228, "font-size": 12 }, series.start);
  draw("text", { x: 725, y: 228, "text-anchor": "end", "font-size": 12 }, series.end);
  let previous = null;
  for (const point of points) {
    if (previous && Date.parse(point.business_date)-Date.parse(previous.business_date) === 86400000) draw("path", { d: `M${x(previous.business_date)},${y(previous.values[code])} L${x(point.business_date)},${y(point.values[code])}`, stroke: "#258054", "stroke-width": 2, fill: "none" });
    const dot = draw("circle", { cx: x(point.business_date), cy: y(point.values[code]), r: 4, fill: "#258054" });
    const title = document.createElementNS(ns, "title"); title.textContent = point.business_date + " · " + point.values[code] + " " + formatUnit(column.unit); dot.append(title); previous = point;
  }
  host.append(svg);
  const details = node("details"); details.append(node("summary", "查看曲线数据"));
  const table = node("table", "", "research-table"), heading = node("tr"); heading.append(node("th", "观察日"), node("th", column.name + " · " + formatUnit(column.unit))); table.append(heading);
  for (const point of points) { const row = node("tr"); row.append(node("td", point.business_date), node("td", String(point.values[code]))); table.append(row); }
  details.append(table); host.append(details);
}

export function renderTableCurves(host, table) {
  host.replaceChildren();
  if (!table?.rows?.length || !table.columns?.length) return;
  const rows = table.rows.filter((row) => row.object && row.business_date && row.values);
  const columns = table.columns.filter((column) => rows.some((row) => Number.isFinite(row.values[column.code])));
  if (!rows.length || !columns.length) return;
  const objects = [...new Map(rows.map((row) => [objectKey(row.object), row.object])).entries()];
  const days = rows.map((row) => row.business_date).sort();
  const series = { start: days[0], end: days.at(-1), columns: columns.map((column) => ({ ...column, output: "result" })), rows: rows.map((row) => ({ ...row, output: "result" })) };
  const controls = node("div", "", "research-curve-controls"), variable = node("select"), object = node("select");
  variable.setAttribute("aria-label", "选择曲线指标"); object.setAttribute("aria-label", "选择曲线研究对象");
  for (const column of columns) { const option = node("option", column.name + " · " + formatUnit(column.unit)); option.value = column.code; variable.append(option); }
  for (const [key, item] of objects) { const option = node("option", item.field_ref + " · " + item.crop_code + " · " + item.season_ref); option.value = key; object.append(option); }
  if (columns.length > 1) { const label = node("label", "指标 "); label.append(variable); controls.append(label); }
  if (objects.length > 1) { const label = node("label", "研究对象 "); label.append(object); controls.append(label); }
  else controls.append(node("p", "研究对象：" + objects[0][1].field_ref));
  const chart = node("div", "", "observation-curve");
  const render = () => renderSeriesCurve(chart, series, "result", variable.value, object.value, "条结果记录");
  variable.addEventListener("change", render); object.addEventListener("change", render);
  host.append(controls, chart); render();
}
