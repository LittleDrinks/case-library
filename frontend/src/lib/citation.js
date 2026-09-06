import { Extension, Mark } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export function citationKey(sourceType, sourceId) {
  return `${sourceType}:${sourceId}`;
}

export function sourceKey(source) {
  return citationKey(source.sourceType, source.id);
}

export function citationNumberMap(sources) {
  const map = new Map();
  (sources || []).forEach((source, index) => map.set(sourceKey(source), source.number ?? index + 1));
  return map;
}

export function collectCitationKeys(document) {
  const keys = [];
  const stack = [...(document?.content || [])];
  while (stack.length) {
    const node = stack.shift();
    stack.unshift(...(node?.content || []));
    (node?.marks || []).filter((mark) => mark.type === "citation").forEach((mark) => {
      const key = citationKey(mark.attrs?.sourceType, mark.attrs?.sourceId);
      if (!keys.includes(key)) keys.push(key);
    });
  }
  return keys;
}

export function caseVersionUrl(source) {
  if (source.url) return source.url;
  const base = `#/cases/${encodeURIComponent(source.caseId)}`;
  return source.versionId ? `${base}?versionId=${encodeURIComponent(source.versionId)}` : base;
}

export const CitationMark = Mark.create({
  name: "citation",
  inclusive: false,
  addAttributes() {
    return { sourceType: { default: "case" }, sourceId: { default: "" } };
  },
  parseHTML() {
    return [{
      tag: "span[data-citation-source-id]",
      getAttrs: (element) => ({
        sourceType: element.getAttribute("data-citation-source-type"),
        sourceId: element.getAttribute("data-citation-source-id"),
      }),
    }];
  },
  renderHTML({ mark }) {
    return ["span", {
      class: "citation-anchor",
      "data-citation-source-type": mark.attrs.sourceType,
      "data-citation-source-id": mark.attrs.sourceId,
    }, 0];
  },
});

export const citationMarkerKey = new PluginKey("citationMarkers");

function markerWidget(mark, sources) {
  const key = citationKey(mark.attrs.sourceType, mark.attrs.sourceId);
  const number = citationNumberMap(sources).get(key);
  const title = (sources || []).find((source) => sourceKey(source) === key)?.title;
  const sup = window.document.createElement("sup");
  sup.className = "citation-marker";
  sup.dataset.citationKey = key;
  sup.textContent = `〔${number ?? "?"}〕`;
  sup.title = title ? `来源：${title}` : "来源已移除或尚未同步";
  return sup;
}

function citationDecorations(document, sources) {
  const decorations = [];
  document.descendants((node, pos, parent, index) => {
    const mark = node.isText && node.marks.find((item) => item.type.name === "citation");
    const next = parent?.maybeChild(index + 1);
    if (mark && next?.marks.some((item) => item.eq(mark))) return false;
    if (mark) decorations.push(Decoration.widget(
      pos + node.nodeSize, () => markerWidget(mark, sources),
      { key: `citation-${pos}`, side: 1 },
    ));
    return !node.isText;
  });
  return DecorationSet.create(document, decorations);
}

function applyCitationMarkers(transaction, previous) {
  const sources = transaction.getMeta(citationMarkerKey) ?? previous.sources;
  return { set: citationDecorations(transaction.doc, sources), sources };
}

export const citationMarkerExtension = Extension.create({
  name: "citationMarkers",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: citationMarkerKey,
      state: {
        init: () => ({ set: DecorationSet.empty, sources: [] }),
        apply: applyCitationMarkers,
      },
      props: { decorations: (state) => citationMarkerKey.getState(state).set },
    })];
  },
});

export function refreshCitationMarkers(editor, sources) {
  if (!editor) return;
  editor.view.dispatch(editor.state.tr.setMeta(citationMarkerKey, sources || []));
}
