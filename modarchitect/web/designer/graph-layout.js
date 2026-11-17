// 布局只读取真实依赖，不修改方案、端口或科学参数。
export function dependencyLayers(items, edges) {
  const byKey = new Map(items.map((item) => [item.key, item]));
  const parents = new Map(items.map((item) => [item.key, new Set()]));
  const children = new Map(items.map((item) => [item.key, new Set()]));
  for (const [from, to] of edges) {
    if (!byKey.has(from) || !byKey.has(to)) throw new Error("连线引用了不存在的节点。");
    parents.get(to).add(from);
    children.get(from).add(to);
  }
  const remaining = new Map([...parents].map(([key, values]) => [key, values.size]));
  const depth = new Map(items.map((item) => [item.key, 0]));
  const ready = items.filter((item) => remaining.get(item.key) === 0).map((item) => item.key).sort();
  const ordered = [];
  while (ready.length) {
    const key = ready.shift();
    ordered.push(key);
    for (const next of children.get(key)) {
      depth.set(next, Math.max(depth.get(next), depth.get(key) + 1));
      remaining.set(next, remaining.get(next) - 1);
      if (remaining.get(next) === 0) { ready.push(next); ready.sort(); }
    }
  }
  if (ordered.length !== items.length) throw new Error("存在循环依赖，请先修正连线。");
  const layers = [];
  for (const key of ordered) {
    const index = depth.get(key);
    (layers[index] ||= []).push(byKey.get(key));
  }
  return { layers, depth };
}

export function orthogonalPoints(start, end, { channel = .5, bypass } = {}) {
  if (bypass !== undefined || end.x <= start.x) {
    const y = bypass ?? Math.max(start.y, end.y) + 35;
    return [start, { x: start.x + 14, y: start.y }, { x: start.x + 14, y },
      { x: end.x - 14, y }, { x: end.x - 14, y: end.y }, end];
  }
  const x = start.x + (end.x - start.x) * channel;
  return [start, { x, y: start.y }, { x, y: end.y }, end];
}
