<script setup>
import { Bot, FileStack, LoaderCircle, PackageOpen, RefreshCw } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";

const cases = ref([]);
const loading = ref(true);
const error = ref("");
const reviewCases = computed(() => cases.value.filter(needsReview));
const publishedCases = computed(() => cases.value.filter(isPublished));

function needsReview(item) {
  return ["pending", "reviewing"].includes(item.workflowStatus);
}

function isPublished(item) {
  return item.workflowStatus === "published";
}

function reviewLabel(item) {
  return item.workflowStatus === "pending" ? "待开始" : "审核中";
}

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "日期待定";
}

async function loadCases() {
  loading.value = true;
  error.value = "";
  try { cases.value = await api.listCases("admin"); }
  catch (reason) { error.value = reason.message || "管理队列加载失败"; }
  finally { loading.value = false; }
}

onMounted(loadCases);
</script>

<template>
  <div class="admin-page">
    <SiteHeader />
    <main id="main-content" class="admin-main">
      <header class="admin-heading">
        <div><span>平台管理</span><h1>管理后台</h1></div>
        <nav aria-label="管理工具">
          <RouterLink :to="{ name: 'material-imports' }"><PackageOpen :size="16" />素材入库</RouterLink>
          <RouterLink :to="{ name: 'admin-ai-settings' }"><Bot :size="16" />平台 AI</RouterLink>
        </nav>
      </header>
      <div v-if="loading" class="admin-state"><LoaderCircle class="spin" :size="20" />正在加载管理队列</div>
      <div v-else-if="error" class="admin-state error-state" role="alert">
        {{ error }}<button type="button" @click="loadCases"><RefreshCw :size="15" />重试</button>
      </div>
      <template v-else>
        <section class="admin-queue" aria-labelledby="review-queue-title">
          <header><div><span>案例管理</span><h2 id="review-queue-title">案例审核</h2></div><b>{{ reviewCases.length }}</b></header>
          <p v-if="!reviewCases.length" class="admin-empty">暂无待审核案例</p>
          <article v-for="item in reviewCases" :key="item.id" :aria-label="`待审核：${item.title}`">
            <span :data-status="item.workflowStatus">{{ reviewLabel(item) }}</span>
            <div><h3>{{ item.title }}</h3><p>{{ item.author || "作者待补充" }} · 提交更新 {{ dateLabel(item.updatedAt) }}</p></div>
            <RouterLink :to="{ name: 'case-review', params: { id: item.id } }">审核</RouterLink>
          </article>
        </section>
        <section class="admin-queue" aria-labelledby="publication-title">
          <header><div><span>公开内容</span><h2 id="publication-title">发布管理</h2></div><b>{{ publishedCases.length }}</b></header>
          <p v-if="!publishedCases.length" class="admin-empty">暂无已发布案例</p>
          <article v-for="item in publishedCases" :key="item.id" :aria-label="`已发布：${item.title}`">
            <FileStack :size="18" aria-hidden="true" />
            <div><h3>{{ item.title }}</h3><p>{{ item.publicationStatus === "public" ? "公开中" : "已隐藏" }} · {{ dateLabel(item.publishedAt) }}</p></div>
            <RouterLink :to="{ name: 'case-review', params: { id: item.id } }">发布管理</RouterLink>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>
