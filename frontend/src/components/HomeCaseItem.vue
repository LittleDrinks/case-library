<script setup>
import { ArrowUpRight } from "@lucide/vue";

defineProps({
  caseRecord: { type: Object, required: true },
});

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "日期待定";
}
</script>

<template>
  <RouterLink
    class="home-case-item"
    :to="{ name: 'case-public', params: { id: caseRecord.id } }"
  >
    <span class="home-case-tags">
      <span>
        <span class="home-tag primary">{{ caseRecord.typeName || "教学案例" }}</span>
        <span class="home-tag">{{ caseRecord.stageText || "全部学段" }}</span>
      </span>
      <ArrowUpRight class="home-case-arrow" :size="18" aria-hidden="true" />
    </span>
    <h3>{{ caseRecord.title }}</h3>
    <p v-if="caseRecord.summary">{{ caseRecord.summary }}</p>
    <span class="home-case-meta">
      <span v-if="caseRecord.course">{{ caseRecord.course }}</span>
      <span>更新 {{ dateLabel(caseRecord.updatedAt) }}</span>
      <span v-if="caseRecord.likes">{{ caseRecord.likes }} 人推荐</span>
    </span>
  </RouterLink>
</template>
