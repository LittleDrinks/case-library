import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import { session } from "../session.js";
import PublicAttachmentList from "./PublicAttachmentList.vue";

vi.mock("../api.js", () => ({
  api: {
    listAttachments: vi.fn(),
    attachmentContentUrl: (caseId, attachmentId, versionId) => (
      `/api/cases/${caseId}/attachments/${attachmentId}/content?versionId=${versionId}`
    ),
  },
}));
vi.mock("../session.js", () => ({
  session: { user: null },
}));

const privateAttachment = {
  id: "private-1", name: "私密附件.docx", mediaType: "application/docx",
  size: 24, accessLevel: "private", createdAt: "2026-08-14T00:00:00Z",
};

async function render(user) {
  session.user = user;
  const wrapper = mount(PublicAttachmentList, {
    props: {
      caseId: "case-1", versionId: "version-1", isOwner: user?.id === "owner-1",
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  session.user = null;
  api.listAttachments.mockResolvedValue([privateAttachment]);
});

test.each([
  ["案例作者", { id: "owner-1", role: "user" }],
  ["管理员", { id: "admin-1", role: "admin" }],
])("%s可从公开详情下载私密附件", async (_role, user) => {
  const wrapper = await render(user);
  expect(wrapper.get("[aria-label='下载私密附件.docx']").attributes("href"))
    .toBe("/api/cases/case-1/attachments/private-1/content?versionId=version-1");
});

test.each([
  ["匿名用户", null],
  ["其他登录用户", { id: "other-1", role: "user" }],
])("%s不能从公开详情下载私密附件", async (_role, user) => {
  const wrapper = await render(user);
  expect(wrapper.find("[aria-label='下载私密附件.docx']").exists()).toBe(false);
  expect(wrapper.text()).toContain("仅作者与管理员可下载");
});
