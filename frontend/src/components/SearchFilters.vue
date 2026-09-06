<script setup>
import { computed, ref } from "vue";
import { ChevronDown, X } from "@lucide/vue";
import {
  CATALOG_KINDS, emptyFilters, facetGroups, filterChips, selected, updateFilter,
} from "../lib/searchFilters.js";
import { catalogSections, tagLabel } from "../lib/tagCatalog.js";

const props = defineProps({
  facets: { type: Object, required: true },
  kind: { type: String, required: true },
  catalog: { type: Array, default: () => [] },
  catalogError: { type: String, default: "" },
});
const emit = defineEmits(["retry-catalog"]);
const filters = defineModel("filters", { type: Object, required: true });
const open = ref(false);
const groups = computed(() => facetGroups(props.facets, filters.value, props.kind));
const chips = computed(() => filterChips(filters.value, props.kind));
const withCatalog = computed(() => CATALOG_KINDS.includes(props.kind));
const sections = computed(() => (withCatalog.value
  ? catalogSections(props.catalog, props.facets.tagCatalog, filters.value.tagIds)
  : []));
const tagChips = computed(() => (withCatalog.value
  ? filters.value.tagIds.map(id => ({ value: id, label: tagLabel(props.catalog, id) }))
  : []));

function change(group, value, event) {
  filters.value = updateFilter(filters.value, group, value, event.target.checked);
}

function changeTag(id, event) {
  filters.value = updateFilter(filters.value, "tagIds", id, event.target.checked);
}

function setTagMode(mode) {
  filters.value = { ...filters.value, tagMode: mode };
}

function removeTag(id) {
  filters.value = updateFilter(filters.value, "tagIds", id, false);
}

function remove(chip) {
  filters.value = updateFilter(filters.value, chip.group, chip.value, false);
}

function clear() {
  filters.value = emptyFilters();
}
</script>

<template>
  <div v-if="groups.length || chips.length || sections.length || tagChips.length || catalogError" class="advanced-filter">
    <button type="button" :aria-expanded="open" @click="open = !open">高级筛选<ChevronDown :size="14" /></button>
    <div v-if="open" class="filter-popover">
      <template v-if="withCatalog">
        <p v-if="catalogError" class="filter-catalog-state" role="alert">
          {{ catalogError }}<button type="button" @click="emit('retry-catalog')">重试</button>
        </p>
        <template v-else-if="sections.length">
          <div class="tag-mode" role="group" aria-label="标签匹配方式">
            <span>标签匹配</span>
            <button type="button" :aria-pressed="filters.tagMode !== 'any'" @click="setTagMode('all')">全部符合</button>
            <button type="button" :aria-pressed="filters.tagMode === 'any'" @click="setTagMode('any')">任一符合</button>
          </div>
          <fieldset v-for="section in sections" :key="section.id">
            <legend>{{ section.name }}</legend>
            <label v-for="option in section.options" :key="option.value">
              <input type="checkbox" :checked="option.selected" @change="changeTag(option.value, $event)" />
              <span>{{ option.label }}</span><small>{{ option.count }}</small>
            </label>
          </fieldset>
        </template>
      </template>
      <fieldset v-for="group in groups" :key="group.key">
        <legend>{{ group.title }}</legend>
        <label v-for="option in group.options" :key="option.value">
          <input :type="group.key === 'time' ? 'radio' : 'checkbox'" :name="group.key" :checked="selected(filters, group.key, option.value)" @change="change(group.key, option.value, $event)" />
          <span>{{ option.label }}</span><small>{{ option.count }}</small>
        </label>
      </fieldset>
    </div>
    <div v-if="chips.length || tagChips.length" class="filter-chips" aria-label="已选筛选">
      <button v-for="chip in tagChips" :key="`tag-${chip.value}`" type="button" :aria-label="`移除标签：${chip.label}`" @click="removeTag(chip.value)">{{ chip.label }}<X :size="12" /></button>
      <button v-for="chip in chips" :key="`${chip.group}-${chip.value}`" type="button" :aria-label="`移除筛选：${chip.label}`" @click="remove(chip)">{{ chip.label }}<X :size="12" /></button>
      <button type="button" class="clear-filters" @click="clear">清空筛选</button>
    </div>
  </div>
</template>
