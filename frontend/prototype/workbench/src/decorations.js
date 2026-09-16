// decoration 层：批注锚点高亮、待定修订预览（删除线+插入预览）、选区 chip 高亮。
// 预览是临时展示层，不写入正文；采用/拒绝走真实事务。
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export const overlayKey = new PluginKey("prototypeOverlay");

function findTextRange(doc, needle) {
  if (!needle) return null;
  let found = null;
  doc.descendants((node, pos) => {
    if (found || !node.isText || !node.text.includes(needle)) return;
    const start = pos + node.text.indexOf(needle);
    found = { from: start, to: start + needle.length };
    return false;
  });
  return found;
}

function annotationDecorations(doc, annotations) {
  const items = [];
  for (const ann of annotations) {
    if (ann.resolved && ann.kind === "comment") continue;
    const range = ann.range || findTextRange(doc, ann.anchorQuote);
    if (!range) continue;
    items.push(Decoration.inline(range.from, range.to, {
      class: `ann-anchor kind-${ann.kind}`,
      "data-ann": ann.id,
    }));
  }
  return items;
}

function revisionDecorations(doc, revisions) {
  const items = [];
  for (const rev of revisions) {
    if (rev.status !== "pending") continue;
    const range = rev.range || findTextRange(doc, rev.original);
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
  const range = chip.range || findTextRange(doc, chip.quote);
  if (!range) return [];
  return [Decoration.inline(range.from, range.to, { class: "chip-anchor" })];
}

export function buildOverlay(state, snapshot) {
  const doc = state.doc;
  const items = [
    ...annotationDecorations(doc, snapshot.annotations),
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
