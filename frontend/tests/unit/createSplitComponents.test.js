import { afterEach, describe, expect, it, vi } from "vitest";
import { createApp, defineComponent, h, nextTick, ref } from "vue";

import CreateContentEditor from "../../src/components/create/CreateContentEditor.vue";
import CreateMarkdownPreview from "../../src/components/create/CreateMarkdownPreview.vue";

function mount(component) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const app = createApp(component);
  const vm = app.mount(container);

  return {
    container,
    vm,
    unmount() {
      app.unmount();
      container.remove();
    },
  };
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("CreateContentEditor", () => {
  it("forwards v-model updates, touch, editor scroll, and textarea ref", async () => {
    const events = [];
    const wrapper = defineComponent({
      setup() {
        const content = ref("初始正文");
        return { content, events };
      },
      render() {
        return h(CreateContentEditor, {
          ref: "editor",
          modelValue: this.content,
          "onUpdate:modelValue": (value) => {
            this.content = value;
          },
          wordCount: 12,
          readingTime: 2,
          onTouch: (value) => events.push(["touch", value]),
          onEditorScroll: () => events.push(["editor-scroll"]),
        });
      },
    });
    const { container, vm, unmount } = mount(wrapper);

    const textarea = container.querySelector("textarea");
    textarea.value = "更新后的正文";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await nextTick();

    textarea.dispatchEvent(new Event("blur", { bubbles: true }));
    textarea.dispatchEvent(new Event("scroll", { bubbles: true }));
    await nextTick();

    expect(vm.content).toBe("更新后的正文");
    expect(events).toEqual([["touch", "content"], ["editor-scroll"]]);
    expect(vm.$refs.editor.contentTextarea).toBe(textarea);

    unmount();
  });
});

describe("CreateMarkdownPreview", () => {
  it("renders supported markdown while escaping unsafe HTML", async () => {
    const content = [
      "## 标题 **重点**",
      "- 列表 `code`",
      "> <img src=x onerror=alert(1)>",
      "<script>alert(1)</script>",
    ].join("\n");
    const events = [];
    const wrapper = defineComponent({
      setup() {
        return { content, events };
      },
      render() {
        return h(CreateMarkdownPreview, {
          ref: "preview",
          content: this.content,
          onPreviewScroll: () => events.push("preview-scroll"),
        });
      },
    });
    const { container, vm, unmount } = mount(wrapper);
    await nextTick();

    const body = container.querySelector(".preview-body");
    body.dispatchEvent(new Event("scroll", { bubbles: true }));
    await nextTick();

    expect(body.querySelector("h4 strong").textContent).toBe("重点");
    expect(body.querySelector(".md-list-item code").textContent).toBe("code");
    expect(body.querySelector("blockquote").textContent).toContain("<img src=x onerror=alert(1)>");
    expect(body.textContent).toContain("<script>alert(1)</script>");
    expect(body.querySelector("img")).toBeNull();
    expect(body.querySelector("script")).toBeNull();
    expect(events).toEqual(["preview-scroll"]);
    expect(vm.$refs.preview.previewBody).toBe(body);

    unmount();
  });
});
