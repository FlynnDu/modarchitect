import { formatUnit } from "./modeling.js?v=continuous1";

const element = (tag, text = "") => { const item = document.createElement(tag); item.textContent = text; return item; };
const number = (value) => value === null || value === undefined ? "资料不足" : typeof value === "number" ? Number(value.toFixed(6)).toString() : value;

function table(host, headings, rows) {
  const view = element("table"); view.className = "research-table";
  const head = element("tr"); for (const title of headings) head.append(element("th", title)); view.append(head);
  for (const values of rows) { const row = element("tr"); for (const value of values) row.append(element("td", number(value))); view.append(row); }
  host.append(view);
}

export function renderAgronomicResult(host, result) {
  if (result?.format === "catalog_weather_conditions_v1") {
    const states = { triggered: "达到参考条件，需结合田间证据核查", not_triggered: "完整窗口未达到参考条件", not_evaluated: "资料覆盖不足，不能判断" };
    for (const item of result.results) {
      host.append(element("h3", item.object.field_ref + " · " + item.name), element("p", states[item.result]));
      table(host, ["窗口", "有效日", "窗口统计值", "参考阈值"], [[item.window.start_date + " 至 " + item.window.end_date, item.window.valid_days + "/" + item.window.expected_days, number(item.metric) + " " + formatUnit(item.unit), item.threshold + " " + formatUnit(item.unit)]]);
      if (item.window.missing_dates.length) host.append(element("p", "缺少日期：" + item.window.missing_dates.join("、")));
    }
    host.append(element("p", result.interpretation)); return true;
  }
  if (result?.format === "research_weather_conditions_v1") {
    const rule = result.rule, window = rule.window;
    const states = { triggered: "出现需要进一步核查的条件", not_triggered: "完整资料未达到本规则的条件", not_evaluated: "资料不足，当前不能判断" };
    host.append(element("h3", rule.name_zh), element("p", states[rule.result]), element("p", "截至 " + result.as_of + "，本窗口有 " + window.valid_days + " / " + window.expected_days + " 个合格日。"));
    const labels = { observed_tmin_c: "已有记录的最低温（℃）", minimum_temperature_c: "完整窗口最低温（℃）", observed_tmax_c: "已有记录的最高温（℃）", maximum_temperature_c: "完整窗口最高温（℃）", mean_temperature_c: "窗口平均温度（℃）", mean_vpd_kpa: "平均饱和水汽压差（kPa）", observed_rain_mm: "已有记录降雨量（mm）", rain_mm: "完整窗口降雨量（mm）", water_stress_factor: "模拟水分限制系数" };
    table(host, ["研究指标", "结果"], Object.entries(rule.metrics).map(([key, value]) => [labels[key] || "相关条件指标", value]));
    if (rule.qualification !== "complete") host.append(element("p", "日期覆盖或来源质量不足。已知信号不能解释为整个时段的完整结论，也不能据此排除其他风险。"));
    if (rule.reason_codes.includes("water_state_unavailable")) host.append(element("p", "缺少同日水分状态，本次只分析降雨条件。"));
    host.append(element("p", result.interpretation)); return true;
  }
  if (result?.format !== "agronomic_indicator_analysis_v1") return false;
  host.append(element("h3", "指标过程分析"), element("p", result.start_date + " 至 " + result.end_date + " · " + result.row_count + " 条记录 · " + result.context.support));
  const nature = { observed: "实测", estimated: "估计", simulated: "模拟" };
  table(host, ["指标与单位", "数值性质", "有效记录", "缺测", "最小值", "最大值", "均值", "首末变化"], result.indicators.map((item) => [item.name + " · " + formatUnit(item.unit), nature[item.value_kind], item.count, item.missing_count, item.minimum_value, item.maximum_value, item.mean, item.change]));
  const names = new Map(result.indicators.map((item) => [item.code, item.name]));
  if (result.relationships.length) {
    host.append(element("h4", "同日指标关系"));
    table(host, ["指标", "对照指标", "有效配对", "描述性相关系数"], result.relationships.map((item) => [names.get(item.left), names.get(item.right), item.paired_rows, item.correlation]));
    host.append(element("p", "少于三个有效配对或指标没有变化时，不计算相关系数；连续日期不等于独立试验单元。"));
  }
  const details = element("details"); details.append(element("summary", "查看所用日期与指标数值"));
  table(details, ["日期", ...result.indicators.map((item) => item.name + " · " + formatUnit(item.unit))], result.series.map((row) => [row.date, ...result.indicators.map((item) => row.values[item.code])]));
  host.append(details, element("p", result.interpretation)); return true;
}
