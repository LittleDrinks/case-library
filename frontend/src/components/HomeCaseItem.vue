<script setup>
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
    <span class="home-case-title-row">
      <h3>{{ caseRecord.title }}</h3>
      <span class="home-tag green">已发布</span>
    </span>
    <span class="home-case-meta">
      <span class="home-tag primary">{{ caseRecord.typeName || "教学案例" }}</span>
      <span class="home-tag">{{ caseRecord.stageText || "全部学段" }}</span>
      <span>更新 {{ dateLabel(caseRecord.updatedAt) }}</span>
      <span v-if="caseRecord.likes">赞 {{ caseRecord.likes }}</span>
    </span>
  </RouterLink>
</template>
