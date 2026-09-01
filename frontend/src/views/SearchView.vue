<script setup>
import { computed, ref, watch } from "vue";
import { LoaderCircle, Search } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";
import CatalogPagination from "../components/CatalogPagination.vue";
import SearchGraph from "../components/SearchGraph.vue";
import SearchFilters from "../components/SearchFilters.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { publicUrl } from "../lib/publicUrl.js";
import { emptyFilters, filterQuery, filtersFromQuery } from "../lib/searchFilters.js";

const route = useRoute();
const router = useRouter();
const query = ref(String(route.query.q || ""));
const submitted = ref("");
const payload = ref({
  items: [], facets: {}, counts: { all: 0, case: 0, knowledge: 0, material: 0 },
});
const activeKind = ref(searchKind(route.query.kind));
const page = ref(1);
const cursor = ref("");
const view = ref(route.query.view === "graph" ? "graph" : "list");
const loading = ref(false);
const error = ref("");
const filters = ref(filtersFromQuery(route.query, activeKind.value));
const items = computed(() => payload.value.items);
let searchGeneration = 0;

function tabLabel(kind, label) {
  return `${label} ${payload.value.counts[kind] || 0}`;
}

function searchKind(value) {
  return ["case", "knowledge", "material"].includes(value) ? value : "all";
}

function destination(item) {
  return item.kind === "case"
    ? { name: "case-public", params: { id: item.id } }
    : publicUrl(item.sourceUrl);
}

function kindLabel(item) {
  return { case: "案例", knowledge: "知识", material: "素材" }[item.kind];
}

function metaLine(item) {
  const fields = item.kind === "case"
    ? [item.typeName, item.course]
    : [item.chapter || item.source, item.unit || item.materialType];
  return fields.filter(Boolean).join(" · ");
}

function routeQuery(overrides = {}) {
  const state = {
    term: query.value.trim(), kind: activeKind.value, mode: view.value,
    filters: filters.value, ...overrides,
  };
  return {
    ...(state.term ? { q: state.term } : {}),
    ...(state.kind === "all" ? {} : { kind: state.kind }),
    ...(state.mode === "list" ? {} : { view: state.mode }),
    ...filterQuery(state.filters, state.kind),
  };
}

function selectView(mode) {
  view.value = mode;
  router.replace({ name: "search", query: routeQuery({ mode }) });
}

async function requestSearch(term, kind, activeCursor, searchFilters) {
  const current = ++searchGeneration;
  loading.value = true;
  error.value = "";
  try {
    const result = await api.search(term, kind, activeCursor, 20, filterQuery(searchFilters, kind));
    if (current === searchGeneration) {
      payload.value = mergeMetadata(result);
      submitted.value = term;
      page.value = result.page;
    }
  } catch (caught) {
    if (current === searchGeneration) error.value = caught.message || "检索失败";
  } finally {
    if (current === searchGeneration) loading.value = false;
  }
}

function mergeMetadata(result) {
  if (result.metadataIncluded) return result;
  return {
    ...result, total: payload.value.total, counts: payload.value.counts,
    facets: payload.value.facets,
  };
}

async function submitSearch() {
  const term = query.value.trim();
  const routed = String(route.query.q || "").trim();
  if (term === routed) {
    cursor.value = "";
    return requestSearch(term, activeKind.value, null, filters.value);
  }
  await router.replace({ name: "search", query: routeQuery({ term }) });
}

function syncSearchRoute(values) {
  const [rawTerm, rawKind] = values;
  const term = String(rawTerm || "").trim();
  const kind = searchKind(rawKind);
  query.value = term;
  activeKind.value = kind;
  cursor.value = "";
  filters.value = filtersFromQuery(route.query, kind);
  requestSearch(term, kind, null, filters.value);
}

function selectKind(kind) {
  router.replace({
    name: "search", query: routeQuery({ kind, filters: emptyFilters() }),
  });
}

function selectPage(nextCursor) {
  cursor.value = nextCursor;
  requestSearch(submitted.value, activeKind.value, nextCursor, filters.value);
}

function selectFilters(next) {
  filters.value = next;
  router.replace({ name: "search", query: routeQuery({ filters: next }) });
}

function searchRouteState() {
  const names = ["typeName", "audience", "authority", "materialType", "tag", "publishedWithin"];
  return [route.query.q, route.query.kind, ...names.map(name => route.query[name])];
}

watch(searchRouteState, syncSearchRoute, { immediate: true });
watch(() => route.query.view, (value) => {
  view.value = value === "graph" ? "graph" : "list";
});
</script>

<template>
  <div class="home-page search-page">
    <SiteHeader />
    <main id="main-content" class="search-shell">
      <form class="search-query" role="search" @submit.prevent="submitSearch">
        <Search :size="18" aria-hidden="true" />
        <input v-model="query" aria-label="搜索公开案例" placeholder="用自然语言或关键词检索案例、知识、素材；留空回车即浏览全部" />
        <button type="submit">检索</button>
        <div class="search-views" aria-label="检索视图">
          <button v-for="mode in ['list', 'graph']" :key="mode" type="button" :aria-pressed="view === mode" @click="selectView(mode)">
            {{ { list: "列表", graph: "图谱" }[mode] }}
          </button>
        </div>
      </form>

      <div v-if="loading && !payload.pageSize" class="search-state"><LoaderCircle class="spin" :size="20" />检索中</div>
      <div v-else-if="error" class="search-state error-state" role="alert">{{ error }}</div>
      <template v-else-if="view === 'list'">
        <p v-if="loading" class="search-refresh" role="status"><LoaderCircle class="spin" :size="14" />更新结果中</p>
        <div class="result-toolbar">
          <div class="result-tabs" role="tablist" aria-label="资源类型">
            <button v-for="tab in [['all','全部'],['case','案例'],['knowledge','知识'],['material','素材']]" :key="tab[0]" type="button" role="tab" :aria-selected="activeKind === tab[0]" @click="selectKind(tab[0])">
              {{ tabLabel(tab[0], tab[1]) }}
            </button>
          </div>
          <SearchFilters :filters="filters" :facets="payload.facets || {}" :kind="activeKind" @update:filters="selectFilters" />
        </div>
        <section class="mixed-results" aria-label="检索结果">
          <article v-for="item in items" :key="`${item.kind}-${item.id}`" class="mixed-result">
            <span>{{ kindLabel(item) }}</span>
            <h2><RouterLink v-if="item.kind === 'case'" :to="destination(item)">{{ item.title }}</RouterLink><a v-else-if="item.kind === 'material' && destination(item)" :href="destination(item)" target="_blank" rel="noopener noreferrer">{{ item.title }}</a><span v-else>{{ item.title }}</span></h2>
            <p>{{ item.summary || "暂无摘要" }}</p>
            <small>{{ metaLine(item) }}</small>
          </article>
          <p v-if="!items.length" class="search-empty">{{ submitted ? "平台内没有命中结果，可换个关键词" : "平台内暂无资源" }}</p>
        </section>
        <CatalogPagination v-if="payload.total" :page="page" :total="payload.total" :next-cursor="payload.nextCursor" :previous-cursor="payload.previousCursor" @change="selectPage" />
      </template>
      <SearchGraph v-else :query="submitted" :items="items" />
    </main>
  </div>
</template>
