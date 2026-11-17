import { dependencyLayers } from "./graph-layout.js?v=continuous1";
import { applicationPath } from "./http-path.js?v=proxy1";
import { researchFlow } from "./research-flow.js?v=continuous1";
import { studySettings } from "./study-settings.js?v=continuous1";

const element = (tag, text = "", className = "") => {
  const value = document.createElement(tag); value.textContent = text;
  if (className) value.className = className; return value;
};

export function researchTitle(plan) {
  return plan?.layout?.study_template?.id === "survey-658b" ? "已有地块综合研究" : plan?.name || "未命名研究方案";
}

export function researchQuestion(plan) {
  return plan?.layout?.study_template?.id === "survey-658b" ? "已有研究保留供历史查看；开展新研究时，请按问题分别选择独立方案。" : plan?.question || "";
}

// 归档流程仍读取冻结依赖；它与下方实际执行的组件图有明确的范围说明。
export function archivedFlow(host, workflow) {
  const items = workflow.steps.map((step) => ({ key: step.code, title: step.title }));
  const edges = workflow.steps.flatMap((step) => step.depends_on.map((parent) => [parent, step.code]));
  const { layers } = dependencyLayers(items, edges), positions = new Map();
  const ns = "http://www.w3.org/2000/svg", width = 900, rowHeight = 78;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${layers.length * rowHeight + 12}`);
  svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "原冻结勘察方案完整依赖；这些归档步骤本次不重新执行");
  layers.forEach((layer, depth) => layer.forEach((item, index) => positions.set(item.key, { x: width / layer.length * (index + .5), y: 12 + depth * rowHeight })));
  for (const [from, to] of edges) {
    const a = positions.get(from), b = positions.get(to), mid = (a.y + 48 + b.y) / 2;
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", `M${a.x},${a.y + 48} V${mid} H${b.x} V${b.y} m-4,-6 l4,6 l4,-6`);
    path.setAttribute("class", "archive-edge"); svg.append(path);
  }
  for (const item of items) {
    const { x, y } = positions.get(item.key), group = document.createElementNS(ns, "g");
    const rect = document.createElementNS(ns, "rect");
    for (const [key, value] of Object.entries({ x: x - 145, y, width: 290, height: 48, rx: 6 })) rect.setAttribute(key, value);
    const text = document.createElementNS(ns, "text"); text.setAttribute("x", x); text.setAttribute("y", y + 29); text.setAttribute("text-anchor", "middle");
    text.textContent = item.title.length > 22 ? item.title.slice(0, 21) + "…" : item.title;
    const title = document.createElementNS(ns, "title"); title.textContent = item.title;
    group.append(title, rect, text); svg.append(group);
  }
  host.append(svg);
}

export function showTemplateSummary(value, options = {}) {
  const host = document.getElementById("study-template-summary"); host.replaceChildren(); host.hidden = !value;
  if (!value) return;
  const info = value.researcher || { question: "查看已有研究的输入、方法与结果。", needed: "按当前方案的数据要求", method: "保留该研究采用的方法", outcome: "该研究实际产生的结果", limits: [], data_description: "历史研究数据" };
  host.append(element("h2", value.researcher ? value.title : "已有研究方案"), element("p", info.question));
  const facts = element("div", "", "study-research-facts");
  for (const [title, content] of [["需要哪些数据", info.needed], ["采用什么方法", info.method], ["可以得到什么", info.outcome]]) {
    const item = element("section"); item.append(element("h3", title), element("p", content)); facts.append(item);
  } host.append(facts);
  host.append(element("p", info.data_description, "study-data-description"), element("p", info.data_usage || "请核对所选研究数据与当前对象的关系。", "study-data-usage"));
  studySettings(host, value, options);
  const notes = element("details"), title = element("summary", "数据要求与结论适用范围"); notes.append(title);
  const limits = element("ul"); for (const note of info.limits) limits.append(element("li", note)); notes.append(limits); host.append(notes);
}

export function showStudyFlow(context, records = new Map()) {
  const section = document.getElementById("research-flow-section"), host = document.getElementById("public-research-flow");
  section.hidden = !context.definition?.composition?.nodes?.length;
  if (section.hidden) { host.replaceChildren(); return; }
  try { researchFlow(host, context.definition, records, context); }
  catch {
    const message = element("p", "流程暂无法显示，请先补齐输入和连接，再检查方案。", "research-flow-error");
    message.setAttribute("role", "alert"); host.replaceChildren(message);
  }
}

export async function mountStudyLibrary({ openTemplate }) {
  const host = document.getElementById("study-template-list"), status = document.getElementById("study-library-status");
  try {
    const response = await fetch(applicationPath("/api/v1/workspace/study-templates"), { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error("现成方案暂时无法读取，请刷新重试。");
    const { items } = await response.json();
    host.replaceChildren();
    const filters = element("div", "", "study-topic-filters"); filters.setAttribute("aria-label", "按研究主题筛选");
    for (const category of ["全部研究", ...new Set(items.map((item) => item.researcher?.category || "已有研究"))]) {
      const button = element("button", category, "button button-secondary"); button.type = "button"; button.setAttribute("aria-pressed", String(category === "全部研究"));
      button.addEventListener("click", () => {
        for (const control of filters.querySelectorAll("button")) control.setAttribute("aria-pressed", String(control === button));
        for (const card of host.children) card.hidden = category !== "全部研究" && card.dataset.category !== category;
      }); filters.append(button);
    }
    host.parentElement.querySelector(".study-topic-filters")?.remove(); host.before(filters);
    for (const value of items) {
      const card = element("article", "", "study-template-card"); card.dataset.studyTemplate = value.id;
      const info = value.researcher;
      card.dataset.category = info?.category || "已有研究";
      card.append(element("span", info?.category || "已有研究", "study-template-kind"), element("h3", value.title), element("p", info?.question || "查看该研究的数据、方法与成果"), element("p", info?.outcome || "查看研究结果", "study-template-result"));
      let method = null;
      if (value.method_options) {
        const label = element("label", "研究方法" ); method = document.createElement("select"); method.setAttribute("aria-label", value.title + "的方法");
        for (const item of value.method_options) method.add(new Option(item.name, item.id)); label.append(method); card.append(label);
      }
      const actions = element("div", "", "research-actions");
      for (const [save, label] of [[false, "查看研究流程"], [true, "使用这个方案"]]) {
        const button = element("button", label, save ? "button button-primary" : "button button-secondary"); button.type = "button";
        button.addEventListener("click", async () => {
          for (const action of host.querySelectorAll("button")) action.disabled = true;
          try { await openTemplate(method?.value || value.id, save); }
          catch (error) { status.textContent = error.message; }
          finally { for (const action of host.querySelectorAll("button")) action.disabled = false; }
        }); actions.append(button);
      }
      card.append(actions); host.append(card);
    }
    status.textContent = "共 " + items.length + " 个研究主题。按研究问题选择方案，再设置数据、时间与方法。";
  } catch (error) { status.textContent = error.message; }
}
