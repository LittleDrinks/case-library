import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import MaterialDownloadAction from "./MaterialDownloadAction.vue";

function render(material) {
  return mount(MaterialDownloadAction, { props: { material } });
}

test("可读文件素材显示带提示的下载入口", () => {
  const wrapper = render({
    id: "material-1", title: "教学资料", filename: "教学资料.txt",
    contentAvailable: true, hasFile: true,
  });

  const link = wrapper.get("a");
  expect(link.attributes("href")).toBe("/api/materials/material-1/content");
  expect(link.attributes("aria-label")).toBe("下载教学资料");
  expect(link.attributes("title")).toBe("下载 教学资料.txt");
  expect(link.attributes("download")).toBe("");
});

test("受限素材只显示禁用提示且不提供下载链接", () => {
  const wrapper = render({
    id: "material-2", title: "校内资料", contentAvailable: false, hasFile: true,
  });

  expect(wrapper.find("a").exists()).toBe(false);
  const button = wrapper.get("button");
  expect(button.attributes("disabled")).toBeDefined();
  expect(button.attributes("title")).toBe("当前账号无权下载");
});

test("没有原文件的可读素材不提供失效下载链接", () => {
  const wrapper = render({
    id: "material-3", title: "网页素材", contentAvailable: true,
  });

  expect(wrapper.find("a").exists()).toBe(false);
  expect(wrapper.find("button").exists()).toBe(false);
});
