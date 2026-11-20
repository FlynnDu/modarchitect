import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";
import { mountDraftLifecycle } from "../modarchitect/web/designer/draft-lifecycle.js";

test("正式方案只读且保留查看导航，显式开启草稿后恢复原控件规则", async () => {
  const html = await readFile(new URL("../modarchitect/web/designer/index.html", import.meta.url), "utf8");
  const dom = new JSDOM(html);
  globalThis.document = dom.window.document;
  try {
    let opened = 0, changed = 0;
    const lifecycle = mountDraftLifecycle({ onOpen: () => opened++, report() {} });
    const input = document.getElementById("wizard-name"), technical = document.getElementById("auto-layout");
    const reviewFields = [...document.querySelectorAll("#wizard-review [data-draft-fields] :is(input, textarea)")];
    assert.equal(reviewFields.length, 2);
    technical.disabled = false;
    technical.addEventListener("click", () => changed++);
    lifecycle.set({ draft_state: "published" });
    assert.ok(input.matches(":disabled"));
    assert.ok(reviewFields.every((field) => field.matches(":disabled")));
    assert.equal(document.querySelector('[data-section="calculation"]').matches(":disabled"), false);
    technical.click(); assert.equal(changed, 0);
    document.getElementById("open-version-draft").click(); assert.equal(opened, 1);
    const dynamic = document.createElement("input"); document.getElementById("wizard-role-table").append(dynamic);
    assert.ok(dynamic.matches(":disabled"));
    lifecycle.set({ draft_state: "draft" });
    assert.equal(input.matches(":disabled"), false);
    assert.ok(reviewFields.every((field) => !field.matches(":disabled")));
    assert.equal(dynamic.matches(":disabled"), false);
    assert.equal(document.getElementById("open-version-draft").hidden, true);
    assert.equal(document.getElementById("apply-method").disabled, true);
    technical.click(); assert.equal(changed, 1);
    lifecycle.set(null); assert.equal(document.getElementById("draft-lifecycle-status").hidden, true);
  } finally { delete globalThis.document; dom.window.close(); }
});
