<script setup>
import { computed, ref } from "vue";
import { ChevronDown, LoaderCircle, X } from "@lucide/vue";
import {
  TAG_KINDS, TAG_MODES, emptyFilters, facetGroups, filterChips, selected,
  tagCounts, updateFilter, updateTagMode,
} from "../lib/searchFilters.js";

const props = defineProps({
  facets: { type: Object, required: true },
  kind: { type: String, required: true },
  catalog: { type: Array, default: () => [] },
  catalogLoading: { type: Boolean, default: false },
  catalogError: { type: String, default: "" },
});
const emit = defineEmits(["update:filters", "retry"]);
const filters = defineModel("filters", { type: Object, required: true });
const open = ref(false);
const tagSearch = ref("");
const groups = computed(() => facetGroups(props.facets, filters.value, props.kind));
const chips = computed(() => filterChips(filters.value, props.kind, props.catalog));
const counts = computed(() => tagCounts(props.facets));
const tagsVisible = computed(() => TAG_KINDS.includes(props.kind));
const catalogGroups = computed(() => props.catalog
  .filter(group => group.enabled !== false)
  .map(group => ({ ...group, tags: group.tags.filter(tag => tag.enabled !== false) }))
  .map(group => ({
    ...group,
    tags: group.tags.filter(tag => `${group.name} ${tag.name}`.includes(tagSearch.value.trim())),
  }))
  .filter(group => group.tags.length));

function change(group, value, event) {
  filters.value = updateFilter(filters.value, group, value, event.target.checked);
}

function applyMode(mode) {
  filters.value = updateTagMode(filters.value, mode);
}

function remove(chip) {
  filters.value = updateFilter(filters.value, chip.group, chip.value, false);
}

function clear() {
  filters.value = emptyFilters();
}
</script>

<template>
  <div v-if="groups.length || chips.length || tagsVisible" class="advanced-filter">
    <button type="button" :aria-expanded="open" @click="open = !open">高级筛选<ChevronDown :size="14" /></button>
    <div v-if="open" class="filter-popover">
      <fieldset v-if="tagsVisible" class="tag-catalog-filter">
        <legend>标签目录</legend>
        <p v-if="catalogLoading" class="filter-state"><LoaderCircle class="spin" :size="12" />标签目录加载中</p>
        <p v-else-if="catalogError" class="filter-state" role="alert">
          {{ catalogError }}<button type="button" @click="emit('retry')">重试</button>
        </p>
        <template v-else>
          <input v-model="tagSearch" type="search" aria-label="按名称查找标签" placeholder="按名称查找标签" />
          <div v-if="filters.tagIds?.length" class="tag-mode" role="group" aria-label="标签匹配方式">
            <button v-for="mode in TAG_MODES" :key="mode.value" type="button"
                    :aria-pressed="(filters.tagMode === 'any') === (mode.value === 'any')"
                    @click="applyMode(mode.value)">{{ mode.label }}</button>
          </div>
          <p v-if="!catalogGroups.length" class="filter-state">没有匹配的标签</p>
          <div v-for="group in catalogGroups" :key="group.id" class="tag-group">
            <b>{{ group.name }}</b>
            <label v-for="tag in group.tags" :key="tag.id">
              <input type="checkbox" :checked="selected(filters, 'tagCatalog', tag.id)" @change="change('tagCatalog', tag.id, $event)" />
              <span>{{ tag.name }}</span><small>{{ counts.get(tag.id) || 0 }}</small>
            </label>
          </div>
        </template>
      </fieldset>
      <fieldset v-for="group in groups" :key="group.key">
        <legend>{{ group.title }}</legend>
        <label v-for="option in group.options" :key="option.value">
          <input :type="group.key === 'time' ? 'radio' : 'checkbox'" :name="group.key" :checked="selected(filters, group.key, option.value)" @change="change(group.key, option.value, $event)" />
          <span>{{ option.label }}</span><small>{{ option.count }}</small>
        </label>
      </fieldset>
    </div>
    <div v-if="chips.length" class="filter-chips" aria-label="已选筛选">
      <button v-for="chip in chips" :key="`${chip.group}-${chip.value}`" type="button" :aria-label="`移除筛选：${chip.label}`" @click="remove(chip)">{{ chip.label }}<X :size="12" /></button>
      <button type="button" class="clear-filters" @click="clear">清空筛选</button>
    </div>
  </div>
</template>
