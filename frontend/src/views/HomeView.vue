<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, ArrowRight, LoaderCircle, RefreshCw, Search } from "@lucide/vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import HomeCaseItem from "../components/HomeCaseItem.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { useHomeMotion } from "../composables/useHomeMotion.js";
import { session } from "../session.js";

const router = useRouter();
const root = ref(null);
const hero = ref(null);
const query = ref("");
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

useHomeMotion(root, hero, loading);

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

function countLabel(value) {
  return loading.value || error.value ? "—" : value;
}

function submitSearch() {
  const term = query.value.trim();
  router.push({ name: "search", query: term ? { q: term } : {} });
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
  <div ref="root" class="home-page">
    <SiteHeader />
    <main id="main-content" class="home-main recommendation-main">
      <h1 class="visually-hidden">“强国有我”思政案例库首页</h1>
      <section ref="hero" class="home-hero" aria-label="上海大学校园与全库检索">
        <img class="home-hero-media" src="/shu-campus-lake.webp" alt="" fetchpriority="high" />
        <div class="home-hero-shade" />
        <div class="home-hero-content">
          <div class="home-hero-search">
            <form role="search" @submit.prevent="submitSearch">
              <Search :size="20" aria-hidden="true" />
              <input v-model="query" aria-label="检索全库资源" placeholder="检索案例、知识或教学素材" />
              <button type="submit">检索<ArrowRight :size="17" aria-hidden="true" /></button>
            </form>
            <RouterLink v-if="session.user" class="home-workbench-link" to="/my-cases">进入我的工作台<ArrowRight :size="15" /></RouterLink>
          </div>
          <dl class="home-hero-stats" aria-label="平台资源概览">
            <div><dt>公开教学案例</dt><dd>{{ countLabel(cases.length) }}</dd></div>
            <div><dt>可见教学素材</dt><dd>{{ countLabel(catalog.counts.material) }}</dd></div>
            <div><dt>教材知识资源</dt><dd>{{ countLabel(catalog.counts.knowledge) }}</dd></div>
          </dl>
        </div>
        <a class="home-hero-credit" href="https://www.shu.edu.cn/" target="_blank" rel="noreferrer">上海大学官网 · 摄影：韦明其</a>
      </section>

      <div v-if="loading" class="catalog-state"><LoaderCircle class="spin" :size="22" /><span>正在加载案例</span></div>
      <div v-else-if="error" class="catalog-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ error }}</span>
        <button type="button" @click="loadCases"><RefreshCw :size="15" />重试</button>
      </div>
      <template v-else>
        <section class="home-week" aria-label="平台动态" data-reveal>
          <h2>近 7 天</h2>
          <ul>
            <li><span>新增案例</span><b>{{ newCasesThisWeek }}</b></li>
            <li><span>新增素材</span><b>{{ newMaterialsThisWeek }}</b></li>
            <li><span>新发布</span><b>{{ newPublishedThisWeek }}</b></li>
          </ul>
          <RouterLink to="/search">查看全部资源<ArrowRight :size="15" /></RouterLink>
        </section>

        <div class="home-recommendation-grid">
          <section class="recommendation-section" aria-labelledby="recommendation-title" data-reveal>
            <header class="home-card-title">
              <h2 id="recommendation-title">推荐案例</h2>
              <RouterLink :to="{ name: 'search', query: { kind: 'case' } }">全部案例<ArrowRight :size="14" /></RouterLink>
            </header>
            <div v-if="recommended.length">
              <HomeCaseItem v-for="item in recommended" :key="item.id" :case-record="item" />
            </div>
            <div v-else class="home-empty">暂无推荐</div>
          </section>

          <section class="material-recommendations" aria-labelledby="material-title" data-reveal>
            <header class="home-card-title">
              <h2 id="material-title">推荐素材</h2>
              <RouterLink :to="{ name: 'search', query: { kind: 'material' } }">检索<ArrowRight :size="14" /></RouterLink>
            </header>
            <div v-if="recommendedMaterials.length">
              <RouterLink
                v-for="(item, index) in recommendedMaterials"
                :key="item.id"
                class="home-material-item"
                :to="{ name: 'material-detail', params: { id: item.id } }"
              >
                <span class="home-material-index">{{ String(index + 1).padStart(2, "0") }}</span>
                <span class="home-material-copy">
                  <b>{{ item.title }}</b>
                  <span>{{ item.source || "来源未设置" }} · {{ item.materialType || "素材" }}</span>
                </span>
                <ArrowRight :size="14" aria-hidden="true" />
              </RouterLink>
            </div>
            <p v-else class="home-empty">暂无推荐</p>
          </section>
        </div>

        <section class="home-info-grid" aria-label="平台信息">
          <article class="home-card home-card-padded" data-reveal>
            <header class="home-section-title"><h2>时政要闻</h2></header>
            <p class="dynamic-empty">暂时没有可展示的新闻</p>
          </article>
          <article class="home-card home-card-padded" data-reveal>
            <header class="home-section-title"><h2>平台公告</h2></header>
            <p class="dynamic-empty">暂无公告</p>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>
