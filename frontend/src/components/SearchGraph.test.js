import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SearchGraph from "./SearchGraph.vue";

const items = [
  { id: "material-1", kind: "material", title: "资料一", tags: ["共同主题"] },
  { id: "material-2", kind: "material", title: "资料二", tags: ["共同主题"] },
];

class TestResizeObserver {
  constructor(callback) {
    this.callback = callback;
  }

  observe(target) {
    this.callback([{ target, contentRect: { width: 1000, height: 520 } }]);
  }

  disconnect() {}
}

function mountGraph() {
  return mount(SearchGraph, {
    props: { items, query: "公开资源" },
    global: { stubs: { RouterLink: true } },
  });
}

function setStageBounds(wrapper) {
  const stage = wrapper.get(".graph-stage");
  stage.element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 520 });
}

describe("SearchGraph", () => {
  beforeEach(() => vi.stubGlobal("ResizeObserver", TestResizeObserver));
  afterEach(() => vi.unstubAllGlobals());

  it("lets users drag a node within the force graph", async () => {
    const wrapper = mountGraph();
    setStageBounds(wrapper);
    const node = wrapper.get('[aria-label="素材：资料一"]');

    await node.trigger("pointerdown", { button: 0, pointerId: 1, clientX: 500, clientY: 80 });
    await node.trigger("pointermove", { pointerId: 1, clientX: 850, clientY: 400 });

    expect(node.attributes("style")).toContain("left: 850px");
    expect(wrapper.findAll(".graph-link")[0].attributes("x2")).toBe("850");
    wrapper.unmount();
  });
});
