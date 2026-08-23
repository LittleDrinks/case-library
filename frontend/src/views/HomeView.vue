<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, LoaderCircle, RefreshCw } from "@lucide/vue";
import { api } from "../api.js";
import HomeCaseItem from "../components/HomeCaseItem.vue";
import SiteHeader from "../components/SiteHeader.vue";

const cases = ref([]);
const catalog = ref({ items: [], counts: { all: 0, knowledge: 0, material: 0 } });
const loading = ref(true);
const error = ref("");
const recommended = computed(() => [...cases.value].sort(recommendationOrder).slice(0, 5));
const recommendedMaterials = computed(() => catalog.value.items
  .filter(item => item.kind === "material").slice(0, 6));
const newCasesThisWeek = computed(() => cases.value.filter(createdThisWeek).length);
const newPublishedThisWeek = computed(() => cases.value.filter(publishedThisWeek).length);
const newMaterialsThisWeek = computed(() => recommendedMaterials.value.filter(materialThisWeek).length);

function recommendationOrder(left, right) {
  return recommendationScore(right) - recommendationScore(left)
    || String(right.publishedAt || "").localeCompare(String(left.publishedAt || ""));
}

function recommendationScore(item) {
  return (item.likes || 0) + (item.summary ? 8 : 0) + (item.typeName ? 4 : 0)
    + Math.min(item.theoryPoints?.length || 0, 4);
}

function withinWeek(value) {
  const timestamp = Date.parse(value || "");
  return Number.isFinite(timestamp) && Date.now() - timestamp <= 7 * 86400000;
}

function createdThisWeek(item) {
  return withinWeek(item.createdAt);
}

function publishedThisWeek(item) {
  return withinWeek(item.publishedAt);
}

function materialThisWeek(item) {
  return withinWeek(item.publishedAt);
}

async function loadCases() {
  loading.value = true;
  error.value = "";
  try {
    [cases.value, catalog.value] = await Promise.all([
      api.listCases("public"), api.search("", "all", null, 50),
    ]);
  } catch (reason) {
    error.value = reason.message || "案例加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(loadCases);
</script>

<template>
  <div class="home-page">
    <SiteHeader />
    <main id="main-content" class="home-main recommendation-main">
      <div v-if="loading" class="catalog-state"><LoaderCircle class="spin" :size="22" /><span>正在加载案例</span></div>
      <div v-else-if="error" class="catalog-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ error }}</span>
        <button type="button" @click="loadCases"><RefreshCw :size="15" />重试</button>
      </div>
      <template v-else>
        <h1 class="visually-hidden">思政教学案例首页</h1>
        <section class="dynamic-grid" aria-label="平台动态">
          <article class="home-card home-card-padded dynamic-card">
            <header class="home-section-title">
              <h2>平台动态</h2><RouterLink to="/search">检索全部</RouterLink>
            </header>
            <div class="dynamic-metrics">
              <div><b>{{ newCasesThisWeek }}</b><span>近 7 天新案例</span></div>
              <div><b>{{ newMaterialsThisWeek }}</b><span>近 7 天新素材</span></div>
              <div><b>{{ newPublishedThisWeek }}</b><span>近 7 天新发布</span></div>
            </div>
            <p class="platform-total">全库 {{ cases.length }} 个已发布案例 · {{ catalog.counts.material }} 条可见素材 · {{ catalog.counts.knowledge }} 本教材</p>
          </article>
          <article class="home-card home-card-padded dynamic-card">
            <header class="home-section-title"><h2>时政要闻</h2></header>
            <p class="dynamic-empty">暂时没有可展示的新闻</p>
          </article>
          <article class="home-card home-card-padded dynamic-card">
            <header class="home-section-title"><h2>平台公告</h2></header>
            <p class="dynamic-empty">暂无公告</p>
          </article>
        </section>

        <div class="home-recommendation-grid">
          <section class="home-card recommendation-section" aria-labelledby="recommendation-title">
            <header class="home-card-title">
              <h2 id="recommendation-title">推荐案例</h2>
              <span>按全部学段 · 质量与热度</span>
            </header>
            <div v-if="recommended.length">
              <HomeCaseItem v-for="item in recommended" :key="item.id" :case-record="item" />
            </div>
            <div v-else class="home-empty">暂无推荐</div>
          </section>

          <section class="home-card material-recommendations" aria-labelledby="material-title">
            <header class="home-card-title">
              <h2 id="material-title">推荐素材</h2><RouterLink to="/search">检索</RouterLink>
            </header>
            <div v-if="recommendedMaterials.length">
              <a
                v-for="item in recommendedMaterials"
                :key="item.id"
                class="home-material-item"
                :href="item.sourceUrl || undefined"
                :target="item.sourceUrl ? '_blank' : undefined"
                :rel="item.sourceUrl ? 'noreferrer' : undefined"
              >
                <b>{{ item.title }}</b>
                <span>{{ item.source || "来源未设置" }} · {{ item.materialType || "素材" }}</span>
              </a>
            </div>
            <p v-else class="home-empty">暂无推荐</p>
          </section>
        </div>
      </template>
    </main>
  </div>
</template>
