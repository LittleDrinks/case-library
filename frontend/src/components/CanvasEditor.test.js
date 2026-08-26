import { mount } from "@vue/test-utils";
import { TextSelection } from "@tiptap/pm/state";
import { nextTick } from "vue";
import { expect, it } from "vitest";
import CanvasEditor from "./CanvasEditor.vue";

const caseDocument = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: "案例原文" }] },
  ],
};

async function setup(options = {}) {
  const wrapper = mount(CanvasEditor, {
    props: { document: caseDocument, editable: true, ...options },
  });
  await nextTick();
  const context = wrapper.emitted("writing-context").at(-1)[0];
  return { wrapper, context };
}

async function selectParagraph(wrapper, length = 4) {
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(
    editor.state.doc, 9, 9 + length,
  )));
  const textNode = wrapper.get(".canvas-editor p").element.firstChild;
  const range = globalThis.document.createRange();
  range.setStart(textNode, 0);
  range.setEnd(textNode, length);
  const browserSelection = globalThis.getSelection();
  browserSelection.removeAllRanges();
  browserSelection.addRange(range);
  globalThis.document.dispatchEvent(new Event("selectionchange"));
  await wrapper.vm.recaptureSelection();
  await nextTick();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function candidate(context, mode, text = "候选正文") {
  return {
    id: text, context, mode, text, reason: "使教学任务与目标一致", status: "pending",
  };
}

it("待确认修订在正文原位显示删增和理由但不污染文档", async () => {
  const { wrapper, context } = await setup();
  const original = structuredClone(caseDocument);
  await wrapper.setProps({ candidatePreviews: [candidate(context, "replace-section")] });

  expect(wrapper.get(".candidate-inline-removed").text()).toBe("案例原文");
  expect(wrapper.get(".candidate-inline-preview").text()).toContain("候选正文");
  expect(wrapper.get(".candidate-inline-preview").text()).toContain("使教学任务与目标一致");
  expect(caseDocument).toEqual(original);
});

it("三条未决修订同时在正文原位显示", async () => {
  const { wrapper, context } = await setup();
  const candidates = ["候选一", "候选二", "候选三"]
    .map((text) => candidate(context, "replace-section", text));
  await wrapper.setProps({ candidatePreviews: candidates });

  expect(wrapper.findAll(".candidate-inline-preview")).toHaveLength(3);
});

it.each([
  ["replace-section", "一、教学说明候选正文", "案例原文"],
  ["append-section", "一、教学说明案例原文候选正文", ""],
  ["new-section", "一、教学说明案例原文补充候选正文", ""],
])("%s 按明确落点修改 ProseMirror 正文", async (mode, expected, removed) => {
  const { wrapper, context } = await setup();
  wrapper.vm.applyCandidate(candidate(context, mode));
  expect(wrapper.get(".canvas-editor").text()).toBe(expected);
  if (removed) expect(wrapper.get(".canvas-editor").text()).not.toContain(removed);
});

it("replace-selection 只替换生成时选中的文字", async () => {
  const { wrapper, context } = await setup();
  const selection = {
    ...context, from: context.sectionFrom + 1, to: context.sectionFrom + 5,
    quote: "案例原文",
  };
  wrapper.vm.applyCandidate(candidate(selection, "replace-selection", "选区候选"));
  expect(wrapper.get(".canvas-editor").text()).toBe("一、教学说明选区候选");
});

it("捕获正文选区的精确位置、引用和当前修订号", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  await selectParagraph(wrapper);
  const captured = wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0];
  expect(captured).toMatchObject({ quote: "案例原文", revision: 3, from: 9, to: 13 });
  expect(captured.quoteHash).toHaveLength(64);
  expect(wrapper.get('[aria-label="添加选区批注"]').exists()).toBe(true);
});

it("修订变化或手动编辑会立即清除旧选区", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  await selectParagraph(wrapper);
  await wrapper.setProps({ revision: 4 });
  expect(wrapper.find('[aria-label="添加选区批注"]').exists()).toBe(false);
  await wrapper.setProps({ revision: 3 });
  await selectParagraph(wrapper);
  const captured = wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0];
  globalThis.getSelection().removeAllRanges();
  wrapper.vm.applyCandidate(candidate(captured, "replace-selection", "新文字"));
  await nextTick();
  expect(wrapper.find('[aria-label="添加选区批注"]').exists()).toBe(false);
});
