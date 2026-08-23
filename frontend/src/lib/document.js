export const EMPTY_DOCUMENT = Object.freeze({
  type: "doc",
  content: [{ type: "paragraph" }],
});

export function normalizeDocument(document) {
  if (document?.type !== "doc" || !Array.isArray(document.content)) return structuredClone(EMPTY_DOCUMENT);
  return structuredClone(document);
}

function nodeText(node) {
  if (typeof node?.text === "string") return node.text;
  return (node?.content || []).map(nodeText).join("");
}

export function documentOutline(document) {
  return (document?.content || []).flatMap((node, index) => {
    const level = node.attrs?.level;
    if (node.type !== "heading" || ![1, 2].includes(level)) return [];
    return [{ index, level, text: nodeText(node) || "未命名小节" }];
  });
}
