import { mount } from "@vue/test-utils";
import { TextSelection } from "@tiptap/pm/state";
import { nextTick } from "vue";
import { afterEach, expect, it, vi } from "vitest";
import CanvasEditor from "./CanvasEditor.vue";

// 挂载过的编辑器必须在环境销毁前 destroy，否则 DOMObserver 挂起定时器越界触发
const mounted = [];

afterEach(() => {
  while (mounted.length) mounted.pop().unmount();
});

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
  mounted.push(wrapper);
  await nextTick();
  const context = wrapper.emitted("writing-context").at(-1)[0];
  return { wrapper, context };
}

function selectDomRange(textNode, length, start = 0) {
  const range = globalThis.document.createRange();
  range.setStart(textNode, start);
  range.setEnd(textNode, start + length);
  const browserSelection = globalThis.getSelection();
  browserSelection.removeAllRanges();
  browserSelection.addRange(range);
  globalThis.document.dispatchEvent(new Event("selectionchange"));
}

function clearDomSelection() {
  globalThis.getSelection().removeAllRanges();
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

it("清理选区同时折叠编辑器状态，后续批注刷新不会复活旧选区", async () => {
  const annotation = {
    id: "annotation-1", from: 9, to: 13, quote: "案例原文", revision: 3,
    anchorState: "active",
  };
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  await selectParagraph(wrapper);
  wrapper.vm.clearSelection();
  expect(wrapper.vm.editor.state.selection.empty).toBe(true);
  await wrapper.setProps({ annotations: [annotation] });
  expect(globalThis.getSelection().toString()).toBe("");
  expect(wrapper.find('[aria-label="添加选区批注"]').exists()).toBe(false);
});


// 复现 selectionchange 早于编辑器 DOM→state 同步的真实顺序。
async function selectWhileStateStale(wrapper, paragraph) {
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 9)));
  selectDomRange(paragraph.firstChild, 4);
  await wrapper.vm.recaptureSelection();
  globalThis.document.dispatchEvent(new Event("selectionchange"));
}

it("selectionchange 早于编辑器状态同步时不得清除正在建立的 DOM 选区", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  globalThis.document.body.appendChild(wrapper.element);
  await nextTick();
  const paragraph = wrapper.get(".canvas-editor p").element;
  const editor = wrapper.vm.editor;
  await selectWhileStateStale(wrapper, paragraph);
  // 早到的观察不得清除正在建立的 DOM 选区：
  expect(globalThis.getSelection().toString()).toBe("案例原文");
  // PM 的 DOM→state 同步随后完成，选区被正常捕获：
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 13)));
  await wrapper.vm.recaptureSelection();
  await vi.waitUntil(() => (wrapper.emitted("selection") ?? []).some((event) => event[0]), { interval: 20 });
  expect(wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0])
    .toMatchObject({ quote: "案例原文" });
});

it("批注装饰刷新等待 DOM 选区完成编辑器同步", async () => {
  const annotation = {
    id: "annotation-1", from: 9, to: 13, quote: "案例原文", revision: 3,
    anchorState: "active",
  };
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  document.body.appendChild(wrapper.element);
  await nextTick();
  const editor = wrapper.vm.editor;
  const paragraph = wrapper.get(".canvas-editor p").element;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 9))); selectDomRange(paragraph.firstChild, 4);
  await wrapper.setProps({ annotations: [annotation] });
  expect(globalThis.getSelection().toString()).toBe("案例原文");
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 9)));
  clearDomSelection();
  await wrapper.vm.recaptureSelection();
  await nextTick();
  expect(wrapper.get(".annotation-anchor").text()).toBe("案例原文");
});

it("相同 quote 的不同 DOM 位置不会被当作当前编辑器选区", async () => {
  const document = {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: "案例原文案例原文" }] },
    ],
  };
  const { wrapper } = await setup({ document, annotatable: true, revision: 3 });
  globalThis.document.body.appendChild(wrapper.element);
  await nextTick();
  const editor = wrapper.vm.editor;
  const paragraph = wrapper.get(".canvas-editor p").element;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 13)));
  selectDomRange(paragraph.firstChild, 4, 4);
  await wrapper.vm.recaptureSelection();
  expect(globalThis.getSelection().toString()).toBe("案例原文");
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
});
// 启动一次悬挂中的摘要捕获，再把选区收起为光标（观察路径）。
async function suspendDigestAndCollapse(wrapper, pending) {
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 13)));
  void wrapper.vm.recaptureSelection();
  await vi.waitUntil(() => pending.length > 0, { interval: 10 });
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9)));
  await wrapper.vm.recaptureSelection();
}

it("悬挂的选区摘要完成时不得写回已被收起的选区", async () => {
  const { wrapper } = await setup({ annotatable: true });
  const pending = [];
  vi.stubGlobal("crypto", { subtle: { digest: () => new Promise((resolve) => pending.push(resolve)) } });
  try {
    await suspendDigestAndCollapse(wrapper, pending);
    const domLength = globalThis.getSelection().rangeCount;
    pending.forEach((resolve) => resolve(new Uint8Array(32).buffer));
    await nextTick();
    await nextTick();
    expect(globalThis.getSelection().rangeCount).toBe(domLength);
    expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
  } finally {
    vi.unstubAllGlobals();
  }
});
it("正文插入由编辑器映射批注标记并上报原生 steps", async () => {
  const annotation = {
    id: "annotation-1", from: 9, to: 13, quote: "案例原文", revision: 3,
    anchorState: "active",
  };
  const { wrapper } = await setup({ revision: 3, annotations: [annotation] });
  expect(wrapper.get(".annotation-anchor").text()).toBe("案例原文");

  const { editor } = wrapper.vm;
  editor.view.dispatch(editor.state.tr.insertText("前置", 9, 9));
  await nextTick();

  expect(wrapper.get(".annotation-anchor").text()).toBe("案例原文");
  expect(wrapper.emitted("change").at(-1)[0]).toMatchObject({
    document: expect.any(Object), steps: expect.arrayContaining([expect.any(Object)]),
  });
});

it("已解决批注不在正文绘制标记", async () => {
  const annotation = {
    id: "annotation-1", from: 9, to: 13, quote: "案例原文", revision: 3,
    status: "resolved", anchorState: "active",
  };
  const { wrapper } = await setup({ revision: 3, annotations: [annotation] });
  expect(wrapper.find(".annotation-anchor").exists()).toBe(false);
});

it("跨 hardBreak 批注用与创建一致的换行文本渲染标记", async () => {
  const breakDocument = {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [
        { type: "text", text: "第一行" }, { type: "hardBreak" }, { type: "text", text: "第二行" },
      ] },
    ],
  };
  const annotation = {
    id: "annotation-1", from: 9, to: 16, quote: "第一行\n第二行", revision: 3,
    anchorState: "active",
  };
  const { wrapper } = await setup({ document: breakDocument, revision: 3, annotations: [annotation] });
  const { editor } = wrapper.vm;
  expect(editor.state.doc.textBetween(9, 16, "\n", "\n")).toBe(annotation.quote);
  expect(wrapper.find(".annotation-anchor").exists()).toBe(true);
});

it("点击正文批注标记只发出打开事件", async () => {
  const annotation = {
    id: "annotation-1", from: 9, to: 13, quote: "案例原文", revision: 3,
    anchorState: "active",
  };
  const { wrapper } = await setup({ revision: 3, annotations: [annotation] });
  const { editor } = wrapper.vm;
  editor.view.someProp("handleClick", (handler) => handler(editor.view, 10));
  expect(wrapper.emitted("annotation-click")).toEqual([["annotation-1"]]);
});
