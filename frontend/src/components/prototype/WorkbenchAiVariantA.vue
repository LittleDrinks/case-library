<script setup>
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, CircleAlert,
  ListChecks, MessageSquareText, Plus, RotateCcw, Search,
  Send, Square, WandSparkles, Wrench, X,
} from "@lucide/vue";
import { computed, nextTick, ref, watch } from "vue";
import AgentCapabilityPickerPrototype from "./AgentCapabilityPickerPrototype.vue";
import AgentContextPickerPrototype from "./AgentContextPickerPrototype.vue";
import AgentMarkdownPrototype from "./AgentMarkdownPrototype.vue";
import AgentSkillActivityPrototype from "./AgentSkillActivityPrototype.vue";
import AgentThinkingActivityPrototype from "./AgentThinkingActivityPrototype.vue";
import AgentToolCallPrototype from "./AgentToolCallPrototype.vue";
import StructuredPromptEditorPrototype from "./StructuredPromptEditorPrototype.vue";

const props = defineProps({
  activeThread: { type: String, required: true },
  contexts: { type: Array, required: true },
  liveState: { type: String, required: true },
  liveTurns: { type: Array, required: true },
  promptParts: { type: Array, required: true },
  selected: { type: String, required: true },
  skillIds: { type: Array, required: true },
  toolIds: { type: Array, required: true },
  threads: { type: Array, required: true },
});
const emit = defineEmits(["accept", "new-thread", "prompt-parts", "reject", "retry", "select-thread", "send", "stop", "toggle-tool"]);
const contextPickerOpen = ref(false);
const conversationRef = ref(null);
const editorRef = ref(null);
const surface = ref("chat");
const threadQuery = ref("");
const filteredThreads = computed(() => props.threads.filter((thread) => (
  `${thread.title}${thread.preview}`.includes(threadQuery.value.trim())
)));
const liveContent = computed(() => props.liveTurns.map((turn) => `${turn.state}:${turn.answer}`).join("|"));
const insertedIds = computed(() => props.promptParts.filter((part) => part.type === "context").map((part) => part.resourceId));
const skillPickerOpen = ref(false);

function scrollToLatest() {
  nextTick(() => {
    const element = conversationRef.value;
    if (element) element.scrollTop = element.scrollHeight;
  });
}

function selectThread(id) {
  emit("select-thread", id);
  surface.value = "chat";
}

function createThread() {
  emit("new-thread");
  surface.value = "chat";
}

function insertContext(item) {
  editorRef.value?.insertContext(item);
  contextPickerOpen.value = false;
}

function toggleContextPicker() {
  skillPickerOpen.value = false;
  contextPickerOpen.value = !contextPickerOpen.value;
}

function toggleSkillPicker() {
  contextPickerOpen.value = false;
  skillPickerOpen.value = !skillPickerOpen.value;
}

function insertSkill(item) {
  editorRef.value?.insertSkill(item);
  skillPickerOpen.value = false;
}

watch([() => props.liveTurns.length, liveContent], scrollToLatest, { flush: "post" });

</script>

<template>
  <section class="agent-proto-panel agent-proto-a">
    <div v-if="surface === 'threads'" class="thread-browser">
      <header><button type="button" aria-label="返回当前对话" title="返回当前对话" @click="surface = 'chat'"><ArrowLeft :size="17" /></button><span><b>对话</b><small>{{ threads.length }} 个案例工作对话</small></span><button type="button" aria-label="新建对话" title="新建对话" @click="createThread"><Plus :size="17" /></button></header>
      <label class="thread-search"><Search :size="14" /><input v-model="threadQuery" type="search" placeholder="搜索对话" aria-label="搜索对话" /></label>
      <div class="thread-browser-list">
        <button v-for="thread in filteredThreads" :key="thread.id" type="button" :class="{ active: thread.id === activeThread }" @click="selectThread(thread.id)">
          <MessageSquareText :size="16" /><span><b>{{ thread.title }}</b><small>{{ thread.preview }}</small></span><time>{{ thread.time }}</time>
        </button>
      </div>
    </div>

    <template v-else>
      <header class="agent-proto-thread-header">
        <button type="button" class="thread-title-button" @click="surface = 'threads'">
          <MessageSquareText :size="15" /><b>{{ threads.find((item) => item.id === activeThread)?.title }}</b><ChevronRight :size="15" />
        </button>
        <button type="button" class="icon-command" aria-label="新建对话" title="新建对话" @click="createThread"><Plus :size="17" /></button>
      </header>

      <div ref="conversationRef" class="agent-proto-conversation">
      <article class="message-row user-message"><p>结合平台资料，把选中的教学目标改得更可操作。</p></article>
      <article class="message-row assistant-message">
        <p>我检索了平台内与课堂治理、学术诚信相关的案例，并据此收紧了学习结果。</p>
        <ol class="agent-activity-timeline" aria-label="Agent 活动">
          <AgentSkillActivityPrototype status="done" />
          <AgentThinkingActivityPrototype status="done" />
          <AgentToolCallPrototype status="done" />
        </ol>
      </article>

      <article class="revision-artifact">
        <header><ListChecks :size="16" /><span><b>待确认修订</b><small>教学目的 · 第 1 段</small></span></header>
        <div class="revision-diff"><del>形成对学术诚信、数据安全与教师责任的基本判断。</del><ins>辨识课堂使用生成式 AI 时的责任主体，并提出可执行的学术诚信与数据安全边界。</ins></div>
        <p class="revision-reason">将“形成判断”改为可观察的辨识与提出任务，保留原有三个责任维度。</p>
        <footer><button type="button" @click="emit('reject')"><X :size="14" />拒绝</button><button type="button" class="primary-command" @click="emit('accept')"><Check :size="14" />接受修订</button></footer>
      </article>

      <template v-for="turn in liveTurns" :key="turn.id">
        <article class="message-row user-message live-user-message"><p>{{ turn.question }}</p></article>
        <article class="message-row assistant-message live-assistant-message">
          <ol class="agent-activity-timeline" aria-label="真实模型活动">
            <AgentSkillActivityPrototype v-if="turn.skillIds.length" status="done" />
            <AgentThinkingActivityPrototype :status="turn.state === 'streaming' ? 'running' : 'done'" />
          </ol>
          <div v-if="turn.answer" class="live-model-answer"><AgentMarkdownPrototype :content="turn.answer" /><span v-if="turn.state === 'streaming'" class="stream-caret" /></div>
          <p v-else-if="turn.state === 'streaming'" class="live-waiting">正在等待真实模型返回内容<span class="thinking-ellipsis">...</span></p>
          <small v-if="turn.state === 'complete'" class="live-run-fact">本轮使用真实模型 · {{ turn.skillIds.length ? "思政案例生成 v2.1" : "自动匹配 Skill" }} · {{ turn.toolIds.length }} 项工具可用，本轮未调用</small>
        </article>
        <article v-if="turn.state === 'error'" class="run-state error-state">
          <CircleAlert :size="17" /><div><b>本次生成未完成</b><small>{{ turn.error || "模型服务暂时不可用" }}</small></div>
          <button type="button" @click="emit('retry')"><RotateCcw :size="13" />重试</button>
        </article>
      </template>
      </div>

      <form class="agent-proto-composer" @submit.prevent="emit('send')">
      <StructuredPromptEditorPrototype ref="editorRef" :model-value="promptParts" @update:model-value="emit('prompt-parts', $event)" />
      <footer>
        <div class="composer-left-actions">
          <div class="context-launcher">
            <button type="button" class="composer-tool-button" aria-label="添加到对话" title="添加到对话" :aria-expanded="contextPickerOpen" @click="toggleContextPicker"><Plus :size="16" /></button>
            <AgentContextPickerPrototype v-if="contextPickerOpen" :inserted-ids="insertedIds" :items="contexts" @close="contextPickerOpen = false" @insert="insertContext" />
          </div>
          <div class="skill-launcher">
            <button type="button" class="skill-picker" title="配置本轮能力" :aria-expanded="skillPickerOpen" @click="toggleSkillPicker"><WandSparkles :size="13" /><span>Skills</span><i>{{ skillIds.length }}</i><Wrench :size="11" /><i>{{ toolIds.length }}</i><ChevronDown :size="12" /></button>
            <AgentCapabilityPickerPrototype v-if="skillPickerOpen" :skill-ids="skillIds" :tool-ids="toolIds" @close="skillPickerOpen = false" @insert-skill="insertSkill" @toggle-tool="emit('toggle-tool', $event)" />
          </div>
          <span v-if="liveState === 'streaming'" class="composer-run-label"><i></i>真实模型生成中</span>
        </div>
        <button v-if="liveState === 'streaming'" type="button" class="icon-command primary-icon" aria-label="停止生成" title="停止生成" @click="emit('stop')"><Square :size="13" fill="currentColor" /></button>
        <button v-else type="submit" class="icon-command primary-icon" aria-label="发送" title="发送"><Send :size="16" /></button>
      </footer>
      </form>
    </template>
  </section>
</template>
