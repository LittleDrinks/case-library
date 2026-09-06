<script setup>
import { BookOpen, ExternalLink, LockKeyhole } from "@lucide/vue";

defineProps({ sources: { type: Array, default: () => [] } });

function sourceMeta(row) {
  const parts = [];
  if (row.versionNumber != null) parts.push(`v${row.versionNumber}`);
  if (row.publishedAt) parts.push(String(row.publishedAt).slice(0, 10));
  return parts.join(" · ");
}
</script>

<template>
  <section class="public-attachments public-sources" aria-labelledby="public-sources-title">
    <h2 id="public-sources-title"><BookOpen :size="16" />来源</h2>
    <p v-if="!sources.length">暂无来源</p>
    <ul v-else>
      <li v-for="(row, index) in sources" :key="row.id">
        <BookOpen :size="16" aria-hidden="true" />
        <span>〔{{ index + 1 }}〕{{ row.title }}</span>
        <a
          v-if="row.contentAvailable && row.sourceUrl"
          :href="row.sourceUrl"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="`打开来源${row.title}`"
          :title="`打开固定版本：${row.title}`"
        ><ExternalLink :size="15" /></a>
        <small>
          {{ sourceMeta(row) || "案例来源" }}
          <template v-if="!row.contentAvailable">
            <LockKeyhole :size="12" />内容按权限开放
          </template>
        </small>
      </li>
    </ul>
  </section>
</template>
