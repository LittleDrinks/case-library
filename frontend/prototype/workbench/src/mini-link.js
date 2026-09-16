// 最小链接 Mark：项目依赖里没有 @tiptap/extension-link，原型自带精简版。
import { Mark, mergeAttributes } from "@tiptap/core";

export const MiniLink = Mark.create({
  name: "link",
  inclusive: false,
  addAttributes() {
    return { href: { default: null } };
  },
  parseHTML() {
    return [{ tag: "a[href]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["a", mergeAttributes(HTMLAttributes, { rel: "noopener" })];
  },
  addCommands() {
    return {
      setLink: (attributes) => ({ commands }) => commands.setMark(this.name, attributes),
      unsetLink: () => ({ commands }) => commands.unsetMark(this.name),
    };
  },
});
