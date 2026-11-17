// 设计器位于应用根目录下；代理前缀由当前页面地址确定。
export function applicationPath(path) {
  if (!path.startsWith("/")) return path;
  return new URL("../", document.baseURI).pathname.replace(/\/$/, "") + path;
}
