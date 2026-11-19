import { dependencyLayers, orthogonalPoints } from "./graph-layout.js?v=continuous1";
import { flowOverview } from "./flow-overview.js?v=overview1";

function componentFlow(host, plan, records = new Map(), externalCodes = null) {
  const ns = "http://www.w3.org/2000/svg", parameters = new Set(plan.composition.inputs.filter((input) => plan.input_recipes[input.code]?.kind === "configuration").map((input) => input.code));
  const items = plan.composition.inputs.filter((input) => !parameters.has(input.code)).map((input) => {
    const recipe = plan.input_recipes[input.code], codes = recipe?.kind === "observations" ? recipe.variable_codes.filter((code) => externalCodes === null || externalCodes.has(code)) : null;
    return { key: "input:" + input.code, name: codes ? "观测表 · " + codes.length + " 项指标" : input.name, kind: "data",
      description: codes ? "观测表：" + codes.map((code) => plan.variables.find((variable) => variable.code === code)?.name || code).join("、") : input.name };
  });
  for (const node of plan.composition.nodes) {
    const definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
    items.push({ key: "node:" + node.code, name: plan.layout?.node_labels?.[node.code] || definition?.name || "研究方法", kind: "method" });
  }
  for (const output of plan.composition.outputs) {
    const node = plan.composition.nodes.find((item) => item.code === output.source.node), definition = records.get(node.component.code + "@" + node.component.revision)?.definition;
    items.push({ key: "output:" + output.code, name: definition?.outputs.find((port) => port.code === output.source.port)?.name || "研究结果", kind: "result" });
  }
  const edges = plan.composition.nodes.flatMap((node) => node.bindings.filter((binding) => binding.source.node || !parameters.has(binding.source.port)).map((binding) => [binding.source.node ? "node:" + binding.source.node : "input:" + binding.source.port, "node:" + node.code]));
  edges.push(...plan.composition.outputs.map((output) => ["node:" + output.source.node, "output:" + output.code]));
  const { layers } = dependencyLayers(items, edges), width = layers.length * 240, height = Math.max(...layers.map((layer) => layer.length), 1) * 96 + 24, positions = new Map();
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "研究流程：数据、分析方法与成果");
  layers.forEach((layer, depth) => layer.forEach((item, index) => positions.set(item.key, { x: 12 + depth * 240, y: 16 + index * 96 })));
  for (const [from, to] of edges) {
    const start = positions.get(from), end = positions.get(to), path = document.createElementNS(ns, "path"), a = start.x + 204, b = end.x, y1 = start.y + 31, y2 = end.y + 31, mid = (a + b) / 2;
    path.setAttribute("d", `M${a},${y1} H${mid} V${y2} H${b} m-6,-4 l6,4 l-6,4`); path.setAttribute("class", "research-flow-edge"); svg.append(path);
  }
  for (const item of items) {
    const position = positions.get(item.key), group = document.createElementNS(ns, "g"), rect = document.createElementNS(ns, "rect"), title = document.createElementNS(ns, "title");
    title.textContent = item.description || item.name;
    for (const [key, value] of Object.entries({ x: position.x, y: position.y, width: 204, height: 62, rx: 8 })) rect.setAttribute(key, value);
    rect.setAttribute("class", "research-flow-" + item.kind); group.append(title, rect);
    const chars = [...item.name], lines = chars.length > 14 ? [chars.slice(0, 14).join(""), chars.slice(14, 28).join("")] : [item.name];
    for (const [index, line] of lines.entries()) {
      const text = document.createElementNS(ns, "text"); text.setAttribute("x", position.x + 102); text.setAttribute("y", position.y + (lines.length === 1 ? 36 : 27 + index * 18)); text.setAttribute("text-anchor", "middle"); text.textContent = line; group.append(text);
    } svg.append(group);
  }
  host.replaceChildren(svg);
}

const element = (tag, text = "", className = "") => {
  const node = document.createElement(tag); node.textContent = text;
  if (className) node.className = className; return node;
};

const views = new WeakMap();
const iconPaths = {
  database: ["M20 6c0 2.2-16 2.2-16 0s16-2.2 16 0Z", "M4 6v12c0 2.7 16 2.7 16 0V6", "M4 12c0 2.7 16 2.7 16 0"],
  monitor: ["M4 4h16v12H4z", "M9 20h6M12 16v4", "m8 10 3 3 5-6"],
  cpu: ["M6 6h12v12H6zM9 9h6v6H9z", "M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"],
  shield: ["M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z", "m8 12 3 3 5-6"],
  sparkles: ["m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z", "M20 2v4m-2-2h4"],
  check: ["m6 12 4 4 8-8"], info: ["M12 8h.01M12 11v5", "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0"],
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(key, value);
  for (const d of iconPaths[name] || iconPaths.info) { const path = document.createElementNS(svg.namespaceURI, "path"); path.setAttribute("d", d); svg.append(path); }
  return svg;
}
function information(items, segments = []) {
  const list = element("dl", "", "research-stage-values");
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);
  for (const [label, value] of items) {
    const title = element("dt", label), content = element("dd", String(value)), segment = segments.find((item) => item.label === label);
    if (segment && total > 0) { title.dataset.segment = segment.tone; content.append(element("small", " · " + Math.round(segment.count / total * 100) + "%", "research-split-percent")); }
    list.append(title, content);
  }
  return list;
}
function sourceGroups(groups) {
  const root = element("div", "", "research-source-groups");
  for (const group of groups) {
    const section = element("section", "", "research-source-group"), title = element("h4", group.name);
    title.append(element("span", group.count + " 项", "research-source-count")); section.append(title);
    if (group.children.some((child) => child.name !== "已选指标")) section.append(element("p", group.children.map((child) => child.name).join(" / "), "research-source-subcategories"));
    for (const child of group.children) for (const variable of child.variables) {
      const row = element("div", "", "research-source-row");
      const name = element("span", variable.name, "research-source-variable"); name.dataset.variableCode = variable.code; name.title = child.name + " · " + variable.unit + " · " + (variable.used ? "当前方法采用" : "尚未用于计算");
      row.append(name, element("span", variable.status, "research-source-status")); section.append(row);
    } root.append(section);
  } return root;
}
function cardBody(stage) {
  const body = element("div", "", "research-stage-body"), headline = element("strong", "", "research-stage-headline");
  const metric = stage.headline.match(/^(\d+)(.*)$/);
  if (metric) headline.append(element("span", metric[1], "research-stage-quantity"), element("span", metric[2], "research-stage-unit")); else headline.textContent = stage.headline;
  body.append(headline);
  if (stage.description) body.append(element("p", stage.description, "research-stage-description"));
  if (stage.highlight) body.append(element("p", stage.highlight, "research-stage-highlight"));
  if (stage.groups?.length) body.append(sourceGroups(stage.groups)); else {
    if (stage.segments?.length) body.append(element("h4", "样本构成", "research-dataset-label"));
    body.append(information(stage.items.slice(0, 6), stage.segments));
  }
  if (stage.segments?.some((segment) => segment.count > 0)) {
    const bar = element("div", "", "research-split-bar"), total = stage.segments.reduce((sum, segment) => sum + segment.count, 0);
    bar.setAttribute("role", "img"); bar.setAttribute("aria-label", stage.segments.map((segment) => segment.label + " " + segment.count + " 条").join("，"));
    for (const segment of stage.segments) { const part = element("span", "", "research-split-segment"); part.dataset.segment = segment.tone; part.style.flexGrow = segment.count / total; part.title = segment.label + " " + Math.round(segment.count / total * 100) + "%"; bar.append(part); }
    body.append(bar);
  } return body;
}
function controls(host, scroll, diagram, toolbar, cleanup) {
  let manual = host.dataset.flowZoomMode === "manual", zoom = Number(host.dataset.flowZoom) || 1, forceFit = false;
  const output = element("output", "100%", "research-flow-zoom"); output.setAttribute("aria-label", "当前画布缩放");
  const apply = (next) => { zoom = Math.max(.2, Math.min(1.4, next)); diagram.style.zoom = zoom; output.textContent = Math.round(zoom * 100) + "%"; host.dataset.flowZoom = String(zoom); };
  const fit = () => { if (!manual && scroll.clientWidth && diagram.offsetWidth) apply(scroll.clientWidth < 700 ? 1 : Math.max(forceFit ? .2 : .85, Math.min(1, (scroll.clientWidth - 20) / diagram.offsetWidth))); };
  const button = (text, label, action) => { const control = element("button", text); control.type = "button"; control.setAttribute("aria-label", label); control.title = label; control.addEventListener("click", action); toolbar.append(control); return control; };
  button("−", "缩小研究流程", () => { manual = true; host.dataset.flowZoomMode = "manual"; apply(zoom - .1); });
  toolbar.append(output);
  button("+", "放大研究流程", () => { manual = true; host.dataset.flowZoomMode = "manual"; apply(zoom + .1); });
  button("适应宽度", "将研究流程适应当前宽度", () => { forceFit = true; manual = false; host.dataset.flowZoomMode = "fit"; fit(); });
  const expand = button(host.classList.contains("research-flow-expanded") ? "退出全屏" : "全屏查看", "切换研究流程全屏视图", () => {
    host.classList.toggle("research-flow-expanded"); expand.textContent = host.classList.contains("research-flow-expanded") ? "退出全屏" : "全屏查看"; expand.setAttribute("aria-pressed", String(host.classList.contains("research-flow-expanded"))); fit();
  });
  expand.setAttribute("aria-pressed", String(host.classList.contains("research-flow-expanded")));
  const escape = (event) => {
    if (!host.classList.contains("research-flow-expanded")) return;
    if (event.key === "Escape") { expand.click(); expand.focus(); }
    if (event.key === "Tab") {
      const focusable = [...host.querySelectorAll('button, summary, [tabindex="0"]')], first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && (document.activeElement === first || !host.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !host.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    }
  };
  document.addEventListener("keydown", escape);
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(fit) : null; observer?.observe(scroll);
  apply(zoom); fit();
  views.set(host, () => { observer?.disconnect(); cleanup?.(); document.removeEventListener("keydown", escape); });
}
export function researchFlow(host, plan, records = new Map(), context = {}) {
  views.get(host)?.();
  const opened = new Set([...host.querySelectorAll("details[open]")].map((node) => node.dataset.detail));
  const overview = flowOverview(plan, records, context); host.replaceChildren();
  const toolbar = element("div", "", "research-flow-toolbar"), caption = element("div", "", "research-flow-caption");
  caption.append(element("span", overview.context, "research-flow-context"), element("span", overview.stages.length + " 个环节 · " + overview.edges.length + " 条实际数据连接", "research-flow-hint"));
  const tools = element("div", "", "research-flow-tools"); toolbar.append(caption, tools); host.append(toolbar);
  const scroll = element("div", "", "research-stages-scroll"); scroll.tabIndex = 0; scroll.setAttribute("role", "region"); scroll.setAttribute("aria-label", "研究流程，共 " + overview.stages.length + " 个实际环节，可滚动或缩放查看");
  const diagram = element("div", "", "research-stages-diagram");
  const alignment = element("aside", "", "research-alignment"); alignment.append(element("strong", overview.alignmentTitle), element("p", overview.alignment), element("span", "按实际资料对齐，运行时核对")); diagram.append(alignment);
  const list = element("ol", "", "research-stage-list"), columnCount = Math.max(1, overview.layers.length), rowCount = Math.max(1, ...overview.layers.map((layer) => layer.length));
  diagram.style.setProperty("--flow-columns", String(columnCount)); diagram.style.setProperty("--flow-gap-total", (columnCount - 1) * 56 + "px");
  list.dataset.parallel = String(rowCount > 1);
  for (const [index, stage] of overview.stages.entries()) {
    const step = element("li", "", "research-stage-step"); step.dataset.accent = stage.accent; step.dataset.flowKey = stage.code;
    const column = overview.depth.get(stage.code), layer = overview.layers[column];
    step.style.gridColumn = String(column + 1); step.style.gridRow = layer.length === 1 && rowCount > 1 ? "1 / span " + rowCount : String(layer.indexOf(stage.code) + 1);
    const marker = element("div", "", "research-stage-marker"); marker.append(element("span", String(index + 1).padStart(2, "0"), "research-stage-number")); step.append(marker);
    const card = element("article", "", "research-stage-card"); card.dataset.flowStage = stage.code; card.dataset.flowKind = stage.kind; if (stage.nodeCode) card.dataset.nodeCode = stage.nodeCode; if (stage.inputCode) card.dataset.inputCode = stage.inputCode; card.dataset.tone = stage.tone; card.dataset.accent = stage.accent;
    const header = element("header"), badge = element("span", "", "research-stage-status"); badge.append(icon(stage.tone === "success" ? "check" : "info"), document.createTextNode(stage.status)); header.append(icon(stage.icon), element("h3", stage.title), badge);
    card.append(header, cardBody(stage));
    const footer = element("footer"); footer.append(element("p", stage.note));
    const details = element("details"); details.dataset.detail = stage.code; details.open = opened.has(stage.code); details.append(element("summary", stage.detailTitle));
    if (stage.groups?.length || stage.items.length > 6) details.append(information(stage.items));
    for (const note of stage.details || []) if (note) details.append(element("p", note));
    if (!details.querySelector("p, dl")) details.append(element("p", "当前阶段依据已保存方案及实际运行记录展示。"));
    footer.append(details); card.append(footer); step.append(card);
    list.append(step);
  }
  diagram.append(list);
  const routes = diagramConnections(diagram, list, overview);
  scroll.append(diagram); host.append(scroll); controls(host, scroll, diagram, tools, routes.close); routes.refresh();
  const connections = element("details", "", "research-component-flow"); connections.dataset.detail = "connections"; connections.open = opened.has("connections"); connections.append(element("summary", "查看模型连接关系"), element("p", "以下按准确组件合同展示计算依赖；上方卡片是研究阶段，不是额外的计算节点。"));
  const graph = element("div", "", "research-component-graph"); componentFlow(graph, plan, records, new Set(overview.rows.filter((row) => row.used).map((row) => row.variable.code))); connections.append(graph); host.append(connections);
}

let diagramSequence = 0;
function diagramConnections(diagram, list, overview) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), markerId = "flow-arrow-" + ++diagramSequence;
  svg.setAttribute("class", "research-overview-connections"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "按实际输入输出依赖连接的研究流程");
  const defs = document.createElementNS(ns, "defs"), marker = document.createElementNS(ns, "marker"), arrow = document.createElementNS(ns, "path");
  for (const [key, value] of Object.entries({ id: markerId, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" })) marker.setAttribute(key, value);
  arrow.setAttribute("d", "M1 1 9 5 1 9"); arrow.setAttribute("fill", "none"); arrow.setAttribute("stroke", "#6d8c78"); marker.append(arrow); defs.append(marker); svg.append(defs);
  const nodes = new Map([...list.children].map((step) => [step.dataset.flowKey, step.querySelector("article")]));
  const routeNodes = overview.edges.map((edge) => {
    const group = document.createElementNS(ns, "g"), path = document.createElementNS(ns, "path"), title = document.createElementNS(ns, "title"), label = document.createElementNS(ns, "text");
    group.dataset.from = edge.from; group.dataset.to = edge.to; group.dataset.kind = edge.kind;
    group.setAttribute("class", "research-overview-edge" + (edge.kind === "validation" ? " research-data-branch" : ""));
    if (edge.kind === "validation") { group.dataset.branchSource = edge.from; group.dataset.branchTarget = edge.to; group.setAttribute("aria-label", edge.label + "，不参与训练，进入评价"); }
    title.textContent = overview.stages.find((stage) => stage.code === edge.from).title + " → " + overview.stages.find((stage) => stage.code === edge.to).title + "：" + edge.label;
    path.setAttribute("marker-end", "url(#" + markerId + ")");
    label.textContent = edge.label.length > 4 ? edge.label.slice(0, 3) + "…" : edge.label; group.append(title, path, label); svg.append(group);
    return { edge, path, label };
  });
  diagram.prepend(svg);
  const refresh = () => {
    if (!diagram.offsetWidth || !list.offsetHeight) return;
    const origin = diagram.getBoundingClientRect(), scale = origin.width / diagram.offsetWidth;
    const narrow = list.getBoundingClientRect().width / scale < 600 && window.getComputedStyle(list).display === "flex";
    const box = (key) => { const rect = nodes.get(key).getBoundingClientRect(); return { x: (rect.left - origin.left) / scale, y: (rect.top - origin.top) / scale, w: rect.width / scale, h: rect.height / scale }; };
    let bypass = 0;
    for (const { edge, path, label } of routeNodes) {
      const a = box(edge.from), b = box(edge.to), long = overview.depth.get(edge.to) > overview.depth.get(edge.from) + 1;
      let points, labelX, labelY;
      if (narrow) {
        const direct = list.children[overview.stages.findIndex((stage) => stage.code === edge.from) + 1]?.dataset.flowKey === edge.to;
        const start = { x: a.x + a.w / 2, y: a.y + a.h + 2 }, end = { x: b.x + b.w / 2, y: b.y - 5 }, mid = (start.y + end.y) / 2;
        const channel = 4 + (bypass++ % 3) * 5;
        points = direct ? [start, { x: start.x, y: mid }, { x: end.x, y: mid }, end] : [start, { x: start.x, y: start.y + 8 }, { x: channel, y: start.y + 8 }, { x: channel, y: end.y - 8 }, { x: end.x, y: end.y - 8 }, end];
        labelX = direct ? start.x + 8 : 22; labelY = direct ? mid - 4 : end.y - 10;
      } else {
        const outgoing = overview.edges.filter((item) => item.from === edge.from), incoming = overview.edges.filter((item) => item.to === edge.to);
        const gapEdges = overview.edges.filter((item) => overview.depth.get(item.from) === overview.depth.get(edge.from) && overview.depth.get(item.to) === overview.depth.get(edge.to));
        const start = { x: a.x + a.w + 2, y: a.y + 29 + outgoing.indexOf(edge) * Math.min(22, (a.h - 58) / Math.max(1, outgoing.length - 1)) };
        const end = { x: b.x - 4, y: b.y + 29 + incoming.indexOf(edge) * Math.min(22, (b.h - 58) / Math.max(1, incoming.length - 1)) };
        const lane = long ? list.offsetTop + list.offsetHeight + 22 + bypass++ * 25 : undefined;
        points = orthogonalPoints(start, end, { bypass: lane, channel: (gapEdges.indexOf(edge) + 1) / (gapEdges.length + 1) }); labelX = (start.x + end.x) / 2; labelY = lane === undefined ? start.y - 9 : lane - 5;
      }
      path.setAttribute("d", points.map((point, index) => (index ? "L" : "M") + point.x + "," + point.y).join(" "));
      label.setAttribute("x", labelX); label.setAttribute("y", labelY); label.setAttribute("text-anchor", narrow ? "start" : "middle");
    }
    diagram.style.paddingBottom = narrow || !bypass ? "10px" : 35 + bypass * 25 + "px";
    svg.setAttribute("viewBox", "0 0 " + diagram.offsetWidth + " " + diagram.offsetHeight); svg.setAttribute("width", diagram.offsetWidth); svg.setAttribute("height", diagram.offsetHeight);
  };
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(refresh) : null;
  for (const article of nodes.values()) observer?.observe(article); observer?.observe(list);
  return { refresh, close() { observer?.disconnect(); } };
}
