const byId = (id) => document.getElementById(id);

byId("reload-designer").addEventListener("click", () => location.reload());

try {
  await import("./studio.js?v=calculation1");
} catch {
  byId("designer-startup-error").hidden = false;
  byId("stage-loading").textContent = "设计器加载失败，请点击重新加载页面。";
  const status = byId("study-library-status");
  if (status.dataset.state !== "ready") status.textContent = "设计器尚未完成加载，请重新加载页面后读取方案。";
}
