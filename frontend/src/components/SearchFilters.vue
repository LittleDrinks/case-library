<script setup>
import { computed, ref } from "vue";
import { ChevronDown, X } from "@lucide/vue";
import { emptyFilters, facetGroups, filterChips, selected, updateFilter } from "../lib/searchFilters.js";

const props = defineProps({ facets: { type: Object, required: true }, kind: { type: String, required: true } });
const filters = defineModel("filters", { type: Object, required: true });
const open = ref(false);
const groups = computed(() => facetGroups(props.facets, filters.value, props.kind));
const chips = computed(() => filterChips(filters.value, props.kind));

function change(group, value, event) {
  filters.value = updateFilter(filters.value, group, value, event.target.checked);
}

function remove(chip) {
  filters.value = updateFilter(filters.value, chip.group, chip.value, false);
}

function clear() {
  filters.value = emptyFilters();
}
</script>

<template>
  <div v-if="groups.length || chips.length" class="advanced-filter">
    <button type="button" :aria-expanded="open" @click="open = !open">高级筛选<ChevronDown :size="14" /></button>
    <div v-if="open" class="filter-popover">
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
