<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ChevronDown, CornerDownLeft, Globe, Lightbulb, Paperclip, Sparkles, X } from "@lucide/vue";
import { store, mockSkills, activeThread } from "../store.js";

// AI 输入区：选区 chip（可展开/移除/定位）+ 输入框 + 底部 model/web/thinking 控件。
const props = defineProps({
  busy: { type: Boolean, default: false },
  elapsed: { type: Number, default: 0 },
  modelSupportedThinking: { type: Boolean, default: false },
});
const emit = defineEmits(["send", "stop", "locate-chip", "open-ai-menu", "remove-chip"]);
const inputEl = ref(null);
const chipExpanded = ref(false);
const chipFlash = ref(false);
const modelMenuOpen = ref(false);
const webLater = ref(false);

const draft = computed({
  get: () => store.composerDraft,
  set: (v) => { store.composerDraft = v; },
});
const thinkingEnabled = computed(() => store.aiConfig.ready && props.modelSupportedThinking);
const chosenSkills = computed(() => {
  const thread = activeThread();
  return thread?.pendingSkills || [];
});

const currentModelLabel = computed(() => {
  if (!store.aiConfig.ready) return store.aiConfig.error ? "AI 未就绪" : "加载中";
  return store.modelId || store.aiConfig.defaultModel || "Auto";
});
const liveElapsed = computed(() => {
  void props.elapsed;
  const job = store.runningJob;
  return job ? performance.now() - job.startedAt : 0;
});

watch(() => store.selectionChip, (chip, old) => {
  if (chip && chip !== old) {
    chipFlash.value = true;
    setTimeout(() => { chipFlash.value = false; }, 620);
    chipExpanded.value = false;
  }
});

function canSend() {
  return Boolean(draft.value.trim()) && !props.busy && store.aiConfig.ready;
}
function submit() {
  if (!canSend()) return;
  emit("send", { text: draft.value.trim(), skills: [...chosenSkills.value] });
  draft.value = "";
  const thread = activeThread();
  if (thread) thread.pendingSkills = [];
}
function removeSkill(id) {
  const thread = activeThread();
  if (thread) thread.pendingSkills = (thread.pendingSkills || []).filter((s) => s.id !== id);
}
</script>

<template>
  <div class="ai-composer">
    <div v-if="busy" class="ai-run-row">
      <span class="ai-run-dot" />运行中 {{ (liveElapsed / 1000).toFixed(1) }}s
      <button type="button" class="ai-stop" @click="emit('stop')">停止</button>
    </div>
    <div v-if="store.selectionChip" :class="['sel-chip', { flash: chipFlash }]">
      <button type="button" class="sel-chip-main" :title="store.selectionChip.quote" @click="chipExpanded = !chipExpanded">
        <span class="sel-chip-quote">{{ store.selectionChip.quote }}</span>
        <ChevronDown :size="12" class="chev" :class="{ open: chipExpanded }" />
      </button>
      <button type="button" class="sel-chip-locate" title="回到正文位置" @click="emit('locate-chip')">定位</button>
      <button type="button" class="sel-chip-remove" title="移除引用" @click="emit('remove-chip')"><X :size="12" /></button>
      <div v-if="chipExpanded" class="sel-chip-full">“{{ store.selectionChip.quote }}”</div>
    </div>
    <div v-for="skill in chosenSkills" :key="skill.id" class="msg-skill-block">
      <Sparkles :size="13" />
      <span>{{ skill.name }}（{{ skill.version }}）</span>
      <small>本条消息调用</small>
      <button type="button" @click="removeSkill(skill.id)"><X :size="12" /></button>
    </div>
    <div class="compose-box">
      <textarea
        ref="inputEl"
        v-model="draft"
        rows="2"
        placeholder="Ask AI anything…"
        @keydown.enter.exact.prevent="submit"
      />
      <div class="compose-side">
        <button type="button" title="附件（演示）"><Paperclip :size="15" /></button>
        <button type="button" class="ai-menu-trigger" title="AI 命令" @click="emit('open-ai-menu')"><Sparkles :size="15" /></button>
        <button type="button" class="send" :disabled="!canSend()" title="发送" @click="submit"><CornerDownLeft :size="15" /></button>
      </div>
    </div>
    <div class="capability-bar">
      <div class="capability-left">
        <button type="button" class="capability model" @click="modelMenuOpen = !modelMenuOpen">
          {{ currentModelLabel }} <ChevronDown :size="12" />
        </button>
        <div v-if="modelMenuOpen" class="model-menu" @mousedown.prevent>
          <button v-for="m in store.aiConfig.models" :key="m" type="button" :class="{ active: m === store.modelId }" @click="store.modelId = m; modelMenuOpen = false">
            {{ m }}
            <small v-if="m === store.aiConfig.defaultModel">默认</small>
          </button>
        </div>
        <button type="button" class="capability" title="联网：Later，未接入" @click="webLater = true">
          <Globe :size="14" /> <span v-if="webLater" class="later-hint">联网 Later · 未接入</span>
        </button>
        <button
          type="button"
          class="capability"
          :class="{ on: store.thinking && thinkingEnabled }"
          :disabled="!thinkingEnabled"
          :title="thinkingEnabled ? '请求推理内容' : '当前模型不支持思考参数'"
          @click="store.thinking = !store.thinking"
        >
          <Lightbulb :size="14" />
        </button>
      </div>
      <span class="ai-disclaimer">AI 使用真实模型 · 文档仅内存</span>
    </div>
  </div>
</template>
