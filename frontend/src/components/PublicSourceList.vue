<script setup>
import { BookOpen, ExternalLink, FileSearch, FileText, LockKeyhole } from "@lucide/vue";

defineProps({ sources: { type: Array, default: () => [] } });

function sourceMeta(row) {
  const parts = [];
  if (row.version) parts.push(row.version);
  if (row.publishedAt) parts.push(String(row.publishedAt).slice(0, 10));
  return parts.join(" · ") || ({ attachment: "附件", material: "素材", case: "案例来源" }[row.sourceType] || "资料");
}

function SourceIcon({ sourceType }) {
  return sourceType === "attachment" ? FileText : sourceType === "material" ? FileSearch : BookOpen;
}
</script>

<template>
  <section class="public-attachments public-sources" aria-labelledby="public-sources-title">
    <h2 id="public-sources-title"><BookOpen :size="16" />来源</h2>
    <p v-if="!sources.length">暂无来源</p>
    <ul v-else>
      <li v-for="row in sources" :key="row.id">
        <component :is="SourceIcon(row)" :size="16" aria-hidden="true" />
        <span>〔{{ row.number }}〕{{ row.title }}</span>
        <a
          v-if="row.contentAvailable && row.url"
          :href="row.url"
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
