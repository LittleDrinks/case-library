<script setup>
import { ArrowUp, Check, ChevronDown, Search, Sparkles, TextSelect, X } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { ElPopover } from "element-plus";
import { useConversationSources } from "../composables/useConversationSources.js";
import AgentSourcePicker from "./AgentSourcePicker.vue";

const props = defineProps({
  caseId: { type: String, required: true },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  configured: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  threadId: { type: String, default: "" },
  writingContext: { type: Object, default: null },
  skills: { type: Array, default: () => [] },
  catalog: { type: String, default: "loading" },
});
const emit = defineEmits(["send", "clear-selection", "reload-catalog"]);
const { sources, remove } = useConversationSources();
const sourcePicker = ref(null);
const draft = ref("");
const chosenSkillId = ref("");
const skillOpen = ref(false);
const skillQuery = ref("");

const placeholder = computed(() => (props.configured
  ? (props.readOnly ? "输入问题" : "输入问题，或输入 $ 插入 Skill…") : "请先配置 AI 模型"));
const selectionText = computed(() => props.writingContext?.quote || "");
const chosenSkill = computed(() => props.skills.find((skill) => skill.id === chosenSkillId.value) || null);
const matchedSkills = computed(() => {
  const term = skillQuery.value.trim().toLowerCase();
  return props.skills.filter((skill) => !term || `${skill.name} ${skill.id}`.toLowerCase().includes(term));
});
const canSend = computed(() => Boolean(draft.value.trim() && props.configured && !props.busy));

function skillLabel(skill) {
  return skill.version ? `${skill.name}（${skill.version}）` : skill.name;
}

function trackDraft() {
  if (props.readOnly) return;
  const pending = draft.value.match(/\$([^\s$]*)$/);
  if (!pending) return;
  skillQuery.value = pending[1];
  skillOpen.value = true;
}

function chooseSkill(skill) {
  draft.value = draft.value.replace(/\$([^\s$]*)$/, "");
  chosenSkillId.value = skill.id;
  skillOpen.value = false;
  skillQuery.value = "";
}

function chooseFirstSkill() {
  if (matchedSkills.value[0]) chooseSkill(matchedSkills.value[0]);
}

function showAllSources() {
  sourcePicker.value?.openPicker();
}

watch(() => props.threadId, () => {
  chosenSkillId.value = "";
  skillOpen.value = false;
});

function submit() {
  if (!canSend.value) return;
  emit("send", { text: draft.value.trim(), skillId: chosenSkillId.value });
  draft.value = "";
  chosenSkillId.value = "";
  skillOpen.value = false;
  skillQuery.value = "";
}
</script>

<template>
  <div class="agent-composer" data-testid="agent-composer">
    <div class="context-strip">
      <AgentSourcePicker
        ref="sourcePicker"
        :case-id="caseId"
        :version-id="versionId"
        :read-only="readOnly"
        :disabled="busy"
      />
      <span v-if="sources.length || selectionText" class="context-divider" />
      <span v-for="source in sources.slice(0, 1)" :key="`${source.sourceType}:${source.id}`" class="context-chip" :title="source.title || source.id">
        <span>{{ source.title || source.id }}</span>
        <button type="button" :aria-label="`取消参考${source.title || source.id}`" @click="remove(source)"><X :size="11" /></button>
      </span>
      <button v-if="sources.length > 1" type="button" class="more-context" aria-label="查看全部已选资料" @click="showAllSources">+{{ sources.length - 1 }}</button>
      <span v-if="selectionText" class="context-chip selection-chip" :title="selectionText" data-testid="composer-selection">
        <TextSelect :size="12" aria-hidden="true" /><span>正文选区 {{ selectionText.length }} 字</span>
        <button type="button" aria-label="移除正文选区" @click="emit('clear-selection')"><X :size="11" /></button>
      </span>
    </div>
    <div class="compose-box">
      <div v-if="chosenSkill" class="message-skill-block" data-testid="composer-skill-block">
        <Sparkles :size="14" aria-hidden="true" />
        <span><b>{{ chosenSkill.name }}</b><small>本条消息调用</small></span>
        <button type="button" aria-label="移除 Skill 调用" @click="chosenSkillId = ''"><X :size="13" /></button>
      </div>
      <textarea
        v-model="draft"
        aria-label="向 AI 提问"
        :placeholder="placeholder"
        :disabled="!configured || busy"
        @input="trackDraft"
        @keydown.enter.ctrl.prevent="submit"
      />
      <div class="capability-bar">
        <div class="capability-actions">
          <ElPopover
            v-if="!readOnly"
            v-model:visible="skillOpen"
            trigger="click"
            placement="top-start"
            :width="310"
            popper-class="composer-popover skill-popover"
            :show-arrow="false"
          >
            <template #reference>
              <button type="button" class="capability" aria-label="插入 Skill" data-testid="skill-picker-toggle">
                <Sparkles :size="15" aria-hidden="true" /><span>插入 Skill</span><ChevronDown :size="11" aria-hidden="true" />
              </button>
            </template>
            <div class="picker-heading">
              <div><b>插入 Skill</b><small>作为调用块加入这条消息，发送后清空</small></div>
            </div>
            <div class="picker-search">
              <Search :size="15" aria-hidden="true" />
              <input
                v-model="skillQuery"
                aria-label="搜索 Skill"
                placeholder="搜索 Skill"
                data-testid="skill-search"
                @keydown.enter.prevent="chooseFirstSkill"
              />
            </div>
            <div class="picker-items">
              <span v-if="catalog === 'loading'" class="skill-catalog-state" data-testid="skill-catalog-loading">正在加载目录</span>
              <template v-else-if="catalog === 'error'">
                <span class="skill-catalog-state error" data-testid="skill-catalog-error">目录加载失败</span>
                <button type="button" class="skill-catalog-retry" data-testid="skill-catalog-retry" @click="emit('reload-catalog')">重试</button>
              </template>
              <span v-else-if="!skills.length" class="skill-catalog-state" data-testid="skill-catalog-empty">暂无已发布 Skill</span>
              <button
                v-else
                v-for="skill in matchedSkills"
                :key="skill.id"
                type="button"
                class="skill-choice"
                data-testid="skill-option"
                @click="chooseSkill(skill)"
              >
                <span><b>{{ skillLabel(skill) }}</b><small>{{ skill.description || "以已发布 Skill 处理这条消息" }}</small></span>
                <Check :size="14" aria-hidden="true" />
              </button>
              <p v-if="catalog === 'ready' && skills.length && !matchedSkills.length" class="empty-picker">没有匹配的 Skill</p>
            </div>
            <div class="picker-bottom"><small>下条消息按需重新插入</small></div>
          </ElPopover>
        </div>
        <button type="button" class="send-button" aria-label="发送" :disabled="!canSend" @click="submit">
          <ArrowUp :size="18" aria-hidden="true" />
        </button>
      </div>
    </div>
    <div class="compose-footnote">
      <span>AI 内容请核实后使用</span>
      <span v-if="!readOnly">Ctrl ↵ 发送 · Enter 换行</span>
    </div>
  </div>
</template>
