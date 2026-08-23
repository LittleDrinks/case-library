<script setup>
import { ArrowRight, CalendarDays, Heart, UserRound } from "@lucide/vue";

defineProps({
  caseRecord: { type: Object, required: true },
  destination: { type: Object, required: true },
  status: { type: String, default: "" },
  actionLabel: { type: String, default: "" },
});

function dateLabel(value) {
  if (!value) return "日期待定";
  return String(value).slice(0, 10);
}
</script>

<template>
  <article class="case-card">
    <div class="case-card-meta">
      <span>{{ caseRecord.typeName || "教学案例" }}</span>
      <span v-if="caseRecord.course">{{ caseRecord.course }}</span>
      <strong v-if="status" :data-status="caseRecord.workflowStatus">{{ status }}</strong>
    </div>
    <h2><RouterLink :to="destination">{{ caseRecord.title }}</RouterLink></h2>
    <p>{{ caseRecord.summary || "案例简介待补充" }}</p>
    <ul v-if="caseRecord.theoryPoints?.length" class="case-card-theory" aria-label="理论要点">
      <li v-for="point in caseRecord.theoryPoints.slice(0, 3)" :key="point">{{ point }}</li>
    </ul>
    <footer>
      <span><UserRound :size="14" aria-hidden="true" />{{ caseRecord.author || "作者待补充" }}</span>
      <span><CalendarDays :size="14" aria-hidden="true" />{{ dateLabel(caseRecord.publishedAt || caseRecord.updatedAt) }}</span>
      <span v-if="caseRecord.likes"><Heart :size="14" aria-hidden="true" />{{ caseRecord.likes }}</span>
    </footer>
    <RouterLink v-if="actionLabel" class="case-card-action" :to="destination">
      {{ actionLabel }}<ArrowRight :size="15" aria-hidden="true" />
    </RouterLink>
  </article>
</template>
