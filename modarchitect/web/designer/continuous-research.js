import { renderSeriesCurve as renderDailyCurve } from "./observation-curves.js?v=continuous1";
export { renderDailyCurve };

const node = (tag, text = "", className = "") => {
  const value = document.createElement(tag); value.textContent = text;
  if (className) value.className = className;
  return value;
};
const STATUS = { active: "每日跟踪中", paused: "已暂停", completed: "观察期已完成", waiting_data: "等待资料", collecting: "正在获取资料", queued: "等待计算", running: "正在计算", succeeded: "已完成", failed: "未完成" };
const objectKey = (value) => JSON.stringify([value.field_ref, value.crop_code, value.season_ref]);
const issueText = (message) => {
  if (/manual observations have not been provided/i.test(message)) return "尚未补充本批次要求的人工观测。";
  if (/Provider data is unavailable/i.test(message)) return "提供方资料尚未齐备，将保留原观察日并等待重试。";
  if (/dispatch requires reconciliation/i.test(message)) return "资料采集回执待平台核对，暂缓重复提交。";
  if (/authorization or scope changed|boundary or season evidence changed/i.test(message)) return "研究对象的授权、边界或种植季已变化，请重新确认研究范围。";
  if (/predictors are not identifiable/i.test(message)) return "所选因素缺少独立变化，无法确定回归关系；请检查地块间土壤差异及重复因素。";
  if (/Insufficient training observations/i.test(message)) return "训练观测不足，请补充实测记录或调整训练范围。";
  return "本次资料或计算尚未通过校验，请查看本次运行结果中的具体说明。";
};

export function mountContinuousResearch({ api, save, getModel, report, follow }) {
  const host = document.getElementById("continuous-research");
  if (!host) return { refresh: async () => {} };
  let selected = null, page = 1, generation = 0, busy = false, series = null;
  host.append(node("h3", "每日研究"), node("p", "在观察期内，每天凌晨2点处理前一天完整资料，最后一天在次日出报告。缺资料会保留待补记录；当前支持逐日采样。"));
  const setup = node("details"); setup.append(node("summary", "启用当前方案的每日跟踪"));
  const form = node("form", "", "daily-settings"), scope = node("div", "", "daily-objects");
  const field = (parent, title, name, type = "text") => {
    const label = node("label", title), input = node("input"); input.name = name; input.type = type; input.required = true;
    if (type === "number") input.step = "any";
    label.append(input); parent.append(label); return input;
  };
  const start = field(form, "观察开始日", "start", "date"), end = field(form, "观察结束日", "end", "date");
  const addObject = () => {
    const row = node("fieldset"); row.append(node("legend", "自有研究对象"));
    for (const [title, name, type] of [["地块编号", "field_ref"], ["作物代码", "crop_code"], ["种植季编号", "season_ref"], ["参考点纬度", "latitude", "number"], ["参考点经度", "longitude", "number"]]) field(row, title, name, type);
    const remove = node("button", "移除此对象", "text-button"); remove.type = "button"; remove.addEventListener("click", () => { if (scope.children.length > 1) row.remove(); }); row.append(remove); scope.append(row);
  };
  addObject(); form.append(scope);
  const add = node("button", "＋ 添加研究对象", "button button-secondary"); add.type = "button"; add.addEventListener("click", addObject); form.append(add);
  const useModelLabel = node("label", "使用当前已选模型预测（无需提供预测目标）"), useModel = node("input"); useModel.type = "checkbox"; useModelLabel.prepend(useModel); form.append(useModelLabel);
  const submit = node("button", "启用每日研究", "button button-primary"); submit.type = "submit"; form.append(submit); setup.append(form); host.append(setup);
  const tools = node("div", "", "research-actions"), select = node("select"); select.setAttribute("aria-label", "选择每日研究");
  const reload = node("button", "刷新每日研究", "button button-secondary"), toggle = node("button", "暂停", "button button-secondary"); toggle.hidden = true; tools.append(select, reload, toggle); host.append(tools);
  const status = node("p"); status.setAttribute("role", "status"); host.append(status);
  const batches = node("div", "", "research-table-wrap"), pagination = node("div", "", "research-actions");
  const before = node("button", "较新批次", "text-button"), after = node("button", "较早批次", "text-button"); pagination.append(before, after); host.append(batches, pagination);
  const range = node("form", "", "research-actions"), from = field(range, "曲线开始日", "from", "date"), through = field(range, "曲线结束日", "through", "date");
  const apply = node("button", "查看日期范围", "button button-secondary"); range.append(apply); host.append(range);
  const choices = node("div", "", "research-actions"), variable = node("select"), object = node("select"); variable.setAttribute("aria-label", "曲线指标与来源"); object.setAttribute("aria-label", "曲线研究对象"); choices.append(variable, object); host.append(choices);
  const chart = node("div", "", "daily-chart"); host.append(chart);
  async function guard(action) {
    if (busy) return; busy = true;
    for (const control of host.querySelectorAll("button,select")) control.disabled = true;
    try { await action(); } catch (error) { status.textContent = error.message; report(error.message, true); }
    finally { busy = false; for (const control of host.querySelectorAll("button,select")) control.disabled = false; }
  }
  const draw = () => { const [output, code] = JSON.parse(variable.value || "[null,null]"); renderDailyCurve(chart, series, output, code, object.value); };
  async function loadSeries(custom = false) {
    const token = generation, identity = selected.task_id;
    const query = custom ? "?start="+from.value+"&end="+through.value : "";
    const result = await api("/report-tasks/"+identity+"/series"+query);
    if (token !== generation) return;
    series = result; from.value = result.start; through.value = result.end;
    const previous = variable.value; variable.replaceChildren();
    for (const column of result.columns) variable.add(new Option((column.output === "input" ? "输入 · " : "结果 · ")+column.name+" · "+formatUnit(column.unit), JSON.stringify([column.output, column.code])));
    if ([...variable.options].some((option) => option.value === previous)) variable.value = previous;
    object.replaceChildren(); const seen = new Set();
    for (const row of result.rows) { const key = objectKey(row.object); if (!seen.has(key)) { object.add(new Option(row.object.field_ref+" · "+row.object.crop_code+" · "+row.object.season_ref, key)); seen.add(key); } }
    draw();
  }
  async function show() {
    if (!select.value) return;
    generation += 1; selected = await api("/report-tasks/"+select.value);
    toggle.hidden = selected.status === "completed"; toggle.textContent = selected.status === "paused" ? "恢复每日研究" : "暂停每日研究";
    status.textContent = STATUS[selected.status]+" · 观察期 "+selected.observation_start+" 至 "+selected.observation_end+" · "+selected.objects.length+" 个研究对象";
    const result = await api("/report-tasks/"+selected.task_id+"/batches?page="+page);
    batches.replaceChildren(); const table = node("table", "", "research-table"), head = node("tr");
    for (const title of ["观察日", "计划触发（上海时间）", "最近更新（上海时间）", "状态", "操作"]) head.append(node("th", title)); table.append(head);
    for (const batch of result.items) {
      const row = node("tr"), actions = node("td"); row.append(node("td", batch.observation_day), node("td", new Date(batch.scheduled_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })), node("td", new Date(batch.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })), node("td", STATUS[batch.status]));
      if (batch.error) { const details = node("details"); details.append(node("summary", "查看原因"), node("p", issueText(batch.error))); row.children[3].append(details); }
      if (batch.run_id) { const view = node("button", "查看本次结果", "text-button"); view.addEventListener("click", () => guard(async () => follow(await api("/runs/"+batch.run_id)))); actions.append(view); }
      if (!batch.dataset_id && !["succeeded", "failed"].includes(batch.status)) {
        const download = node("button", "下载人工观测模板", "text-button"); download.addEventListener("click", () => guard(async () => {
          const template = await api("/report-batches/"+batch.batch_id+"/observation-template"), url = URL.createObjectURL(new Blob([JSON.stringify(template, null, 2)], { type: "application/json" }));
          const link = node("a"); link.href = url; link.download = batch.observation_day+"-人工观测.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        }));
        const uploadLabel = node("label", "补充人工观测"), file = node("input"); file.type = "file"; file.accept = ".json,application/json"; uploadLabel.append(file);
        file.addEventListener("change", () => guard(async () => { const chosen = file.files[0]; if (!chosen || chosen.size > 4000000) throw new Error("请选择4MB以内、已填写的当日人工观测文件。"); await api("/report-batches/"+batch.batch_id+"/observations", { method: "PUT", body: JSON.parse(await chosen.text()) }); await show(); }));
        actions.append(download, uploadLabel);
      }
      row.append(actions); table.append(row);
    }
    batches.append(result.items.length ? table : node("p", "尚未到首次触发时刻，等待海豚日计划启动。"));
    before.hidden = page <= 1; after.hidden = result.items.length < 100; await loadSeries();
  }
  async function refresh() {
    const result = await api("/report-tasks"), previous = select.value; select.replaceChildren();
    for (const task of result.items) select.add(new Option(task.name+" · "+task.observation_start+" 至 "+task.observation_end+" · "+STATUS[task.status], task.task_id));
    if ([...select.options].some((option) => option.value === previous)) select.value = previous;
    if (select.value) await show(); else status.textContent = "尚未启用每日研究。";
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); guard(async () => {
    if (!form.reportValidity()) return;
    const saved = await save(), version = await api("/plans/"+saved.design_id+"/publish", { method: "POST", body: { expected_revision: saved.revision } });
    const model = getModel(); if (useModel.checked && !model) throw new Error("请先选择已保存的预测模型。");
    const objects = [...scope.children].map((row) => { const read = (name) => row.querySelector(`[name=${name}]`).value; return { object: { field_ref: read("field_ref"), crop_code: read("crop_code"), season_ref: read("season_ref") }, reference_point: { latitude: Number(read("latitude")), longitude: Number(read("longitude")) } }; });
    const task = await api("/report-tasks", { method: "POST", idempotent: true, body: { design_version_id: version.design_version_id, observation_start: start.value, observation_end: end.value, objects, ...(useModel.checked ? { model_id: model.model_id } : {}) } });
    await refresh(); select.value = task.task_id; page = 1; await show(); setup.open = false;
  }); });
  select.addEventListener("change", () => guard(async () => { page = 1; await show(); })); reload.addEventListener("click", () => guard(refresh));
  toggle.addEventListener("click", () => guard(async () => { await api("/report-tasks/"+selected.task_id+(selected.status === "paused" ? "/resume" : "/pause"), { method: "POST", body: { expected_revision: selected.revision } }); await refresh(); }));
  before.addEventListener("click", () => guard(async () => { page = Math.max(1, page-1); await show(); })); after.addEventListener("click", () => guard(async () => { page += 1; await show(); }));
  range.addEventListener("submit", (event) => { event.preventDefault(); if (selected) guard(() => loadSeries(true)); });
  variable.addEventListener("change", draw); object.addEventListener("change", draw);
  return { refresh: () => guard(refresh) };
}
