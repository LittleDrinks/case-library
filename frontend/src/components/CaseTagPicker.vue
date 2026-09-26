<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown, LoaderCircle, Tags, X } from "@lucide/vue";
import { ElPopover } from "element-plus";
import "element-plus/theme-chalk/el-popper.css";
import "element-plus/theme-chalk/el-popover.css";
import { tagIndex } from "../lib/tagCatalog.js";

const props = defineProps({
  tagIds: { type: Array, required: true },
  groups: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["update:tagIds", "retry"]);
const open = ref(false);
const query = ref("");
const picker = ref(null);
const triggerButton = ref(null);
const queryInput = ref(null);
const selectableGroups = computed(() => props.groups
  .filter((group) => group.enabled !== false)
  .map((group) => ({ ...group, tags: group.tags.filter((tag) => tag.enabled !== false) }))
  .filter((group) => group.tags.length));
const filteredGroups = computed(() => selectableGroups.value.map((group) => ({
  ...group, tags: group.tags.filter((tag) => `${group.name} ${tag.name}`.includes(query.value.trim())),
})).filter((group) => group.tags.length));
const labels = computed(() => {
  const index = tagIndex(props.groups);
  return props.tagIds
    .filter((id) => index.has(id))
    .map((id) => ({ id, name: index.get(id).name }));
});
const quiet = computed(() => (
  !props.editable && !props.tagIds.length && !props.loading && !props.error
));

function toggle(id, event) {
  const next = event.target.checked
    ? [...new Set([...props.tagIds, id])]
    : props.tagIds.filter(item => item !== id);
  emit("update:tagIds", next);
}

function remove(id) {
  emit("update:tagIds", props.tagIds.filter(item => item !== id));
}

function closeOnOutsideClick(event) {
  if (!open.value) return;
  const path = event.composedPath();
  if (path.includes(picker.value) || path.some((node) => node?.classList?.contains("case-tag-popover"))) return;
  open.value = false;
}

function closeOnEscape(event) {
  if (!open.value || event.key !== "Escape") return;
  event.preventDefault();
  open.value = false;
  triggerButton.value?.focus();
}

onMounted(() => {
  document.addEventListener("click", closeOnOutsideClick, true);
  // Restore focus before ElPopover's focus trap handles Escape.
  document.addEventListener("keydown", closeOnEscape, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", closeOnOutsideClick, true);
  document.removeEventListener("keydown", closeOnEscape, true);
});

function focusSearch() {
  queryInput.value?.focus({ preventScroll: true });
}
</script>

<template>
  <div v-if="!quiet" ref="picker" class="case-tags">
    <Tags :size="13" aria-hidden="true" />
    <span v-if="loading" class="case-tags-state"><LoaderCircle class="spin" :size="12" />标签目录加载中</span>
    <span v-else-if="error" class="case-tags-state" role="alert">
      {{ error }}<button type="button" @click="emit('retry')">重试</button>
    </span>
    <template v-else>
      <ul v-if="labels.length" class="case-tag-list" aria-label="案例标签">
        <li v-for="tag in labels" :key="tag.id">
          {{ tag.name }}
          <button v-if="editable" type="button" :aria-label="`移除标签：${tag.name}`" @click="remove(tag.id)"><X :size="11" /></button>
        </li>
      </ul>
      <span v-else-if="editable" class="case-tags-state">未设置标签</span>
      <div v-if="editable" class="case-tag-editor">
        <ElPopover
          v-model:visible="open"
          trigger="click"
          role="dialog"
          placement="bottom-start"
          :width="300"
          popper-class="case-tag-popover"
          :show-arrow="false"
          @after-enter="focusSearch"
        >
          <template #reference>
            <button ref="triggerButton" type="button" class="case-tag-trigger" :aria-expanded="open">
              设置标签<ChevronDown :size="12" />
            </button>
          </template>
          <input ref="queryInput" v-model="query" type="search" aria-label="查找标签" placeholder="查找标签" />
          <p v-if="!selectableGroups.length" class="case-tags-state">暂无可选标签</p>
          <fieldset v-for="group in filteredGroups" :key="group.id">
            <legend>{{ group.name }}<b v-if="group.requiredForSubmission">投稿必填</b></legend>
            <label v-for="tag in group.tags" :key="tag.id">
              <input type="checkbox" :checked="tagIds.includes(tag.id)" @change="toggle(tag.id, $event)" />
              <span>{{ tag.name }}</span>
            </label>
          </fieldset>
        </ElPopover>
      </div>
    </template>
  </div>
</template>
