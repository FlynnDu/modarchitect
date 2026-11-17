import { dependencyLayers, orthogonalPoints } from "./graph-layout.js?v=continuous1";

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function canvasContext(canvas) {
  const { width, height } = canvas.getBoundingClientRect();
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  const pixelsWide = Math.max(1, Math.round(width * scale));
  const pixelsHigh = Math.max(1, Math.round(height * scale));
  if (canvas.width !== pixelsWide) canvas.width = pixelsWide;
  if (canvas.height !== pixelsHigh) canvas.height = pixelsHigh;
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  return { context, width, height };
}

function fromRect(rect, base, outgoing, vertical) {
  return vertical
    ? { x: rect.left + rect.width / 2 - base.left, y: (outgoing ? rect.bottom : rect.top) - base.top }
    : { x: (outgoing ? rect.right : rect.left) - base.left, y: rect.top + rect.height / 2 - base.top };
}

function drawConnection(context, start, end, accent, routing) {
  const points = orthogonalPoints(start, end, routing);
  context.beginPath();
  points.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
  context.lineWidth = accent ? 1.7 : 1.2;
  context.strokeStyle = accent ? "#35795a" : "#819e8d";
  context.stroke();
  context.beginPath();
  context.moveTo(end.x, end.y); context.lineTo(end.x - 7, end.y - 4); context.lineTo(end.x - 7, end.y + 4);
  context.closePath(); context.fillStyle = context.strokeStyle; context.fill();
}

function socketPoint(socket, base) {
  const rect = (socket.querySelector(".port-marker") || socket).getBoundingClientRect();
  return { x: rect.left + rect.width / 2 - base.left, y: rect.top + rect.height / 2 - base.top };
}

export function createGraph(stage, graph, canvas, actions) {
  const nodes = new Map();
  let edges = [];
  let selection = "";
  let source = "";
  let positions = {};
  let zoomLevel = 1;
  let depths = new Map();

  function redraw() {
    if (!stage.getBoundingClientRect().width) return;
    const frames = [...nodes.values()].map((item) => item.frame.getBoundingClientRect());
    const bottom = Math.max(stage.getBoundingClientRect().top, ...frames.map((rect) => rect.bottom));
    canvas.style.width = Math.max(stage.clientWidth, graph.scrollWidth * zoomLevel) + "px";
    canvas.style.height = Math.max(stage.clientHeight, graph.offsetHeight * zoomLevel, bottom - stage.getBoundingClientRect().top + edges.length * 14 + 24) + "px";
    const { context } = canvasContext(canvas);
    const bounds = canvas.getBoundingClientRect();
    for (const [index, [origin, destination, port, output]] of edges.entries()) {
      const from = nodes.get(origin);
      const to = nodes.get(destination);
      if (!from || !to) continue;
      const fromPin = from.sockets.get("out:" + output) || from.sockets.get("out");
      const toPin = to.sockets.get(port ? "in:" + port : "in");
      const fromBox = from.frame.getBoundingClientRect();
      const toBox = to.frame.getBoundingClientRect();
      const longEdge = depths.get(destination) - depths.get(origin) > 1 || toBox.left <= fromBox.right;
      drawConnection(context,
        fromPin ? socketPoint(fromPin, bounds) : fromRect(fromBox, bounds, true, false),
        toPin ? socketPoint(toPin, bounds) : fromRect(toBox, bounds, false, false),
        origin === selection || destination === selection,
        { channel: .38 + (index % 4) * .08, bypass: longEdge ? bottom - bounds.top + 18 + index * 14 : undefined });
    }
  }

  function position(key, desired) {
    const item = nodes.get(key);
    const bounds = graph.getBoundingClientRect();
    const box = item.frame.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return { x: 0, y: 0 };
    const left = box.left - item.dx * zoomLevel;
    const top = box.top - item.dy * zoomLevel;
    const dx = Number.isFinite(desired?.x) ? desired.x : 0;
    const dy = Number.isFinite(desired?.y) ? desired.y : 0;
    const x = Math.max(bounds.left + 4 - left,
      Math.min(bounds.right - 4 - left - box.width, dx * bounds.width));
    const y = Math.max(bounds.top + 4 - top,
      Math.min(bounds.bottom - 4 - top - box.height, dy * bounds.height));
    item.dx = x / zoomLevel;
    item.dy = y / zoomLevel;
    item.frame.style.transform = "translate(" + item.dx + "px," + item.dy + "px)";
    return { x: x / bounds.width, y: y / bounds.height };
  }

  function reflow() {
    for (const key of nodes.keys()) position(key, positions[key]);
    redraw();
  }

  function portButton(label, className, callback) {
    const pin = element("button", "node-port pin " + className);
    pin.type = "button";
    pin.title = label;
    pin.setAttribute("aria-label", label);
    pin.addEventListener("click", callback);
    return pin;
  }

  function modelPorts(sockets, ports, direction, callback) {
    const name = direction === "in" ? "输入" : "输出";
    const group = element("div", "model-port-group " + direction);
    group.append(element("span", "model-port-heading", name));
    for (const { code, name: label } of ports) {
      const pin = element("button", "model-port " + direction, label);
      pin.type = "button";
      pin.setAttribute("aria-label", name + " " + label);
      const marker = element("span", "port-marker");
      marker.setAttribute("aria-hidden", "true");
      pin.append(marker);
      pin.addEventListener("click", () => callback(code));
      pin.dataset[direction === "in" ? "port" : "outputPort"] = code;
      sockets.set(direction + ":" + code, pin);
      group.append(pin);
    }
    return group;
  }

  function bindMovement(entry, key, grip) {
    const { button, frame } = entry;
    let start = null;
    let moved = false;
    let pending = null;
    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || (event.pointerType !== "mouse" && event.target !== grip)) return;
      moved = false;
      pending = null;
      const { width, height } = graph.getBoundingClientRect();
      start = {
        id: event.pointerId, x: event.clientX, y: event.clientY,
        offset: { x: entry.dx * zoomLevel / width, y: entry.dy * zoomLevel / height },
      };
      button.setPointerCapture(event.pointerId);
    });
    button.addEventListener("pointermove", (event) => {
      if (start?.id !== event.pointerId) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < 4) return;
      moved = true;
      frame.dataset.dragging = "true";
      const { width, height } = graph.getBoundingClientRect();
      pending = position(key, { x: start.offset.x + dx / width, y: start.offset.y + dy / height });
      redraw();
    });
    button.addEventListener("pointerup", (event) => {
      if (start?.id !== event.pointerId) return;
      start = null;
      delete frame.dataset.dragging;
      if (pending) {
        positions[key] = pending;
        actions.onMove(key, pending);
      }
    });
    button.addEventListener("pointercancel", () => {
      start = null;
      moved = false;
      delete frame.dataset.dragging;
      reflow();
    });
    button.addEventListener("click", () => {
      if (!moved) actions.onSelect(key);
      moved = false;
    });
    button.addEventListener("keydown", (event) => {
      const shift = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }[event.key];
      if (!event.altKey || !shift) return;
      event.preventDefault();
      const { width, height } = graph.getBoundingClientRect();
      const offset = position(key, {
        x: (entry.dx * zoomLevel + shift[0] * 12) / width,
        y: (entry.dy * zoomLevel + shift[1] * 12) / height,
      });
      positions[key] = offset;
      actions.onMove(key, offset);
      redraw();
    });
  }

  function addNode(item, lane) {
    const frame = element("div", lane === "models" ? "graph-item model-item" : "graph-item");
    const button = element("button", "graph-node " + item.kind);
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-keyshortcuts", "Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight");
    button.dataset.node = item.key;
    const grip = element("span", "node-grip");
    grip.title = "拖动节点，或按 Alt 和方向键移动";
    grip.setAttribute("aria-hidden", "true");
    button.append(grip);
    const title = element("div", "node-header");
    const text = element("span", "");
    text.append(element("strong", "node-title", item.name));
    if (lane !== "models") text.append(element("small", "node-code", item.subtitle));
    const glyph = element("span", "node-chip " + item.kind, item.glyph);
    glyph.setAttribute("aria-hidden", "true");
    title.append(glyph, text);
    button.append(title);
    frame.append(button);
    const sockets = new Map();
    if (lane === "inputs") {
      const pin = portButton("从" + item.name + "连线", "out", () => actions.onSource({ node: null, port: item.code }));
      pin.dataset.source = item.code;
      sockets.set("out", pin);
      frame.append(pin);
    } else if (lane === "models") {
      const groups = element("div", "model-ports");
      groups.append(
        modelPorts(sockets, item.sockets.filter((port) => !item.configurationPorts?.includes(port.code)), "in", (code) => actions.onTarget(item.code, code)),
        modelPorts(sockets, item.outgoing, "out", (code) => actions.onSource({ node: item.code, port: code })),
      );
      frame.append(groups);
      if (item.configurationPorts?.length) {
        const settings = element("button", "graph-settings text-button", "设置目标、因素与参数"); settings.type = "button";
        settings.addEventListener("click", () => actions.onConfigure(item.code)); frame.append(settings);
      }
    } else {
      const pin = element("span", "node-port in");
      sockets.set("in", pin);
      frame.append(pin);
    }
    const entry = { frame, button, sockets, dx: 0, dy: 0 };
    nodes.set(item.key, entry);
    bindMovement(entry, item.key, grip);
    return frame;
  }

  new ResizeObserver(reflow).observe(stage);
  document.fonts.ready.then(reflow);
  return {
    render(description, savedPositions) {
      const items = [...description.inputs.filter((input) => input.kind !== "parameter"), ...description.models, ...description.outputs];
      const visible = new Set(items.map((item) => item.key));
      edges = description.edges.filter(([from, to]) => visible.has(from) && visible.has(to));
      let layout, layoutError = "";
      try { layout = dependencyLayers(items, edges); }
      catch (error) { layoutError = error.message; layout = { layers: [items], depth: new Map(items.map((item) => [item.key, 0])) }; }
      depths = layout.depth;
      positions = { ...savedPositions };
      nodes.clear();
      graph.style.gridTemplateColumns = `repeat(${Math.max(1, layout.layers.length)}, 230px)`;
      graph.replaceChildren(...layout.layers.map((items, index) => {
        const lane = element("div", "lane");
        const content = element("div", "lane-nodes");
        const kind = (item) => item.key.startsWith("input:") ? "inputs" : item.key.startsWith("output:") ? "outputs" : "models";
        content.append(...items.map((item) => addNode(item, kind(item))));
        const label = layoutError || (items.every((item) => kind(item) === "inputs") ? "观测数据" : items.every((item) => kind(item) === "outputs") ? "成果" : `计算步骤 ${index}`);
        lane.append(element("div", "lane-label", label), content);
        return lane;
      }));
      for (const [, destination, port] of edges) {
        if (port) nodes.get(destination)?.sockets.get("in:" + port)?.setAttribute("data-connected", "");
      }
      reflow();
    },
    refresh: reflow,
    select(key) {
      selection = key;
      for (const [id, node] of nodes) {
        node.button.setAttribute("aria-pressed", String(id === key));
        node.frame.toggleAttribute("data-selected", id === key);
      }
      redraw();
    },
    connectFrom(value) {
      source = value;
      for (const [id, node] of nodes) {
        for (const [key, pin] of node.sockets) {
          if (!key.startsWith("out") || pin.tagName !== "BUTTON") continue;
          const active = source && (source.node ? id === "node:" + source.node && key === "out:" + source.port : id === "input:" + source.port);
          pin.setAttribute("aria-pressed", String(Boolean(active)));
        }
      }
    },
    focusInput(key, port) {
      nodes.get(key)?.sockets.get("in:" + port)?.focus({ preventScroll: true });
    },
    zoom(value) {
      zoomLevel = value;
      graph.style.setProperty("--zoom", value);
      reflow();
    },
  };
}

export function createChart(canvas, dataset, pointsButton, curveButton) {
  const font = '11px Geist, "Microsoft YaHei", system-ui, sans-serif';

  function render() {
    const { context, width, height } = canvasContext(canvas);
    if (width < 50 || height < 50) return;
    const left = 36;
    const right = width - 14;
    const top = 15;
    const bottom = height - 31;
    const xLimit = Math.max(...dataset.curve.map(([day]) => day));
    const yLimit = Math.ceil(Math.max(...dataset.curve.map(([, value]) => value), ...dataset.observations.map(([, value]) => value)) / 25) * 25;
    const x = (day) => left + day / xLimit * (right - left);
    const y = (value) => bottom - value / yLimit * (bottom - top);

    context.font = font;
    context.lineWidth = 1;
    context.fillStyle = "#526b5d";
    context.textBaseline = "middle";
    context.textAlign = "right";
    for (let value = 0; value <= yLimit; value += 25) {
      context.strokeStyle = "#e3ece5";
      context.beginPath();
      context.moveTo(left, y(value));
      context.lineTo(right, y(value));
      context.stroke();
      context.fillText(String(value), left - 6, y(value));
    }
    context.fillText("cm", left - 6, top - 9);
    context.textAlign = "center";
    for (let day = 0; day <= xLimit; day += 20) context.fillText(String(day), x(day), bottom + 11);
    context.fillText("播种后天数", (left + right) / 2, height - 6);

    if (curveButton.getAttribute("aria-pressed") === "true") {
      const line = new Path2D();
      dataset.curve.forEach(([day, value], index) => {
        if (index === 0) line.moveTo(x(day), y(value));
        else line.lineTo(x(day), y(value));
      });
      const area = new Path2D(line);
      area.lineTo(x(xLimit), bottom);
      area.lineTo(x(0), bottom);
      area.closePath();
      context.fillStyle = "#b9dbc33d";
      context.fill(area);
      context.lineWidth = 2;
      context.strokeStyle = "#277655";
      context.stroke(line);
    }
    if (pointsButton.getAttribute("aria-pressed") === "true") {
      context.lineWidth = 1.3;
      context.strokeStyle = "#9c6d32";
      context.fillStyle = "#fff4d9";
      for (const [day, value] of dataset.observations) {
        context.beginPath();
        context.arc(x(day), y(value), 3, 0, Math.PI * 2);
        context.fill();
        context.stroke();
      }
    }
  }

  for (const button of [pointsButton, curveButton]) {
    button.addEventListener("click", () => {
      button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true"));
      render();
    });
  }
  new ResizeObserver(render).observe(canvas);
  render();
}
