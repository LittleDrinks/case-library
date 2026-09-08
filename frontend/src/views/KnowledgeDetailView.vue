<script setup>
import { onMounted, ref } from "vue";
import { LoaderCircle } from "@lucide/vue";
import { useRoute } from "vue-router";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";

const route = useRoute();
const knowledge = ref(null);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    knowledge.value = await api.getKnowledge(route.params.id);
  } catch (caught) {
    error.value = caught.message || "知识详情加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="home-page">
    <SiteHeader />
    <main class="material-detail-shell knowledge-detail-shell">
      <RouterLink class="material-detail-back" :to="{ name: 'search', query: route.query }">返回检索</RouterLink>
      <div v-if="loading" class="material-detail-state"><LoaderCircle class="spin" :size="20" />加载知识详情</div>
      <div v-else-if="error" class="material-detail-state error-state" role="alert">{{ error }}</div>
      <article v-else class="material-detail-content">
        <header class="material-detail-heading">
          <div>
            <p>知识{{ knowledge.kind === "source" ? "教材" : "章节" }}</p>
            <h1>{{ knowledge.title }}</h1>
            <p v-if="knowledge.sourceTitle">{{ knowledge.sourceTitle }}</p>
            <p v-if="knowledge.edition">{{ knowledge.edition }}</p>
          </div>
        </header>
        <div class="material-detail-main knowledge-detail-main">
          <section v-if="knowledge.summary" class="material-detail-summary">
            <h2>摘要</h2>
            <p>{{ knowledge.summary }}</p>
          </section>
          <section v-if="knowledge.kind === 'source'" class="knowledge-chapters">
            <h2>章节目录</h2>
            <ol><li v-for="chapter in knowledge.chapters" :key="chapter.id">{{ chapter.title }}</li></ol>
          </section>
          <section v-else class="knowledge-content-section">
            <h2>正文</h2>
            <p class="knowledge-content">{{ knowledge.content || "暂无正文" }}</p>
          </section>
        </div>
      </article>
    </main>
  </div>
</template>
