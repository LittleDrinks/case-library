import { mount } from "@vue/test-utils";
import { TextSelection } from "@tiptap/pm/state";
import { nextTick } from "vue";
import { expect, it, vi } from "vitest";
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

function selectDomRange(textNode, length) {
  const range = globalThis.document.createRange();
  range.setStart(textNode, 0);
  range.setEnd(textNode, length);
  const browserSelection = globalThis.getSelection();
  browserSelection.removeAllRanges();
  browserSelection.addRange(range);
  globalThis.document.dispatchEvent(new Event("selectionchange"));
}

async function selectParagraph(wrapper, length = 4) {
  // captureSelection 异步 emit；等待本轮新增的非空 selection 事件，避免 CI 调度竞态。
  const emitted = () => wrapper.emitted("selection")?.filter((event) => event[0]) ?? [];
  const known = emitted().length;
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(
    editor.state.doc, 9, 9 + length,
  )));
  selectDomRange(wrapper.get(".canvas-editor p").element.firstChild, length);
  await wrapper.vm.recaptureSelection();
  await vi.waitUntil(() => emitted().length > known, { interval: 20 });
  await nextTick();
}

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
  wrapper.vm.editor.commands.insertContent("新增");
  await nextTick();
  expect(wrapper.find('[aria-label="添加选区批注"]').exists()).toBe(false);
});
