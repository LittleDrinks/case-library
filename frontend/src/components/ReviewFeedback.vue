<script setup>
defineProps({ review: { type: Object, required: true } });
</script>

<template>
  <section id="review-feedback-panel" class="assistant-panel review-feedback" aria-label="审核意见">
    <header>
      <h2>审核意见</h2>
      <span>v{{ review.versionNumber }} · 退回修改</span>
    </header>
    <div class="review-feedback-content" tabindex="0" aria-label="退回原因和留言">
      <ul class="review-feedback-reasons" aria-label="退回原因">
        <li v-for="reason in review.reasonTypes" :key="reason">{{ reason }}</li>
      </ul>
      <div v-if="review.message" class="review-feedback-message">{{ review.message }}</div>
    </div>
  </section>
</template>
