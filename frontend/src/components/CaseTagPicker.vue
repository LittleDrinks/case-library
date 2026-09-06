<script setup>
import { computed, ref } from "vue";
import { ChevronDown, LoaderCircle, Tags, X } from "@lucide/vue";
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
const filteredGroups = computed(() => props.groups.map((group) => ({
  ...group, tags: group.tags.filter((tag) => `${group.name} ${tag.name}`.includes(query.value.trim())),
})).filter((group) => group.tags.length));
const labels = computed(() => {
  const index = tagIndex(props.groups);
  return props.tagIds.map(id => ({ id, name: index.get(id)?.name || id }));
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
</script>

<template>
  <div v-if="!quiet" class="case-tags">
    <Tags :size="13" aria-hidden="true" />
    <span v-if="loading" class="case-tags-state"><LoaderCircle class="spin" :size="12" />标签目录加载中</span>
    <span v-else-if="error" class="case-tags-state" role="alert">
      {{ error }}<button v-if="editable" type="button" @click="emit('retry')">重试</button>
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
        <button type="button" :aria-expanded="open" @click="open = !open">设置标签<ChevronDown :size="12" /></button>
        <div v-if="open" class="case-tag-popover">
          <input v-model="query" type="search" aria-label="查找标签" placeholder="查找标签" />
          <p v-if="!groups.length" class="case-tags-state">管理员尚未维护标签目录</p>
          <fieldset v-for="group in filteredGroups" :key="group.id">
            <legend>{{ group.name }}<b v-if="group.requiredForSubmission">投稿必填</b></legend>
            <label v-for="tag in group.tags" :key="tag.id">
              <input type="checkbox" :checked="tagIds.includes(tag.id)" @change="toggle(tag.id, $event)" />
              <span>{{ tag.name }}</span>
            </label>
          </fieldset>
        </div>
      </div>
    </template>
  </div>
</template>
