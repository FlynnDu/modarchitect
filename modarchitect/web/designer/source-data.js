const recordKey = (row) => [row.object.field_ref, row.object.crop_code, row.object.season_ref, row.business_date].join("\u0000");

export function mergeSourceTables(table, sources) {
  if (!table && !sources.length) throw new Error("尚无可采用的来源记录。");
  const union = [...new Map(sources.flatMap((source) => source.rows).map((row) => [recordKey(row), row])).values()];
  const result = table ? structuredClone(table) : { columns: [], rows: union.map((row) => ({ ...structuredClone(row), values: {} })) };
  const columns = new Map(result.columns.map((column) => [column.code, column]));
  const collected = new Map();
  for (const source of sources) {
    for (const column of source.columns) {
      const expected = columns.get(column.code);
      if (column.value_kind !== "estimated" || expected && (expected.unit !== column.unit || expected.name !== column.name)) throw new Error("采集指标与当前研究不一致，请重新核对来源。");
      if (expected) Object.assign(expected, column);
      else { const added = structuredClone(column); result.columns.push(added); columns.set(added.code, added); }
      if (!collected.has(column.code)) collected.set(column.code, new Map());
      const rows = collected.get(column.code);
      for (const row of source.rows) {
        const key = recordKey(row);
        if (rows.has(key)) throw new Error("平台资料存在重复对象和日期，请核对来源。");
        rows.set(key, row.values[column.code]);
      }
    }
  }
  for (const row of result.rows) {
    for (const [code, rows] of collected) {
      if (!rows.has(recordKey(row))) throw new Error("采集资料未覆盖当前观测的对象和日期，已保留原数据。");
      row.values[code] = rows.get(recordKey(row));
    }
  }
  delete result.source_sha256;
  return result;
}

export function commonSourceDates(table, sources) {
  const coverage = new Map();
  for (const source of sources) for (const column of source.columns) {
    if (!coverage.has(column.code)) coverage.set(column.code, new Set());
    for (const row of source.rows) coverage.get(column.code).add(recordKey(row));
  }
  const candidates = table?.rows || [...new Map(sources.flatMap((source) => source.rows).map((row) => [recordKey(row), row])).values()];
  const rows = candidates.filter((row) => [...coverage.values()].every((keys) => keys.has(recordKey(row))));
  if (!rows.length) throw new Error("没有各项来源都齐备的对象和日期，请调整研究范围或补充资料。");
  const base = table ? { ...structuredClone(table), rows: structuredClone(rows) } : { columns: [], rows: rows.map((row) => ({ ...structuredClone(row), values: {} })) };
  return { table: mergeSourceTables(base, sources), total: candidates.length, excluded: candidates.length-rows.length };
}

export function splitAcquisitionRange(range, maximum) {
  const day = 86400000, start = Date.parse(range.start_date), end = Date.parse(range.end_date);
  if (!Number.isInteger(maximum) || maximum < 1 || !Number.isFinite(start) || !Number.isFinite(end) || start > end) throw new Error("请核对取数日期范围与来源约束。");
  const ranges = [];
  for (let cursor = start; cursor <= end; cursor += maximum*day) ranges.push({ ...range, start_date: new Date(cursor).toISOString().slice(0,10), end_date: new Date(Math.min(end,cursor+(maximum-1)*day)).toISOString().slice(0,10) });
  return ranges;
}

export function acquisitionRange(table) {
  if (!table?.rows?.length) throw new Error("请先载入实测观测，用它确定研究对象与日期。");
  const first = table.rows[0].object;
  if (table.rows.some((row) => ["field_ref", "crop_code", "season_ref"].some((key) => row.object[key] !== first[key]))) throw new Error("本次采集支持一个地块种植季，多个对象请分开采集和研究。");
  const dates = table.rows.map((row) => row.business_date).sort();
  if (dates.some((value) => !/^\d{4}-\d{2}-\d{2}$/.test(value))) throw new Error("请先填写有效观测日期。");
  return { object: structuredClone(first), start_date: dates[0], end_date: dates.at(-1) };
}

export function mountSourceData({ api, getDefinition, getData, getDataKind, saveDefinition, adopt, report }) {
  const host = document.getElementById("source-data-panel");
  if (!host) return { render() {} };
  let pending = false, candidates = null;
  const title = document.createElement("h3"); title.textContent = "采集平台资料";
  const note = document.createElement("p"); note.className = "research-caption";
  note.textContent = "按明确对象和日期取得天气、土壤或卫星资料。卫星仅在合格过境日有记录；参考位置由你声明。";
  const form = document.createElement("form"); form.className = "research-actions";
  const scope = document.createElement("fieldset"); scope.hidden = true;
  const legend = document.createElement("legend"); legend.textContent = "自动取数的研究对象和日期"; scope.append(legend);
  for (const [name, title, type] of [["field_ref", "地块编号", "text"], ["crop_code", "作物代码", "text"], ["season_ref", "种植季编号", "text"], ["start_date", "开始日期", "date"], ["end_date", "结束日期", "date"]]) {
    const label = document.createElement("label"); label.textContent = title;
    const input = document.createElement("input"); input.name = name; input.type = type; label.append(input); scope.append(label);
  }
  form.append(scope);
  for (const [name, text, min, max] of [["latitude", "参考点纬度", -90, 90], ["longitude", "参考点经度", -180, 180]]) {
    const label = document.createElement("label"); label.textContent = text;
    const input = document.createElement("input"); input.name = name; input.type = "number"; input.step = "any"; input.min = min; input.max = max; input.required = true;
    label.append(input); form.append(label);
  }
  const extra = document.createElement("div"); form.append(extra);
  let objectSignature = "";
  const button = document.createElement("button"); button.type = "submit"; button.className = "button button-secondary"; button.textContent = "采集所选平台指标"; form.append(button);
  const status = document.createElement("p"); status.className = "research-caption"; status.setAttribute("role", "status");
  const adoption = document.createElement("div"); adoption.hidden = true;
  const coverage = document.createElement("p"), dates = document.createElement("p");
  const apply = document.createElement("button"); apply.type = "button"; apply.className = "button button-secondary"; apply.textContent = "重新应用已取得资料";
  const intersect = document.createElement("button"); intersect.type = "button"; intersect.className = "button button-secondary"; intersect.textContent = "仅采用来源齐备的对象和日期";
  adoption.append(coverage, dates, apply, intersect);
  host.append(title, note, form, status, adoption);
  function applySources(onlyCommon = false) {
    if (!candidates || JSON.stringify(getDefinition()) !== candidates.definition) throw new Error("研究输入已变化，请重新核对取数要求。");
    const tables = candidates.sources.map((source) => source.observations);
    const selection = onlyCommon ? commonSourceDates(getData(), tables) : { table: mergeSourceTables(getData(), tables), excluded: 0 };
    const keys = new Set(selection.table.rows.map(recordKey));
    const ids = candidates.ids.filter((id, index) => candidates.sources[index].observations.rows.some((row) => keys.has(recordKey(row))));
    adopt(ids, selection.table);
    const needsTargets = ["train", "fit"].includes(getDefinition().purpose) && getDefinition().evaluation?.target_codes?.length;
    status.textContent = "已采用 " + selection.table.rows.length + " 条配对记录" + (selection.excluded ? "；本次明确排除 " + selection.excluded + " 条资料不齐备记录。" : needsTargets ? "；平台数值只读，实测目标仍需提供。" : "；平台数值只读，请核对对象、日期和资料覆盖。");
    report(status.textContent);
  }
  for (const [control, onlyCommon] of [[apply, false], [intersect, true]]) control.addEventListener("click", () => {
    try { applySources(onlyCommon); } catch (error) { status.textContent = error.message; report(error.message, true); }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    pending = true; button.disabled = true;
    for (const input of form.querySelectorAll("input")) input.disabled = true;
    try {
      if (getDataKind() !== "user_supplied") throw new Error("请先载入自有实测记录；合成示例不能与平台资料组合后当作真实研究。");
      const definition = JSON.stringify(getDefinition());
      const data = getData(), ranges = [];
      if (data?.rows?.length) {
        const groups = new Map();
        for (const row of data.rows) { const key = recordKey({ ...row, business_date: "" }); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(row); }
        for (const rows of groups.values()) ranges.push(acquisitionRange({ rows }));
      } else {
        const read = (name) => form.elements.namedItem(name).value;
        const object = Object.fromEntries(["field_ref", "crop_code", "season_ref"].map((name) => [name, read(name)]));
        if (Object.values(object).some((value) => !value) || !read("start_date") || !read("end_date")) throw new Error("请填写研究对象与完整日期范围。");
        ranges.push({ object, start_date: read("start_date"), end_date: read("end_date") });
      }
      const saved = await saveDefinition();
      const catalog = await api("/api/v1/model-center/research-inputs");
      const requirements = getDefinition().collection_requirements.filter((item) => item.source === "third_party");
      const selectedEntries = requirements.map((requirement) => catalog.items.find((item) => item.source.binding?.code === requirement.catalog_binding.code && item.source.binding?.contract_sha256 === requirement.catalog_binding.contract_sha256));
      if (selectedEntries.some((entry) => !entry)) throw new Error("取数要求未在当前目录中找到准确来源，请检查方案。");
      const maximum = Math.min(366, ...selectedEntries.map((entry) => entry.source.definition?.acquisition?.maximum_days || 366));
      const allSources = [], ids = [];
      for (const [index, range] of ranges.entries()) {
      const suffix = index ? "_" + index : "";
      for (const part of splitAcquisitionRange(range, maximum)) {
      const body = { ...part, expected_revision: saved.revision, reference_point: { latitude: form.elements.namedItem("latitude"+suffix).valueAsNumber, longitude: form.elements.namedItem("longitude"+suffix).valueAsNumber } };
      const job = await api("/plans/" + saved.design_id + "/input-acquisitions", { method: "POST", body, idempotent: true });
      let value;
      const end = Date.now() + 600000;
      while (Date.now() < end) {
        value = await api("/input-acquisitions/" + job.acquisition_id);
        if (["succeeded", "failed", "cancelled", "uncertain"].includes(value.status)) break;
        status.textContent = value.status === "running" ? "正在取得并核验平台资料…" : "采集请求已保存，等待调度…";
        await new Promise((resolve) => setTimeout(resolve, 1800));
      }
      if (value?.status !== "succeeded") throw new Error(value?.error || "采集尚未完成，请稍后重试；当前观测未被替换。");
      const sources = await Promise.all(value.snapshot_ids.map((id) => api("/input-snapshots/" + id)));
      if (JSON.stringify(getDefinition()) !== definition) throw new Error("采集期间研究方案发生变化，资料已保留，本次未自动应用。");
      if (sources.some((item) => item.support?.requested_point?.latitude !== body.reference_point.latitude || item.support?.requested_point?.longitude !== body.reference_point.longitude)) throw new Error("平台资料的参考位置与本次请求不一致，未自动应用。");
      allSources.push(...sources); ids.push(...value.snapshot_ids);
      }
      }
      candidates = { definition, sources: allSources, ids };
      adoption.hidden = false;
      coverage.textContent = "资料已取得，请核对完整配对范围。"; dates.textContent = "";
      const common = commonSourceDates(getData(), allSources.map((source) => source.observations));
      coverage.textContent = "资料已取得：" + common.table.rows.length + " / " + common.total + " 条对象日期记录可完整配对；未采用前保留当前研究数据。";
      const availableDates = [...new Set(common.table.rows.map((row) => row.business_date))].sort();
      dates.textContent = "可配对日期：" + availableDates.slice(0,20).join("、")+(availableDates.length > 20 ? "…（共"+availableDates.length+"天）" : "");
      intersect.hidden = common.excluded === 0;
      if (!common.excluded) applySources();
      else { status.textContent = "存在缺测。请核对可配对日期，再明确是否缩小本次研究样本；系统未自动删减记录。"; report(status.textContent); }
    } catch (error) { status.textContent = error.message; report(error.message, true); }
    finally { pending = false; render(); }
  });
  function render() {
    host.hidden = !getDefinition().collection_requirements.some((item) => item.catalog_binding && item.source === "third_party");
    button.disabled = pending;
    apply.disabled = pending; intersect.disabled = pending;
    if (candidates && candidates.definition !== JSON.stringify(getDefinition())) adoption.hidden = true;
    const data = getData(); scope.hidden = Boolean(data?.rows?.length);
    for (const input of scope.querySelectorAll("input")) input.required = !scope.hidden;
    const objects = [...new Map((data?.rows || []).map((row) => [recordKey({ ...row, business_date: "" }), row.object])).values()];
    const signature = JSON.stringify(objects);
    if (!pending && signature !== objectSignature) {
      objectSignature = signature; extra.replaceChildren();
      for (const [index, object] of objects.entries()) {
        if (!index) continue;
        const fieldset = document.createElement("fieldset"), legend = document.createElement("legend"); legend.textContent = object.field_ref+" · "+object.crop_code+" · "+object.season_ref; fieldset.append(legend);
        for (const [name, title, min, max] of [["latitude", "参考点纬度", -90, 90], ["longitude", "参考点经度", -180, 180]]) {
          const label = document.createElement("label"); label.textContent = title; const input = document.createElement("input"); input.name = name+"_"+index; input.type = "number"; input.step = "any"; input.min = min; input.max = max; input.required = true; label.append(input); fieldset.append(label);
        } extra.append(fieldset);
      }
    }
    for (const input of form.querySelectorAll("input")) input.disabled = pending;
  }
  return { render };
}
