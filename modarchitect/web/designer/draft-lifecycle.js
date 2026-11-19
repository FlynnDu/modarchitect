// 用禁用的字段组保护配置，保留原控件自身的可用性规则及配置步骤导航。
export function mountDraftLifecycle({ onOpen, report }) {
  const groups = [...document.querySelectorAll("[data-wizard-section]")].map((section) => {
    const group = document.createElement("fieldset");
    group.className = "draft-configuration-fields";
    group.style.cssText = "border:0;margin:0;padding:0;min-width:0";
    group.append(...section.childNodes); section.append(group); return group;
  });
  const button = document.getElementById("open-version-draft"), status = document.getElementById("draft-lifecycle-status");
  let published = false;
  button.addEventListener("click", onOpen);
  for (const event of ["click", "pointerdown", "keydown", "input", "change"]) {
    document.addEventListener(event, (value) => {
      if (!published || !value.target.closest("[data-wizard-section],#technical-workspace,#edit-plan,#auto-layout")) return;
      value.preventDefault(); value.stopImmediatePropagation();
      if (event === "click") report("已发布配置只读，请先基于已发布版本开启新草稿。");
    }, true);
  }
  return {
    set(saved) {
      published = saved?.draft_state === "published";
      for (const group of groups) group.disabled = published;
      button.hidden = !published;
      status.hidden = !saved;
      status.textContent = published ? "已发布 · 配置只读。再次编辑将开启新草稿，已发布版本及已应用的地块研究保持原版本。" : "草稿 · 编辑保存不影响已发布版本。";
      for (const id of ["cloud-save", "wizard-save-draft"]) document.getElementById(id).hidden = published;
      document.getElementById("plan-state").textContent = published ? "已发布 · 只读" : "研究草稿";
    },
  };
}
