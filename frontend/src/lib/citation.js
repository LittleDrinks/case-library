import { Mark, mergeAttributes } from "@tiptap/core";

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

export function sourceKey(source) {
  return `${source.sourceType}:${source.id}`;
}
