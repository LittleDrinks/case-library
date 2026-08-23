import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { expect, it } from "vitest";
import CanvasEditor from "./CanvasEditor.vue";

const document = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: "案例原文" }] },
  ],
};

async function setup() {
  const wrapper = mount(CanvasEditor, { props: { document, editable: true } });
  await nextTick();
  const context = wrapper.emitted("writing-context").at(-1)[0];
  return { wrapper, context };
}

function candidate(context, mode, text = "候选正文") {
  return {
    id: text, context, mode, text, reason: "使教学任务与目标一致", status: "pending",
  };
}

it("待确认修订在正文原位显示删增和理由但不污染文档", async () => {
  const { wrapper, context } = await setup();
  const original = structuredClone(document);
  await wrapper.setProps({ candidatePreviews: [candidate(context, "replace-section")] });

  expect(wrapper.get(".candidate-inline-removed").text()).toBe("案例原文");
  expect(wrapper.get(".candidate-inline-preview").text()).toContain("候选正文");
  expect(wrapper.get(".candidate-inline-preview").text()).toContain("使教学任务与目标一致");
  expect(document).toEqual(original);
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
