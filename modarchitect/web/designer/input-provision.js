// 只解释已保存的来源合同；不据此判断当次资料是否齐备。
export const canAddInput = (entry) => entry.selectable;

export function inputGroup(catalog, entry) {
  return catalog.categories?.find((parent) => parent.code === entry.category)?.children?.find((child) => child.code === entry.subcategory)?.name || "";
}

export function inputProvision(requirement, catalog = { items: [], categories: [] }) {
  const binding = requirement?.catalog_binding;
  const entry = binding && catalog.items.find((item) => ["kind", "code", "definition_version", "contract_sha256"].every((key) => binding[key] && item.source.binding?.[key] === binding[key]));
  if (!entry) return { entry: null, label: binding ? "历史来源待核验" : "未绑定来源", details: [binding
    ? "当前目录未找到该准确来源版本；请在数据来源中核对。"
    : "请从系统指标库确认来源；不能仅凭指标名称判断采集方式。"] };
  const category = catalog.categories?.find((item) => item.code === entry.category)?.name || "系统输入";
  const group = inputGroup(catalog, entry);
  const instruction = !entry.execution.available ? entry.execution.reason
    : entry.execution.channel === "source_snapshot" ? "平台采集后引用来源快照；在数据来源中设置对象、位置和日期。"
    : "按标准填写或导入人工记录；需保留采集证据。";
  const selectors = Object.entries(binding.selectors || {}).map(([key, value]) =>
    ({ depth: "土层", statistic: "统计方式" }[key] || key) + "：" + (value === "mean" ? "均值" : value)).join(" · ");
  const temporal = entry.source.definition?.support?.temporal_support;
  return { entry, label: [category, group].filter(Boolean).join(" · "), details: [entry.source.name, instruction, selectors,
    temporal === "static" ? "静态网格参考，不是逐日实测。" : temporal === "scene_observation" ? "仅实际清晰过境日期有记录。" : ""].filter(Boolean) };
}
