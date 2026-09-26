import { mount } from "@vue/test-utils";
import { TextSelection } from "@tiptap/pm/state";
import { nextTick } from "vue";
import { afterEach, expect, it, vi } from "vitest";
import CanvasEditor from "./CanvasEditor.vue";

// 挂载过的编辑器必须在环境销毁前 destroy，否则 DOMObserver 挂起定时器越界触发
const mounted = [];

afterEach(() => {
  while (mounted.length) mounted.pop().unmount();
  globalThis.getSelection()?.removeAllRanges();
});

const caseDocument = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: "案例原文" }] },
  ],
};
const replacedDocument = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: "替换后的正文" }] },
  ],
};

async function setup(options = {}) {
  if (!document.getElementById("workbench-format-toolbar")) {
    const toolbar = document.createElement("div");
    toolbar.id = "workbench-format-toolbar";
    document.body.appendChild(toolbar);
  }
  const wrapper = mount(CanvasEditor, {
    props: { document: caseDocument, editable: true, ...options },
  });
  mounted.push(wrapper);
  await nextTick();
  const context = wrapper.emitted("writing-context").at(-1)[0];
  return { wrapper, context };
}

function selectDomRange(textNode, length, start = 0, notify = true) {
  const range = globalThis.document.createRange();
  range.setStart(textNode, start);
  range.setEnd(textNode, start + length);
  const browserSelection = globalThis.getSelection();
  browserSelection.removeAllRanges();
  browserSelection.addRange(range);
  if (notify) globalThis.document.dispatchEvent(new Event("selectionchange"));
}

function paragraphTextNode(paragraph) {
  return paragraph.querySelector(".annotation-anchor")?.firstChild ?? paragraph.firstChild;
}

function clearDomSelection() {
  globalThis.getSelection().removeAllRanges();
  globalThis.document.dispatchEvent(new Event("selectionchange"));
}

function toolbarButton(label) {
  return document.querySelector(`#workbench-format-toolbar [aria-label="${label}"]`);
}

function triggerToolbarButton(label) {
  toolbarButton(label).dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
}

function pressEditorKey(editor, key) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  editor.view.dom.dispatchEvent(event);
  return event;
}

function adjacentCitationDocument(firstSource, secondSource) {
  const citation = (source) => ({
    type: "citation",
    attrs: { sourceType: source.sourceType, sourceId: source.id },
  });
  return {
    type: "doc",
    content: [{
      type: "paragraph",
      content: [
        { type: "text", text: "Before " },
        { type: "text", text: "first", marks: [{ type: "bold" }, citation(firstSource)] },
        { type: "text", text: "second", marks: [{ type: "bold" }, citation(secondSource)] },
        { type: "text", text: " after" },
      ],
    }],
  };
}

async function selectParagraph(wrapper, length = 4) {
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(
    editor.state.doc, 9, 9 + length,
  )));
  selectDomRange(wrapper.get(".canvas-editor p").element.firstChild, length);
  wrapper.vm.recaptureSelection();
  await nextTick();
}

async function waitForWritingContext(wrapper, predicate) {
  await vi.waitUntil(() => (wrapper.emitted("writing-context") ?? [])
    .some(([context]) => predicate(context)), { interval: 10 });
}

async function selectAnnotationAndWait(wrapper, annotation) {
  expect(wrapper.vm.selectAnnotation(annotation)).toBe(true);
  await wrapper.vm.recaptureSelection();
  await waitForWritingContext(wrapper, (context) => context?.annotationId === annotation.id);
}

async function deleteSelectedAnnotation(wrapper, annotation) {
  await selectAnnotationAndWait(wrapper, annotation);
  wrapper.vm.editor.commands.deleteSelection();
  await nextTick();
  expectUnlinkedWritingContext(wrapper);
  wrapper.vm.clearSelection();
  clearDomSelection();
}

function expectUnlinkedWritingContext(wrapper) {
  expect(wrapper.emitted("writing-context").at(-1)[0]).not.toHaveProperty("annotationId");
}

function clearAndExpectWritingContextNull(wrapper) {
  wrapper.vm.clearSelection();
  expect(wrapper.emitted("writing-context").at(-1)[0]).toBeNull();
  clearDomSelection();
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
  for (const label of ["选区加粗", "选区斜体", "编辑选区链接", "带选区问 AI"]) {
    expect(wrapper.find(`[aria-label="${label}"]`).exists()).toBe(true);
  }
  expect(wrapper.find('[aria-label="添加选区批注"]').exists()).toBe(false);
  await wrapper.get('[aria-label="带选区问 AI"]').trigger("click");
  expect(wrapper.emitted("ask-ai")).toHaveLength(1);
});

it("编号列表序列化只包含后端接受的起点属性", async () => {
  const document = {
    type: "doc",
    content: [{
      type: "orderedList",
      attrs: { start: 3 },
      content: [{
        type: "listItem",
        content: [{ type: "paragraph", content: [{ type: "text", text: "第一项" }] }],
      }],
    }],
  };
  const { wrapper } = await setup({ document });

  expect(wrapper.vm.editor.getJSON()).toEqual(document);
});

it("工具栏创建的编号列表序列化为默认起点", async () => {
  const document = {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text: "第一项" }] }],
  };
  const { wrapper } = await setup({ document });

  triggerToolbarButton("编号列表");

  expect(wrapper.vm.editor.getJSON()).toEqual({
    type: "doc",
    content: [{
      type: "orderedList",
      attrs: { start: 1 },
      content: [{
        type: "listItem",
        content: [{ type: "paragraph", content: [{ type: "text", text: "第一项" }] }],
      }],
    }],
  });
});

it("后续编辑保留嵌套编号列表起点且不序列化额外属性", async () => {
  const document = {
    type: "doc",
    content: [{
      type: "orderedList",
      attrs: { start: 3 },
      content: [{
        type: "listItem",
        content: [
          { type: "paragraph", content: [{ type: "text", text: "第一层" }] },
          {
            type: "orderedList",
            attrs: { start: 6 },
            content: [{
              type: "listItem",
              content: [{ type: "paragraph", content: [{ type: "text", text: "嵌套项" }] }],
            }],
          },
        ],
      }],
    }],
  };
  const { wrapper } = await setup({ document });
  const editor = wrapper.vm.editor;
  editor.commands.focus("end");
  editor.commands.insertContent("后续编辑");

  expect(editor.getJSON()).toEqual({
    type: "doc",
    content: [{
      type: "orderedList",
      attrs: { start: 3 },
      content: [{
        type: "listItem",
        content: [
          { type: "paragraph", content: [{ type: "text", text: "第一层" }] },
          {
            type: "orderedList",
            attrs: { start: 6 },
            content: [{
              type: "listItem",
              content: [{ type: "paragraph", content: [{ type: "text", text: "嵌套项后续编辑" }] }],
            }],
          },
        ],
      }],
    }],
  });
});

it("批注选区重捕获保留关联，改选和显式清除会解除", async () => {
  const annotation = { id: "annotation-1", from: 9, to: 13, quote: "案例原文", anchorState: "active" };
  const { wrapper } = await setup({ annotatable: true, revision: 3, annotations: [annotation] });
  document.body.appendChild(wrapper.element);
  await selectAnnotationAndWait(wrapper, annotation);
  const paragraph = wrapper.get(".canvas-editor p").element;
  const editor = wrapper.vm.editor;
  selectDomRange(paragraphTextNode(paragraph), 4);
  await wrapper.vm.recaptureSelection();
  await waitForWritingContext(wrapper, (context) => context?.annotationId === annotation.id);
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 12)));
  selectDomRange(paragraphTextNode(paragraph), 3);
  await wrapper.vm.recaptureSelection();
  await waitForWritingContext(wrapper, (context) => context?.quote === "案例原" && !context.annotationId);
  expectUnlinkedWritingContext(wrapper);
  clearAndExpectWritingContextNull(wrapper);
  await deleteSelectedAnnotation(wrapper, annotation);
});

it("编辑 AI 输入框时 selectionchange 不清除当前批注关联", async () => {
  const annotation = { id: "annotation-1", from: 9, to: 13, quote: "案例原文", anchorState: "active" };
  const { wrapper } = await setup({ annotatable: true, annotations: [annotation] });
  document.body.appendChild(wrapper.element);
  await selectAnnotationAndWait(wrapper, annotation);
  const composer = document.createElement("textarea");
  document.body.appendChild(composer);
  composer.focus();
  document.dispatchEvent(new Event("selectionchange"));
  expect(wrapper.emitted("writing-context").at(-1)[0]).toMatchObject({ annotationId: annotation.id });
  expect(wrapper.get(".annotation-anchor").text()).toBe(annotation.quote);
  composer.remove();
});

it("批注刷新移除当前关联时保留正文选区但解除关联", async () => {
  const annotation = { id: "annotation-1", from: 9, to: 13, quote: "案例原文", anchorState: "active" };
  const { wrapper } = await setup({ annotatable: true, annotations: [annotation] });
  document.body.appendChild(wrapper.element);
  await selectAnnotationAndWait(wrapper, annotation);
  await wrapper.setProps({ annotations: [] });
  await vi.waitUntil(() => {
    const context = wrapper.emitted("writing-context")?.at(-1)?.[0];
    return context?.from === annotation.from && context?.to === annotation.to && !context.annotationId;
  }, { interval: 10 });
  expect(wrapper.emitted("writing-context").at(-1)[0]).toMatchObject({
    from: annotation.from, to: annotation.to, quote: annotation.quote,
  });
  expect(wrapper.find(".annotation-anchor").exists()).toBe(false);
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
  triggerToolbarButton("取消当前引用");
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
  const cancel = toolbarButton("取消当前引用");
  expect(cancel.hasAttribute("disabled")).toBe(false);
  triggerToolbarButton("取消当前引用");
  const nodes = editor.getJSON().content[1].content;
  expect(nodes).toHaveLength(1);
  expect(nodes[0].text).toBe("案例原文");
  expect(nodes.every((node) => !node.marks)).toBe(true);
  await framesSettled();
  expect(cancel.hasAttribute("disabled")).toBe(true);
});

it("Backspace 删除引用正文标记并保留正文与资料区来源", async () => {
  const source = { sourceType: "attachment", id: "att-1", number: 1, title: "图示" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  await selectParagraph(wrapper);
  expect(wrapper.vm.insertCitation(source)).toBe("linked");

  const editor = wrapper.vm.editor;
  editor.commands.setTextSelection(13);
  const event = pressEditorKey(editor, "Backspace");
  await nextTick();

  expect(event.defaultPrevented).toBe(true);
  expect(editor.state.doc.child(1).textContent).toBe("案例原文");
  expect(editor.getJSON().content[1].content[0].marks).toBeUndefined();
  expect(wrapper.props("sources")).toEqual([source]);
});

it.each([
  ["Backspace", 11],
  ["Delete", 9],
])("%s 在引用正文边界删除标记且保留后续普通正文", async (key, position) => {
  const source = { sourceType: "attachment", id: "att-1", number: 1, title: "图示" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  await selectParagraph(wrapper, 2);
  expect(wrapper.vm.insertCitation(source)).toBe("linked");

  const editor = wrapper.vm.editor;
  editor.commands.setTextSelection(position);
  const event = pressEditorKey(editor, key);
  await nextTick();

  expect(event.defaultPrevented).toBe(true);
  expect(editor.state.doc.child(1).textContent).toBe("案例原文");
  expect(editor.getJSON().content[1].content.flatMap((node) => node.marks ?? [])).not.toContainEqual(
    { type: "citation", attrs: { sourceType: source.sourceType, sourceId: source.id } },
  );
  expect(wrapper.props("sources")).toEqual([source]);
});

it.each([
  ["甲", 13, "source-b"],
  ["乙", 19, "source-a"],
])("相邻粗体不同来源引用%s末尾 Backspace 只取消目标", async (_, position, remainingSourceId) => {
  const sourceA = { sourceType: "case", id: "source-a", number: 1, title: "来源甲" };
  const sourceB = { sourceType: "case", id: "source-b", number: 2, title: "来源乙" };
  const sources = [sourceA, sourceB];
  const { wrapper } = await setup({
    annotatable: true,
    document: adjacentCitationDocument(sourceA, sourceB),
    sources,
  });
  const editor = wrapper.vm.editor;

  editor.commands.setTextSelection(position);
  const event = pressEditorKey(editor, "Backspace");
  await nextTick();

  expect(event.defaultPrevented).toBe(true);
  expect(editor.state.doc.firstChild.textContent).toBe("Before firstsecond after");
  expect(editor.getJSON().content[0].content
    .flatMap((node) => node.marks ?? [])
    .filter((mark) => mark.type === "citation")
    .map((mark) => mark.attrs.sourceId)).toEqual([remainingSourceId]);
  expect(wrapper.props("sources")).toEqual(sources);
});

it("相邻粗体不同来源引用内部取消只移除当前来源标记", async () => {
  const sourceA = { sourceType: "case", id: "source-a", number: 1, title: "来源甲" };
  const sourceB = { sourceType: "case", id: "source-b", number: 2, title: "来源乙" };
  const sources = [sourceA, sourceB];
  const { wrapper } = await setup({
    annotatable: true,
    document: adjacentCitationDocument(sourceA, sourceB),
    sources,
  });
  const editor = wrapper.vm.editor;

  editor.commands.setTextSelection(15);
  await framesSettled();
  triggerToolbarButton("取消当前引用");

  expect(editor.state.doc.firstChild.textContent).toBe("Before firstsecond after");
  expect(editor.getJSON().content[0].content
    .flatMap((node) => node.marks ?? [])
    .filter((mark) => mark.type === "citation")
    .map((mark) => mark.attrs.sourceId)).toEqual([sourceA.id]);
  expect(wrapper.props("sources")).toEqual(sources);
});

it.each(["Backspace", "Delete"])("引用正文内部按 %s 不触发整段引用移除", async (key) => {
  const source = { sourceType: "attachment", id: "att-1", number: 1, title: "图示" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  await selectParagraph(wrapper);
  expect(wrapper.vm.insertCitation(source)).toBe("linked");

  const editor = wrapper.vm.editor;
  editor.commands.setTextSelection(11);
  const event = pressEditorKey(editor, key);
  await nextTick();

  expect(event.defaultPrevented).toBe(false);
  expect(editor.state.doc.child(1).textContent).toBe("案例原文");
  expect(editor.getJSON().content[1].content[0].marks).toEqual([
    { type: "citation", attrs: { sourceType: source.sourceType, sourceId: source.id } },
  ]);
  expect(wrapper.props("sources")).toEqual([source]);
});

it.each([
  ["Delete", 13],
  ["Backspace", 14],
])("%s 在空引用锚点的对应边界删除锚点且保留相邻正文", async (key, position) => {
  const source = { sourceType: "case", id: "src-1", number: 1, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = await insertAnchorAtEnd(wrapper, source);

  editor.commands.setTextSelection(position);
  const event = pressEditorKey(editor, key);
  await nextTick();

  expect(event.defaultPrevented).toBe(true);
  expect(editor.state.doc.child(1).textContent).toBe("案例原文");
  expect(editor.getJSON().content[1].content).toEqual([{ type: "text", text: "案例原文" }]);
  expect(wrapper.props("sources")).toEqual([source]);
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
  expect(toolbarButton("取消当前引用").hasAttribute("disabled")).toBe(true);
});

it("游标移到锚点前界取消只删锚点不误伤正文", async () => {
  const source = { sourceType: "case", id: "src-1", number: 2, title: "引用案例" };
  const { wrapper } = await setup({ annotatable: true, sources: [source] });
  const editor = await insertAnchorAtEnd(wrapper, source);
  editor.commands.insertContent("继续输入");
  // 游标移到锚点前界（13）：取消应仅删除锚点，保留前后正文。
  editor.commands.setTextSelection({ from: 13, to: 13 });
  await framesSettled();
  const cancel = toolbarButton("取消当前引用");
  expect(cancel.hasAttribute("disabled")).toBe(false);
  triggerToolbarButton("取消当前引用");
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

it("相同正文保存修订保留有效选区，正文替换或手动编辑会清除旧选区", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  globalThis.document.body.appendChild(wrapper.element);
  await nextTick();
  await selectParagraph(wrapper);
  await wrapper.setProps({ revision: 4 });
  expect(wrapper.emitted("selection").at(-1)[0]).not.toBeNull();
  expect(globalThis.getSelection().toString()).toBe("案例原文");
  expect(wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0])
    .toMatchObject({ quote: "案例原文", revision: 4 });
  await wrapper.setProps({ document: replacedDocument, revision: 5 });
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
  await wrapper.setProps({ document: caseDocument, revision: 6 });
  await selectParagraph(wrapper);
  wrapper.vm.editor.commands.insertContent("新增");
  await nextTick();
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
});

it("原生选区消失时修订变化不会复活 PM 旧选区", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  globalThis.document.body.appendChild(wrapper.element);
  await selectParagraph(wrapper);
  clearDomSelection();
  await wrapper.setProps({ revision: 4 });
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
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
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
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

it("autosave 修订早于 PM 同步时保留新原生选区并阻塞旧触发器", async () => {
  const { wrapper } = await setup({ annotatable: true, revision: 3 });
  globalThis.document.body.appendChild(wrapper.element);
  await selectParagraph(wrapper);
  const editor = wrapper.vm.editor;
  await selectWhileStateStale(wrapper, wrapper.get(".canvas-editor p").element);
  await wrapper.setProps({ revision: 4 });
  expect(globalThis.getSelection().toString()).toBe("案例原文");
  expect(wrapper.emitted("selection").at(-1)[0]).toBeNull();
  expect((wrapper.emitted("selection") ?? []).some(([event]) => event?.revision === 4)).toBe(false);
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, 9, 13)));
  await wrapper.vm.recaptureSelection();
  await vi.waitUntil(() => (wrapper.emitted("selection") ?? [])
    .some(([event]) => event?.quote === "案例原文" && event.revision === 4), { interval: 10 });
  await nextTick();
  expect(wrapper.emitted("selection").at(-1)[0]).not.toBeNull();
  expect(wrapper.emitted("selection").filter((event) => event[0]).at(-1)[0])
    .toMatchObject({ quote: "案例原文", revision: 4 });
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

it("挂起选区锚点在失焦塌陷后仍绘制高亮", async () => {
  const pending = { from: 9, to: 13, quote: "案例原文" };
  const { wrapper } = await setup({ revision: 3, pendingAnchor: pending });
  expect(wrapper.get(".pending-anchor").text()).toBe("案例原文");

  clearDomSelection();
  await framesSettled();
  expect(wrapper.get(".pending-anchor").text()).toBe("案例原文");
  expect(wrapper.find(".annotation-anchor").exists()).toBe(false);
});

it("正文不再包含挂起引文时丢弃临时高亮", async () => {
  const pending = { from: 9, to: 13, quote: "案例原文" };
  const { wrapper } = await setup({ revision: 3, pendingAnchor: pending });
  const editor = wrapper.vm.editor;
  editor.view.dispatch(editor.state.tr.insertText("变化", 9, 13));
  await new Promise((resolve) => setTimeout(resolve, 20));
  await nextTick();
  expect(wrapper.find(".pending-anchor").exists()).toBe(false);
});

it("正文前置编辑映射后挂起锚点仍通过保存校验", async () => {
  const pending = { from: 9, to: 13, quote: "案例原文", revision: 3 };
  const { wrapper } = await setup({ revision: 3, pendingAnchor: pending });
  const editor = wrapper.vm.editor;
  // 前置插入 2 字符（模拟保存前编辑）：装饰链把 pending 映射到新位置，校验仍通过。
  editor.view.dispatch(editor.state.tr.insertText("前置", 9, 9));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(wrapper.vm.getPendingAnchor()).toBeTruthy();
  const mapped = wrapper.findAll(".pending-anchor");
  expect(mapped).toHaveLength(1);
  expect(mapped[0].text()).toBe("案例原文");
  expect(wrapper.vm.getPendingAnchor()).toMatchObject({ quote: "案例原文" });
  expect(wrapper.vm.getPendingAnchor().from).toBeGreaterThan(9);
});

it("挂起锚点失效或清空后移除临时高亮", async () => {
  const pending = { from: 9, to: 13, quote: "案例原文" };
  const { wrapper } = await setup({ revision: 3, pendingAnchor: pending });
  await wrapper.setProps({ pendingAnchor: null });
  expect(wrapper.find(".pending-anchor").exists()).toBe(false);
  await wrapper.setProps({ pendingAnchor: { ...pending, quote: "其他文字" } });
  expect(wrapper.find(".pending-anchor").exists()).toBe(false);
  await wrapper.setProps({ pendingAnchor: { ...pending, quote: "案例原文" } });
  expect(wrapper.get(".pending-anchor").text()).toBe("案例原文");
});

it("显示正文内修订差异并用原生 steps 应用，保留撤销历史", async () => {
  const { wrapper } = await setup();
  const editor = wrapper.vm.editor;
  const target = {
    id: "artifact-1", from: 9, to: 13, quote: "案例原文", replacement: "新正文",
  };

  expect(await wrapper.vm.previewRevision(target)).toBe(true);
  expect(wrapper.get(".revision-preview-old").text()).toBe("案例原文");
  expect(wrapper.get(".revision-preview-new").text()).toBe("新正文");
  const steps = editor.state.tr.insertText("新正文", 9, 13).steps.map((step) => step.toJSON());
  expect(await wrapper.vm.applyRevisionSteps(steps, target)).toBe(true);
  await nextTick();

  expect(editor.state.doc.textBetween(9, 12)).toBe("新正文");
  expect(wrapper.get(".revision-applied-new").text()).toBe("新正文");
  expect(wrapper.emitted("change")).toBeUndefined();
  expect(editor.commands.undo()).toBe(true);
  expect(editor.state.doc.textBetween(9, 13)).toBe("案例原文");
  expect(wrapper.emitted("change")).toHaveLength(1);
});

it("等正文平滑滚动结束后再展示修订预览", async () => {
  const { wrapper } = await setup();
  const scrollColumn = wrapper.element;
  scrollColumn.classList.add("canvas-column");
  const paragraph = wrapper.get(".canvas-editor p").element;
  paragraph.scrollIntoView = vi.fn(() => {
    window.setTimeout(() => {
      scrollColumn.scrollTop = 24;
      scrollColumn.dispatchEvent(new Event("scroll"));
    }, 40);
  });
  const target = {
    id: "artifact-1", from: 9, to: 13, quote: "案例原文", replacement: "新正文",
  };

  const preview = wrapper.vm.previewRevision(target);
  await new Promise((resolve) => window.setTimeout(resolve, 70));
  expect(wrapper.find(".revision-preview-old").exists()).toBe(false);
  await preview;

  expect(paragraph.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
  expect(wrapper.get(".revision-preview-old").text()).toBe("案例原文");
});

it("locates an applied record by its replacement without showing a stale preview", async () => {
  const { wrapper } = await setup({ document: replacedDocument, editable: false });
  const paragraph = wrapper.get(".canvas-editor p").element;
  paragraph.scrollIntoView = vi.fn();
  const target = {
    id: "artifact-accepted", from: 9, to: 13, quote: "案例原文",
    replacement: "替换后的正文", status: "accepted", locateOnly: true,
  };

  expect(await wrapper.vm.previewRevision(target)).toBe(true);
  expect(paragraph.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
  expect(wrapper.find(".revision-preview-old").exists()).toBe(false);
  expect(wrapper.find(".revision-preview-new").exists()).toBe(false);
});

it("does not guess a historical location when the replacement text repeats", async () => {
  const replacement = "替换后的正文";
  const documentWithRepeatedReplacement = {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: replacement }] },
      { type: "paragraph", content: [{ type: "text", text: "后来插入的间隔段落" }] },
      { type: "paragraph", content: [{ type: "text", text: replacement }] },
    ],
  };
  const { wrapper } = await setup({ document: documentWithRepeatedReplacement, editable: false });
  const domAtPos = vi.spyOn(wrapper.vm.editor.view, "domAtPos");
  const paragraphs = wrapper.findAll(".canvas-editor p");
  paragraphs.forEach(({ element }) => { element.scrollIntoView = vi.fn(); });

  expect(await wrapper.vm.previewRevision({
    id: "artifact-repeated", from: 9, to: 9 + replacement.length,
    quote: "旧原文", replacement, status: "accepted", locateOnly: true,
  })).toBe(false);

  expect(domAtPos).not.toHaveBeenCalled();
  paragraphs.forEach(({ element }) => expect(element.scrollIntoView).not.toHaveBeenCalled());
});

it("does not use a replacement when the original historical quote is ambiguous", async () => {
  const documentWithAmbiguousQuote = {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "旧原文" }] },
      { type: "paragraph", content: [{ type: "text", text: "间隔段落" }] },
      { type: "paragraph", content: [{ type: "text", text: "旧原文" }] },
      { type: "paragraph", content: [{ type: "text", text: "唯一替换" }] },
    ],
  };
  const { wrapper } = await setup({ document: documentWithAmbiguousQuote, editable: false });
  const domAtPos = vi.spyOn(wrapper.vm.editor.view, "domAtPos");
  wrapper.findAll(".canvas-editor p")
    .forEach(({ element }) => { element.scrollIntoView = vi.fn(); });

  expect(await wrapper.vm.previewRevision({
    id: "artifact-ambiguous-quote", from: 1, to: 4, quote: "旧原文",
    replacement: "唯一替换", status: "superseded", locateOnly: true,
  })).toBe(false);
  expect(domAtPos).not.toHaveBeenCalled();
});

it("does not locate an unapplied historical suggestion by its replacement", async () => {
  const { wrapper } = await setup({ document: replacedDocument, editable: false });
  const domAtPos = vi.spyOn(wrapper.vm.editor.view, "domAtPos");
  const paragraph = wrapper.get(".canvas-editor p").element;
  paragraph.scrollIntoView = vi.fn();

  expect(await wrapper.vm.previewRevision({
    id: "artifact-rejected", from: 9, to: 13, quote: "已不存在的原文",
    replacement: "替换后的正文", status: "rejected", locateOnly: true,
  })).toBe(false);
  expect(domAtPos).not.toHaveBeenCalled();
  expect(paragraph.scrollIntoView).not.toHaveBeenCalled();
});

it("does not report a historical record located when its text is absent", async () => {
  const { wrapper } = await setup({ document: replacedDocument, editable: false });
  const paragraph = wrapper.get(".canvas-editor p").element;
  paragraph.scrollIntoView = vi.fn();

  expect(await wrapper.vm.previewRevision({
    id: "artifact-missing", from: 9, to: 13, quote: "已不存在的原文",
    replacement: "也已不存在", status: "accepted", locateOnly: true,
  })).toBe(false);
  expect(paragraph.scrollIntoView).not.toHaveBeenCalled();
});

it("discards a preview whose smooth scroll finishes after a newer request", async () => {
  const { wrapper } = await setup();
  const scrollColumn = wrapper.element;
  scrollColumn.classList.add("canvas-column");
  const paragraph = wrapper.get(".canvas-editor p").element;
  paragraph.scrollIntoView = vi.fn();
  const first = {
    id: "artifact-first", from: 9, to: 13, quote: "案例原文", replacement: "第一条修改",
  };
  const second = { ...first, id: "artifact-second", replacement: "第二条修改" };

  const firstPreview = wrapper.vm.previewRevision(first);
  const secondPreview = wrapper.vm.previewRevision(second);
  scrollColumn.dispatchEvent(new Event("scroll"));
  await new Promise((resolve) => window.setTimeout(resolve, 150));

  expect(await firstPreview).toBe(false);
  expect(await secondPreview).toBe(true);
  expect(wrapper.get(".revision-preview-new").text()).toBe("第二条修改");
});

it("目标原文变化后清除差异并拒绝应用", async () => {
  const { wrapper } = await setup();
  const editor = wrapper.vm.editor;
  const target = {
    id: "artifact-1", from: 9, to: 13, quote: "案例原文", replacement: "新正文",
  };
  wrapper.vm.previewRevision(target);
  editor.view.dispatch(editor.state.tr.insertText("已改", 9, 13));
  await nextTick();

  expect(wrapper.find(".revision-preview-old").exists()).toBe(false);
  expect(wrapper.vm.isRevisionCurrent(target)).toBe(false);
  expect(await wrapper.vm.applyRevisionSteps([], target)).toBe(false);
});

it("空段落建议预览新增文字，应用原生插入步骤后显示正文", async () => {
  const { wrapper } = await setup({ document: {
    type: "doc", content: [{ type: "paragraph" }],
  } });
  const target = { id: "fill-empty", from: 1, to: 1, quote: "", replacement: "教学目标" };
  expect(await wrapper.vm.previewRevision(target)).toBe(true);
  expect(wrapper.get(".revision-preview-new").text()).toBe("教学目标");
  expect(wrapper.find(".revision-preview-old").exists()).toBe(false);
  const steps = [{ stepType: "replace", from: 1, to: 1,
    slice: { content: [{ type: "text", text: "教学目标" }] } }];
  expect(await wrapper.vm.applyRevisionSteps(steps, target)).toBe(true);
  expect(wrapper.vm.editor.getJSON().content[0].content[0].text).toBe("教学目标");
  expect(wrapper.vm.isRevisionCurrent(target)).toBe(false);
  expect(await wrapper.vm.previewRevision(target)).toBe(false);
});
