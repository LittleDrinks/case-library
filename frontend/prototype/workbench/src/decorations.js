// decoration 层：待定修订预览（删除线+插入预览）、选区 chip 高亮。
// 预览是临时展示层，不写入正文；采用/拒绝走真实事务。
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export const overlayKey = new PluginKey("prototypeOverlay");

import { findTextRange } from "./text-range.js";

function revisionDecorations(doc, revisions) {
  const items = [];
  for (const rev of revisions) {
    if (rev.status !== "pending") continue;
    const range = rev.anchorMissing ? null : findTextRange(doc, rev.original, rev.range);
    if (!range) continue;
    items.push(Decoration.inline(range.from, range.to, { class: "rev-del", "data-rev": rev.id }));
    items.push(Decoration.widget(range.to, () => {
      const span = document.createElement("span");
      span.className = "rev-ins";
      span.dataset.rev = rev.id;
      span.textContent = rev.replacement;
      return span;
    }, { side: 1 }));
  }
  return items;
}

function chipDecoration(doc, chip) {
  if (!chip?.quote) return [];
  const range = chip.anchorMissing ? null : findTextRange(doc, chip.quote, chip.range);
  if (!range) return [];
  return [Decoration.inline(range.from, range.to, { class: "chip-anchor" })];
}

export function buildOverlay(state, snapshot) {
  const doc = state.doc;
  const items = [
    ...revisionDecorations(doc, snapshot.revisions || []),
    ...chipDecoration(doc, snapshot.chip),
  ];
  return DecorationSet.create(doc, items);
}

export const OverlayExtension = Extension.create({
  name: "prototypeOverlay",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: overlayKey,
      state: {
        init: (_, state) => buildOverlay(state, this.options.snapshot()),
        apply: (tr, old, state) => buildOverlay(state, this.options.snapshot()),
      },
      props: { decorations: (state) => overlayKey.getState(state) },
    })];
  },
});
