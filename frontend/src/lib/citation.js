import { Mark, mergeAttributes } from "@tiptap/core";

export const CitationMark = Mark.create({
  name: "citation",
  inclusive: false,
  addAttributes: () => ({ sourceType: { default: null }, sourceId: { default: null } }),
  parseHTML: () => [{ tag: "span[data-citation-source]" }],
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
