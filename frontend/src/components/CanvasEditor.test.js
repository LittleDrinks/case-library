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

// tiptap vue-3 的 state 是双 rAF 去抖 ref，工具栏启用态需等两帧后才刷新。
function framesSettled() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => nextTick().then(resolve)));
  });
}

async function insertAnchorAtEnd(wrapper, source) {
  const editor = wrapper.vm.editor;
  editor.commands.focus("end");
  await wrapper.get(".canvas-editor").trigger("focus");
  expect(wrapper.vm.insertCitation(source)).toBe("inserted");
  await framesSettled();
  return editor;
}

it("捕获正文选区的精确位置、引用和当前修订号", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  await selectParagraph(wrapper);
  const captured = wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0];
  expect(captured).toMatchObject({ quote: "案例原文", revision: 3, from: 9, to: 13 });
  expect(captured.quoteHash).toHaveLength(64);
  expect(wrapper.get('[aria-label="添加选区批注"]').exists()).toBe(true);
});

it("选中文字可关联资料，工具栏可取消引用", async () => {
  const source = { sourceType: "attachment", id: "att-1", number: 1, title: "图示" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  await selectParagraph(wrapper);
  expect(wrapper.vm.insertCitation(source)).toBe("linked");
  expect(wrapper.vm.editor.getJSON().content[1].content[0].marks).toContainEqual({
    type: "citation", attrs: { sourceType: "attachment", sourceId: "att-1" },
  });
  await nextTick();
  await framesSettled();
  await wrapper.get('[aria-label="取消当前引用"]').trigger("mousedown");
  expect(wrapper.vm.editor.getJSON().content[1].content[0].marks).toBeUndefined();
});

it("无选区时在光标处插入引用锚点并显示编号", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = wrapper.vm.editor;
  editor.commands.focus("end");
  await wrapper.get(".canvas-editor").trigger("focus");
  expect(wrapper.vm.insertCitation(source)).toBe("inserted");
  await nextTick();
  const nodes = editor.getJSON().content[1].content;
  expect(nodes.at(-1).text).toBe("\u200B");
  expect(nodes.at(-1).marks).toContainEqual({
    type: "citation", attrs: { sourceType: "case", sourceId: "src-1" },
  });
  expect(wrapper.get(".canvas-editor .citation-number").text()).toBe("〔2〕");
});

it("未放置光标或只读时拒绝插入引用", async () => {
  const source = { sourceType: "case", id: "src-1", number: 1, title: "引用案例" };
  const unpositioned = await setup({ annotatable: true, sources: [source] });
  expect(unpositioned.wrapper.vm.insertCitation(source)).toBe("unpositioned");
  expect(unpositioned.wrapper.vm.editor.getJSON().content[1].content).toHaveLength(1);
  const readonly = await setup({ editable: false, sources: [source] });
  expect(readonly.wrapper.vm.insertCitation(source)).toBe("readonly");
  expect(readonly.wrapper.find('[aria-label="取消当前引用"]').exists()).toBe(false);
});

it("光标锚点引用可整段取消且无残留", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = await insertAnchorAtEnd(wrapper, source);
  const cancel = wrapper.get('[aria-label="取消当前引用"]');
  expect(cancel.attributes("disabled")).toBeUndefined();
  await cancel.trigger("mousedown");
  const nodes = editor.getJSON().content[1].content;
  expect(nodes).toHaveLength(1);
  expect(nodes[0].text).toBe("案例原文");
  expect(nodes.every((node) => !node.marks)).toBe(true);
  await framesSettled();
  expect(cancel.attributes("disabled")).toBeDefined();
});

it("引用锚点后的后续输入不带引用标记", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = await insertAnchorAtEnd(wrapper, source);
  editor.commands.insertContent("继续输入");
  const nodes = editor.getJSON().content[1].content;
  expect(nodes.at(-1).text).toBe("继续输入");
  expect(nodes.at(-1).marks).toBeUndefined();
  await framesSettled();
  expect(wrapper.get('[aria-label="取消当前引用"]').attributes("disabled")).toBeDefined();
});

it("游标移到锚点前界取消只删锚点不误伤正文", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = await insertAnchorAtEnd(wrapper, source);
  editor.commands.insertContent("继续输入");
  // 游标移到锚点前界（13）：取消应仅删除锚点，保留前后正文。
  editor.commands.setTextSelection({ from: 13, to: 13 });
  await framesSettled();
  const cancel = wrapper.get('[aria-label="取消当前引用"]');
  expect(cancel.attributes("disabled")).toBeUndefined();
  await cancel.trigger("mousedown");
  const after = editor.getJSON().content[1].content;
  expect(after).toHaveLength(1);
  expect(after[0].text).toBe("案例原文继续输入");
  expect(after[0].marks).toBeUndefined();
});

it("正文替换后旧光标作废，插入被拒绝", async () => {
  const source = { sourceType: "case", id: "src-1", number: 1, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  wrapper.vm.editor.commands.focus("end");
  await wrapper.get(".canvas-editor").trigger("focus");
  const replaced = { type: "doc", content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: "替换后的正文" }] },
  ] };
  await wrapper.setProps({ document: replaced });
  expect(wrapper.vm.insertCitation(source)).toBe("unpositioned");
  expect(wrapper.vm.editor.getJSON().content[1].content[0].text).toBe("替换后的正文");
});

it("来源编号变化时正文引用编号同步刷新", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  wrapper.vm.editor.commands.focus("end");
  await wrapper.get(".canvas-editor").trigger("focus");
  wrapper.vm.insertCitation(source);
  await wrapper.setProps({ sources: [{ ...source, number: 3 }] });
  expect(wrapper.get(".canvas-editor .citation-number").text()).toBe("〔3〕");
});

it("引用 HTML 粘贴往返保留资料属性", async () => {
  const source = { sourceType: "attachment", id: "att-1", number: 1, title: "图示" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  await selectParagraph(wrapper);
  wrapper.vm.insertCitation(source);
  const html = wrapper.vm.editor.getHTML();
  expect(html).toContain('data-citation-source="attachment:att-1"');
  wrapper.vm.editor.commands.setContent(html, false);
  expect(wrapper.vm.editor.getJSON().content[1].content[0].marks).toContainEqual({
    type: "citation", attrs: { sourceType: "attachment", sourceId: "att-1" },
  });
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
