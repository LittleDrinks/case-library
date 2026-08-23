import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AssistantRail from "./AssistantRail.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { aiSettings: vi.fn(), streamAI: vi.fn() },
}));

const document = {
  type: "doc",
  content: [{ type: "paragraph", content: [{ type: "text", text: "案例原文" }] }],
};
const props = {
  active: "ai", open: true, caseRecord: {}, caseTitle: "案例标题",
  caseDocument: document, user: { csrfToken: "csrf" }, editable: true,
  beforeAttachmentMutation: vi.fn(), beforeVersionMutation: vi.fn(),
  candidateInvalidation: 0,
  writingContext: {
    quote: "案例原文", section: "一、教学说明", sectionText: "案例原文",
    from: 1, to: 5, sectionFrom: 1, sectionTo: 5,
  },
  applyCandidate: vi.fn(), rollbackCandidateBatch: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "model-a" });
  props.applyCandidate.mockResolvedValue({ snapshotId: "snapshot-batch" });
  props.rollbackCandidateBatch.mockResolvedValue(true);
});

async function fakeStream(messages, _csrf, handlers) {
  expect(messages.at(-1).content).toContain("当前案例正文：案例原文");
  handlers.onToken("第一段");
  handlers.onToken("第二段");
  handlers.onDone();
}

async function askQuestion() {
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("请提出建议");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  return wrapper;
}

it("工作台流式展示 AI 回答且不修改案例正文", async () => {
  api.streamAI.mockImplementation(fakeStream);
  const original = structuredClone(document);
  const wrapper = await askQuestion();
  expect(wrapper.text()).toContain("请提出建议");
  expect(wrapper.text()).toContain("第一段第二段");
  expect(document).toEqual(original);
});

async function candidateStream(_messages, _csrf, handlers) {
  handlers.onToken('{"text":"候选正文","reason":"让教学目标更明确"}');
  handlers.onDone();
}

async function generateCandidate(wrapper) {
  await wrapper.get('[aria-label="改写本节"]').trigger("click");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("精简这一节");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
}

async function mountRail() {
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  return wrapper;
}

function deferredCandidateStream() {
  let finish;
  const stream = (_messages, _csrf, handlers) => new Promise((resolve) => {
    finish = () => {
      handlers.onToken('{"text":"候选正文","reason":"让教学目标更明确"}');
      handlers.onDone();
      resolve();
    };
  });
  return { stream, finish: () => finish() };
}

async function beginCandidate(wrapper) {
  await wrapper.get('[aria-label="改写本节"]').trigger("click");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("精简这一节");
  await wrapper.get('[aria-label="发送"]').trigger("click");
}

async function generateDuringInvalidation(wrapper) {
  const deferred = deferredCandidateStream();
  api.streamAI.mockImplementation(deferred.stream);
  await beginCandidate(wrapper);
  await wrapper.setProps({ candidateInvalidation: 1 });
  deferred.finish();
  await flushPromises();
}

async function fillCandidateLimit() {
  api.streamAI.mockImplementation(candidateStream);
  const wrapper = await mountRail();
  await generateCandidate(wrapper);
  await generateCandidate(wrapper);
  await generateCandidate(wrapper);
  return wrapper;
}

async function acceptCandidate(candidate) {
  await candidate.get('[aria-label="接受修订"]').trigger("click");
  await flushPromises();
}

it("教师拒绝候选时正文不变", async () => {
  api.streamAI.mockImplementation(candidateStream);
  const original = structuredClone(document);
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await generateCandidate(wrapper);
  expect(wrapper.get('[aria-label="待确认修订"]').text()).toContain("候选正文");
  expect(wrapper.emitted("candidate-previews").at(-1)[0]).toHaveLength(1);

  await wrapper.get('[aria-label="拒绝修订"]').trigger("click");

  expect(props.applyCandidate).not.toHaveBeenCalled();
  expect(document).toEqual(original);
  expect(wrapper.text()).toContain("已拒绝");
});

it("正文变化后待确认修订失效且不能再接受", async () => {
  api.streamAI.mockImplementation(candidateStream);
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await generateCandidate(wrapper);

  await wrapper.setProps({ candidateInvalidation: 1 });

  expect(wrapper.get('[aria-label="待确认修订"]').text()).toContain("正文已变化，请重新生成");
  expect(wrapper.find('[aria-label="接受修订"]').exists()).toBe(false);
  expect(wrapper.emitted("candidate-previews").at(-1)[0]).toHaveLength(0);
  expect(props.applyCandidate).not.toHaveBeenCalled();
});

it("候选生成期间正文变化时结果直接失效", async () => {
  const wrapper = await mountRail();
  await generateDuringInvalidation(wrapper);
  expect(wrapper.get('[aria-label="待确认修订"]').text()).toContain("正文已变化，请重新生成");
  expect(wrapper.find('[aria-label="接受修订"]').exists()).toBe(false);
});

it("三条未决修订阻塞并允许教师显式继续生成一次", async () => {
  const wrapper = await fillCandidateLimit();
  expect(wrapper.findAll('[aria-label="待确认修订"]')).toHaveLength(3);
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("3 条修订待确认，请先接受或拒绝");
  await wrapper.get('[aria-label="继续生成"]').trigger("click");
  expect(wrapper.get('[aria-label="向 AI 提问"]').attributes("disabled")).toBeUndefined();
  await generateCandidate(wrapper);
  expect(wrapper.findAll('[aria-label="待确认修订"]')).toHaveLength(4);
  expect(wrapper.get('[aria-label="继续生成"]')).toBeTruthy();
});

it("连续接受的候选共享批前快照并一起标记回滚", async () => {
  api.streamAI.mockImplementation(candidateStream);
  const wrapper = await mountRail();
  await generateCandidate(wrapper);
  await acceptCandidate(wrapper.get('[aria-label="待确认修订"]'));
  await generateCandidate(wrapper);
  const cards = wrapper.findAll('[aria-label="待确认修订"]');
  await acceptCandidate(cards[1]);
  expect(props.applyCandidate).toHaveBeenCalledTimes(2);
  await cards[1].get('[aria-label="回滚本批"]').trigger("click");
  await flushPromises();
  expect(props.rollbackCandidateBatch).toHaveBeenCalledWith("snapshot-batch");
  expect(cards[0].text()).toContain("已回滚");
  expect(cards[1].text()).toContain("已回滚");
});

it("接受一条修订会使同一旧正文的其他待确认修订失效", async () => {
  api.streamAI.mockImplementation(candidateStream);
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await generateCandidate(wrapper);
  await generateCandidate(wrapper);
  const candidates = wrapper.findAll('[aria-label="待确认修订"]');

  await candidates[0].get('[aria-label="接受修订"]').trigger("click");
  await flushPromises();

  expect(candidates[0].text()).toContain("已接受");
  expect(candidates[1].text()).toContain("正文已变化，请重新生成");
  expect(candidates[1].find('[aria-label="接受修订"]').exists()).toBe(false);
});

it("接受修订后正文变化会让整批回滚过期", async () => {
  api.streamAI.mockImplementation(candidateStream);
  const wrapper = mount(AssistantRail, {
    props, global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await generateCandidate(wrapper);
  const candidate = wrapper.get('[aria-label="待确认修订"]');
  await candidate.get('[aria-label="接受修订"]').trigger("click");
  await flushPromises();

  await wrapper.setProps({ candidateInvalidation: 1 });

  expect(candidate.text()).toContain("回滚已过期");
  expect(candidate.find('[aria-label="回滚本批"]').exists()).toBe(false);
});
