<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ChevronDown, CornerDownLeft, Lightbulb, Sparkles, X } from "@lucide/vue";
import { store, activeThread } from "../store.js";

// AI 输入区：选区 chip（可展开/移除/定位）+ 输入框 + 底部 model/web/thinking 控件。
const props = defineProps({
  busy: { type: Boolean, default: false },
  elapsed: { type: Number, default: 0 },
  modelSupportedThinking: { type: Boolean, default: false },
});
const emit = defineEmits(["send", "stop", "locate-chip", "remove-chip"]);
const inputEl = ref(null);
const composerEl = ref(null);
const modelButton = ref(null);
const composing = ref(false);
let flashTimer = 0;
const chipExpanded = ref(false);
const chipFlash = ref(false);
const modelMenuOpen = ref(false);

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

async function focusInput() {
  await nextTick();
  inputEl.value?.focus({ preventScroll: true });
}
async function flashChip(chip) {
  clearTimeout(flashTimer);
  chipExpanded.value = false;
  chipFlash.value = false;
  await nextTick();
  if (!chip) return;
  requestAnimationFrame(() => {
    chipFlash.value = true;
    flashTimer = setTimeout(() => { chipFlash.value = false; }, 620);
  });
  if (!store.ui.aiCollapsed) focusInput();
}
watch(() => store.selectionChip, flashChip);
function outside(event) {
  if (!composerEl.value?.contains(event.target)) { modelMenuOpen.value = false; chipExpanded.value = false; }
  else if (!event.target.closest(".capability-left")) modelMenuOpen.value = false;
}
function escape(event) {
  if (!modelMenuOpen.value && !chipExpanded.value) return;
  event.preventDefault(); event.stopPropagation();
  if (modelMenuOpen.value) modelButton.value?.focus();
  modelMenuOpen.value = false;
  chipExpanded.value = false;
}
async function toggleModels() {
  modelMenuOpen.value = !modelMenuOpen.value;
  if (!modelMenuOpen.value) return;
  await nextTick();
  composerEl.value.querySelector(".model-menu .active, .model-menu button")?.focus();
}
function modelKey(event) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const buttons = [...composerEl.value.querySelectorAll(".model-menu button")];
  const current = buttons.indexOf(document.activeElement);
  const step = event.key === "ArrowDown" ? 1 : -1;
  const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + step + buttons.length) % buttons.length;
  buttons[index]?.focus();
}
function setModel(model) {
  store.modelId = model;
  modelMenuOpen.value = false;
  modelButton.value?.focus();
}
function enter(event) {
  if (event.isComposing || composing.value || event.keyCode === 229 || event.shiftKey) return;
  event.preventDefault();
  submit();
}
function endComposition() {
  setTimeout(() => { composing.value = false; }, 0);
}
onMounted(() => document.addEventListener("pointerdown", outside));
onBeforeUnmount(() => { document.removeEventListener("pointerdown", outside); clearTimeout(flashTimer); });
defineExpose({ focusInput });

function canSend() {
  return Boolean(draft.value.trim()) && !props.busy && store.aiConfig.ready;
}
function submit(revise = false) {
  if (!canSend()) return;
  emit("send", { text: draft.value.trim(), skills: [...chosenSkills.value], revise });
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
  <div ref="composerEl" class="ai-composer" @keydown.esc="escape">
    <div v-if="busy" class="ai-run-row">
      <span class="ai-run-dot" />运行中 {{ (liveElapsed / 1000).toFixed(1) }}s
      <button type="button" class="ai-stop" @click="emit('stop')">停止</button>
    </div>
    <p v-if="store.selectionChip?.anchorMissing" class="selection-stale" role="status">引用的原文已变化；仍可讨论，修改前请重新选取。</p>
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
        placeholder="向 AI 提问，或讨论当前文稿…"
        aria-label="发送给 AI 的消息"
        @compositionstart="composing = true"
        @compositionend="endComposition"
        @keydown.enter="enter"
      />
      <div class="compose-side">
        <button type="button" class="send" :disabled="!canSend()" title="发送" @click="submit()"><CornerDownLeft :size="15" /></button>
      </div>
    </div>
    <button v-if="store.selectionChip" type="button" class="request-revision" :disabled="!canSend() || store.selectionChip.anchorMissing" @click="submit(true)">按输入生成修改建议</button>
    <div class="capability-bar">
      <div class="capability-left">
        <button ref="modelButton" type="button" class="capability model" aria-haspopup="menu" :aria-expanded="modelMenuOpen" @click="toggleModels">
          {{ currentModelLabel }} <ChevronDown :size="12" />
        </button>
        <div v-if="modelMenuOpen" class="model-menu" role="menu" aria-label="选择模型" @keydown="modelKey">
          <button v-for="m in store.aiConfig.models" :key="m" type="button" role="menuitemradio" :aria-checked="m === store.modelId" :class="{ active: m === store.modelId }" @click="setModel(m)">
            {{ m }}
            <small v-if="m === store.aiConfig.defaultModel">默认</small>
          </button>
        </div>

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
      <span class="ai-disclaimer">{{ store.editDemo ? "固定模拟结果 · 不调用模型" : "AI 使用真实模型 · 文档仅内存" }}</span>
    </div>
  </div>
</template>

<style scoped>
.sel-chip-full { top: auto; bottom: calc(100% + 6px); max-height: min(280px, 40vh); overflow-y: auto; white-space: pre-wrap; }
.sel-chip-locate { width: auto; min-width: 30px; font-size: 11px; }
button:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.compose-side button:disabled { opacity: .45; cursor: not-allowed; }
.model-menu { max-height: min(320px, 40vh); overflow-y: auto; }
</style>
