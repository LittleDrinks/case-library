import { Extension, Mark, getMarkRange, mergeAttributes } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export const citationNumbersKey = new PluginKey("citationNumbers");

function citationParts(element) {
  const value = element.getAttribute("data-citation-source") || "";
  const separator = value.indexOf(":");
  return {
    sourceType: value.slice(0, separator), sourceId: value.slice(separator + 1),
  };
}

export const CitationMark = Mark.create({
  name: "citation",
  inclusive: false,
  addAttributes: () => ({
    sourceType: {
      default: null,
      parseHTML: (element) => element.getAttribute("data-citation-source-type") || citationParts(element).sourceType,
      renderHTML: (attributes) => ({ sourceType: attributes.sourceType }),
    },
    sourceId: {
      default: null,
      parseHTML: (element) => element.getAttribute("data-citation-source-id") || citationParts(element).sourceId,
      renderHTML: (attributes) => ({ sourceId: attributes.sourceId }),
    },
  }),
  parseHTML: () => [{ tag: "span[data-citation-source], span[data-citation-source-type]" }],
  renderHTML({ HTMLAttributes }) {
    const { sourceType, sourceId, ...rest } = HTMLAttributes;
    return ["span", mergeAttributes(rest, {
      "data-citation-source": `${sourceType}:${sourceId}`,
      class: "citation-mark",
    }), 0];
  },
});

// 按首次出现顺序去重的引用键；用于保存成功后判断资料区编号是否需要重取。
export function citationSignature(document) {
  const refs = [];
  const walk = (node) => {
    const mark = node.marks?.find((item) => item.type === "citation");
    if (mark) {
      const key = `${mark.attrs.sourceType}:${mark.attrs.sourceId}`;
      if (!refs.includes(key)) refs.push(key);
    }
    node.content?.forEach(walk);
  };
  walk(document || {});
  return refs.join("|");
}

// 空选区时 getMarkRange 兼容 inclusive:false 锚点的游标边界；有选区时检查范围内引用。
export function citationRangeAt(state) {
  const type = state.schema.marks.citation;
  if (!type) return null;
  const { selection } = state;
  if (!selection.empty) {
    let range = null;
    state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
      if (!range && node.isText && node.marks.some((mark) => mark.type === type)) {
        range = { from: pos, to: pos + node.nodeSize };
      }
    });
    return range;
  }
  return getMarkRange(selection.$from, type) || null;
}

function anchorOnly(document, range) {
  const text = document.textBetween(range.from, range.to, "\u0000", "\u0000");
  return text !== "" && [...text].every((char) => char === "\u200B");
}

// 取消引用：纯锚点直接删除锚点本身；引用文字仅去标记，保留正文。
export function removeCitation(editor) {
  const { state } = editor;
  if (!citationRangeAt(state)) return false;
  const { selection } = state;
  const range = selection.empty
    ? getMarkRange(selection.$from, state.schema.marks.citation)
    : { from: selection.from, to: selection.to };
  if (anchorOnly(state.doc, range)) {
    return editor.chain().focus().deleteRange(range).run();
  }
  return editor.chain().focus().unsetMark("citation", { extendEmptyMarkRange: true }).run();
}

function citationMarkKey(mark) {
  return `${mark.attrs.sourceType}:${mark.attrs.sourceId}`;
}

function sourceNumbers(sources) {
  return new Map(sources.map((source) => [
    `${source.sourceType}:${source.id}`, source.number,
  ]));
}

function citationWidget(number) {
  const element = window.document.createElement("sup");
  element.className = "citation-number";
  element.textContent = `〔${number}〕`;
  element.setAttribute("aria-label", `引用${number}`);
  return element;
}

function appendCitationNumber(decorations, numbers, range) {
  const number = numbers.get(range.key);
  if (number == null) return;
  decorations.push(Decoration.widget(range.end, () => citationWidget(number), {
    side: 1, key: `${range.key}:${range.end}:${number}`,
  }));
}

// 相邻同来源的文字视为一个引用区间，区间末尾统一追加编号上标。
function citationDecorations(document, sources) {
  const numbers = sourceNumbers(sources);
  const decorations = [];
  const active = { key: "", parent: null, end: 0 };
  document.descendants((node, position, parent) => {
    const mark = node.isText ? node.marks.find((item) => item.type.name === "citation") : null;
    const key = mark ? citationMarkKey(mark) : "";
    if (active.key && (active.key !== key || active.parent !== parent)) {
      appendCitationNumber(decorations, numbers, active);
      active.key = "";
    }
    if (key) Object.assign(active, { key, parent, end: position + node.nodeSize });
  });
  if (active.key) appendCitationNumber(decorations, numbers, active);
  return DecorationSet.create(document, decorations);
}

export function createCitationNumbers(readSources) {
  return Extension.create({
    name: "citationNumbers",
    addProseMirrorPlugins() {
      return [new Plugin({
        key: citationNumbersKey,
        state: {
          init: (_, state) => citationDecorations(state.doc, readSources()),
          apply(transaction, previous) {
            const sources = transaction.getMeta(citationNumbersKey);
            return sources ? citationDecorations(transaction.doc, sources)
              : transaction.docChanged ? citationDecorations(transaction.doc, readSources()) : previous;
          },
        },
        props: { decorations: (state) => citationNumbersKey.getState(state) },
      })];
    },
  });
}

export function refreshCitationNumbers(editor, sources) {
  if (!editor) return;
  editor.view.dispatch(editor.state.tr.setMeta(citationNumbersKey, sources));
}
