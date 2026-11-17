import { formatUnit } from "./modeling.js?v=continuous1";
import { renderAgronomicResult } from "./agronomic-results.js?v=continuous1";

// 旧方案省略操作以保持请求身份；新方案把研究目的明确送往服务端核验。
export function runOperation(plan) {
  if (plan.schema_version !== "1.5") return {};
  const operation = { train: "train", explore: "analyze", simulate: "simulate", fit: "calibrate" }[plan.purpose];
  if (!operation) throw new Error("这个研究目的尚未接入执行，请选择已保存模型预测或调整研究设置。");
  return { operation };
}

export function renderSummary(host, value) {
  if (renderAgronomicResult(host, value)) return true;
  if (value?.format !== "research_descriptive_summary_v1") return renderNativeResult(host, value);
  const text = (tag, content) => { const item = document.createElement(tag); item.textContent = content; return item; };
  host.append(text("p", `${value.business_date_start} — ${value.business_date_end} · ${value.row_count} 条观测 · ${value.object_count} 个地块作物种植季。多天观测不等于多个独立试验单位。`));
  const table = document.createElement("table"); table.className = "research-table";
  const heading = document.createElement("tr");
  for (const title of ["指标与单位", "记录数", "最小值", "最大值", "均值", "样本标准差"]) heading.append(text("th", title));
  table.append(heading);
  for (const variable of value.variables) {
    const row = document.createElement("tr");
    row.append(text("td", variable.name + " · " + formatUnit(variable.unit)));
    for (const key of ["count", "minimum", "maximum", "mean", "sample_std"]) row.append(text("td", variable[key] === null ? "样本不足" : Number(variable[key].toFixed(6)).toString()));
    table.append(row);
  }
  host.append(table); return true;
}

function renderNativeResult(host, value) {
  const text = (tag, content) => { const item = document.createElement(tag); item.textContent = content; return item; };
  const payload = value?.payload;
  if (payload && value.product) {
    const productNames = { greenhouse_reference_et: "温室日参考蒸散", greenhouse_weighing_crop_et_day: "完整 24 小时称重耗水", greenhouse_crop_et_comparison: "气象估算与称重实测对照" };
    host.append(text("h4", payload.algorithm ? "方法的独立留出评价" : productNames[value.product.code] || value.product.code));
    if (payload.algorithm && Array.isArray(payload.rows)) {
      const methods = { random_forest: "随机森林", xgboost: "XGBoost", gaussian_process: "高斯过程", lstm: "LSTM", convlstm: "ConvLSTM" };
      host.append(text("p", `方法 ${methods[payload.algorithm] || "所选预测方法"} · 训练 ${payload.training_count} 条 · 留出 ${payload.rows.length} 条 · MAE ${payload.mae.toFixed(5)} · RMSE ${payload.rmse.toFixed(5)} ${formatUnit(payload.target.unit)}`));
      const table = document.createElement("table"); table.className = "research-table";
      const heading = document.createElement("tr"); for (const label of ["试验对象", "预测目标时刻", "预测值", "实测值"]) heading.append(text("th", label)); table.append(heading);
      for (const row of payload.rows) {
        const line = document.createElement("tr");
        for (const item of [row.unit_ref, row.target_at, row.estimated.map((v) => v.toFixed(4)).join("、"), row.observed.map((v) => v.toFixed(4)).join("、")]) line.append(text("td", item));
        table.append(line);
      } host.append(table);
    } else if (Array.isArray(payload.hours)) {
      const table = document.createElement("table"); table.className = "research-table";
      const heading = document.createElement("tr"); for (const label of ["小时开始", "耗水（g/h）", "蒸腾（g/h）"]) heading.append(text("th", label)); table.append(heading);
      for (const hour of payload.hours) {
        const line = document.createElement("tr"); line.append(text("td", hour.scope.started_at), text("td", Number(hour.evapotranspiration_g_h.toFixed(4))), text("td", hour.transpiration_g_h === null ? "缺少蒸发分离证据" : Number(hour.transpiration_g_h.toFixed(4)))); table.append(line);
      } host.append(table);
    } else {
      const names = { reference_et_mm_d: "日参考蒸散（mm/d）", estimated_crop_et_mm_d: "模型日耗水（mm/d）", weighing_crop_et_mm_d: "称重日耗水（mm/d）", ground_area_m2: "栽培地面面积（m²）", et0_mm_d: "日参考蒸散（mm/d）", crop_et_mm_d: "作物日耗水（mm/d）", model_crop_et_mm_d: "模型日耗水（mm/d）", measured_crop_et_mm_d: "称重日耗水（mm/d）", difference_mm_d: "模型减实测（mm/d）", et_mm_d: "日蒸散（mm/d）", business_date: "业务日期" };
      const table = document.createElement("table"); table.className = "research-table";
      for (const [key, item] of Object.entries(payload)) if (typeof item === "number" || key === "business_date") {
        const line = document.createElement("tr"); line.append(text("th", names[key] || key), text("td", typeof item === "number" ? Number(item.toFixed(6)).toString() : item)); table.append(line);
      } host.append(table);
    }
  } else if (Array.isArray(value?.module_scores) && value.overall) {
    host.append(text("h4", "地块条件与结论适用性"), text("p", value.overall.comment));
    const table = document.createElement("table"); table.className = "research-table";
    const heading = document.createElement("tr"); for (const title of ["模块", "分数 / 状态", "依据与缺项"]) heading.append(text("th", title)); table.append(heading);
    for (const module of value.module_scores) {
      const line = document.createElement("tr"); line.append(text("td", module.name), text("td", module.score === null ? module.grade : module.score), text("td", module.unscored_reason || module.overall_exclusion_reason || module.score_scope)); table.append(line);
    } host.append(table);
  } else return false;
  return true;
}
